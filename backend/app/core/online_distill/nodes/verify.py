"""Verify node — evaluates execution success/score/evidence via ReflectionEngine."""

from __future__ import annotations

import logging
from typing import List

from app.core.online_distill.config import get_distill_config
from app.core.online_distill.models import DistillState, VerifyResult

logger = logging.getLogger(__name__)


def _extract_error_tags(result) -> List[str]:
    """Extract error tags from ReflectionResult."""
    tags: List[str] = []
    if result.failure_type and result.failure_type != "none":
        tags.append(result.failure_type)
    if not result.completed:
        tags.append("incomplete")
    if result.quality_score < 4.0:
        tags.append("quality_low")
    return tags


async def verify_node(state: DistillState) -> DistillState:
    """Evaluate online execution result: success/score/evidence/error_tags.

    Reuses ReflectionEngine.reflect() as the evaluation engine.
    """
    from app.memory.auto_learning.reflection.reflection_engine import ReflectionEngine

    distill_config = get_distill_config()
    user_query = state.get("user_query", "")
    agent_output = state.get("agent_output", "")
    tool_calls = state.get("tool_calls", [])
    execution_time = state.get("execution_time", 0.0)

    engine = ReflectionEngine()
    try:
        result = await engine.reflect(
            user_query=user_query,
            agent_output=agent_output,
            tool_calls=tool_calls,
            execution_time=execution_time,
        )
    except Exception as e:
        logger.warning("[OnlineDistill] ReflectionEngine failed: %s", e)
        state["verify_result"] = VerifyResult(
            success=False,
            score=0.0,
            error_tags=["reflection_failed"],
            should_distill=False,
        )
        return state

    # Build evidence from tool calls + reflection
    evidence = {
        "tool_quotes": [
            tc.get("output_preview", "")[:200]
            for tc in tool_calls
            if tc.get("success")
        ],
        "reasoning": (result.suggestions[:500] if result.suggestions else ""),
    }

    should_distill = (
        result.quality_score >= distill_config.min_quality_score
        and (result.completed or distill_config.allow_failure_distill)
    )

    # Additional check: failure tags must be in allowed list for failure distill
    if should_distill and not result.completed:
        tags = _extract_error_tags(result)
        allowed = distill_config.failure_distill_tags
        if not any(t in allowed for t in tags):
            should_distill = False

    state["verify_result"] = VerifyResult(
        success=result.completed,
        score=result.quality_score,
        error_tags=_extract_error_tags(result),
        evidence=evidence,
        reusable_pattern=result.reusable_pattern,
        failure_type=result.failure_type if result.failure_type != "none" else None,
        should_distill=should_distill,
    )
    return state
