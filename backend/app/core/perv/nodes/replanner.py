"""
Replanner node - generates corrective steps on verification failure.

When the verifier rejects the execution results, the replanner analyses
the failure and produces a PlanUpdate (append / replace / retry) that
modifies the plan for another execution round.
"""

import copy
import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from app.config import get_settings
from app.core.llm import create_llm
from app.core.llm_retry import retry_llm_call
from app.core.perv.json_repair import repair_json_or_none
from app.core.perv.prompts import build_replanner_prompt, build_tool_list_text, build_skills_list_text, extract_system_core
from app.core.execution_trace.perv_trace import PEVRTrace as PEVRLogger
from app.core.execution_trace.token_utils import extract_token_usage
from app.tools import CORE_TOOLS

logger = logging.getLogger(__name__)


async def replanner_node(state: dict) -> dict:
    """Generate corrective steps based on verification failure.

    Parses the LLM response into a PlanUpdate, applies it to the current
    plan, and returns the updated plan with an incremented retry count.

    Args:
        state: Current PlannerState dictionary.

    Returns:
        Dictionary with updated ``plan``, incremented ``retry_count``,
        and appended ``reasoning_trace``.
    """
    task: str = state.get("task", "")
    plan: List[dict] = state.get("plan", [])
    observations: List[dict] = state.get("observations", [])
    verifier_report: Dict[str, Any] = state.get("verifier_report", {})
    retry_count: int = state.get("retry_count", 0)
    system_prompt: str = state.get("system_prompt", "")
    session_context: Dict[str, Any] = state.get("session_context", {})
    consecutive_failures: int = state.get("consecutive_failures", 0)
    pevr_log: PEVRLogger | None = state.get("_pevr_log")

    conversation_context: str = ""
    semantic_history: str = ""
    if isinstance(session_context, dict):
        conversation_context = session_context.get("conversation_context", "")
        semantic_history = session_context.get("semantic_history", "")

    start = time.time()

    # Initialize all branch variables so they are always defined
    action = "error"
    target_step = None
    new_steps: List[dict] = []
    updated_plan = copy.deepcopy(plan)
    token_usage: Dict[str, int] = {}

    try:
        # --- Build replanner prompt ---
        tools_text = build_tool_list_text(CORE_TOOLS)
        skills_text = build_skills_list_text()
        prompt_text = build_replanner_prompt(
            system_prompt=system_prompt,
            task=task,
            plan=plan,
            observations=observations,
            verifier_report=verifier_report,
            tool_list_text=tools_text,
            skills_list_text=skills_text,
            conversation_context=conversation_context,
            semantic_history=semantic_history,
            consecutive_failures=consecutive_failures,
        )

        logger.debug(
            "[PEVR Replanner] Prompt: %d chars, retry=%d, "
            "verifier_reason=%s missing=%s",
            len(prompt_text),
            retry_count,
            verifier_report.get("reason", "")[:100],
            verifier_report.get("missing", []),
        )

        # --- Call LLM ---
        settings = get_settings()
        provider = settings.llm_provider
        llm = create_llm(provider)

        response = await retry_llm_call(
            coro_factory=lambda: llm.ainvoke([HumanMessage(content=prompt_text)]),
            context="pevr_replanner",
        )

        # --- Extract token usage ---
        token_usage = extract_token_usage(response)

        raw_content: str = getattr(response, "content", str(response))
        logger.debug(
            "[PEVR Replanner] LLM response: %d chars preview=%s",
            len(raw_content),
            raw_content[:300],
        )

        _fallback_update: Dict[str, Any] = {
            "action": "append",
            "target_step": None,
            "steps": [],
        }
        update: Dict[str, Any] = repair_json_or_none(raw_content) or _fallback_update

        # Determine update mode: new patch format or old action format
        update_mode = update.get("mode", "")

        if update_mode == "repair_patch":
            # New PERV patch mode: apply patch operations
            updated_plan = copy.deepcopy(plan)
            patches = update.get("patch", [])
            reason = update.get("reason", "")

            logger.info(
                "[PEVR Replanner] Patch mode: %d operations, reason=%s",
                len(patches), reason[:100],
            )

            for patch_op in patches:
                op = patch_op.get("op", "")
                target_id = patch_op.get("step_id", patch_op.get("after_step_id", ""))

                if op == "edit_step_inputs":
                    new_inputs = patch_op.get("new_inputs", {})
                    for idx, step in enumerate(updated_plan):
                        if step.get("id") == target_id:
                            updated_plan[idx]["inputs"] = new_inputs
                            updated_plan[idx]["input"] = new_inputs  # backward compat
                            logger.debug(
                                "[PEVR Replanner]   edit_step_inputs: %s", target_id,
                            )
                            break

                elif op == "replace_step_tool":
                    new_tool = patch_op.get("new_tool", "")
                    new_inputs = patch_op.get("new_inputs", {})
                    for idx, step in enumerate(updated_plan):
                        if step.get("id") == target_id:
                            updated_plan[idx]["tool"] = new_tool
                            updated_plan[idx]["inputs"] = new_inputs
                            updated_plan[idx]["input"] = new_inputs  # backward compat
                            logger.debug(
                                "[PEVR Replanner]   replace_step_tool: %s -> %s",
                                target_id, new_tool,
                            )
                            break

                elif op == "insert_step_after":
                    after_id = patch_op.get("after_step_id", "")
                    new_step = patch_op.get("step", {})
                    # Normalize the new step
                    new_step.setdefault("inputs", new_step.get("input", {}))
                    new_step.setdefault("input", new_step.get("inputs", {}))
                    new_step.setdefault("description", new_step.get("purpose", ""))
                    new_step.setdefault("expected", "")
                    new_step.setdefault("skill", None)

                    insert_idx = len(updated_plan)
                    for idx, step in enumerate(updated_plan):
                        if step.get("id") == after_id:
                            insert_idx = idx + 1
                            break
                    updated_plan.insert(insert_idx, new_step)
                    logger.debug(
                        "[PEVR Replanner]   insert_step_after: %s -> %s",
                        after_id, new_step.get("id", "?"),
                    )

                else:
                    logger.warning(
                        "[PEVR Replanner] Unknown patch op: %s", op,
                    )

            action = "repair_patch"
            target_step = None
            new_steps = [p.get("step", {}) for p in patches if p.get("op") == "insert_step_after"]

        elif update_mode == "full_replan":
            # Full replan: replace entire plan
            new_plan = update.get("steps", [])
            if new_plan:
                # Normalize new plan steps
                for step in new_plan:
                    step.setdefault("inputs", step.get("input", {}))
                    step.setdefault("input", step.get("inputs", {}))
                    step.setdefault("description", step.get("purpose", ""))
                    step.setdefault("expected", "")
                    step.setdefault("skill", None)
                    step.setdefault("name", step.get("description", ""))
                    step.setdefault("purpose", step.get("description", ""))
                    step.setdefault("depends_on", [])
                    step.setdefault("output_key", f"out_{step.get('id', 'unknown')}")
                    step.setdefault("on_fail", {"retry": 1, "fallback_tool": None, "fallback_inputs": None})
                updated_plan = new_plan
            else:
                updated_plan = copy.deepcopy(plan)

            action = "full_replan"
            target_step = None
            new_steps = new_plan
            # Reset cursor for fresh execution
            logger.info("[PEVR Replanner] Full replan: %d new steps", len(new_plan))

        else:
            # Fallback: old action format (backward compat)
            action = update.get("action", "append")
            target_step = update.get("target_step")
            new_steps = update.get("steps", [])

            if action not in ("append", "replace", "retry"):
                logger.warning(
                    "[PEVR Replanner] Unknown action '%s', defaulting to append",
                    action,
                )
                action = "append"

            updated_plan = copy.deepcopy(plan)

            if action == "append":
                updated_plan.extend(new_steps)
            elif action in ("replace", "retry"):
                if target_step:
                    replaced = False
                    for idx, step in enumerate(updated_plan):
                        if step.get("id") == target_step:
                            updated_plan[idx:idx + 1] = new_steps
                            replaced = True
                            break
                    if not replaced:
                        logger.warning(
                            "[PEVR Replanner] target_step '%s' not found, appending instead",
                            target_step,
                        )
                        updated_plan.extend(new_steps)
                else:
                    logger.warning(
                        "[PEVR Replanner] replace/retry without target_step, appending",
                    )
                    updated_plan.extend(new_steps)

        duration = time.time() - start
        logger.info(
            "[PEVR Replanner] action=%s target=%s new_steps=%d total=%d "
            "retry=%d/%d consecutive_failures=%d (%.1fms)",
            action,
            target_step,
            len(new_steps),
            len(updated_plan),
            retry_count + 1,
            state.get("max_retries", "?"),
            consecutive_failures,
            duration * 1000,
        )

        # Log each new step at debug level
        for ns in new_steps:
            logger.debug(
                "[PEVR Replanner]   new step: tool=%s desc=%s",
                ns.get("tool", "?"),
                ns.get("description", "")[:80],
            )

        if pevr_log:
            pevr_log.log_replanning(
                loop_index=retry_count,
                action=action,
                target_step=target_step,
                new_steps_count=len(new_steps),
                duration_s=duration,
                token_usage=token_usage,
            )

    except Exception as e:
        duration = time.time() - start
        logger.error(
            "[PEVR Replanner] FAILED after %.1fms: %s",
            duration * 1000,
            e,
            exc_info=True,
        )
        updated_plan = copy.deepcopy(plan)
        if pevr_log:
            pevr_log.log_replanning(
                loop_index=retry_count,
                action="error",
                target_step=None,
                new_steps_count=0,
                duration_s=duration,
                error=e,
            )
            pevr_log.log_node_error(
                "replanner",
                e,
                f"retry={retry_count} plan_steps={len(plan)}",
            )

    return {
        "plan": updated_plan,
        "observations": [],
        "retry_count": retry_count + 1,
        "consecutive_failures": consecutive_failures + (1 if action != "repair_patch" else 0),
        "reasoning_trace": [
            {
                "phase": "replanning",
                "action": action,
                "target_step": target_step,
                "new_steps": new_steps,
            }
        ],
    }
