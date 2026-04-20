"""PERV SkillPolicyNode — planner → skill_policy → executor.

Compiles skill references in the plan into concrete tool calls through
the four-stage Match → Gate → Compile → Guard pipeline.
"""

import logging
from typing import Any, Dict, List

from app.core.skill_policy.engine import match_skills, gate_skills, compile_skill, guard_compiled_plan
from app.core.skill_policy.types import SkillPolicyReport

logger = logging.getLogger(__name__)


def _extract_skill_refs_from_plan(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract skill references from plan steps.

    Matches steps whose tool starts with "skill." or whose skill_group is non-empty.
    """
    refs = []
    for step in plan:
        tool = step.get("tool", "")
        skill_group = step.get("skill_group")

        if tool.startswith("skill."):
            skill_name = tool.split(".", 1)[1]
            refs.append({
                "skill_name": skill_name,
                "source_steps": [step.get("id", "")],
                "step": step,
            })
        elif skill_group:
            refs.append({
                "skill_name": skill_group,
                "source_steps": [step.get("id", "")],
                "step": step,
            })
    return refs


def _build_gate_context(state: dict) -> Dict[str, Any]:
    """Build context dict for GATE stage."""
    tools = state.get("_injected_tools")
    if tools:
        core_tools = [t.name for t in tools]
    else:
        # Fallback: state 中未注入 tools 时，直接从 CORE_TOOLS 获取
        from app.tools import CORE_TOOLS
        core_tools = [t.name for t in CORE_TOOLS]
        logger.debug("SkillPolicy _build_gate_context: _injected_tools empty, using CORE_TOOLS (%d tools)", len(core_tools))

    return {
        "core_tools": core_tools,
        "prev_report": state.get("skill_policy_report"),
    }


def _compile_plan_steps(
    plan: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    gate_results: List[Dict[str, Any]],
    state: dict,
) -> List[Dict[str, Any]]:
    """Replace skill references in plan with compiled tool calls.

    Preserves original step structure (depends_on, output_key, etc.),
    only replacing tool and inputs.
    """
    # Build map of skill_name → compiled tool call
    allowed_skills = {}
    for cand, gate in zip(candidates, gate_results):
        if gate.get("allowed"):
            compiled = compile_skill(
                cand["skill_name"],
                cand["skill_type"],
                state.get("task", ""),
            )
            allowed_skills[cand["skill_name"]] = compiled

    # Build reverse map: step_id → compiled
    step_compile_map: Dict[str, Dict] = {}
    for cand in candidates:
        compiled = allowed_skills.get(cand["skill_name"])
        if compiled:
            for sid in cand.get("source_steps", []):
                step_compile_map[sid] = compiled

    # Apply compilations to plan
    compiled_plan = []
    for step in plan:
        step_id = step.get("id", "")
        if step_id in step_compile_map:
            compiled = step_compile_map[step_id]
            new_step = dict(step)  # shallow copy preserves depends_on, output_key, etc.
            new_step["tool"] = compiled["tool"]
            new_step["inputs"] = compiled["args"]
            new_step["_original_skill"] = step.get("tool") or step.get("skill_group")
            compiled_plan.append(new_step)
        else:
            compiled_plan.append(step)

    return compiled_plan


async def skill_policy_node(state: dict) -> dict:
    """PERV SkillPolicyNode: planner → skill_policy → executor.

    Four-stage pipeline: Match → Gate → Compile → Guard.
    On failure, returns the original plan unchanged (PASS_THROUGH).
    """
    start = __import__("time").monotonic()
    plan = state.get("plan", [])
    enrichment = state.get("enrichment", {})
    retry_count = state.get("retry_count", 0)
    pevr_log = state.get("_pevr_log")

    logger.info(
        "SkillPolicyNode: ENTERED at loop %d with %d plan steps, tools=[%s]",
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
        duration_ms = (__import__("time").monotonic() - start) * 1000
        report = SkillPolicyReport(
            policy_applied=False,
            matched_skills=[],
            gate_results=[],
            guard_passed=False,
            guard_issues=[],
            compiled_plan=None,
            error=None,
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
            duration_ms = (__import__("time").monotonic() - start) * 1000
            logger.info(
                "SkillPolicyNode: no skill refs found in plan (%d steps), PASS_THROUGH",
                len(plan),
            )
            report = SkillPolicyReport(
                policy_applied=False,
                matched_skills=[],
                gate_results=[],
                guard_passed=False,
                guard_issues=[],
                compiled_plan=None,
                error=None,
            )
            _log_to_pevr(pevr_log, retry_count, {
                "policy_applied": False, "feature_enabled": True,
                "plan_steps_in": len(plan), "skill_refs_found": 0,
                "plan_steps_out": len(plan),
            }, duration_ms)
            return {"plan": plan, "skill_policy_report": report}

        # 2. MATCH
        candidates = match_skills(state["task"], skill_refs, enrichment)
        logger.info(
            "SkillPolicyNode: MATCH found %d candidates from %d refs: %s",
            len(candidates), len(skill_refs),
            [c["skill_name"] for c in candidates],
        )
        if not candidates:
            duration_ms = (__import__("time").monotonic() - start) * 1000
            report = SkillPolicyReport(
                policy_applied=False,
                matched_skills=[],
                gate_results=[],
                guard_passed=False,
                guard_issues=[],
                compiled_plan=None,
                error=None,
            )
            _log_to_pevr(pevr_log, retry_count, {
                "policy_applied": False, "feature_enabled": True,
                "plan_steps_in": len(plan), "skill_refs_found": len(skill_refs),
                "skill_refs": [{"name": r.get("skill_name"), "steps": r.get("source_steps")} for r in skill_refs],
                "matched_count": 0, "plan_steps_out": len(plan),
            }, duration_ms)
            return {"plan": plan, "skill_policy_report": report}

        # 3. GATE
        gate_ctx = _build_gate_context(state)
        gate_results = gate_skills(candidates, gate_ctx)

        # 4. COMPILE — replace skill references in plan
        compiled_plan = _compile_plan_steps(plan, candidates, gate_results, state)

        # Collect compiled skill info for logging
        compiled_skills = []
        for cand, gate in zip(candidates, gate_results):
            if gate.get("allowed"):
                compiled_skills.append({
                    "skill_name": cand["skill_name"],
                    "skill_type": cand["skill_type"],
                    "compiled_tool": next(
                        (s.get("tool") for s in compiled_plan
                         if s.get("_original_skill") == cand["skill_name"]
                         or s.get("_original_skill") == f"skill.{cand['skill_name']}"),
                        "?",
                    ),
                })

        # 5. GUARD
        tool_plans = [
            {"tool": s.get("tool", ""), "args": s.get("inputs", {})}
            for s in compiled_plan
            if s.get("_original_skill")
        ]
        guard_result = guard_compiled_plan(tool_plans, state)

        if not guard_result["passed"]:
            duration_ms = (__import__("time").monotonic() - start) * 1000
            logger.warning("SkillPolicy GUARD failed: %s", guard_result["issues"])
            report = SkillPolicyReport(
                policy_applied=False,
                matched_skills=[c for c in candidates],
                gate_results=[g for g in gate_results],
                guard_passed=False,
                guard_issues=guard_result["issues"],
                compiled_plan=None,
                error=None,
            )
            _log_to_pevr(pevr_log, retry_count, {
                "policy_applied": False, "feature_enabled": True,
                "plan_steps_in": len(plan), "skill_refs_found": len(skill_refs),
                "skill_refs": [{"name": r.get("skill_name")} for r in skill_refs],
                "matched_skills": candidates, "gate_results": gate_results,
                "guard_passed": False, "guard_issues": guard_result["issues"],
                "compiled_count": 0, "plan_steps_out": len(plan),
            }, duration_ms)
            return {"plan": plan, "skill_policy_report": report}

        # Strip internal metadata before returning to pipeline
        final_plan = []
        for step in compiled_plan:
            clean = {k: v for k, v in step.items() if not k.startswith("_")}
            final_plan.append(clean)

        report = SkillPolicyReport(
            policy_applied=True,
            matched_skills=[c for c in candidates],
            gate_results=[g for g in gate_results],
            guard_passed=True,
            guard_issues=[],
            compiled_plan=final_plan,
            error=None,
        )

        duration_ms = (__import__("time").monotonic() - start) * 1000
        logger.info(
            "SkillPolicyNode: COMPILED %d skills successfully, plan %d→%d steps (%.0fms)",
            sum(1 for g in gate_results if g.get("allowed")),
            len(plan), len(final_plan), duration_ms,
        )

        _log_to_pevr(pevr_log, retry_count, {
            "policy_applied": True, "feature_enabled": True,
            "plan_steps_in": len(plan), "skill_refs_found": len(skill_refs),
            "skill_refs": [{"name": r.get("skill_name")} for r in skill_refs],
            "matched_skills": candidates, "gate_results": gate_results,
            "guard_passed": True, "guard_issues": [],
            "compiled_count": len(compiled_skills),
            "compiled_skills": compiled_skills,
            "plan_steps_out": len(final_plan),
        }, duration_ms)

        return {
            "plan": final_plan,
            "skill_policy_report": report,
            "reasoning_trace": [{
                "phase": "skill_policy",
                "matched": len(candidates),
                "compiled": sum(1 for g in gate_results if g.get("allowed")),
                "guard_passed": True,
            }],
        }

    except Exception as e:
        duration_ms = (__import__("time").monotonic() - start) * 1000
        logger.error("SkillPolicyNode failed: %s", e, exc_info=True)
        report = SkillPolicyReport(
            policy_applied=False,
            matched_skills=[],
            gate_results=[],
            guard_passed=False,
            guard_issues=[],
            compiled_plan=None,
            error=str(e),
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
