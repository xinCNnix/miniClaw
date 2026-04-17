"""Extract node — entity and fact extraction from chunks.

Uses the existing KGExtractor for triple extraction and extends to
produce structured facts/entities for all memory layers.
"""

import json
import logging

from app.memory.engine.state import MemoryState

logger = logging.getLogger(__name__)


async def extract_entities_facts(state: MemoryState) -> MemoryState:
    """Extract entities, facts, and relations from chunks.

    Processes chunks from the previous step (chunk_and_embed).
    Uses KGExtractor for triple extraction, then classifies each
    extracted item into memory layers (semantic, episodic, procedural).
    """
    chunks = state.get("chunks", [])
    if not chunks:
        return state

    logs = state.get("logs", [])
    session_id = state.get("session_id", "")

    extracted = {
        "entities": [],
        "facts": [],
        "relations": [],
    }

    # Collect all chunk texts for LLM extraction
    combined_text = "\n\n---\n\n".join(
        c.get("text", "") for c in chunks[:20]  # Limit to avoid token overflow
    )

    if len(combined_text.strip()) < 30:
        logs.append("[extract] Text too short for extraction, skipping")
        state["extracted"] = extracted
        state["logs"] = logs
        return state

    settings = _get_settings()

    # --- KG Triple extraction (if enabled) ---
    kg_triples = []
    if settings.enable_kg:
        kg_triples = await _extract_kg_triples(combined_text, logs)
        extracted["relations"] = [
            {
                "subject": t.subject,
                "subject_type": t.subject_type,
                "predicate": t.predicate,
                "object": t.object,
                "object_type": t.object_type,
                "confidence": t.confidence,
                "layer": "semantic",
            }
            for t in kg_triples
        ]

    # --- Fact extraction (LLM-based) ---
    facts = await _extract_facts(combined_text, logs)
    extracted["facts"] = facts

    # --- Entity extraction from facts and triples ---
    entities = _collect_entities(facts, kg_triples)
    extracted["entities"] = entities

    # Build scored candidates from extracted facts
    scored_candidates = []
    for fact in facts:
        scored_candidates.append({
            "layer": fact.get("layer", "semantic"),
            "text": fact.get("text", ""),
            "confidence": fact.get("confidence", 0.5),
            "evidence": fact.get("evidence", []),
            "entity_id": fact.get("entity_id"),
            "entity_type": fact.get("entity_type", "concept"),
            "entity_name": fact.get("entity_name", ""),
        })

    # Add KG relations as semantic facts
    for rel in extracted["relations"]:
        text = f"{rel['subject']} {rel['predicate']} {rel['object']}"
        scored_candidates.append({
            "layer": "semantic",
            "text": text,
            "confidence": rel["confidence"],
            "evidence": [],
            "entity_name": rel["subject"],
        })

    logs.append(
        f"[extract] facts={len(facts)}, kg_triples={len(kg_triples)}, "
        f"entities={len(entities)}, candidates={len(scored_candidates)}"
    )

    state["extracted"] = extracted
    state["scored"] = scored_candidates  # Pass to score node
    state["logs"] = logs
    return state


def _get_settings():
    from app.config import get_settings
    return get_settings()


async def _extract_kg_triples(text: str, logs: list) -> list:
    """Extract KG triples using the existing KGExtractor."""
    try:
        from app.memory.kg.extractor import KGExtractor
        extractor = KGExtractor()
        triples = await extractor.extract_triples(text)
        return triples
    except Exception as e:
        logs.append(f"[extract] KG extraction failed: {e}")
        logger.warning(f"KG triple extraction failed: {e}")
        return []


async def _extract_facts(text: str, logs: list) -> list[dict]:
    """Extract structured facts from text using LLM.

    Returns a list of dicts with: text, confidence, layer, evidence, entity info.
    """
    try:
        from app.core.llm import get_default_llm
        from app.memory.engine.evidence_registry import MemoryEvidence
    except Exception as e:
        logs.append(f"[extract] LLM import failed: {e}")
        return []

    prompt = """Extract key facts from the following text. Return a JSON array of objects with:
- "text": the fact in natural language (string)
- "confidence": 0.0 to 1.0 how certain this fact is
- "layer": one of "semantic" (factual knowledge), "procedural" (how-to steps), "episodic" (event description)
- "entity_name": the main entity this fact is about (if applicable)

Only extract facts that are:
1. Non-trivial (not greetings, acknowledgments)
2. Specific (not vague generalities)
3. Grounded in the text (not inferred beyond what's stated)

Return empty array if no meaningful facts found.

Text:
""" + text[:3000]

    try:
        llm = get_default_llm()
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = response.content.strip()

        # Strip markdown fences
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        items = json.loads(content)
        if not isinstance(items, list):
            return []

        facts = []
        for item in items[:20]:  # Cap at 20 facts
            fact_text = item.get("text", "").strip()
            if not fact_text or len(fact_text) < 5:
                continue

            facts.append({
                "text": fact_text,
                "confidence": min(1.0, max(0.0, float(item.get("confidence", 0.5)))),
                "layer": item.get("layer", "semantic"),
                "entity_name": item.get("entity_name", ""),
                "entity_type": "concept",
                "evidence": [
                    MemoryEvidence(
                        source_type="conversation",
                        ref_id="extracted",
                        summary=fact_text[:100],
                        confidence=0.8,
                    ).model_dump()
                ],
            })

        return facts

    except Exception as e:
        logs.append(f"[extract] Fact extraction failed: {e}")
        logger.warning(f"Fact extraction failed: {e}")
        return []


def _collect_entities(facts: list[dict], kg_triples: list) -> list[dict]:
    """Collect unique entities from facts and KG triples."""
    seen = set()
    entities = []

    for fact in facts:
        name = fact.get("entity_name", "")
        if name and name not in seen:
            seen.add(name)
            entities.append({
                "entity_name": name,
                "entity_type": fact.get("entity_type", "concept"),
                "summary": fact.get("text", "")[:200],
            })

    for triple in kg_triples:
        for field in ("subject", "object"):
            name = getattr(triple, field, "")
            if name and name not in seen:
                seen.add(name)
                entities.append({
                    "entity_name": name,
                    "entity_type": getattr(triple, f"{field}_type", "Other"),
                    "summary": "",
                })

    return entities
