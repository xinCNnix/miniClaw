"""
Termination Checker Node

Decides whether to continue reasoning or generate final answer.
"""

import logging
from typing import List, Literal
from langchain_core.messages import HumanMessage

from app.core.tot.state import ToTState, Thought

logger = logging.getLogger(__name__)


# Termination decision type
TerminationDecision = Literal["continue", "finalize"]


async def termination_checker_node(state: ToTState) -> ToTState:
    """
    Check termination conditions and decide whether to continue reasoning.

    Termination conditions:
    1. High-quality answer found (best_score >= threshold)
    2. Reached max_depth
    3. Diminishing returns detected

    Args:
        state: Current ToT state

    Returns:
        Updated state with either final_answer or incremented current_depth
    """
    current_score = state["best_score"]
    current_depth = state["current_depth"]
    max_depth = state["max_depth"]
    quality_threshold = 6.0  # Reduced from 8.0 to prevent timeouts

    logger.info(
        f"Checking termination: depth={current_depth}/{max_depth}, "
        f"score={current_score:.2f}/{quality_threshold}"
    )

    # Check for high-quality answer
    if current_score >= quality_threshold:
        logger.info(f"High-quality answer found (score: {current_score:.2f})")
        state["final_answer"] = await _generate_final_answer(state)
        state["reasoning_trace"].append({
            "type": "termination",
            "reason": "high_quality",
            "score": current_score
        })
        return state

    # Check max depth
    if current_depth >= max_depth:
        logger.info(f"Reached max depth ({max_depth})")
        state["final_answer"] = await _generate_final_answer(state)
        state["reasoning_trace"].append({
            "type": "termination",
            "reason": "max_depth",
            "depth": current_depth
        })
        return state

    # Check for diminishing returns
    if _check_diminishing_returns(state):
        logger.info("Diminishing returns detected, terminating early")
        state["final_answer"] = await _generate_final_answer(state)
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
    Decide whether to continue reasoning or finalize.

    This is used by LangGraph's conditional routing.

    Args:
        state: Current ToT state

    Returns:
        "continue" to generate more thoughts, "finalize" to end
    """
    # If we already have a final answer, stop
    if state.get("final_answer"):
        return "finalize"

    # Check termination conditions
    current_score = state["best_score"]
    current_depth = state["current_depth"]
    max_depth = state["max_depth"]
    quality_threshold = 6.0  # Reduced from 8.0 to prevent timeouts

    if current_score >= quality_threshold:
        return "finalize"

    if current_depth >= max_depth:
        return "finalize"

    if _check_diminishing_returns(state):
        return "finalize"

    return "continue"


async def _generate_final_answer(state: ToTState) -> str:
    """
    Generate final answer based on best path reasoning.

    Args:
        state: Current ToT state

    Returns:
        Final answer string
    """
    llm = state["llm"]
    user_query = state["user_query"]
    best_path_ids = state["best_path"]
    all_thoughts = state["thoughts"]

    # Get thoughts on best path
    best_thoughts = [t for t in all_thoughts if t.id in best_path_ids]

    if not best_thoughts:
        # Fallback: simple answer
        return f"I've analyzed your query about: {user_query}\n\nBased on my reasoning, I recommend exploring this topic further using available tools."

    # Build reasoning summary
    reasoning_summary = _build_reasoning_summary(best_thoughts)

    # Generate final answer
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
        # Fallback
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

        # Add tool results if available
        if thought.tool_results:
            results_summary = _summarize_tool_results(thought.tool_results)
            part += f"\n   Results: {results_summary}"

        # Add evaluation score if available
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

    Signs of diminishing returns:
    1. Score improvement < 0.5 over last 2 depths
    2. Very similar thoughts being generated
    3. Low scores across all recent thoughts

    Args:
        state: Current ToT state

    Returns:
        True if diminishing returns detected
    """
    current_depth = state["current_depth"]
    all_thoughts = state["thoughts"]

    # Need at least 2 depth levels to check
    if current_depth < 2:
        return False

    # Check score improvement
    # Get scores from last 2 depths
    recent_scores = []
    for depth in range(max(0, current_depth - 2), current_depth + 1):
        thoughts_at_depth = [
            t for t in all_thoughts
            if _get_thought_depth(t, all_thoughts) == depth
            and t.evaluation_score is not None
        ]
        if thoughts_at_depth:
            max_score = max(t.evaluation_score for t in thoughts_at_depth)
            recent_scores.append(max_score)

    # Check if improvement is minimal
    if len(recent_scores) >= 2:
        improvement = recent_scores[-1] - recent_scores[0]
        if improvement < 0.5:
            logger.info(f"Diminishing returns: improvement only {improvement:.2f}")
            return True

    return False


def _get_thought_depth(thought: Thought, all_thoughts: list[Thought]) -> int:
    """Calculate depth of a thought."""
    from app.core.tot.state import get_depth_of_thought
    return get_depth_of_thought(thought, all_thoughts)
