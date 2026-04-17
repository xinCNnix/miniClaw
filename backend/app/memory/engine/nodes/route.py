"""Route node — query intent classification for retrieval routing.

Analyzes the user query to determine which memory layers to search.
Routes to: semantic | episodic | procedural | case | hybrid
"""

import logging

from app.memory.engine.state import MemoryState

logger = logging.getLogger(__name__)

# Intent keywords for routing
_INTENT_PATTERNS = {
    "semantic": [
        "what is", "what's", "定义", "什么是", "解释", "explain",
        "怎么用", "how to use", "用法", "用法是", "是什么",
        "区别", "difference", "比较", "compare",
    ],
    "episodic": [
        "上次", "之前", "last time", "previously", "刚才",
        "我们讨论过", "we discussed", "聊过", "mentioned",
        "什么时候", "when did", "历史", "history",
    ],
    "procedural": [
        "怎么做", "如何", "how do", "how to", "步骤", "steps",
        "流程", "process", "操作", "operation",
        "怎么处理", "怎么解决", "如何解决",
    ],
    "case": [
        "类似", "similar", "之前解决", "solved before",
        "遇到过", "encountered", "同样的问题", "same problem",
        "案例", "case", "复用", "reuse",
    ],
}


async def route_query(state: MemoryState) -> MemoryState:
    """Classify query intent and route to appropriate memory layers.

    Uses keyword matching for intent classification.
    Falls back to "hybrid" (search all layers) for ambiguous queries.
    """
    query = state.get("query", "").lower()
    logs = state.get("logs", [])

    if not query:
        state["routed_to"] = "hybrid"
        return state

    # Score each intent
    scores = {}
    for intent, keywords in _INTENT_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in query)
        if score > 0:
            scores[intent] = score

    if not scores:
        # No clear intent → hybrid (search all)
        state["routed_to"] = "hybrid"
        logs.append(f"[route_query] No clear intent, routing to hybrid for: '{query[:50]}'")
    elif len(scores) == 1:
        # Single clear intent
        intent = list(scores.keys())[0]
        state["routed_to"] = intent
        logs.append(f"[route_query] Routed to {intent} for: '{query[:50]}'")
    else:
        # Multiple intents → hybrid
        state["routed_to"] = "hybrid"
        top_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        logs.append(
            f"[route_query] Multiple intents {top_intents}, routing to hybrid"
        )

    state["logs"] = logs
    return state
