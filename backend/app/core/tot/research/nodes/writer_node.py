"""
Writer Node

Writes or updates an incremental draft based on accumulated evidence,
coverage analysis, and detected contradictions. Uses an LLM with a
writing-level prompt (SOUL + IDENTITY + BASE_RESEARCH) for high-quality
draft generation.

Includes a conditional call mechanism that skips the LLM call when
coverage has not changed significantly since the last draft, saving
tokens on redundant rewrites.

For non-research task modes, performs no writing.
"""

import json
import logging
import time
from typing import Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.tot.state import ToTState
from app.core.tot.research.evidence_utils import format_evidence_for_prompt
from app.core.tot.research.prompts import get_writer_prompt
from app.core.tot.prompt_composer import compose_system_prompt

logger = logging.getLogger(__name__)

# Minimum draft length to be considered valid (chars).
# Drafts shorter than this are rejected in favor of the previous draft.
_MIN_DRAFT_LENGTH = 100


async def writer_node(state: ToTState) -> Dict:
    """Write or update the incremental draft based on evidence and coverage.

    Uses the conditional call logic to skip the Writer when coverage
    has not changed significantly since the last draft:
      - If coverage delta < min_delta AND a draft already exists, skip.
      - Otherwise, call the LLM to generate an updated draft.

    For non-research task modes, returns an empty dict (no writing).

    Args:
        state: Current ToT state with evidence_store, coverage_map,
            contradictions, and draft.

    Returns:
        Dict with updated draft and prev_coverage_score.
    """
    task_mode = state.get("task_mode", "standard")

    # Skip for non-research modes
    if task_mode != "research":
        logger.debug("writer_node: non-research mode, skipping")
        return {}

    # Conditional call logic: skip if coverage hasn't changed enough
    current_score = _get_coverage_score(state)
    prev_score = float(state.get("prev_coverage_score", 0.0))
    delta = current_score - prev_score
    min_delta = float(state.get("writer_min_delta", 0.15))
    existing_draft = state.get("draft", "")

    if delta < min_delta and existing_draft:
        logger.info(
            f"writer_node: skipping (delta={delta:.3f} < min_delta={min_delta:.3f}, "
            f"existing draft length={len(existing_draft)})"
        )
        return {"prev_coverage_score": current_score}

    # Proceed with LLM draft generation
    user_query = state.get("user_query", "")
    evidence_store = state.get("evidence_store") or []
    coverage_map = state.get("coverage_map") or {}
    contradictions = state.get("contradictions") or []

    # Format evidence
    evidence_summary = format_evidence_for_prompt(evidence_store)

    # Serialize coverage_map and contradictions for the prompt
    coverage_map_str = json.dumps(coverage_map, ensure_ascii=False, indent=2) if coverage_map else "{}"
    contradictions_str = json.dumps(contradictions, ensure_ascii=False, indent=2) if contradictions else "[]"

    # Build the writer prompt
    user_prompt = get_writer_prompt(
        user_query=user_query,
        coverage_map=coverage_map_str,
        contradictions=contradictions_str,
        draft=existing_draft,
        evidence_summary=evidence_summary,
    )

    # Compose writing-level system prompt
    system_prompt = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="termination",  # reuse termination role
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="writing",
    )

    llm = state["llm"]

    start = time.monotonic()
    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        new_draft = response.content
        elapsed_ms = (time.monotonic() - start) * 1000

        logger.info(
            f"writer_node: LLM response received in {elapsed_ms:.0f}ms, "
            f"draft length={len(new_draft)}"
        )

    except Exception as exc:
        logger.error(f"writer_node: LLM call failed: {exc}")
        # Keep previous draft on failure
        if existing_draft:
            return {"prev_coverage_score": current_score}
        return {"prev_coverage_score": current_score}

    # Validate draft is substantial
    if not new_draft or len(new_draft.strip()) < _MIN_DRAFT_LENGTH:
        logger.warning(
            f"writer_node: draft too short ({len(new_draft.strip())} chars), "
            f"keeping previous draft"
        )
        if existing_draft:
            return {"prev_coverage_score": current_score}
        # No previous draft: use whatever we got (even if short)
        new_draft = new_draft or ""

    # Log via ToTExecutionLogger
    _log_draft_update(state, new_draft)

    # Emit SSE trace event
    _emit_sse_writer_event(state, new_draft, current_score)

    logger.info(
        f"writer_node: draft updated, length={len(new_draft)}, "
        f"coverage_score={current_score:.2f}"
    )

    return {
        "draft": new_draft,
        "prev_coverage_score": current_score,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_coverage_score(state: ToTState) -> float:
    """Extract coverage_score from the state's coverage_map safely.

    Args:
        state: Current ToT state.

    Returns:
        The coverage score as a float, defaulting to 0.0.
    """
    coverage_map = state.get("coverage_map")
    if not coverage_map or not isinstance(coverage_map, dict):
        return 0.0
    return float(coverage_map.get("coverage_score", 0.0))


def _log_draft_update(state: ToTState, draft: str) -> None:
    """Log draft update via ToTExecutionLogger if available.

    Args:
        state: Current ToT state.
        draft: The updated draft text.
    """
    try:
        tot_logger = state.get("tot_logger")
        if tot_logger is not None:
            # Count sections (## headers) and citations
            sections_count = draft.count("## ")
            citations_count = draft.count("[")  # Rough citation count
            tot_logger.log_draft_update(
                depth=state.get("current_depth", 0),
                sections_count=sections_count,
                citations_count=citations_count,
            )
    except Exception:
        pass  # Logging is non-critical


def _emit_sse_writer_event(
    state: ToTState,
    draft: str,
    coverage_score: float,
) -> None:
    """Emit an SSE research_draft_update event into the reasoning trace.

    Args:
        state: Current ToT state.
        draft: The updated draft text.
        coverage_score: Current coverage score.
    """
    trace = state.setdefault("reasoning_trace", [])
    trace.append({
        "type": "research_draft_update",
        "draft_length": len(draft),
        "sections_count": draft.count("## "),
        "coverage_score": coverage_score,
    })
