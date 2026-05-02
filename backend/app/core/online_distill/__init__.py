"""Online Distill — online skill distillation system.

Provides `online_distill_skill()` as the unified async entry point.
Called via `asyncio.create_task()` after agent execution completes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.core.online_distill.config import get_distill_config
from app.core.online_distill.graph import build_distill_graph

logger = logging.getLogger(__name__)

_distill_graph = None


def _get_distill_graph():
    """Lazily initialize and cache the compiled graph."""
    global _distill_graph
    if _distill_graph is None:
        _distill_graph = build_distill_graph()
    return _distill_graph


async def online_distill_skill(
    user_query: str,
    agent_output: str,
    tool_calls: list[dict],
    execution_time: float,
    execution_mode: str = "normal",
    # PEVR extended params
    plan: list[dict] | None = None,
    observations: list[dict] | None = None,
    verifier_report: dict | None = None,
    # ToT extended params
    thought_count: int = 0,
    best_score: float = 0.0,
    max_depth: int = 0,
) -> Optional[str]:
    """Online skill distillation entry — unified for all three modes.

    Called via asyncio.create_task(), non-blocking.
    Returns written skill_id or None.
    """
    config = get_distill_config()
    if not config.enabled:
        return None

    try:
        graph = _get_distill_graph()
        result = await asyncio.wait_for(
            graph.ainvoke(
                {
                    "user_query": user_query,
                    "agent_output": agent_output,
                    "tool_calls": tool_calls,
                    "execution_time": execution_time,
                    "execution_mode": execution_mode,
                    "plan": plan,
                    "observations": observations,
                    "verifier_report": verifier_report,
                    "thought_count": thought_count,
                    "best_score": best_score,
                    "max_depth": max_depth,
                }
            ),
            timeout=config.timeout_seconds,
        )
        skill_id = result.get("written_skill_id")
        if skill_id:
            logger.info("[OnlineDistill] Distilled skill: %s", skill_id)
        return skill_id
    except asyncio.TimeoutError:
        logger.warning("[OnlineDistill] Timed out for query: %s", user_query[:50])
        return None
    except Exception as e:
        logger.error("[OnlineDistill] Failed: %s", e)
        return None
