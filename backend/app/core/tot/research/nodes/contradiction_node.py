"""
Contradiction Node

Detects contradictions and conflicts between evidence sources.
Uses an LLM with an analysis-level prompt to identify metric
conflicts, claim conflicts, definition conflicts, and missing
context issues across the evidence store.

For non-research task modes, returns an empty contradictions list.
"""

import json
import logging
import time
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.tot.state import ToTState
from app.core.tot.research.evidence_utils import format_evidence_for_prompt
from app.core.tot.research.prompts import get_contradiction_prompt, parse_json_output
from app.core.tot.prompt_composer import compose_system_prompt

logger = logging.getLogger(__name__)


async def contradiction_node(state: ToTState) -> Dict:
    """Detect contradictions between evidence sources.

    Formats the current evidence store and sends it to the LLM with
    the contradiction detection prompt. Parses the structured JSON
    response to produce an updated contradictions list.

    For non-research task modes, returns an empty contradictions list.

    Args:
        state: Current ToT state with evidence_store and user_query.

    Returns:
        Dict with updated contradictions list.
    """
    task_mode = state.get("task_mode", "standard")

    # Skip for non-research modes
    if task_mode != "research":
        logger.debug("contradiction_node: non-research mode, returning empty contradictions")
        return {"contradictions": []}

    user_query = state.get("user_query", "")
    evidence_store = state.get("evidence_store") or []

    # Not enough evidence to detect contradictions
    if len(evidence_store) < 2:
        logger.debug(
            "contradiction_node: fewer than 2 evidence items, "
            "skipping contradiction detection"
        )
        return {"contradictions": []}

    # Format evidence for the prompt
    evidence_summary = format_evidence_for_prompt(evidence_store)

    # Build the contradiction detection prompt
    user_prompt = get_contradiction_prompt(
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
            f"contradiction_node: LLM response received in {elapsed_ms:.0f}ms, "
            f"length={len(raw_output)}"
        )

    except Exception as exc:
        logger.error(f"contradiction_node: LLM call failed: {exc}")
        # Keep previous contradictions on LLM failure
        prev_contradictions = state.get("contradictions")
        if prev_contradictions:
            logger.info(
                "contradiction_node: keeping previous contradictions "
                "due to LLM failure"
            )
            return {}
        return {"contradictions": []}

    # Parse the JSON response
    parsed = parse_json_output(raw_output)

    if not parsed:
        logger.warning("contradiction_node: failed to parse LLM output as JSON")
        prev_contradictions = state.get("contradictions")
        if prev_contradictions:
            return {}
        return {"contradictions": []}

    # Extract contradictions from parsed output
    contradictions = _extract_contradictions(parsed)

    # Log via ToTExecutionLogger
    _log_contradiction_detection(state, contradictions)

    # Emit SSE trace event
    _emit_sse_contradiction_event(state, contradictions)

    logger.info(
        f"contradiction_node: detected {len(contradictions)} contradictions"
    )

    return {"contradictions": contradictions}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_contradictions(parsed: Dict) -> List[Dict]:
    """Extract and normalize contradiction items from parsed LLM output.

    The LLM may return contradictions in different formats: as a
    top-level "contradictions" list, or as the parsed output directly
    being an array under "_array" (from parse_json_output).

    Args:
        parsed: The parsed JSON dict from the LLM.

    Returns:
        List of normalized contradiction dicts.
    """
    # Try to get contradictions from the expected key
    raw_items = parsed.get("contradictions") or parsed.get("conflicts")

    # If the entire parsed output is wrapped as an array
    if raw_items is None and "_array" in parsed:
        raw_items = parsed["_array"]

    if not raw_items or not isinstance(raw_items, list):
        # Check if the parsed dict itself looks like a single contradiction
        if parsed.get("issue") and parsed.get("type"):
            raw_items = [parsed]
        else:
            return []

    normalized: List[Dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        side_a = item.get("side_a", {})
        side_b = item.get("side_b", {})
        if isinstance(side_a, str):
            side_a = {"claim": side_a, "source_ids": [], "quote": ""}
        if isinstance(side_b, str):
            side_b = {"claim": side_b, "source_ids": [], "quote": ""}

        normalized.append({
            "issue": item.get("issue", "Unspecified contradiction"),
            "type": item.get("type", "claim_conflict"),
            "side_a": side_a,
            "side_b": side_b,
            "possible_explanations": item.get("possible_explanations", []),
            "verification_plan": item.get("verification_plan", {}),
            "severity": float(item.get("severity", 0.5)),
        })

    # Sort by severity descending
    normalized.sort(key=lambda c: c["severity"], reverse=True)

    return normalized


def _log_contradiction_detection(
    state: ToTState,
    contradictions: List[Dict],
) -> None:
    """Log contradiction detection results via ToTExecutionLogger.

    Args:
        state: Current ToT state.
        contradictions: List of detected contradiction dicts.
    """
    try:
        tot_logger = state.get("tot_logger")
        if tot_logger is not None:
            max_severity = max(
                (c.get("severity", 0.0) for c in contradictions),
                default=0.0,
            )
            types_found = list({
                c.get("type", "unknown") for c in contradictions
            })
            tot_logger.log_contradiction_detection(
                depth=state.get("current_depth", 0),
                conflict_count=len(contradictions),
                max_severity=max_severity,
                types_found=types_found,
            )
    except Exception:
        pass  # Logging is non-critical


def _emit_sse_contradiction_event(
    state: ToTState,
    contradictions: List[Dict],
) -> None:
    """Emit an SSE research_contradiction_update event into the reasoning trace.

    Args:
        state: Current ToT state.
        contradictions: List of detected contradiction dicts.
    """
    trace = state.setdefault("reasoning_trace", [])
    trace.append({
        "type": "research_contradiction_update",
        "conflict_count": len(contradictions),
        "max_severity": max(
            (c.get("severity", 0.0) for c in contradictions), default=0.0
        ),
        "types_found": list({
            c.get("type", "unknown") for c in contradictions
        }),
    })
