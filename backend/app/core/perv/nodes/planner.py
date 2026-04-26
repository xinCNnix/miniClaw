"""
Planner node - generates structured execution plan.

Analyzes the user task and produces a list of PlanStep dicts describing
which tools to invoke, in what order, and with what arguments.  When
observations from a previous execution round are present the node
operates in "replan" mode, incorporating prior results into the new plan.
"""

import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from app.config import get_settings
from app.core.llm import create_llm
from app.core.llm_retry import retry_llm_call
from app.core.perv.json_repair import repair_json_or_none
from app.core.perv.prompts import (
    build_planner_prompt,
    build_tool_list_text,
    build_skills_list_text,
    extract_system_core,
)
from app.core.execution_trace.perv_trace import PEVRTrace as PEVRLogger
from app.core.execution_trace.token_utils import extract_token_usage
from app.tools import CORE_TOOLS

logger = logging.getLogger(__name__)


async def planner_node(state: dict) -> dict:
    """Generate or regenerate a structured execution plan.

    Args:
        state: Current PlannerState dictionary.

    Returns:
        Dictionary with updated ``plan`` and appended ``reasoning_trace``.
    """
    task: str = state.get("task", "")
    observations: List[dict] = state.get("observations", [])
    retry_count: int = state.get("retry_count", 0)
    pevr_log: PEVRLogger | None = state.get("_pevr_log")
    is_replan = bool(observations)

    system_prompt: str = state.get("system_prompt", "")
    session_context: Dict[str, Any] = state.get("session_context", {})

    conversation_context: str = ""
    semantic_history: str = ""
    if isinstance(session_context, dict):
        conversation_context = session_context.get("conversation_context", "")
        semantic_history = session_context.get("semantic_history", "")

    enrichment: dict = state.get("enrichment") or {}

    start = time.time()
    token_usage: dict = {}

    try:
        # --- Gather context for the prompt ---
        tools_text = build_tool_list_text(CORE_TOOLS)
        skills_text = build_skills_list_text()
        settings = get_settings()
        max_steps: int = getattr(settings, "planner_max_steps", 8)

        logger.debug(
            "[PEVR Planner] Building prompt: is_replan=%s max_steps=%d tools=%s",
            is_replan,
            max_steps,
            [t.name for t in CORE_TOOLS],
        )

        # --- Build prompt ---
        prompt_text = build_planner_prompt(
            system_prompt=system_prompt,
            task=task,
            tool_list_text=tools_text,
            skills_list_text=skills_text,
            max_steps=max_steps,
            observations=observations if is_replan else None,
            conversation_context=conversation_context,
            semantic_history=semantic_history,
            enrichment=enrichment,
        )

        # --- Create LLM and call with retry ---
        provider = settings.llm_provider
        llm = create_llm(provider)

        response = await retry_llm_call(
            coro_factory=lambda: llm.ainvoke([HumanMessage(content=prompt_text)]),
            context="pevr_planner",
        )

        # --- Extract token usage ---
        token_usage = extract_token_usage(response)

        # --- Parse response ---
        raw_content: str = getattr(response, "content", str(response))
        logger.debug(
            "[PEVR Planner] LLM response: %d chars preview=%s",
            len(raw_content),
            raw_content[:200],
        )

        parsed = repair_json_or_none(raw_content)

        # Extract steps list: LLM may return a bare list [...] or {"steps": [...]} or full schema
        if isinstance(parsed, list):
            plan_steps: List[Dict[str, Any]] = parsed
        elif isinstance(parsed, dict):
            plan_steps = parsed.get("steps", [])
            if not isinstance(plan_steps, list):
                plan_steps = []
        else:
            plan_steps = []

        # Validate each step has the minimum required keys and valid tool
        # New format requires {id, name, tool, inputs}, old format has {id, description, tool}
        required_keys = {"id", "tool"}
        available_tool_names = {t.name for t in CORE_TOOLS}

        valid_steps: List[Dict[str, Any]] = []
        for step in plan_steps:
            if not isinstance(step, dict) or not required_keys.issubset(step.keys()):
                continue

            tool_name = step.get("tool", "")
            # Filter out steps referencing non-existent tools (e.g. "ask_user")
            if tool_name and tool_name not in available_tool_names and not tool_name.startswith("skill."):
                logger.warning(
                    "[PEVR Planner] Filtering step %s: unknown tool '%s'",
                    step.get("id", "?"), tool_name,
                )
                continue

            # Warn about tools with required args but empty inputs
            inputs = step.get("inputs", step.get("input", {}))
            if not inputs and tool_name in available_tool_names:
                tool_obj = next((t for t in CORE_TOOLS if t.name == tool_name), None)
                if tool_obj:
                    args_schema = getattr(tool_obj, "args_schema", None)
                    if args_schema:
                        try:
                            required_args = args_schema.schema().get("required", [])
                            if required_args:
                                logger.warning(
                                    "[PEVR Planner] Step %s: tool '%s' requires args %s but inputs is empty",
                                    step.get("id", "?"), tool_name, required_args,
                                )
                        except Exception:
                            pass

            valid_steps.append(step)
        plan_steps = valid_steps

        # Normalize steps: fill defaults for new fields, ensure backward compat
        for step in plan_steps:
            step.setdefault("name", step.get("description", step.get("id", "")))
            step.setdefault("purpose", step.get("description", ""))
            step.setdefault("inputs", step.get("input", {}))
            step.setdefault("depends_on", [])
            step.setdefault("output_key", f"out_{step.get('id', 'unknown')}")
            step.setdefault("on_fail", {"retry": 1, "fallback_tool": None, "fallback_inputs": None})
            # Ensure backward compat fields exist
            step.setdefault("description", step.get("purpose", step.get("name", "")))
            step.setdefault("expected", "")
            step.setdefault("skill", None)
            step.setdefault("input", step.get("inputs", {}))
            step.setdefault("skill_group", step.get("skill", None))

        # --- Code-level skill expansion guard ---
        # When SkillPolicy is enabled, skip auto-expansion: preserve raw skill.*
        # references so SkillPolicy node can compile them. Only expand when
        # SkillPolicy is disabled (fallback for the old executor path).
        skill_policy_enabled = True
        try:
            skill_policy_enabled = getattr(get_settings(), "perv_enable_skill_policy", True)
        except Exception:
            pass

        if not skill_policy_enabled:
            expanded_steps: List[Dict[str, Any]] = []
            skill_expanded_count = 0
            for step in plan_steps:
                tool_name = step.get("tool", "")
                if tool_name.startswith("skill."):
                    skill_name = tool_name[6:]  # strip "skill." prefix
                    skill_expanded_count += 1
                    step_id = step.get("id", f"s_unk_{skill_expanded_count}")

                    logger.warning(
                        "[PEVR Planner] LLM failed to expand skill '%s' in step %s, "
                        "auto-inserting read_file step for SKILL.md",
                        skill_name,
                        step_id,
                    )

                    # Step 1: read_file to load the SKILL.md
                    read_step_id = f"{step_id}_skill"
                    read_step: Dict[str, Any] = {
                        "id": read_step_id,
                        "name": f"Read skill: {skill_name}",
                        "tool": "read_file",
                        "purpose": f"Load skill definition for '{skill_name}'",
                        "inputs": {"path": f"data/skills/{skill_name}/SKILL.md"},
                        "depends_on": list(step.get("depends_on", [])),
                        "output_key": f"skill_{skill_name}_md",
                        "on_fail": {"retry": 1, "fallback_tool": None, "fallback_inputs": None},
                        "description": f"Read SKILL.md for {skill_name}",
                        "expected": "Skill instructions",
                        "skill": skill_name,
                        "input": {"path": f"data/skills/{skill_name}/SKILL.md"},
                        "skill_group": skill_name,
                    }
                    expanded_steps.append(read_step)

                    # Drop the unexpanded skill.* step — it's not executable.
                    # The executor will read the SKILL.md; the verifier/replanner
                    # will see incomplete results and create proper execution steps.
                else:
                    expanded_steps.append(step)

            if skill_expanded_count > 0:
                logger.warning(
                    "[PEVR Planner] Auto-expanded %d unexpanded skill reference(s)",
                    skill_expanded_count,
                )
                plan_steps = expanded_steps

        duration = time.time() - start
        logger.info(
            "[PEVR Planner] Generated %d steps (is_replan=%s, %.1fms)",
            len(plan_steps),
            is_replan,
            duration * 1000,
        )

        for i, step in enumerate(plan_steps):
            logger.debug(
                "[PEVR Planner]   step %s: tool=%s name=%s purpose=%s",
                step.get("id", f"?{i}"),
                step.get("tool", "?"),
                step.get("name", "")[:40],
                step.get("purpose", "")[:60],
            )

        if pevr_log:
            pevr_log.log_planning(
                loop_index=retry_count,
                plan_steps=plan_steps,
                duration_s=duration,
                token_usage=token_usage,
            )

    except Exception as e:
        duration = time.time() - start
        logger.error(
            "[PEVR Planner] FAILED after %.1fms: %s",
            duration * 1000,
            e,
            exc_info=True,
        )
        plan_steps = []
        # token_usage already initialized before try block
        if pevr_log:
            pevr_log.log_planning(
                loop_index=retry_count,
                plan_steps=[],
                duration_s=duration,
                error=e,
                token_usage=token_usage,
            )
            pevr_log.log_node_error("planner", e, f"task={task[:100]}")

    # --- Return state update ---
    return {
        "plan": plan_steps,
        "reasoning_trace": [{"phase": "planning", "plan": plan_steps}],
    }
