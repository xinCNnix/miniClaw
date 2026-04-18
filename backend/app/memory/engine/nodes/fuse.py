"""Fuse node — merge, rerank, and pack context into MemoryContextPack.

Takes all filtered retrieval results, applies weighted reranking,
truncates to token budget, and formats as structured MemoryContextPack
for injection into the LLM system prompt.
"""

import logging
import time

from app.memory.engine.state import MemoryState

logger = logging.getLogger(__name__)

# Source type weights for reranking
_SOURCE_WEIGHTS = {
    "wiki": 0.50,
    "kg": 0.30,
    "entity": 0.25,
    "case": 0.15,
    "procedural": 0.15,
    "vector": 0.05,
}

# Approximate chars per token
_CHARS_PER_TOKEN = 4
_MAX_CONTEXT_TOKENS = 1500  # Matches WIKI_MEMORY budget in config


async def fuse_and_pack_context(state: MemoryState) -> MemoryState:
    """Merge all retrieval results into a single MemoryContextPack string.

    The output follows the structured format:
    - Entity Profiles
    - High-Confidence Facts (with evidence)
    - Relevant Past Episodes
    - Relevant Tool Trajectories
    - Suggested Procedures
    - Warnings / Conflicts
    - Unverified (needs confirmation)
    """
    logs = state.get("logs", [])

    # Collect all items with their weighted scores
    all_items = []

    for item in state.get("retrieved_entities", []):
        item["source_type"] = "entity"
        all_items.append(item)

    for item in state.get("retrieved_graph", []):
        item["source_type"] = "kg"
        all_items.append(item)

    for item in state.get("retrieved_cases", []):
        item["source_type"] = "case"
        all_items.append(item)

    for item in state.get("retrieved_procedures", []):
        item["source_type"] = "procedural"
        all_items.append(item)

    for item in state.get("retrieved_chunks", []):
        item["source_type"] = "vector"
        all_items.append(item)

    # Calculate weighted score for each item
    for item in all_items:
        source_weight = _SOURCE_WEIGHTS.get(item.get("source_type", ""), 0.05)
        evidence_conf = item.get("evidence_confidence", 0.5)
        base_weight = item.get("weight", 1.0)
        item["weighted_score"] = source_weight * evidence_conf * base_weight

    # Sort by weighted score
    all_items.sort(key=lambda x: x.get("weighted_score", 0), reverse=True)

    # Build MemoryContextPack sections
    sections = []
    char_budget = _MAX_CONTEXT_TOKENS * _CHARS_PER_TOKEN

    # 1. Entity Profiles
    entities = [i for i in all_items if i.get("source_type") == "entity"]
    if entities:
        lines = ["## Entity Profiles"]
        for e in entities[:5]:
            name = e.get("name", e.get("text", "")[:40])
            summary = e.get("summary", e.get("text", ""))[:100]
            conf = e.get("evidence_confidence", e.get("confidence", 0))
            lines.append(f"- [{name}] summary: {summary} (conf={conf:.2f})")
        sections.append("\n".join(lines))

    # 2. High-Confidence Facts (with evidence)
    facts = [i for i in all_items if i.get("source_type") in ("kg", "wiki")]
    if facts:
        lines = ["## High-Confidence Facts (with evidence)"]
        for f in facts[:8]:
            text = f.get("text", f.get("summary", ""))[:120]
            evidence = f.get("evidence", [])
            if evidence:
                sources = []
                for ev in evidence[:2]:
                    if isinstance(ev, dict):
                        st = ev.get("source_type", "?")
                        rid = ev.get("ref_id", "?")
                        sources.append(f"{st}:{rid[:20]}")
                source_str = ", ".join(sources)
                conf = f.get("evidence_confidence", 0.5)
                lines.append(f"- {text} (sources: [{source_str}], confidence={conf:.2f})")
            else:
                lines.append(f"- {text}")
        sections.append("\n".join(lines))

    # 3. Relevant Past Episodes
    episodes = [i for i in all_items if i.get("source_type") == "vector"]
    if episodes:
        lines = ["## Relevant Past Episodes"]
        for ep in episodes[:3]:
            content = ep.get("text", ep.get("content", ""))[:150]
            ts = ep.get("ts", "")
            lines.append(f"- (ts={ts}) {content}")
        sections.append("\n".join(lines))

    # 4. Relevant Tool Trajectories (from cases)
    cases = [i for i in all_items if i.get("source_type") == "case"]
    if cases:
        lines = ["## Relevant Tool Trajectories"]
        for c in cases[:3]:
            title = c.get("title", c.get("text", ""))[:80]
            score = c.get("success_score", c.get("weight", 0))
            result = c.get("result", "success")[:40]
            lines.append(f"- Task: {title} → outcome: {result} (score={score:.2f})")
        sections.append("\n".join(lines))

    # 5. Suggested Procedures
    procs = [i for i in all_items if i.get("source_type") == "procedural"]
    if procs:
        lines = ["## Suggested Procedures"]
        for p in procs[:3]:
            name = p.get("name", p.get("text", ""))[:60]
            steps = p.get("steps", [])
            rate = p.get("success_rate", 0)
            steps_str = " → ".join(steps[:3]) if steps else ""
            lines.append(f"- {name}: {steps_str} (success_rate={rate:.2f})")
        sections.append("\n".join(lines))

    # 6. Warnings / Conflicts
    warnings = state.get("warnings", [])
    if warnings:
        lines = ["## Warnings / Conflicts"]
        for w in warnings[:5]:
            lines.append(f"- {str(w)[:100]}")
        sections.append("\n".join(lines))

    # 7. Unverified (needs confirmation)
    unverified = state.get("unverified_items", [])
    if unverified:
        lines = ["## Unverified (needs confirmation)"]
        for u in unverified[:5]:
            text = u.get("text", "")[:100]
            lines.append(f"- {text} (no reliable evidence)")
        sections.append("\n".join(lines))

    # Assemble full context pack
    if sections:
        context = "# MEMORY CONTEXT PACK\n\n" + "\n\n".join(sections)
    else:
        context = ""

    # Truncate to budget
    if len(context) > char_budget:
        context = context[:char_budget] + "\n\n...[truncated]"

    state["memory_context"] = context
    logs.append(
        f"[fuse_and_pack_context] "
        f"items={len(all_items)}, sections={len(sections)}, "
        f"context_len={len(context)}"
    )
    state["logs"] = logs
    return state
