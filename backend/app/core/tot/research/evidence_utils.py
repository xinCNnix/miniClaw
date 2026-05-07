"""
Evidence Utility Functions for ToT Research Enhancement.

Provides hashing, formatting, and deduplication utilities for the
evidence_store used during deep research tasks.
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import List, Dict


def _compute_recency_factor(item: Dict) -> float:
    """Compute a recency multiplier based on the publication date.

    Piecewise linear decay:
      - <= 6 months:  1.5
      - 6-12 months:  1.2
      - 1-2 years:    1.0
      - 2-3 years:    0.8
      - > 3 years:    0.6

    If no date is found, returns 1.0 (neutral).
    """
    now = datetime.now(timezone.utc)

    # Try explicit "published" field (from arxiv extractor)
    date_str = item.get("published", "")
    parsed = None

    if date_str:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                parsed = datetime.strptime(date_str[:19], fmt).replace(tzinfo=timezone.utc)
                break
            except (ValueError, TypeError):
                continue

    # Fallback: try "year" field
    if parsed is None:
        year = item.get("year", "")
        if isinstance(year, int):
            parsed = datetime(year, 1, 1, tzinfo=timezone.utc)
        elif isinstance(year, str) and year.isdigit():
            parsed = datetime(int(year), 1, 1, tzinfo=timezone.utc)

    # Fallback: search for 4-digit year in quote/claim/title text
    if parsed is None:
        for field in ("quote", "claim", "title"):
            text = item.get(field, "")
            if text:
                m = re.search(r"\b(19|20)\d{2}\b", text)
                if m:
                    parsed = datetime(int(m.group()), 1, 1, tzinfo=timezone.utc)
                    break

    if parsed is None:
        return 1.0

    age_days = (now - parsed).days
    age_years = age_days / 365.25

    if age_days <= 180:
        return 1.5
    elif age_days <= 365:
        return 1.2
    elif age_years <= 2:
        return 1.0
    elif age_years <= 3:
        return 0.8
    else:
        return 0.6


def compute_reliability(evidence: Dict) -> float:
    """Compute evidence reliability based on source type and content.

    Scoring rules:
      - search_kb with content > 200 chars: 0.70–0.85
      - fetch_url with content > 200 chars: 0.60–0.75
      - Empty content from any tool: 0.10
      - Unknown tool with content: 0.50
      - Fallback: 0.50

    Args:
        evidence: Dict with keys source_type, tool_name, content_length
                  (or source_text to derive length from).

    Returns:
        Reliability score in [0.0, 1.0].
    """
    source_type = evidence.get("source_type", "")
    tool_name = evidence.get("tool_name", "")
    content_length = evidence.get("content_length", 0)
    if content_length == 0:
        content_length = len(evidence.get("source_text", ""))

    if content_length == 0:
        return 0.10

    if tool_name == "search_kb":
        if content_length > 500:
            return 0.85
        elif content_length > 200:
            return 0.75
        return 0.60

    if tool_name == "fetch_url":
        if content_length > 500:
            return 0.75
        elif content_length > 200:
            return 0.65
        return 0.55

    # source_type based fallback
    if source_type == "tool_output":
        return 0.55 if content_length > 100 else 0.40

    return 0.50


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

    # Sort by relevance * reliability * recency_factor descending
    scored_items: List[Dict] = []
    for item in evidence_store:
        relevance = float(item.get("relevance", 0.5))
        reliability = float(item.get("reliability", 0.5))
        recency = _compute_recency_factor(item)
        score = relevance * reliability * recency
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
                * _compute_recency_factor(existing)
            )
            new_score = (
                float(item.get("relevance", 0.5))
                * float(item.get("reliability", 0.5))
                * _compute_recency_factor(item)
            )

            if new_score > existing_score:
                result[existing_idx] = item

    return result
