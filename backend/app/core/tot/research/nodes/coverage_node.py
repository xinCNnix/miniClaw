"""
Coverage Node

Analyzes evidence coverage against the user query, identifying which
sub-topics are covered, which are missing, and producing a coverage
score. Uses an LLM with an analysis-level prompt for structured
coverage analysis.

For non-research task modes, returns a trivial full-coverage result.
"""

import json
import logging
import time
from typing import Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.tot.state import ToTState
from app.core.tot.research.evidence_utils import format_evidence_for_prompt
from app.core.tot.research.prompts import get_coverage_prompt, parse_json_output
from app.core.tot.prompt_composer import compose_system_prompt

logger = logging.getLogger(__name__)


async def coverage_node(state: ToTState) -> Dict:
    """Analyze evidence coverage and identify gaps.

    Formats the current evidence store, sends it to the LLM with
    the coverage analysis prompt, and parses the structured JSON
    response to produce an updated coverage_map.

    For non-research task modes, returns a trivial coverage map
    indicating full coverage.

    Args:
        state: Current ToT state with evidence_store and user_query.

    Returns:
        Dict with updated coverage_map.
    """
    task_mode = state.get("task_mode", "standard")

    # Skip for non-research modes
    if task_mode != "research":
        logger.debug("coverage_node: non-research mode, returning trivial coverage")
        return {
            "coverage_map": {
                "query": state.get("user_query", ""),
                "score": 1.0,
                "topics": [],
            }
        }

    user_query = state.get("user_query", "")
    evidence_store = state.get("evidence_store") or []

    # Empty evidence: return zero coverage
    if not evidence_store:
        logger.info("coverage_node: empty evidence_store, coverage=0.0")
        return {
            "coverage_map": {
                "query": user_query,
                "topics": [],
                "critical_missing_topics": [],
                "critical_missing_evidence_types": [],
                "coverage_score": 0.0,
                "recommended_next_actions": [],
            }
        }

    # Format evidence for the prompt
    evidence_summary = format_evidence_for_prompt(evidence_store)

    # Build the coverage analysis prompt
    user_prompt = get_coverage_prompt(
        user_query=user_query,
        evidence_summary=evidence_summary,
    )

    # Compose analysis-level system prompt
    system_prompt = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="termination",  # reuse termination role for analysis
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="analysis",
    )

    llm = state["llm"]

    start = time.monotonic()
    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        raw_output = response.content
        elapsed_ms = (time.monotonic() - start) * 1000

        logger.info(
            f"coverage_node: LLM response received in {elapsed_ms:.0f}ms, "
            f"length={len(raw_output)}"
        )

    except Exception as exc:
        logger.error(f"coverage_node: LLM call failed: {exc}")
        # Keep previous coverage_map if LLM fails
        prev_map = state.get("coverage_map")
        if prev_map:
            logger.info("coverage_node: keeping previous coverage_map due to LLM failure")
            return {}
        # No previous map: return empty coverage
        return {
            "coverage_map": {
                "query": user_query,
                "topics": [],
                "critical_missing_topics": [],
                "critical_missing_evidence_types": [],
                "coverage_score": 0.0,
                "recommended_next_actions": [],
            }
        }

    # Parse the JSON response
    parsed = parse_json_output(raw_output)

    if not parsed:
        logger.warning("coverage_node: failed to parse LLM output as JSON")
        # Keep previous coverage_map on parse failure
        prev_map = state.get("coverage_map")
        if prev_map:
            return {}
        return {
            "coverage_map": {
                "query": user_query,
                "topics": [],
                "critical_missing_topics": [],
                "critical_missing_evidence_types": [],
                "coverage_score": 0.0,
                "recommended_next_actions": [],
            }
        }

    # Ensure required fields exist
    coverage_map = _ensure_coverage_fields(parsed, user_query)

    # Log via ToTExecutionLogger
    _log_coverage_update(state, coverage_map)

    # Emit SSE trace event for frontend
    _emit_sse_coverage_event(state, coverage_map)

    logger.info(
        f"coverage_node: coverage_score={coverage_map.get('coverage_score', 0.0):.2f}, "
        f"topics={len(coverage_map.get('topics', []))}, "
        f"critical_missing={len(coverage_map.get('critical_missing_topics', []))}"
    )

    return {"coverage_map": coverage_map}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_coverage_fields(parsed: Dict, user_query: str) -> Dict:
    """Ensure all required fields exist in the parsed coverage map.

    Provides sensible defaults for any missing fields so downstream
    consumers can rely on the structure.

    Args:
        parsed: The parsed JSON dict from the LLM.
        user_query: The original user query.

    Returns:
        Coverage map dict with all required fields populated.
    """
    # Handle case where LLM returns topics in different formats
    topics = parsed.get("topics", [])
    if not isinstance(topics, list):
        topics = []

    # Normalize topic items: ensure each is a dict with required fields
    normalized_topics = []
    for t in topics:
        if isinstance(t, dict):
            normalized_topics.append({
                "topic": t.get("topic", ""),
                "covered": bool(t.get("covered", False)),
                "sources_count": int(t.get("sources_count", 0)),
                "claims_count": int(t.get("claims_count", 0)),
                "numbers_count": int(t.get("numbers_count", 0)),
                "missing_evidence_types": t.get("missing_evidence_types", []),
                "notes": t.get("notes", ""),
            })
        elif isinstance(t, str):
            normalized_topics.append({
                "topic": t,
                "covered": False,
                "sources_count": 0,
                "claims_count": 0,
                "numbers_count": 0,
                "missing_evidence_types": [],
                "notes": "",
            })

    critical_missing_topics = parsed.get("critical_missing_topics", [])
    if not isinstance(critical_missing_topics, list):
        critical_missing_topics = []

    critical_missing_evidence_types = parsed.get(
        "critical_missing_evidence_types", []
    )
    if not isinstance(critical_missing_evidence_types, list):
        critical_missing_evidence_types = []

    recommended_next_actions = parsed.get("recommended_next_actions", [])
    if not isinstance(recommended_next_actions, list):
        recommended_next_actions = []

    # Ensure coverage_score is a float between 0 and 1
    coverage_score = float(parsed.get("coverage_score", 0.0))
    coverage_score = max(0.0, min(1.0, coverage_score))

    return {
        "query": parsed.get("query", user_query),
        "topics": normalized_topics,
        "critical_missing_topics": critical_missing_topics,
        "critical_missing_evidence_types": critical_missing_evidence_types,
        "coverage_score": coverage_score,
        "recommended_next_actions": recommended_next_actions,
    }


def _log_coverage_update(state: ToTState, coverage_map: Dict) -> None:
    """Log coverage update via ToTExecutionLogger if available.

    Args:
        state: Current ToT state.
        coverage_map: The updated coverage map.
    """
    try:
        tot_logger = state.get("tot_logger")
        if tot_logger is not None:
            topics = coverage_map.get("topics", [])
            topics_covered = sum(
                1 for t in topics if isinstance(t, dict) and t.get("covered")
            )
            tot_logger.log_coverage_update(
                depth=state.get("current_depth", 0),
                coverage_score=coverage_map.get("coverage_score", 0.0),
                topics_covered=topics_covered,
                topics_total=len(topics),
                critical_missing=coverage_map.get(
                    "critical_missing_topics", []
                ),
            )
    except Exception:
        pass  # Logging is non-critical


def _emit_sse_coverage_event(state: ToTState, coverage_map: Dict) -> None:
    """Emit an SSE research_coverage_update event into the reasoning trace.

    The reasoning_trace is consumed by the frontend via SSE streaming
    to display real-time research progress.

    Args:
        state: Current ToT state.
        coverage_map: The updated coverage map.
    """
    trace = state.setdefault("reasoning_trace", [])
    trace.append({
        "type": "research_coverage_update",
        "coverage_score": coverage_map.get("coverage_score", 0.0),
        "topics_total": len(coverage_map.get("topics", [])),
        "topics_covered": sum(
            1
            for t in coverage_map.get("topics", [])
            if isinstance(t, dict) and t.get("covered")
        ),
        "critical_missing": coverage_map.get("critical_missing_topics", []),
    })
