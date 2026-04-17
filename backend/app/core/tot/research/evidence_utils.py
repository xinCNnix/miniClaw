"""
Evidence Utility Functions for ToT Research Enhancement.

Provides hashing, formatting, and deduplication utilities for the
evidence_store used during deep research tasks.
"""

import hashlib
from typing import List, Dict


def content_hash(source_text: str) -> str:
    """Compute a fast hash of source text for deduplication.

    Uses the first 2KB of text combined with total length to produce
    a deterministic SHA-256 hex digest. This avoids hashing very large
    documents in full while still being collision-resistant in practice.

    Args:
        source_text: The raw text content to hash.

    Returns:
        A 16-character hex digest string.
    """
    head = source_text[:2048]
    length = len(source_text)
    payload = f"{head}|len={length}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _estimate_tokens(text: str) -> int:
    """Estimate token count for a mixed-language string.

    Uses a simple heuristic: ~1 token per 4 characters for English
    and ~1 token per 2 characters for Chinese, taking the maximum
    of both estimates.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    char_count = len(text)

    # Count CJK characters (Chinese, Japanese, Korean)
    cjk_count = sum(
        1
        for ch in text
        if (
            "\u4e00" <= ch <= "\u9fff"
            or "\u3040" <= ch <= "\u309f"   # Hiragana
            or "\u30a0" <= ch <= "\u30ff"   # Katakana
            or "\uac00" <= ch <= "\ud7af"   # Hangul
        )
    )

    # English-like estimate: 1 token per 4 chars
    english_estimate = char_count / 4.0

    # CJK estimate: 1 token per 2 chars for CJK chars, rest at English rate
    non_cjk_chars = char_count - cjk_count
    cjk_estimate = (cjk_count / 2.0) + (non_cjk_chars / 4.0)

    return max(int(english_estimate), int(cjk_estimate), 1)


def format_evidence_for_prompt(
    evidence_store: List[Dict],
    token_budget: int = 8000,
) -> str:
    """Format evidence_store as prompt-friendly text within a token budget.

    Truncation strategy:
      1. Each EvidenceItem is rendered with key fields only
         (claim, numbers, reliability, source_id).
      2. Items are sorted by relevance * reliability in descending order.
      3. Items are accumulated until the token budget is exhausted.
      4. A summary line is appended indicating total and omitted counts.

    Args:
        evidence_store: List of EvidenceItem dicts from ToTState.
        token_budget: Maximum estimated tokens for the output.

    Returns:
        A formatted string ready to be injected into an LLM prompt.
    """
    if not evidence_store:
        return "（暂无证据）"

    # Sort by relevance * reliability descending
    scored_items: List[Dict] = []
    for item in evidence_store:
        relevance = float(item.get("relevance", 0.5))
        reliability = float(item.get("reliability", 0.5))
        score = relevance * reliability
        scored_items.append((score, item))

    scored_items.sort(key=lambda pair: pair[0], reverse=True)

    # Format each item
    lines: List[str] = []
    used_tokens = 0
    included_count = 0

    for score, item in scored_items:
        source_id = item.get("source_id", "unknown")
        source_type = item.get("source_type", "unknown")
        claim = item.get("claim", "")
        numbers = item.get("numbers", [])
        reliability = item.get("reliability", 0.5)

        # Build compact representation
        parts: List[str] = [f"[{source_id}|{source_type}]"]
        if claim:
            parts.append(f"Claim: {claim}")
        if numbers:
            num_strs: List[str] = []
            for n in numbers:
                if isinstance(n, dict):
                    metric = n.get("metric", "")
                    value = n.get("value", "")
                    dataset = n.get("dataset", "")
                    if metric and value:
                        num_strs.append(f"{metric}={value}" + (f" ({dataset})" if dataset else ""))
                else:
                    num_strs.append(str(n))
            if num_strs:
                parts.append(f"Metrics: {', '.join(num_strs)}")
        parts.append(f"Reliability: {reliability:.2f}")

        line = " | ".join(parts)
        line_tokens = _estimate_tokens(line)

        # Reserve 120 tokens for the summary footer
        if used_tokens + line_tokens > token_budget - 120:
            break

        lines.append(line)
        used_tokens += line_tokens
        included_count += 1

    total_count = len(evidence_store)
    omitted_count = total_count - included_count

    # Build footer
    footer_parts: List[str] = [f"共 {total_count} 条证据"]
    if omitted_count > 0:
        footer_parts.append(f"已省略 {omitted_count} 条低优先级证据")
    footer = "（" + "，".join(footer_parts) + "）"

    if not lines:
        return footer

    return "\n".join(lines) + "\n" + footer


def dedup_evidence(evidence_store: List[Dict]) -> List[Dict]:
    """Deduplicate evidence items by source_id hash.

    When duplicate source_ids are found, the item with the higher
    relevance * reliability score is retained.

    Args:
        evidence_store: List of EvidenceItem dicts, possibly with duplicates.

    Returns:
        Deduplicated list preserving insertion order of the first occurrence.
    """
    if not evidence_store:
        return []

    seen: Dict[str, int] = {}  # source_id -> index in result list
    result: List[Dict] = []

    for item in evidence_store:
        source_id = item.get("source_id", "")
        if not source_id:
            # Items without source_id cannot be deduped; keep them
            result.append(item)
            continue

        if source_id not in seen:
            seen[source_id] = len(result)
            result.append(item)
        else:
            # Compare scores, keep the better one
            existing_idx = seen[source_id]
            existing = result[existing_idx]

            existing_score = (
                float(existing.get("relevance", 0.5))
                * float(existing.get("reliability", 0.5))
            )
            new_score = (
                float(item.get("relevance", 0.5))
                * float(item.get("reliability", 0.5))
            )

            if new_score > existing_score:
                result[existing_idx] = item

    return result
