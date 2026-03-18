"""
Thought Evaluator Node

Evaluates the quality of thoughts using multi-criteria scoring.
"""

import logging
import json
from typing import List, Dict
from langchain_core.messages import HumanMessage

from app.core.tot.state import ToTState, Thought, get_depth_of_thought

logger = logging.getLogger(__name__)


async def thought_evaluator_node(state: ToTState) -> ToTState:
    """
    Evaluate thoughts using multi-criteria scoring.

    Criteria:
    1. Relevance (0-10): How well does this address the user query?
    2. Feasibility (0-10): Can this be executed with available tools?
    3. Novelty (0-10): Is this a new angle or redundant with previous thoughts?

    Final score is weighted average:
    - Relevance: 40%
    - Feasibility: 40%
    - Novelty: 20%

    Args:
        state: Current ToT state

    Returns:
        Updated state with evaluated thoughts and updated best path
    """
    llm = state["llm"]
    user_query = state["user_query"]
    all_thoughts = state["thoughts"]

    # Find thoughts that need evaluation (status == "pending")
    pending_thoughts = [t for t in all_thoughts if t.status == "pending"]

    if not pending_thoughts:
        logger.info("No pending thoughts to evaluate")
        return state

    logger.info(f"Evaluating {len(pending_thoughts)} thoughts")

    # Evaluate each thought
    for thought in pending_thoughts:
        try:
            # Build evaluation prompt
            prompt = _build_evaluation_prompt(thought, user_query, all_thoughts)

            # Get evaluation from LLM
            response = await llm.ainvoke([HumanMessage(content=prompt)])

            # Parse scores
            scores = _parse_evaluation_scores(response.content)

            # Calculate weighted score
            weighted_score = (
                scores.get("relevance", 5.0) * 0.4 +
                scores.get("feasibility", 5.0) * 0.4 +
                scores.get("novelty", 5.0) * 0.2
            )

            # Update thought
            thought.evaluation_score = weighted_score
            thought.criteria_scores = scores
            thought.status = "evaluated"

            logger.info(
                f"Thought {thought.id}: relevance={scores.get('relevance', 0):.1f}, "
                f"feasibility={scores.get('feasibility', 0):.1f}, "
                f"novelty={scores.get('novelty', 0):.1f}, "
                f"final={weighted_score:.2f}"
            )

        except Exception as e:
            logger.error(f"Error evaluating thought {thought.id}: {e}")
            # Assign default score
            thought.evaluation_score = 5.0
            thought.status = "evaluated"

    # Update best path based on evaluations
    _update_best_path(state)

    # Add to reasoning trace
    state["reasoning_trace"].append({
        "type": "thoughts_evaluated",
        "best_path": state["best_path"],
        "best_score": state["best_score"]
    })

    return state


def _build_evaluation_prompt(
    thought: Thought,
    user_query: str,
    all_thoughts: List[Thought]
) -> str:
    """Build prompt for evaluating a single thought."""
    return f"""Evaluate this thought on 3 criteria (score 0-10 each):

**User Query:** {user_query}

**Thought to Evaluate:**
{thought.content}

**Evaluation Criteria:**

1. **Relevance (0-10)**: How well does this thought directly address the user's query?
   - 10: Directly addresses the core question
   - 5: Somewhat related but tangential
   - 0: Irrelevant to the query

2. **Feasibility (0-10)**: Can this be executed with available tools?
   Available tools: terminal, python_repl, search_kb, fetch_url, read_file, write_file
   - 10: Straightforward to execute with available tools
   - 5: Possible but may require creative tool use
   - 0: Not feasible with current toolset

3. **Novelty (0-10)**: Is this a new angle or redundant?
   - 10: Completely new, unique approach
   - 5: Some new elements but similar to previous thoughts
   - 0: Redundant with existing thoughts

Return your evaluation as JSON only:
{{"relevance": X, "feasibility": X, "novelty": X}}

Be objective and critical in your scoring."""


def _parse_evaluation_scores(content: str) -> Dict[str, float]:
    """Parse LLM response to extract evaluation scores."""
    try:
        # Try to parse JSON
        content = content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        scores = json.loads(content)

        return {
            "relevance": float(scores.get("relevance", 5.0)),
            "feasibility": float(scores.get("feasibility", 5.0)),
            "novelty": float(scores.get("novelty", 5.0))
        }

    except json.JSONDecodeError:
        # Fallback: extract numbers using regex
        import re
        numbers = re.findall(r'\d+\.?\d*', content)
        if len(numbers) >= 3:
            return {
                "relevance": float(numbers[0]),
                "feasibility": float(numbers[1]),
                "novelty": float(numbers[2])
            }

    # Default scores
    return {"relevance": 5.0, "feasibility": 5.0, "novelty": 5.0}


def _update_best_path(state: ToTState):
    """
    Update best_path based on highest-scoring thoughts at each depth level.

    This implements a greedy approach: at each depth, select the highest-scoring
    thought to extend the best path.
    """
    all_thoughts = state["thoughts"]

    if not all_thoughts:
        state["best_path"] = []
        state["best_score"] = 0.0
        return

    # Group thoughts by depth
    depth_groups: Dict[int, List[Thought]] = {}
    for thought in all_thoughts:
        depth = get_depth_of_thought(thought, all_thoughts)
        if depth not in depth_groups:
            depth_groups[depth] = []
        depth_groups[depth].append(thought)

    # Select best thought at each depth
    best_path = []
    previous_best = None

    for depth in sorted(depth_groups.keys()):
        thoughts_at_depth = depth_groups[depth]

        if depth == 0:
            # Root: select highest scoring thought
            best = max(thoughts_at_depth, key=lambda t: t.evaluation_score or 0.0)
            best_path.append(best.id)
            previous_best = best
        else:
            # Non-root: select child of previous best with highest score
            children = [
                t for t in thoughts_at_depth
                if t.parent_id == previous_best.id
            ]

            if children:
                best = max(children, key=lambda t: t.evaluation_score or 0.0)
                best_path.append(best.id)
                previous_best = best
            else:
                # No children found, stop here
                break

    state["best_path"] = best_path

    # Update best_score (average score along best path)
    if best_path:
        path_scores = [
            next(t.evaluation_score for t in all_thoughts if t.id == thought_id)
            for thought_id in best_path
            if any(t.id == thought_id for t in all_thoughts)
        ]
        state["best_score"] = sum(path_scores) / len(path_scores) if path_scores else 0.0
    else:
        state["best_score"] = 0.0

    logger.info(
        f"Updated best path: {best_path} with average score {state['best_score']:.2f}"
    )
