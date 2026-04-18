"""Filter node — evidence-based filtering and confidence scoring.

Uses the evidence_registry for source confidence lookup.
Items without evidence are heavily down-weighted.
No-evidence semantic facts are flagged for "needs verification".

红线3: Evidence enforcement — prevents LLM hallucination feedback loop.
"""

import logging

from app.memory.engine.state import MemoryState
from app.memory.engine.evidence_registry import get_source_confidence

logger = logging.getLogger(__name__)


async def evidence_filter(state: MemoryState) -> MemoryState:
    """Filter retrieved items by evidence quality.

    For each retrieved item (from any source):
    1. Check if it has evidence references
    2. Evaluate evidence confidence using the registry
    3. Down-weight items with no evidence
    4. Flag orphaned evidence as needing verification
    5. Separate unverified items from high-confidence ones
    """
    logs = state.get("logs", [])

    all_items = (
        state.get("retrieved_chunks", [])
        + state.get("retrieved_entities", [])
        + state.get("retrieved_graph", [])
        + state.get("retrieved_cases", [])
        + state.get("retrieved_procedures", [])
    )

    verified = []
    unverified = []
    warnings = []

    for item in all_items:
        evidence_list = item.get("evidence", [])

        if not evidence_list:
            # No evidence at all — heavy penalty
            item["weight"] = item.get("weight", 1.0) * 0.3
            item["evidence_confidence"] = 0.0
            item["needs_verification"] = True
            unverified.append(item)
            continue

        # Evaluate evidence using registry
        max_confidence = 0.0
        has_orphaned = False
        valid_sources = 0

        for ev in evidence_list:
            source_type = ev.get("source_type", "") if isinstance(ev, dict) else ""
            orphaned = ev.get("orphaned", False) if isinstance(ev, dict) else False

            if orphaned:
                has_orphaned = True
                continue

            # Get confidence from registry (extensible — new sources just add to registry)
            base_confidence = get_source_confidence(source_type)
            producer_confidence = ev.get("confidence", 1.0) if isinstance(ev, dict) else 1.0

            # Take the lower of registry vs producer confidence
            effective = min(base_confidence, producer_confidence)
            max_confidence = max(max_confidence, effective)
            valid_sources += 1

        if has_orphaned and valid_sources == 0:
            # All evidence is orphaned — severe penalty
            item["weight"] = item.get("weight", 1.0) * 0.2
            item["needs_verification"] = True
            unverified.append(item)
            warnings.append(f"All evidence orphaned for: {item.get('text', '')[:60]}")
            continue

        if max_confidence == 0:
            item["weight"] = item.get("weight", 1.0) * 0.3
            item["needs_verification"] = True
            unverified.append(item)
            continue

        item["evidence_confidence"] = max_confidence
        item["has_orphaned_evidence"] = has_orphaned

        # Scale weight by evidence confidence
        item["weight"] = item.get("weight", 1.0) * (0.5 + max_confidence * 0.5)

        verified.append(item)

    # Sort verified by weighted score
    verified.sort(key=lambda x: x.get("weight", 0) * x.get("evidence_confidence", 0), reverse=True)

    # Update state with filtered results
    state["retrieved_chunks"] = [i for i in verified if i.get("source") == "vector"]
    state["retrieved_entities"] = [i for i in verified if i.get("source") == "entity"]
    state["retrieved_graph"] = [i for i in verified if i.get("source") == "kg"]
    state["retrieved_cases"] = [i for i in verified if i.get("source") == "case"]
    state["retrieved_procedures"] = [i for i in verified if i.get("source") == "procedural"]

    # Store unverified separately for "needs confirmation" section
    state["unverified_items"] = unverified

    # Collect warnings
    if warnings:
        state.setdefault("warnings", []).extend(warnings)

    logs.append(
        f"[evidence_filter] verified={len(verified)}, "
        f"unverified={len(unverified)}, warnings={len(warnings)}"
    )
    state["logs"] = logs
    return state
