"""PERV SkillPolicyNode — planner → skill_policy → executor.

Compiles skill references in the plan into concrete tool calls through
the unified SkillPolicy pipeline (Match → Gate → Compile(LLM) → Guard).
"""

import logging
import time as _time
from typing import Any, Dict, List

from app.core.skill_policy.engine import (
    _classify_skill_type,
    _get_skills_dir,
    guard_compiled_plan,
)
from app.core.skill_policy.types import PolicyInput, SkillPolicyReport
from app.tools import CORE_TOOLS

logger = logging.getLogger(__name__)


def _extract_skill_refs_from_plan(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract skill references from plan steps.

    Only matches steps whose tool starts with "skill.".
    """
    refs = []
    for step in plan:
        tool = step.get("tool", "")
        if tool.startswith("skill."):
            skill_name = tool.split(".", 1)[1]
            refs.append({
                "skill_name": skill_name,
                "source_steps": [step.get("id", "")],
                "step": step,
            })
    return refs


async def _compile_skill_step(
    skill_name: str,
    state: dict,
    llm: Any,
) -> List[Dict[str, Any]]:
    """Compile a single skill using the unified run_skill_policy pipeline.

    Returns a list of compiled plan steps (may be 1 or more if LLM
    generates a multi-step tool_plan).
    """
    from app.core.skill_policy.engine import run_skill_policy

    skills_dir = _get_skills_dir()
    skill_dir = skills_dir / skill_name
    skill_md_path = skill_dir / "SKILL.md"

    if not skill_md_path.exists():
        logger.warning("PERV SkillPolicy: SKILL.md not found for '%s'", skill_name)
        return []

    skill_type = _classify_skill_type(skill_name, skills_dir)
    skill_content = skill_md_path.read_text(encoding="utf-8")

    tools = state.get("_injected_tools")
    if tools:
        available_tools = [t.name for t in tools]
    else:
        available_tools = [t.name for t in CORE_TOOLS]

    policy_input = PolicyInput(
        user_query=state.get("task", ""),
        current_step={"tool": f"skill.{skill_name}"},
        available_tools=available_tools,
        candidate_skills=[],
        skill_content=skill_content,
        skill_name=skill_name,
        skill_type=skill_type,
        history={},
    )

    output = await run_skill_policy(policy_input, llm)

    if output.get("action") != "EXECUTE_TOOL_PLAN":
        logger.info(
            "PERV SkillPolicy: '%s' action=%s, keeping original step",
            skill_name, output.get("action"),
        )
        return []

    tool_plan = output.get("tool_plan", [])
    logger.info(
        "PERV SkillPolicy: '%s' compiled → %d step(s), expanding plan",
        skill_name, len(tool_plan),
    )
    return tool_plan


def _expand_tool_plan_to_steps(
    tool_plan: List[Dict[str, Any]],
    original_step: Dict[str, Any],
    skill_name: str,
) -> List[Dict[str, Any]]:
    """Expand a tool_plan into one or more plan steps replacing the original skill.* step."""
    if not tool_plan:
        return []

    results = []
    base_id = original_step.get("id", f"s_{skill_name}")

    for idx, tp in enumerate(tool_plan):
        step_id = f"{base_id}_c{idx}" if len(tool_plan) > 1 else base_id
        new_step = {
            "id": step_id,
            "name": f"Execute skill {skill_name}" + (f" (step {idx+1})" if len(tool_plan) > 1 else ""),
            "tool": tp.get("tool", ""),
            "purpose": tp.get("reason", f"Compiled from skill.{skill_name}"),
            "inputs": tp.get("args", {}),
            "depends_on": list(original_step.get("depends_on", [])),
            "output_key": f"out_{step_id}",
            "on_fail": {"retry": 1, "fallback_tool": None, "fallback_inputs": None},
            "description": f"Compiled skill step: {tp.get('tool', '?')}",
            "expected": "",
            "skill": None,
            "input": tp.get("args", {}),
            "skill_group": None,
        }
        # Preserve guard metadata for PEVR guard validation
        if "_source_skill_type" in tp:
            new_step["_source_skill_type"] = tp["_source_skill_type"]
        if "_source_skill_name" in tp:
            new_step["_source_skill_name"] = tp["_source_skill_name"]
        # Chain multi-step dependencies
        if idx > 0:
            new_step["depends_on"].append(f"{base_id}_c{idx-1}" if len(tool_plan) > 1 else base_id)
        results.append(new_step)

    return results


async def skill_policy_node(state: dict) -> dict:
    """PERV SkillPolicyNode: planner → skill_policy → executor.

    Unified pipeline via run_skill_policy. On failure, returns the original
    plan unchanged (PASS_THROUGH).
    """
    start = _time.monotonic()
    plan = state.get("plan", [])
    retry_count = state.get("retry_count", 0)
    pevr_log = state.get("_pevr_log")

    logger.info(
        "PERV SkillPolicyNode: ENTERED at loop %d with %d plan steps, tools=[%s]",
        retry_count, len(plan),
        ", ".join(s.get("tool", "?") for s in plan),
    )

    # Feature flag check
    feature_enabled = True
    try:
        from app.config import get_settings
        settings = get_settings()
        feature_enabled = getattr(settings, "perv_enable_skill_policy", True)
    except Exception:
        pass

    if not feature_enabled:
        duration_ms = (_time.monotonic() - start) * 1000
        report = SkillPolicyReport(
            policy_applied=False, matched_skills=[], gate_results=[],
            guard_passed=False, guard_issues=[], compiled_plan=None, error=None,
        )
        _log_to_pevr(pevr_log, retry_count, {
            "policy_applied": False, "feature_enabled": False,
            "plan_steps_in": len(plan), "plan_steps_out": len(plan),
        }, duration_ms)
        return {"plan": plan, "skill_policy_report": report}

    try:
        # 1. Extract skill references from plan
        skill_refs = _extract_skill_refs_from_plan(plan)
        if not skill_refs:
            duration_ms = (_time.monotonic() - start) * 1000
            logger.info("PERV SkillPolicyNode: no skill refs found (%d steps), PASS_THROUGH", len(plan))
            report = SkillPolicyReport(
                policy_applied=False, matched_skills=[], gate_results=[],
                guard_passed=False, guard_issues=[], compiled_plan=None, error=None,
            )
            _log_to_pevr(pevr_log, retry_count, {
                "policy_applied": False, "feature_enabled": True,
                "plan_steps_in": len(plan), "skill_refs_found": 0,
                "plan_steps_out": len(plan),
            }, duration_ms)
            return {"plan": plan, "skill_policy_report": report}

        # 2. Create LLM for compile
        from app.config import get_settings
        from app.core.llm import create_llm
        settings = get_settings()
        llm = create_llm(settings.llm_provider)

        # 3. Compile each skill reference
        compiled_plan = []
        compiled_count = 0
        for step in plan:
            tool = step.get("tool", "")
            if tool.startswith("skill."):
                skill_name = tool.split(".", 1)[1]
                tool_plan = await _compile_skill_step(skill_name, state, llm)

                if tool_plan:
                    expanded = _expand_tool_plan_to_steps(tool_plan, step, skill_name)
                    compiled_plan.extend(expanded)
                    compiled_count += 1
                else:
                    # Compilation failed → drop the step (replanner will handle)
                    logger.warning(
                        "PERV SkillPolicyNode: skill '%s' compilation returned empty, dropping step",
                        skill_name,
                    )
                continue

            compiled_plan.append(step)

        # 4. Guard — validate all compiled skill steps (with tool-skill_type auto-correction)
        skill_tool_plans = []
        for s in compiled_plan:
            is_compiled = (
                any(s.get("id", "").endswith(f"_c{i}") for i in range(5))
                or s.get("description", "").startswith("Compiled skill step")
            )
            if is_compiled:
                tp = {"tool": s.get("tool", ""), "args": s.get("inputs", {})}
                if "_source_skill_type" in s:
                    tp["_source_skill_type"] = s["_source_skill_type"]
                if "_source_skill_name" in s:
                    tp["_source_skill_name"] = s["_source_skill_name"]
                skill_tool_plans.append(tp)

        guard_ok = True
        if skill_tool_plans:
            guard_result = guard_compiled_plan(
                skill_tool_plans,
                {"user_query": state.get("task", ""), **state},
            )
            guard_ok = guard_result.get("passed", False)
            if not guard_ok:
                logger.warning("SkillPolicy GUARD failed: %s", guard_result.get("issues"))
            else:
                # Write back auto-corrected tool/args to compiled_plan
                idx = 0
                for s in compiled_plan:
                    is_compiled = (
                        any(s.get("id", "").endswith(f"_c{i}") for i in range(5))
                        or s.get("description", "").startswith("Compiled skill step")
                    )
                    if is_compiled and idx < len(skill_tool_plans):
                        corrected = skill_tool_plans[idx]
                        s["tool"] = corrected["tool"]
                        s["inputs"] = corrected["args"]
                        s["input"] = corrected["args"]
                        s["description"] = f"Compiled skill step: {corrected['tool']}"
                        idx += 1

        duration_ms = (_time.monotonic() - start) * 1000

        if not guard_ok:
            report = SkillPolicyReport(
                policy_applied=False, matched_skills=[], gate_results=[],
                guard_passed=False, guard_issues=[], compiled_plan=None, error=None,
            )
            _log_to_pevr(pevr_log, retry_count, {
                "policy_applied": False, "feature_enabled": True,
                "plan_steps_in": len(plan), "skill_refs_found": len(skill_refs),
                "compiled_count": compiled_count, "guard_passed": False,
                "plan_steps_out": len(plan),
            }, duration_ms)
            return {"plan": plan, "skill_policy_report": report}

        logger.info(
            "PERV SkillPolicyNode: COMPILED %d skills, plan %d→%d steps (%.0fms)",
            compiled_count, len(plan), len(compiled_plan), duration_ms,
        )

        report = SkillPolicyReport(
            policy_applied=compiled_count > 0,
            matched_skills=[{"skill_name": r["skill_name"]} for r in skill_refs],
            gate_results=[],
            guard_passed=True,
            guard_issues=[],
            compiled_plan=compiled_plan if compiled_count > 0 else None,
            error=None,
        )
        _log_to_pevr(pevr_log, retry_count, {
            "policy_applied": compiled_count > 0, "feature_enabled": True,
            "plan_steps_in": len(plan), "skill_refs_found": len(skill_refs),
            "compiled_count": compiled_count,
            "plan_steps_out": len(compiled_plan),
        }, duration_ms)

        return {
            "plan": compiled_plan,
            "skill_policy_report": report,
            "reasoning_trace": [{
                "phase": "skill_policy",
                "skill_refs": len(skill_refs),
                "compiled": compiled_count,
                "guard_passed": True,
            }],
        }

    except Exception as e:
        duration_ms = (_time.monotonic() - start) * 1000
        logger.error("PERV SkillPolicyNode failed: %s", e, exc_info=True)
        report = SkillPolicyReport(
            policy_applied=False, matched_skills=[], gate_results=[],
            guard_passed=False, guard_issues=[], compiled_plan=None, error=str(e),
        )
        _log_to_pevr(pevr_log, retry_count, {
            "policy_applied": False, "feature_enabled": True,
            "plan_steps_in": len(plan), "error": str(e),
        }, duration_ms)
        return {"plan": plan, "skill_policy_report": report}


def _log_to_pevr(pevr_log, loop_index: int, report: dict, duration_ms: float):
    """Helper to log SkillPolicy results to PEVRLogger if available."""
    if pevr_log and hasattr(pevr_log, "log_skill_policy"):
        try:
            pevr_log.log_skill_policy(
                loop_index=loop_index,
                report=report,
                duration_ms=duration_ms,
            )
        except Exception:
            pass
