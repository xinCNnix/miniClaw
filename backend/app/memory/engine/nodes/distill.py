"""Distill node — summarization and consolidation.

Takes extracted entities/facts and distills them into consolidated
summaries, merging with existing knowledge.
"""

import json
import logging

from app.memory.engine.state import MemoryState

logger = logging.getLogger(__name__)


async def distill_summaries(state: MemoryState) -> MemoryState:
    """Distill extracted data into summaries and updates.

    Processes the scored candidates from extract step:
    - Groups facts by entity/topic
    - Consolidates duplicate/similar facts
    - Enriches each candidate with distilled summary
    """
    scored = state.get("scored", [])
    if not scored:
        return state

    logs = state.get("logs", [])
    distilled_updates = []

    # Group by entity/topic for consolidation
    entity_groups: dict[str, list] = {}
    ungrouped = []

    for item in scored:
        entity_name = item.get("entity_name", "")
        if entity_name:
            entity_groups.setdefault(entity_name, []).append(item)
        else:
            ungrouped.append(item)

    # Consolidate entity groups
    for entity_name, facts in entity_groups.items():
        if len(facts) == 1:
            distilled_updates.append(facts[0])
            continue

        # Multiple facts about same entity — consolidate
        consolidated = _consolidate_facts(entity_name, facts, logs)
        distilled_updates.append(consolidated)

    # Add ungrouped items as-is
    distilled_updates.extend(ungrouped)

    # Merge overlapping semantic facts
    distilled_updates = _merge_overlapping(distilled_updates, logs)

    logs.append(
        f"[distill] input={len(scored)}, output={len(distilled_updates)}, "
        f"entity_groups={len(entity_groups)}"
    )

    state["scored"] = distilled_updates
    state["distilled"] = {
        "updates": distilled_updates,
        "entity_count": len(entity_groups),
    }
    state["logs"] = logs
    return state


def _consolidate_facts(entity_name: str, facts: list[dict], logs: list) -> dict:
    """Consolidate multiple facts about the same entity into one."""
    # Take highest-confidence fact as base
    facts_sorted = sorted(facts, key=lambda f: f.get("confidence", 0), reverse=True)
    base = facts_sorted[0].copy()

    # Merge evidence from all facts
    all_evidence = []
    for f in facts_sorted:
        for ev in f.get("evidence", []):
            all_evidence.append(ev)

    # Deduplicate evidence by ref_id
    seen_refs = set()
    unique_evidence = []
    for ev in all_evidence:
        ref = ev.get("ref_id", "")
        if ref not in seen_refs:
            seen_refs.add(ref)
            unique_evidence.append(ev)

    base["evidence"] = unique_evidence

    # If multiple facts, combine text
    if len(facts_sorted) > 1:
        additional = [f.get("text", "") for f in facts_sorted[1:] if f.get("text") != base.get("text")]
        if additional:
            base["text"] = base.get("text", "") + " | " + "; ".join(additional[:3])

    base["confidence"] = max(f.get("confidence", 0) for f in facts)
    base["entity_name"] = entity_name

    return base


def _merge_overlapping(items: list[dict], logs: list) -> list[dict]:
    """Remove near-duplicate items using text overlap."""
    if len(items) <= 1:
        return items

    merged = []
    seen_texts = []

    for item in items:
        text = item.get("text", "").lower().strip()
        if not text:
            merged.append(item)
            continue

        # Check overlap with already-merged items
        is_dup = False
        text_words = set(text.split())

        for seen_text in seen_texts:
            seen_words = set(seen_text.split())
            if not text_words or not seen_words:
                continue

            # Jaccard similarity
            intersection = text_words & seen_words
            union = text_words | seen_words
            similarity = len(intersection) / len(union) if union else 0

            if similarity > 0.8:
                is_dup = True
                break

        if is_dup:
            continue

        seen_texts.append(text)
        merged.append(item)

    removed = len(items) - len(merged)
    if removed > 0:
        logs.append(f"[distill] Merged {removed} overlapping facts")

    return merged
