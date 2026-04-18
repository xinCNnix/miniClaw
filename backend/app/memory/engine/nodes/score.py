"""Score node — importance scoring and TTL assignment.

Assigns each distilled candidate an importance score and TTL (time-to-live)
based on its type and content. This drives later pruning and decay decisions.
"""

import logging
import re

from app.memory.engine.state import MemoryState

logger = logging.getLogger(__name__)

# Importance heuristics by memory type / content keywords
_HIGH_IMPORTANCE_KEYWORDS = {
    "preference", "always", "never", "必须", "禁止", "偏好", "喜欢", "讨厌",
    "密码", "密钥", "password", "api_key", "secret",
    "项目", "project", "架构", "architecture",
}
_MEDIUM_IMPORTANCE_KEYWORDS = {
    "fact", "模式", "pattern", "经验", "experience", "最佳实践", "best practice",
    "工具", "tool", "命令", "command",
}
_LOW_IMPORTANCE_KEYWORDS = {
    "闲聊", "你好", "hello", "谢谢", "thanks", "哈哈", "ok", "好的",
}


def _compute_importance(item: dict) -> float:
    """Compute importance score based on content and type.

    Returns:
        float between 0.0 and 1.0
    """
    text = item.get("text", "").lower()
    layer = item.get("layer", "semantic")
    base_confidence = item.get("confidence", 0.5)

    # Base importance by layer
    layer_base = {
        "semantic": 0.7,
        "episodic": 0.4,
        "procedural": 0.6,
        "case": 0.5,
    }.get(layer, 0.5)

    # Keyword-based adjustment
    keyword_boost = 0.0
    for kw in _HIGH_IMPORTANCE_KEYWORDS:
        if kw in text:
            keyword_boost = max(keyword_boost, 0.2)
            break

    if keyword_boost == 0:
        for kw in _MEDIUM_IMPORTANCE_KEYWORDS:
            if kw in text:
                keyword_boost = max(keyword_boost, 0.1)
                break

    # Low importance detection
    for kw in _LOW_IMPORTANCE_KEYWORDS:
        if kw in text:
            return min(base_confidence, 0.2)  # Cap at 0.2

    importance = min(layer_base + keyword_boost + base_confidence * 0.1, 1.0)
    return round(importance, 3)


def _compute_ttl(item: dict) -> int | None:
    """Compute TTL in days for a memory item.

    Returns:
        Number of days until expiry, or None for permanent memories.
    """
    text = item.get("text", "").lower()
    layer = item.get("layer", "semantic")
    importance = item.get("importance", 0.5)

    # High importance → permanent
    if importance >= 0.8:
        return None

    # Layer-based defaults
    layer_ttl = {
        "semantic": None,     # Semantic facts are permanent unless low importance
        "episodic": 30,       # Conversational context expires in 30 days
        "procedural": 180,    # Procedures last longer
        "case": 90,           # Cases expire in 90 days
    }.get(layer, 90)

    # Low importance semantic → short TTL
    if layer == "semantic" and importance < 0.3:
        return 7

    return layer_ttl


async def score_and_prune(state: MemoryState) -> MemoryState:
    """Score distilled candidates and assign TTL.

    Reads from state["distilled"] (a dict with "summaries" + "updates" lists)
    and produces state["scored"] — a flat list of scored items ready for writing.
    """
    distilled = state.get("distilled", {})
    scored = []
    logs = state.get("logs", [])

    # Collect candidates from distilled updates or scored items
    candidates = []

    if distilled:
        # From distilled pipeline (updates + summaries)
        candidates.extend(distilled.get("summaries", []))
        candidates.extend(distilled.get("updates", []))

    if not candidates:
        # Fallback: use scored items from extract step (bypassing distill)
        candidates = state.get("scored", [])

    for item in candidates:
        if isinstance(item, str):
            item = {"text": item, "layer": "semantic"}
        item["importance"] = _compute_importance(item)
        item["ttl_days"] = _compute_ttl(item)
        scored.append(item)

    # Prune very low importance items (below threshold)
    from app.config import get_settings
    settings = get_settings()
    prune_threshold = 0.1

    before = len(scored)
    scored = [s for s in scored if s.get("importance", 0) >= prune_threshold]
    pruned = before - len(scored)

    logs.append(
        f"[score_and_prune] scored={len(scored)}, pruned_below_{prune_threshold}={pruned}"
    )
    state["scored"] = scored
    state["logs"] = logs
    return state
