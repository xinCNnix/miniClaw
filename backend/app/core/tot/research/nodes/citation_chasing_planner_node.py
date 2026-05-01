"""
Citation Chasing Planner Node

Plans which citations and references to chase for primary sources.
Uses an LLM with an analysis-level prompt to identify high-value
citation targets based on current evidence, coverage gaps, and
known contradictions.

Citation chasing is skipped when:
- Task mode is not "research"
- Citation chase budget is exhausted
- Coverage score is already sufficient (>= 0.7)

The planner decides whether to chase citations and produces a list
of target queries and source types to pursue.
"""

import json
import logging
import re
import time
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.tot.state import ToTState
from app.core.tot.research.evidence_utils import format_evidence_for_prompt
from app.core.tot.research.prompts import (
    get_citation_chasing_prompt,
    parse_json_output,
)
from app.core.tot.prompt_composer import compose_system_prompt

logger = logging.getLogger(__name__)

# Coverage threshold above which citation chasing is considered unnecessary.
_COVERAGE_SUFFICIENT_THRESHOLD = 0.7


async def citation_chasing_planner_node(state: ToTState) -> Dict:
    """Plan which citations to chase for primary sources.

    Evaluates whether citation chasing is worthwhile based on the
    current coverage score and remaining budget. If worthwhile,
    uses the LLM to identify specific citation targets to pursue.

    For non-research task modes, returns an empty dict (skipped).

    Args:
        state: Current ToT state with evidence, coverage, and
            citation chase budget information.

    Returns:
        Dict with citation_targets if chasing is warranted, or
        an empty dict if skipping.
    """
    task_mode = state.get("task_mode", "standard")

    # Skip for non-research modes
    if task_mode != "research":
        logger.debug(
            "citation_chasing_planner_node: non-research mode, skipping"
        )
        return {}

    # Check budget
    chase_rounds = int(state.get("citation_chase_rounds", 0))
    chase_max = int(state.get("citation_chase_max", 2))
    if chase_rounds >= chase_max:
        logger.info(
            f"citation_chasing_planner_node: budget exhausted "
            f"({chase_rounds}/{chase_max}), skipping"
        )
        return {}

    # Check coverage: skip if already sufficient
    coverage_map = state.get("coverage_map") or {}
    coverage_score = float(coverage_map.get("coverage_score", 0.0))
    if coverage_score >= _COVERAGE_SUFFICIENT_THRESHOLD:
        logger.info(
            f"citation_chasing_planner_node: coverage sufficient "
            f"({coverage_score:.2f} >= {_COVERAGE_SUFFICIENT_THRESHOLD}), skipping"
        )
        return {}

    # Proceed with LLM planning
    user_query = state.get("user_query", "")
    evidence_store = state.get("evidence_store") or []
    contradictions = state.get("contradictions") or []

    # Format evidence
    evidence_summary = format_evidence_for_prompt(evidence_store)

    # Serialize coverage and contradictions for the prompt
    coverage_map_str = json.dumps(coverage_map, ensure_ascii=False, indent=2) if coverage_map else "{}"
    contradictions_str = json.dumps(contradictions, ensure_ascii=False, indent=2) if contradictions else "[]"

    # Build the citation chasing prompt
    user_prompt = get_citation_chasing_prompt(
        user_query=user_query,
        coverage_map=coverage_map_str,
        contradictions=contradictions_str,
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
            f"citation_chasing_planner_node: LLM response in {elapsed_ms:.0f}ms, "
            f"length={len(raw_output)}"
        )

    except Exception as exc:
        logger.error(f"citation_chasing_planner_node: LLM call failed: {exc}")
        return {}

    # Parse JSON response
    parsed = parse_json_output(raw_output)

    if not parsed:
        logger.warning(
            "citation_chasing_planner_node: failed to parse LLM output"
        )
        logger.debug(
            "citation_chasing_planner_node: raw LLM output (first 500 chars): %s",
            raw_output[:500],
        )
        # Fallback: try to extract URLs or text clues from raw output
        targets = _extract_targets_from_text(raw_output)
        if targets:
            logger.info(
                "citation_chasing_planner_node: extracted %d targets from raw text",
                len(targets),
            )
            _log_citation_chase(state, targets)
            return {"citation_targets": targets}
        return {}

    # Check should_chase flag
    should_chase = parsed.get("should_chase", False)
    if not should_chase:
        logger.info("citation_chasing_planner_node: LLM decided not to chase")
        return {}

    # Extract and normalize targets
    targets = _normalize_targets(parsed)

    if not targets:
        logger.info("citation_chasing_planner_node: no valid targets after normalization")
        logger.debug(
            "citation_chasing_planner_node: parsed JSON keys=%s",
            list(parsed.keys()),
        )
        # Fallback: try raw text extraction
        targets = _extract_targets_from_text(raw_output)
        if targets:
            logger.info(
                "citation_chasing_planner_node: fallback extracted %d targets",
                len(targets),
            )
        else:
            return {}

    # Log via ToTExecutionLogger
    _log_citation_chase(state, targets)

    logger.info(
        f"citation_chasing_planner_node: planned {len(targets)} citation targets "
        f"(round {chase_rounds + 1}/{chase_max})"
    )

    return {
        "citation_targets": targets,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_targets(parsed: Dict) -> List[Dict]:
    """Normalize citation targets from parsed LLM output.

    Handles different output formats: "targets" key, "citation_targets"
    key, or "_array" wrapper.

    Args:
        parsed: The parsed JSON dict from the LLM.

    Returns:
        List of normalized citation target dicts, each containing
        at minimum "query" and "source_type" fields.
    """
    raw_targets = (
        parsed.get("targets")
        or parsed.get("citation_targets")
        or parsed.get("chase_targets")
    )

    # Handle array-wrapped output
    if raw_targets is None and "_array" in parsed:
        raw_targets = parsed["_array"]

    if not raw_targets or not isinstance(raw_targets, list):
        return []

    normalized: List[Dict] = []
    for target in raw_targets:
        if isinstance(target, str):
            # Simple string query
            normalized.append({
                "query": target,
                "source_type": "auto",
                "reason": "",
                "priority": 0.5,
            })
        elif isinstance(target, dict):
            query = target.get("query", target.get("search_query", ""))
            if not query:
                continue
            normalized.append({
                "query": query,
                "source_type": target.get("source_type", "auto"),
                "reason": target.get("reason", ""),
                "priority": float(target.get("priority", 0.5)),
            })

    # Sort by priority descending
    normalized.sort(key=lambda t: t.get("priority", 0.5), reverse=True)

    # Cap at 5 targets per round to avoid excessive fetching
    return normalized[:5]


def _extract_targets_from_text(text: str) -> List[Dict]:
    """Fallback: extract citation targets from unstructured LLM output.

    Tries URL extraction, numbered list parsing, and markdown link parsing.
    If no structured data is found, returns a single text-clue entry.

    Args:
        text: Raw LLM output text.

    Returns:
        List of citation target dicts.
    """
    targets: List[Dict] = []

    # 1. Extract URLs (arxiv, doi, generic)
    url_pattern = re.compile(
        r'https?://(?:arxiv\.org/(?:abs|pdf)/\d+\.\d+|doi\.org/[^\s)>\]]+|[^\s)>\]]+(?:\.pdf|\.html))',
        re.IGNORECASE,
    )
    for match in url_pattern.finditer(text):
        url = match.group(0)
        targets.append({
            "query": url,
            "source_type": "url",
            "reason": "Extracted from LLM output",
            "priority": 0.7,
        })

    # 2. Extract numbered list items (1. query text)
    list_pattern = re.compile(r'(?:^|\n)\s*\d+\.\s*(.+?)(?:\n|$)', re.MULTILINE)
    for match in list_pattern.finditer(text):
        item = match.group(1).strip()
        if item and not item.startswith("http") and len(item) > 5:
            targets.append({
                "query": item,
                "source_type": "text_clue",
                "reason": "Extracted from numbered list",
                "priority": 0.5,
            })

    # 3. Extract markdown links [text](url)
    md_link_pattern = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')
    for match in md_link_pattern.finditer(text):
        label, url = match.group(1), match.group(2)
        targets.append({
            "query": url,
            "source_type": "url",
            "reason": f"Markdown link: {label}",
            "priority": 0.7,
        })

    # Deduplicate by query
    seen = set()
    unique = []
    for t in targets:
        if t["query"] not in seen:
            seen.add(t["query"])
            unique.append(t)

    if not unique and len(text.strip()) > 20:
        # No structured data found — pass as text clue
        unique.append({
            "query": text.strip()[:500],
            "source_type": "text_clue",
            "reason": "Unparseable LLM output passed as text clue",
            "priority": 0.3,
        })

    return unique[:5]


def _log_citation_chase(state: ToTState, targets: List[Dict]) -> None:
    """Log citation chase planning via ToTExecutionLogger if available.

    Args:
        state: Current ToT state.
        targets: List of planned citation targets.
    """
    try:
        tot_logger = state.get("tot_logger")
        if tot_logger is not None:
            chase_max = int(state.get("citation_chase_max", 2))
            chase_rounds = int(state.get("citation_chase_rounds", 0))
            tot_logger.log_citation_chasing(
                depth=state.get("current_depth", 0),
                targets_count=len(targets),
                fetched_count=0,  # Fetching happens in the next node
                budget_remaining=chase_max - chase_rounds - 1,
            )
    except Exception:
        pass  # Logging is non-critical
