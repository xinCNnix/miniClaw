"""
Termination Checker Node

Decides whether to continue reasoning or generate final answer.
Phase 5: Beam-aware termination + 3-way routing (continue/regenerate/finalize).
"""

import logging
from typing import List, Literal
from langchain_core.messages import HumanMessage

from app.core.tot.state import ToTState, Thought, get_thought_map, get_depth_cached

logger = logging.getLogger(__name__)


# Termination decision type (Phase 5: 三路路由)
TerminationDecision = Literal["continue", "regenerate", "finalize"]


async def termination_checker_node(state: ToTState) -> ToTState:
    """
    Check termination conditions and decide whether to continue reasoning.

    Phase 5 增强:
    - beam 模式下使用束感知终止逻辑
    - 支持 needs_regeneration 回溯路由

    Termination conditions:
    1. High-quality answer found (best_score >= threshold)
    2. Reached max_depth
    3. Diminishing returns detected (beam-aware)
    """
    current_score = state["best_score"]
    current_depth = state["current_depth"]
    max_depth = state["max_depth"]
    quality_threshold = 8.0
    beam_width = state.get("beam_width")

    # Fix 9: 未执行工具时提高阈值
    best_path_ids = set(state["best_path"])
    all_thoughts = state["thoughts"]
    thought_map = get_thought_map(all_thoughts)
    best_thoughts = [thought_map[tid] for tid in best_path_ids if tid in thought_map]
    has_tool_calls = any(t.tool_calls for t in best_thoughts)
    has_tool_results = any(t.tool_results for t in best_thoughts)

    if has_tool_calls and not has_tool_results:
        quality_threshold = max(quality_threshold + 3.0, 9.5)
        logger.info(f"Tools not yet executed, raising quality threshold to {quality_threshold}")

    domain_profile = state.get("domain_profile") or {}
    required_tools = domain_profile.get("required_tools", [])
    if required_tools and not has_tool_calls:
        quality_threshold = max(quality_threshold + 3.0, 9.5)
        logger.info(f"Required tools {required_tools} never called, raising quality threshold to {quality_threshold}")

    logger.info(
        f"Checking termination: depth={current_depth}/{max_depth}, "
        f"score={current_score:.2f}/{quality_threshold}, "
        f"beam_mode={'on' if beam_width else 'off'}"
    )

    # Check for high-quality answer
    if current_score >= quality_threshold:
        logger.info(f"High-quality answer found (score: {current_score:.2f})")
        state["final_answer"] = "__TERMINATE__"
        state["reasoning_trace"].append({
            "type": "termination",
            "reason": "high_quality",
            "score": current_score
        })
        return state

    # Check max depth
    if current_depth >= max_depth:
        logger.info(f"Reached max depth ({max_depth})")
        state["final_answer"] = "__TERMINATE__"
        state["reasoning_trace"].append({
            "type": "termination",
            "reason": "max_depth",
            "depth": current_depth
        })
        return state

    # Check for low scores → backtrack and regenerate (before diminishing returns check)
    backtrack_count = state.get("backtrack_count", 0) or 0
    max_depth = state.get("max_depth", 3)
    if current_score < 5.0 and backtrack_count < max_depth:
        logger.info(
            f"Score too low ({current_score:.2f} < 5.0), triggering regeneration "
            f"instead of terminating (backtrack {backtrack_count}/{max_depth})"
        )
        state["needs_regeneration"] = [0]  # regenerate beam 0
        state["backtrack_count"] = backtrack_count + 1
        state["reasoning_trace"].append({
            "type": "regeneration",
            "reason": "low_score_backtrack",
            "score": current_score,
        })
        return state

    # Check for diminishing returns (beam-aware)
    if beam_width:
        if _check_diminishing_returns_beam_aware(state):
            logger.info("Beam-aware diminishing returns detected, terminating early")
            state["final_answer"] = "__TERMINATE__"
            state["reasoning_trace"].append({
                "type": "termination",
                "reason": "diminishing_returns_beam"
            })
            return state
    else:
        if _check_diminishing_returns(state):
            logger.info("Diminishing returns detected, terminating early")
            state["final_answer"] = "__TERMINATE__"
            state["reasoning_trace"].append({
                "type": "termination",
                "reason": "diminishing_returns"
            })
            return state

    # Continue reasoning
    state["current_depth"] += 1
    logger.info(f"Continuing reasoning to depth {state['current_depth']}")
    return state


def should_continue_reasoning(state: ToTState) -> TerminationDecision:
    """
    Decide whether to continue reasoning, regenerate, or finalize.

    Phase 5: 三路路由 — continue | regenerate | finalize

    This is used by LangGraph's conditional routing.

    Args:
        state: Current ToT state

    Returns:
        "regenerate" if needs_regeneration is set (回溯重生成)
        "finalize" if termination conditions are met
        "continue" otherwise
    """
    # Phase 5: 优先检查回溯重生成
    if state.get("needs_regeneration"):
        logger.info("[Routing] Regeneration requested, routing to generator")
        return "regenerate"

    # If we already have a final answer, stop
    if state.get("final_answer"):
        return "finalize"

    # Check termination conditions
    current_score = state["best_score"]
    current_depth = state["current_depth"]
    max_depth = state["max_depth"]
    quality_threshold = 8.0
    beam_width = state.get("beam_width")

    # Fix 9: 同步阈值调整
    best_path_ids = set(state["best_path"])
    all_thoughts = state["thoughts"]
    thought_map = get_thought_map(all_thoughts)
    best_thoughts = [thought_map[tid] for tid in best_path_ids if tid in thought_map]
    has_tool_calls = any(t.tool_calls for t in best_thoughts)
    has_tool_results = any(t.tool_results for t in best_thoughts)
    if has_tool_calls and not has_tool_results:
        quality_threshold = max(quality_threshold + 3.0, 9.5)
    domain_profile = state.get("domain_profile") or {}
    required_tools = domain_profile.get("required_tools", [])
    if required_tools and not has_tool_calls:
        quality_threshold = max(quality_threshold + 3.0, 9.5)

    if current_score >= quality_threshold:
        return "finalize"

    if current_depth >= max_depth:
        return "finalize"

    # Beam-aware diminishing returns check
    if beam_width:
        if _check_diminishing_returns_beam_aware(state):
            return "finalize"
    else:
        if _check_diminishing_returns(state):
            return "finalize"

    return "continue"


# ---------------------------------------------------------------------------
# Phase 5: 束感知收益递减检测
# ---------------------------------------------------------------------------

def _check_diminishing_returns_beam_aware(state: ToTState) -> bool:
    """束感知的收益递减检测。

    - 束间分数差异大 → 有更好备选路径，不终止
    - 所有束分数接近且低 → 收益递减
    """
    beam_scores = state.get("beam_scores", [])

    if not beam_scores or len(beam_scores) < 2:
        # 只有一个束或没有，用原逻辑
        return _check_diminishing_returns(state)

    # 如果束间分数差异大，说明有更好的备选路径，不终止
    score_range = max(beam_scores) - min(beam_scores)
    if score_range > 1.0:
        logger.info(f"Beam score range {score_range:.2f} > 1.0, alternatives exist")
        return False

    avg_score = sum(beam_scores) / len(beam_scores)

    # 分数较高且接近 → 已收敛，可以终止
    if avg_score >= 7.0:
        return True

    # 分数中等 → 检查历史趋势
    if avg_score >= 5.0:
        return _check_diminishing_returns(state)

    # 分数很低且接近 → 初始想法不好，应回溯而非终止
    # 但每个 depth 只允许回溯一次，避免死循环
    backtrack_count = state.get("backtrack_count", 0) or 0
    if backtrack_count < 1:
        logger.info(
            f"Beam scores low (avg={avg_score:.2f}), not terminating — "
            f"initial thoughts may be poor, allowing backtrack ({backtrack_count}/1)"
        )
        return False

    logger.info(
        f"Beam scores low (avg={avg_score:.2f}) but backtrack limit reached "
        f"({backtrack_count}/1), continuing exploration"
    )
    return _check_diminishing_returns(state)


# ---------------------------------------------------------------------------
# 原有函数（保持不变，beam_width 未设置时使用）
# ---------------------------------------------------------------------------

async def _generate_final_answer(state: ToTState) -> str:
    """
    Generate final answer based on best path reasoning.
    """
    llm = state["llm"]
    user_query = state["user_query"]
    best_path_ids = set(state["best_path"])
    all_thoughts = state["thoughts"]

    thought_map = get_thought_map(all_thoughts)
    best_thoughts = [thought_map[tid] for tid in best_path_ids if tid in thought_map]

    if not best_thoughts:
        return f"I've analyzed your query about: {user_query}\n\nBased on my reasoning, I recommend exploring this topic further using available tools."

    reasoning_summary = _build_reasoning_summary(best_thoughts)

    prompt = f"""Based on the following reasoning process, provide a comprehensive answer to the user's query.

**User Query:** {user_query}

**Reasoning Process:**
{reasoning_summary}

**Instructions:**
1. Provide a direct, clear answer to the query
2. Summarize key findings from the reasoning
3. Mention any limitations or uncertainties
4. If appropriate, suggest next steps

Be concise but thorough."""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content

    except Exception as e:
        logger.error(f"Error generating final answer: {e}")
        return f"""Based on my analysis of: {user_query}

I explored {len(best_thoughts)} reasoning paths and identified the following approach as most promising:

{''.join([f'{i+1}. {t.content}\n' for i, t in enumerate(best_thoughts)])}

However, I encountered an error while generating the final synthesis. Please try rephrasing your query."""


def _build_reasoning_summary(thoughts: List[Thought]) -> str:
    """Build a readable summary of the reasoning process."""
    if not thoughts:
        return "No reasoning steps available."

    summary_parts = []
    for i, thought in enumerate(thoughts):
        part = f"**Step {i+1}:** {thought.content}"

        if thought.tool_results:
            results_summary = _summarize_tool_results(thought.tool_results)
            part += f"\n   Results: {results_summary}"

        if thought.evaluation_score is not None:
            part += f" (Score: {thought.evaluation_score:.2f})"

        summary_parts.append(part)

    return "\n\n".join(summary_parts)


def _summarize_tool_results(results: list) -> str:
    """Summarize tool execution results."""
    if not results:
        return "No results"

    successful = sum(1 for r in results if r.get("status") == "success")
    failed = sum(1 for r in results if r.get("status") == "error")

    if failed == 0:
        return f"{successful} tools executed successfully"
    elif successful == 0:
        return f"{failed} tools failed"
    else:
        return f"{successful} succeeded, {failed} failed"


def _check_diminishing_returns(state: ToTState) -> bool:
    """
    Check for diminishing returns in reasoning quality.
    """
    current_depth = state["current_depth"]
    all_thoughts = state["thoughts"]

    if current_depth < 2:
        return False

    thought_map = get_thought_map(all_thoughts)

    recent_scores = []
    for depth in range(max(0, current_depth - 2), current_depth + 1):
        thoughts_at_depth = [
            t for t in all_thoughts
            if get_depth_cached(t, thought_map) == depth
            and t.evaluation_score is not None
        ]
        if thoughts_at_depth:
            max_score = max(t.evaluation_score for t in thoughts_at_depth)
            recent_scores.append(max_score)

    if len(recent_scores) >= 2:
        improvement = recent_scores[-1] - recent_scores[0]
        if improvement < 1.0:
            logger.info(f"Diminishing returns: improvement only {improvement:.2f}")
            return True

    return False


def _get_thought_depth(thought: Thought, all_thoughts: list[Thought]) -> int:
    """Calculate depth of a thought."""
    from app.core.tot.state import get_depth_of_thought
    return get_depth_of_thought(thought, all_thoughts)
