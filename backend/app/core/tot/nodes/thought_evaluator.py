"""
Thought Evaluator Node

Evaluates the quality of thoughts using multi-criteria scoring.

Phase 3 Enhancement: Beam Search + Backtracking
- Replaces greedy algorithm with Beam Search
- Maintains top-k candidate paths
- Implements backtracking for failed paths
"""

import logging
import json
from typing import List, Dict, Optional, Tuple
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
    Update best_path using Beam Search (Phase 3 enhancement).

    Replaces greedy algorithm with Beam Search:
    - Maintains top-k candidate paths (beam_width)
    - Uses multi-factor path scoring
    - Supports backtracking when paths fail

    Path scoring factors:
    - Average evaluation score (50%)
    - Tool execution success rate (30%)
    - Information diversity (15%)
    - Path length penalty (5%)
    """
    # Get config
    enable_beam_search = state.get("tot_enable_beam_search", True)
    beam_width = state.get("tot_beam_width", 3)

    if enable_beam_search and beam_width > 1:
        # Use Beam Search
        best_path, best_score = _update_best_path_with_beam_search(state, beam_width)
    else:
        # Use greedy algorithm (original behavior)
        best_path, best_score = _update_best_path_greedy(state)

    state["best_path"] = best_path
    state["best_score"] = best_score

    logger.info(
        f"Updated best path: {best_path} with average score {best_score:.2f}"
    )


def _update_best_path_greedy(state: ToTState) -> Tuple[List[str], float]:
    """
    Original greedy algorithm (preserved for fallback).

    Selects highest-scoring thought at each depth level.
    Enhanced to prioritize thoughts with tool calls for research mode.
    """
    all_thoughts = state["thoughts"]

    if not all_thoughts:
        return [], 0.0

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
            # Root: prioritize thoughts with tool calls
            thoughts_with_tools = [t for t in thoughts_at_depth if t.tool_calls]
            thoughts_without_tools = [t for t in thoughts_at_depth if not t.tool_calls]

            if thoughts_with_tools:
                best = max(thoughts_with_tools, key=lambda t: t.evaluation_score or 0.0)
                logger.info(f"Root depth: Selected thought WITH tools ({best.id}), score={best.evaluation_score:.2f}")
            elif thoughts_without_tools:
                best = max(thoughts_without_tools, key=lambda t: t.evaluation_score or 0.0)
                logger.warning(f"Root depth: No thoughts with tools! Selected thought WITHOUT tools ({best.id})")
            else:
                break

            best_path.append(best.id)
            previous_best = best
        else:
            # Non-root: select child of previous best with highest score
            children = [
                t for t in thoughts_at_depth
                if t.parent_id == previous_best.id
            ]

            if not children:
                break

            children_with_tools = [t for t in children if t.tool_calls]
            children_without_tools = [t for t in children if not t.tool_calls]

            if children_with_tools:
                best = max(children_with_tools, key=lambda t: t.evaluation_score or 0.0)
                logger.info(f"Depth {depth}: Selected child WITH tools ({best.id}), score={best.evaluation_score:.2f}")
            else:
                best = max(children_without_tools, key=lambda t: t.evaluation_score or 0.0)
                logger.warning(f"Depth {depth}: No children with tools! Selected child WITHOUT tools ({best.id})")

            best_path.append(best.id)
            previous_best = best

    # Calculate average score
    if best_path:
        path_scores = [
            next(t.evaluation_score for t in all_thoughts if t.id == thought_id)
            for thought_id in best_path
            if any(t.id == thought_id for t in all_thoughts)
        ]
        best_score = sum(path_scores) / len(path_scores) if path_scores else 0.0
    else:
        best_score = 0.0

    return best_path, best_score


def _update_best_path_with_beam_search(
    state: ToTState,
    beam_width: int = 3
) -> Tuple[List[str], float]:
    """
    Beam Search algorithm (Phase 3).

    Maintains top-k candidate paths instead of just one best path.

    Algorithm:
    1. Start with all root thoughts (depth 0)
    2. For each depth, expand top-k paths
    3. Score each complete path using multi-factor scoring
    4. Keep top-k paths for next iteration
    5. Return best path at the end

    Path scoring:
    - eval_score: 50% (average evaluation score)
    - tool_success: 30% (tool execution success rate)
    - diversity: 15% (information diversity)
    - length_penalty: 5% (shorter paths preferred)
    """
    all_thoughts = state["thoughts"]

    if not all_thoughts:
        return [], 0.0

    # Get path scoring weights
    weights = state.get("tot_path_score_weights", {
        "eval_score": 0.5,
        "tool_success": 0.3,
        "diversity": 0.15,
        "length_penalty": 0.05
    })

    # Group thoughts by depth
    depth_groups: Dict[int, List[Thought]] = {}
    for thought in all_thoughts:
        depth = get_depth_of_thought(thought, all_thoughts)
        if depth not in depth_groups:
            depth_groups[depth] = []
        depth_groups[depth].append(thought)

    if not depth_groups:
        return [], 0.0

    # Initialize beam with root thoughts
    current_depth = 0
    beam_paths = [
        ([thought.id], thought.evaluation_score or 0.0)
        for thought in depth_groups.get(0, [])
    ]

    logger.info(f"[BEAM_SEARCH] Initialized with {len(beam_paths)} root paths, beam_width={beam_width}")

    # Expand beam depth by depth
    while current_depth + 1 in depth_groups:
        next_depth = current_depth + 1
        next_thoughts = depth_groups[next_depth]

        # Expand each path in beam
        expanded_paths = []

        for path_ids, path_score in beam_paths:
            # Find children of last thought in path
            last_thought_id = path_ids[-1]
            children = [
                t for t in next_thoughts
                if t.parent_id == last_thought_id
            ]

            if not children:
                # Path ends here, keep it
                expanded_paths.append((path_ids, path_score))
            else:
                # Extend path with each child
                for child in children:
                    new_path = path_ids + [child.id]
                    new_score = path_score + (child.evaluation_score or 0.0)
                    expanded_paths.append((new_path, new_score))

        if not expanded_paths:
            break

        # Score paths using multi-factor scoring
        scored_paths = []
        for path_ids, cumulative_score in expanded_paths:
            path_thoughts = [t for t in all_thoughts if t.id in path_ids]

            # Calculate path score
            path_score = _calculate_path_score(
                path_thoughts,
                cumulative_score,
                weights
            )

            scored_paths.append((path_ids, path_score))

        # Keep top-k paths (beam width)
        scored_paths.sort(key=lambda x: x[1], reverse=True)
        beam_paths = scored_paths[:beam_width]

        logger.info(
            f"[BEAM_SEARCH] Depth {next_depth}: Expanded to {len(expanded_paths)} paths, "
            f"kept top {len(beam_paths)} paths (best score: {beam_paths[0][1]:.2f})"
        )

        current_depth = next_depth

    # Return best path
    if not beam_paths:
        return [], 0.0

    best_path, best_score = beam_paths[0]
    logger.info(f"[BEAM_SEARCH] Final best path score: {best_score:.2f}")

    return best_path, best_score


def _calculate_path_score(
    path_thoughts: List[Thought],
    cumulative_score: float,
    weights: Dict[str, float]
) -> float:
    """
    Calculate path score using multi-factor scoring.

    Factors:
    1. Average evaluation score (50%)
    2. Tool execution success rate (30%)
    3. Information diversity (15%)
    4. Path length penalty (5%)
    """
    if not path_thoughts:
        return 0.0

    # 1. Average evaluation score
    eval_scores = [t.evaluation_score or 5.0 for t in path_thoughts]
    avg_eval_score = sum(eval_scores) / len(eval_scores)

    # 2. Tool execution success rate
    tool_results = []
    for thought in path_thoughts:
        tool_results.extend(thought.tool_results or [])

    if tool_results:
        success_count = sum(1 for r in tool_results if r.get("status") == "success")
        tool_success_rate = success_count / len(tool_results)
    else:
        tool_success_rate = 0.5  # Neutral if no tools executed

    # 3. Information diversity (unique tools used)
    tools_used = set()
    for thought in path_thoughts:
        for tool_call in thought.tool_calls or []:
            tools_used.add(tool_call.get("name", ""))

    # Max reasonable diversity is ~5 tools (all core tools)
    diversity_score = min(len(tools_used) / 5.0, 1.0)

    # 4. Path length penalty (prefer shorter paths with same quality)
    path_length = len(path_thoughts)
    length_penalty = max(0, 1.0 - (path_length - 1) * 0.1)  # -0.1 per extra level

    # Combine scores with weights
    final_score = (
        avg_eval_score * weights.get("eval_score", 0.5) +
        tool_success_rate * 10 * weights.get("tool_success", 0.3) +  # Scale to 0-10
        diversity_score * 10 * weights.get("diversity", 0.15) +  # Scale to 0-10
        length_penalty * 10 * weights.get("length_penalty", 0.05)  # Scale to 0-10
    )

    return final_score


def should_trigger_backtracking(state: ToTState) -> bool:
    """
    Check if backtracking should be triggered (Phase 3).

    Triggers when:
    1. Current path tool failure rate > threshold
    2. Current path score has plateaued (minimal improvement)

    Returns:
        True if backtracking should be triggered
    """
    enable_backtracking = state.get("tot_enable_backtracking", True)
    if not enable_backtracking:
        return False

    best_path = state["best_path"]
    if not best_path:
        return False

    all_thoughts = state["thoughts"]
    path_thoughts = [t for t in all_thoughts if t.id in best_path]

    # Check 1: Tool failure rate
    failure_threshold = state.get("tot_backtrack_failure_threshold", 0.5)
    tool_results = []
    for thought in path_thoughts:
        tool_results.extend(thought.tool_results or [])

    if tool_results:
        failure_count = sum(1 for r in tool_results if r.get("status") == "error")
        failure_rate = failure_count / len(tool_results)

        if failure_rate > failure_threshold:
            logger.warning(
                f"[BACKTRACK] High failure rate: {failure_rate:.1%} > {failure_threshold:.1%}"
            )
            return True

    # Check 2: Score plateau
    plateau_threshold = state.get("tot_backtrack_plateau_threshold", 0.3)

    # Get scores along path
    scores = [t.evaluation_score or 0.0 for t in path_thoughts]
    if len(scores) >= 3:
        # Check last 3 improvements
        improvements = []
        for i in range(1, min(4, len(scores))):
            improvements.append(scores[i] - scores[i-1])

        if all(imp < plateau_threshold for imp in improvements):
            logger.warning(
                f"[BACKTRACK] Score plateau: improvements {[f'{imp:.2f}' for imp in improvements]} < {plateau_threshold}"
            )
            return True

    return False


async def generate_alternative_thoughts(state: ToTState) -> List[Thought]:
    """
    Generate alternative thoughts when backtracking (Phase 3).

    Creates alternative branches from:
    1. Parent thoughts that weren't selected
    2. Sibling thoughts with high potential

    Returns:
        List of new alternative thoughts
    """
    from app.core.tot.nodes.thought_generator import _generate_fallback_thoughts

    current_depth = state["current_depth"]
    user_query = state["user_query"]
    best_path = state["best_path"]

    logger.info(f"[BACKTRACK] Generating alternatives at depth {current_depth}")

    # Strategy 1: Explore siblings of best path thoughts
    all_thoughts = state["thoughts"]
    alternatives = []

    # Find high-potential siblings (not in best path)
    for thought in all_thoughts:
        if (
            thought.id not in best_path
            and thought.parent_id in best_path  # Is a sibling
            and (thought.evaluation_score or 0) >= 6.0  # High potential
        ):
            # Create alternative thought extending this sibling
            alt_thought = Thought(
                id=f"alt_{thought.id}",
                parent_id=thought.id,
                content=f"Alternative exploration from {thought.id}",
                tool_calls=thought.tool_calls,  # Inherit tool calls
                status="pending"
            )
            alternatives.append(alt_thought)

    # Strategy 2: Generate new fallback thoughts if needed
    if len(alternatives) < 3:
        fallback_thoughts = _generate_fallback_thoughts(
            user_query,
            current_depth,
            best_path[-1] if best_path else None,
            3 - len(alternatives)
        )
        alternatives.extend(fallback_thoughts)

    logger.info(f"[BACKTRACK] Generated {len(alternatives)} alternative thoughts")
    return alternatives
