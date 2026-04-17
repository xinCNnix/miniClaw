"""
Extractor Node

Extracts structured EvidenceItems from raw_sources using the
deep_source_extractor skill. Runs extractions concurrently with
a semaphore for rate control, deduplicates results, and appends
to the evidence_store.

For non-research task modes, performs a lightweight passthrough
that copies raw source text into the evidence_store without
LLM-based extraction.
"""

import asyncio
import logging
import time
from typing import Dict, List

from app.core.tot.state import ToTState
from app.core.tot.research.evidence_utils import content_hash, dedup_evidence

logger = logging.getLogger(__name__)


async def extractor_node(state: ToTState) -> Dict:
    """Extract structured EvidenceItems from raw_sources.

    Uses the deep_source_extractor skill to convert raw source text
    into structured evidence with claims, metrics, and reliability
    scores. Results are deduplicated against the existing
    evidence_store before being appended.

    For non-research task modes, performs a lightweight passthrough
    that copies raw source text into the evidence_store without
    LLM-based extraction.

    Args:
        state: Current ToT state containing raw_sources and
            evidence_store.

    Returns:
        Dict with updated evidence_store and emptied raw_sources.
    """
    task_mode = state.get("task_mode", "standard")

    # Passthrough for non-research modes
    if task_mode != "research":
        return _passthrough(state)

    raw_sources: List[Dict] = state.get("raw_sources") or []
    if not raw_sources:
        logger.debug("extractor_node: no raw_sources to process")
        return {"raw_sources": []}

    existing_store: List[Dict] = state.get("evidence_store") or []
    existing_ids = {item.get("source_id") for item in existing_store if item.get("source_id")}

    llm = state["llm"]
    user_query = state["user_query"]

    # Track which source hashes we have already extracted in this batch
    batch_hash_cache: Dict[str, Dict] = {}

    extracted_items: List[Dict] = []
    sem = asyncio.Semaphore(3)

    async def extract_one(source: Dict) -> List[Dict]:
        """Extract evidence from a single source with concurrency control."""
        source_text = source.get("source_text", "")
        source_id = source.get("source_id", f"anon_{content_hash(source_text)[:8]}")
        source_type = source.get("source_type", "unknown")

        # Dedup: skip if source_id already in the existing store
        if source_id in existing_ids:
            logger.debug(f"extractor_node: skipping duplicate source {source_id}")
            return []

        # Batch-level hash dedup (same content seen twice in this batch)
        text_hash = content_hash(source_text)
        if text_hash in batch_hash_cache:
            logger.debug(f"extractor_node: batch cache hit for {source_id}")
            return batch_hash_cache[text_hash]

        async with sem:
            try:
                from app.skills.loader import execute_skill

                is_citation_chase = source_type == "citation_chase"

                result = await execute_skill(
                    "deep_source_extractor",
                    inputs={
                        "source_id": source_id,
                        "source_text": source_text,
                        "source_type": source_type,
                        "user_query": user_query,
                    },
                    context={"llm": llm},
                )

                extracted_json = result.get("extracted_json", {})
                items = _normalize_extracted(extracted_json, source_id, source_type)

                # Relaxed validation for citation chase sources: allow fewer claims
                if is_citation_chase:
                    items = [item for item in items if len(item.get("claim", "")) >= 10]
                else:
                    # Standard validation: require at least a meaningful claim
                    items = [
                        item for item in items
                        if item.get("claim") and len(item.get("claim", "")) >= 10
                    ]

                batch_hash_cache[text_hash] = items
                return items

            except Exception as exc:
                logger.warning(
                    f"extractor_node: failed to extract from {source_id}: {exc}"
                )
                return []

    start = time.monotonic()

    # Run all extractions concurrently
    all_results = await asyncio.gather(
        *[extract_one(src) for src in raw_sources],
        return_exceptions=True,
    )

    for result in all_results:
        if isinstance(result, Exception):
            logger.warning(f"extractor_node: extraction task raised {result}")
            continue
        if isinstance(result, list):
            extracted_items.extend(result)

    # Dedup combined store
    combined = existing_store + extracted_items
    deduped = dedup_evidence(combined)

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        f"extractor_node: extracted {len(extracted_items)} new items "
        f"from {len(raw_sources)} sources in {elapsed_ms:.0f}ms, "
        f"total store size={len(deduped)}"
    )

    # Log via ToTExecutionLogger if available
    _log_extraction(state, extracted_items, elapsed_ms)

    return {
        "evidence_store": deduped,
        "raw_sources": [],
    }


# ---------------------------------------------------------------------------
# Passthrough for non-research modes
# ---------------------------------------------------------------------------


def _passthrough(state: ToTState) -> Dict:
    """Copy raw_sources to evidence_store without LLM extraction.

    Creates simple EvidenceItem-like dicts from raw source text,
    suitable for standard-mode operation where deep extraction is
    not needed.

    Args:
        state: Current ToT state.

    Returns:
        Dict with updated evidence_store and emptied raw_sources.
    """
    raw_sources: List[Dict] = state.get("raw_sources") or []
    existing_store: List[Dict] = state.get("evidence_store") or []

    passthrough_items: List[Dict] = []
    for src in raw_sources:
        source_text = src.get("source_text", "")
        source_id = src.get("source_id", f"passthrough_{content_hash(source_text)[:8]}")
        passthrough_items.append({
            "source_id": source_id,
            "source_type": src.get("source_type", "unknown"),
            "title": src.get("title", ""),
            "url": src.get("url", ""),
            "quote": source_text[:500],
            "claim": source_text[:300] if source_text else "",
            "numbers": [],
            "reliability": 0.5,
            "relevance": 0.5,
        })

    combined = existing_store + passthrough_items
    deduped = dedup_evidence(combined)

    return {
        "evidence_store": deduped,
        "raw_sources": [],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_extracted(
    extracted_json: Dict,
    source_id: str,
    source_type: str,
) -> List[Dict]:
    """Normalize the deep_source_extractor output into a flat list of dicts.

    The skill may return either a single evidence object or a list of
    evidence items. This function handles both cases and ensures each
    item has required fields with sensible defaults.

    Args:
        extracted_json: Raw output from deep_source_extractor.
        source_id: The source identifier to tag items with.
        source_type: The type of the source.

    Returns:
        List of normalized evidence item dicts.
    """
    if not extracted_json:
        return []

    # If the output has a "key_claims" list, build items from each claim
    if isinstance(extracted_json, dict):
        items = extracted_json.get("items") or extracted_json.get("key_claims")
        if items and isinstance(items, list):
            result: List[Dict] = []
            for idx, item in enumerate(items):
                if isinstance(item, str):
                    result.append({
                        "source_id": f"{source_id}_claim_{idx}",
                        "source_type": source_type,
                        "title": extracted_json.get("title", ""),
                        "url": extracted_json.get("url", ""),
                        "quote": item[:500],
                        "claim": item,
                        "numbers": [],
                        "reliability": float(extracted_json.get("reliability", 0.5)),
                        "relevance": float(extracted_json.get("relevance", 0.5)),
                    })
                elif isinstance(item, dict):
                    result.append({
                        "source_id": item.get("source_id", f"{source_id}_claim_{idx}"),
                        "source_type": item.get("source_type", source_type),
                        "title": item.get("title", extracted_json.get("title", "")),
                        "url": item.get("url", extracted_json.get("url", "")),
                        "quote": item.get("quote", item.get("claim", ""))[:500],
                        "claim": item.get("claim", ""),
                        "numbers": item.get("numbers", []),
                        "reliability": float(item.get("reliability", extracted_json.get("reliability", 0.5))),
                        "relevance": float(item.get("relevance", extracted_json.get("relevance", 0.5))),
                    })
            return result

        # Single-item output (no items/key_claims key)
        claim = extracted_json.get("claim", extracted_json.get("summary", ""))
        if claim:
            return [{
                "source_id": extracted_json.get("source_id", source_id),
                "source_type": extracted_json.get("source_type", source_type),
                "title": extracted_json.get("title", ""),
                "url": extracted_json.get("url", ""),
                "quote": extracted_json.get("quote", claim)[:500],
                "claim": claim,
                "numbers": extracted_json.get("numbers", []),
                "reliability": float(extracted_json.get("reliability", 0.5)),
                "relevance": float(extracted_json.get("relevance", 0.5)),
            }]

    # List output
    if isinstance(extracted_json, list):
        result = []
        for idx, item in enumerate(extracted_json):
            if isinstance(item, dict):
                claim = item.get("claim", item.get("summary", ""))
                if claim:
                    result.append({
                        "source_id": item.get("source_id", f"{source_id}_claim_{idx}"),
                        "source_type": item.get("source_type", source_type),
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "quote": item.get("quote", claim)[:500],
                        "claim": claim,
                        "numbers": item.get("numbers", []),
                        "reliability": float(item.get("reliability", 0.5)),
                        "relevance": float(item.get("relevance", 0.5)),
                    })
        return result

    return []


def _log_extraction(
    state: ToTState,
    extracted_items: List[Dict],
    elapsed_ms: float,
) -> None:
    """Log extraction results via ToTExecutionLogger if available.

    The logger is stored in the reasoning_trace as a special marker
    dict with type "tot_logger_ref". If not found, logging is skipped.

    Args:
        state: Current ToT state.
        extracted_items: List of extracted evidence items.
        elapsed_ms: Elapsed time in milliseconds.
    """
    try:
        tot_logger = state.get("tot_logger")
        if tot_logger is not None:
            depth = state.get("current_depth", 0)
            for item in extracted_items:
                tot_logger.log_evidence_extraction(
                    depth=depth,
                    source_id=item.get("source_id", "unknown"),
                    source_type=item.get("source_type", "unknown"),
                    claim_count=1,
                    number_count=len(item.get("numbers", [])),
                    reliability=item.get("reliability", 0.5),
                    duration_ms=elapsed_ms / max(len(extracted_items), 1),
                )
    except Exception:
        pass  # Logging is non-critical
