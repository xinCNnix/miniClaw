"""ToT SkillPolicyNode — builds gate context for thought_executor.

Unlike PERV's standalone graph node, the ToT integration hooks into
thought_executor's tool execution path.  This module provides the
helper functions used by thought_executor for the SkillPolicy gate.
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.skill_policy.engine import match_skills, gate_skills, compile_skill, guard_compiled_plan

logger = logging.getLogger(__name__)


def build_tot_gate_context(tools: List) -> Dict[str, Any]:
    """Build GATE context from available ToT tools."""
    core_tools = [t.name for t in tools] if tools else []
    return {"core_tools": core_tools}


def check_skill_policy_gate(
    skill_name: str,
    user_query: str,
    tools: List,
    enrichment: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Run Match + Gate + Compile + Guard for a single skill.

    Returns compiled tool call dict on success, None on failure.
    Used by thought_executor before executing a read_file(SKILL.md).
    """
    try:
        # MATCH
        candidates = match_skills(user_query, [{"skill_name": skill_name}], enrichment)
        if not candidates:
            logger.info(
                "[ToT SkillPolicy] MATCH miss for '%s': no candidates returned",
                skill_name,
            )
            return None

        cand = candidates[0]
        logger.info(
            "[ToT SkillPolicy] MATCH hit: '%s' type=%s score=%.2f",
            skill_name, cand["skill_type"], cand["score"],
        )

        # GATE
        gate_ctx = build_tot_gate_context(tools)
        gate_results = gate_skills(candidates, gate_ctx)

        if not gate_results or not gate_results[0].get("allowed"):
            reason = gate_results[0].get("reason", "unknown") if gate_results else "no results"
            logger.info(
                "[ToT SkillPolicy] GATE rejected '%s': %s (core_tools=%s)",
                skill_name, reason,
                sorted(gate_ctx.get("core_tools", [])),
            )
            return None

        # COMPILE
        compiled = compile_skill(
            skill_name,
            cand["skill_type"],
            user_query,
        )
        logger.info(
            "[ToT SkillPolicy] COMPILE '%s' (%s) → %s",
            skill_name, cand["skill_type"], compiled.get("tool"),
        )

        # GUARD
        guard_result = guard_compiled_plan([compiled], {})
        if not guard_result["passed"]:
            logger.warning(
                "[ToT SkillPolicy] GUARD failed for '%s': %s",
                skill_name, guard_result["issues"],
            )
            return None

        logger.info(
            "[ToT SkillPolicy] PASSED for '%s': will execute as %s",
            skill_name, compiled.get("tool"),
        )
        return compiled

    except Exception as e:
        logger.warning(
            "[ToT SkillPolicy] Gate failed for '%s': %s", skill_name, e,
            exc_info=True,
        )
        return None
