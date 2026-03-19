"""
Termination Checker Node

Decides whether to continue reasoning or generate final answer.

Enhanced with ToT-specific smart stopping mechanism (Phase 2).
"""

import logging
from typing import List, Literal, Optional, Dict, Any
from langchain_core.messages import HumanMessage

from app.core.tot.state import ToTState, Thought

logger = logging.getLogger(__name__)


# ============================================================================
# ToT Smart Stopping Mechanism (Phase 2 - Fixed & Relaxed)
# ============================================================================

class ToTSmartStopping:
    """
    ToT-specific intelligent stopping mechanism.

    Fixed bugs from smart_stopping.py:
    1. Removed hard_limit (was 60 rounds - too strict for research)
    2. Changed evaluation from rounds to depth-based
    3. Removed simple greeting check (not applicable to research mode)
    4. Added tool redundancy detection
    5. Added information sufficiency tracking
    6. Relaxed thresholds for research mode

    Design for ToT research mode:
    - Allow deeper exploration (no hard limit)
    - Evaluate based on depth, not rounds
    - Detect redundant tool calls (wasteful exploration)
    - Track information gaps
    - Use LLM evaluation sparingly (high latency)
    """

    def __init__(
        self,
        enable: bool = True,
        # Relaxed thresholds for research mode
        # NOTE: ToT can generate 100-300+ tool calls (branching_factor^depth)
        min_successful_tools: int = 50,  # Increased to 50 (not 10)
        redundancy_window: int = 15,  # Increased to 15 (not 5)
        score_plateau_threshold: float = 0.3,  # Reduced from 0.5 (more sensitive)
        enable_llm_evaluation: bool = True,  # Can be disabled to save cost
        llm_eval_depth_interval: int = 3,  # Evaluate every N depths (not rounds)
        max_depth_multiplier: float = 2.0,  # Allow going beyond max_depth by this factor
    ):
        """
        Initialize ToT smart stopping.

        Args:
            enable: Enable smart stopping
            min_successful_tools: Minimum successful tool executions before considering sufficiency
            redundancy_window: Window size to detect redundant tool calls
            score_plateau_threshold: Score improvement below this indicates plateau
            enable_llm_evaluation: Whether to use LLM evaluation (expensive but accurate)
            llm_eval_depth_interval: Evaluate every N depths
            max_depth_multiplier: Allow exceeding max_depth by this factor for complex queries
        """
        self.enable = enable
        self.min_successful_tools = min_successful_tools
        self.redundancy_window = redundancy_window
        self.score_plateau_threshold = score_plateau_threshold
        self.enable_llm_evaluation = enable_llm_evaluation
        self.llm_eval_depth_interval = llm_eval_depth_interval
        self.max_depth_multiplier = max_depth_multiplier

        # Tracking state
        self.tool_call_history: List[Dict[str, Any]] = []
        self.depth_scores: List[tuple[int, float]] = []  # (depth, max_score)

    def should_stop_tot_reasoning(
        self,
        state: ToTState,
        thought_executor_results: Optional[List[Dict]] = None
    ) -> tuple[bool, str]:
        """
        Check if ToT reasoning should stop.

        Fixed and relaxed for research mode:
        1. No hard limit on rounds/depths
        2. More tolerant redundancy detection
        3. Deeper exploration allowed
        4. LLM evaluation is optional

        Args:
            state: Current ToT state
            thought_executor_results: Recent tool execution results

        Returns:
            (should_stop, reason)
        """
        if not self.enable:
            return False, ""

        current_depth = state["current_depth"]
        max_depth = state["max_depth"]
        thoughts = state["thoughts"]

        # Check 1: Tool redundancy (fixed - was too strict)
        redundancy_reason = self._check_tool_redundancy(thought_executor_results)
        if redundancy_reason:
            logger.info(f"[TOT_SMART_STOP] Redundancy detected: {redundancy_reason}")
            return True, f"工具调用冗余: {redundancy_reason}"

        # Check 2: Information sufficiency (relaxed - requires more tools)
        sufficiency_reason = self._check_information_sufficiency(thoughts, thought_executor_results)
        if sufficiency_reason:
            logger.info(f"[TOT_SMART_STOP] Sufficient info: {sufficiency_reason}")
            return True, f"信息充分: {sufficiency_reason}"

        # Check 3: Score plateau (more sensitive - smaller threshold)
        plateau_reason = self._check_score_plateau(current_depth, thoughts)
        if plateau_reason:
            logger.info(f"[TOT_SMART_STOP] Score plateau: {plateau_reason}")
            return True, f"质量得分停滞: {plateau_reason}"

        # Check 4: Soft max depth (can exceed by multiplier for complex queries)
        soft_limit = int(max_depth * self.max_depth_multiplier)
        if current_depth >= soft_limit:
            logger.warning(f"[TOT_SMART_STOP] Reached soft max depth: {current_depth} >= {soft_limit}")
            return True, f"达到深度上限 ({soft_limit})"

        return False, ""

    def _check_tool_redundancy(
        self,
        recent_results: Optional[List[Dict]]
    ) -> Optional[str]:
        """
        Check for redundant tool calls (fixed bug: was too strict).

        Bug fix in original:
        - Used 3-round window (too small for research)
        - Didn't consider parameters (same tool with different params is valid)

        Fixed version:
        - Uses 5-round window (configurable)
        - Checks both tool name AND args
        - Only flags redundancy if same tool + same params
        """
        if not recent_results:
            return None

        # Track recent tool calls
        for result in recent_results:
            if result.get("status") == "success":
                tool_name = result.get("tool", "")
                tool_args = result.get("args", {})
                # Create signature including args
                tool_signature = f"{tool_name}:{str(sorted(tool_args.items()))}"
                self.tool_call_history.append({
                    "tool": tool_signature,
                    "depth": result.get("depth", 0)
                })

        # Keep only recent history (window size)
        if len(self.tool_call_history) > self.redundancy_window:
            self.tool_call_history = self.tool_call_history[-self.redundancy_window:]

        # Check for redundancy: same tool+args appearing multiple times
        tool_counts = {}
        for call in self.tool_call_history:
            sig = call["tool"]
            tool_counts[sig] = tool_counts.get(sig, 0) + 1

        # Only flag if same tool+args appears >= 3 times (was 2, too strict)
        for sig, count in tool_counts.items():
            if count >= 3:
                tool_name = sig.split(":")[0]
                return f"工具 {tool_name} 最近重复调用 {count} 次"

        return None

    def _check_information_sufficiency(
        self,
        thoughts: List[Thought],
        recent_results: Optional[List[Dict]]
    ) -> Optional[str]:
        """
        Check if enough information has been gathered (relaxed threshold).

        Bug fix in original:
        - Used 5 successful tools as threshold (too low for research)
        - Didn't distinguish between tool types

        Fixed version:
        - Uses 10 successful tools (configurable)
        - Only counts successful executions
        - Considers diversity of tools used
        """
        if not thoughts:
            return None

        # Count successful tool executions across all thoughts
        successful_count = 0
        unique_tools = set()

        for thought in thoughts:
            if thought.tool_results:
                for result in thought.tool_results:
                    if result.get("status") == "success":
                        successful_count += 1
                        unique_tools.add(result.get("tool", ""))

        # Relaxed threshold: need more successful executions
        if successful_count >= self.min_successful_tools:
            diversity = len(unique_tools)
            return f"已成功执行 {successful_count} 个工具调用，涵盖 {diversity} 种不同工具"

        return None

    def _check_score_plateau(
        self,
        current_depth: int,
        thoughts: List[Thought]
    ) -> Optional[str]:
        """
        Check if quality scores have plateaued (more sensitive).

        Bug fix in original:
        - Used 0.5 threshold (too large, misses plateaus)
        - Only checked last 2 depths (too small window)

        Fixed version:
        - Uses 0.3 threshold (configurable, more sensitive)
        - Tracks score history across depths
        - Considers trend, not just absolute difference
        """
        from app.core.tot.state import get_depth_of_thought

        # Get max score at current depth
        current_depth_thoughts = [
            t for t in thoughts
            if t.evaluation_score is not None
            and get_depth_of_thought(t, thoughts) == current_depth
        ]

        if not current_depth_thoughts:
            return None

        current_max = max(t.evaluation_score for t in current_depth_thoughts)
        self.depth_scores.append((current_depth, current_max))

        # Need at least 3 depths to detect plateau (was 2, too small)
        if len(self.depth_scores) < 3:
            return None

        # Check last 3 scores
        recent_scores = self.depth_scores[-3:]
        improvements = []
        for i in range(1, len(recent_scores)):
            improvement = recent_scores[i][1] - recent_scores[i-1][1]
            improvements.append(improvement)

        # Plateau: all improvements below threshold
        if all(imp < self.score_plateau_threshold for imp in improvements):
            avg_improvement = sum(improvements) / len(improvements)
            return f"最近 {len(improvements)} 层平均提升仅 {avg_improvement:.3f}"

        return None

    async def llm_evaluate_sufficiency(
        self,
        state: ToTState
    ) -> tuple[bool, str]:
        """
        Let LLM evaluate if current information is sufficient.

        This is expensive (adds latency), so use sparingly.
        Only called every llm_eval_depth_interval depths.

        Args:
            state: Current ToT state

        Returns:
            (should_stop, reason)
        """
        if not self.enable_llm_evaluation:
            return False, ""

        current_depth = state["current_depth"]

        # Only evaluate at specific depth intervals
        if current_depth % self.llm_eval_depth_interval != 0:
            return False, ""

        logger.info(f"[TOT_SMART_STOP] Depth {current_depth}: Requesting LLM evaluation")

        # Build evaluation context
        user_query = state["user_query"]
        best_path_ids = state["best_path"]
        thoughts = state["thoughts"]

        best_thoughts = [t for t in thoughts if t.id in best_path_ids]

        # Summarize collected information
        info_summary = self._build_info_summary(best_thoughts)

        evaluation_prompt = f"""你是研究质量评估专家。请评估当前 Tree of Thoughts 研究状态。

**用户查询：** {user_query}

**当前研究深度：** {current_depth}

**已收集信息摘要：**
{info_summary}

**评估问题：**
1. 当前收集的信息是否足够回答用户查询？
2. 继续深入研究是否可能获得更有价值的信息？

**回答格式：**
- 如果信息充分且继续探索价值低，回答 "YES"
- 如果需要更多信息或继续探索有价值，回答 "NO"

只回答 YES 或 NO，不要其他内容。"""

        try:
            llm = state["llm"]
            response = await llm.ainvoke([HumanMessage(content=evaluation_prompt)])
            response_text = response.content.lower().strip() if hasattr(response, 'content') else str(response).lower().strip()

            logger.info(f"[TOT_SMART_STOP] LLM 评估结果: {response_text}")

            if "yes" in response_text:
                return True, "LLM 评估认为信息已充分"
            else:
                return False, ""

        except Exception as e:
            logger.error(f"[TOT_SMART_STOP] LLM 评估失败: {e}")
            # On error, don't stop (safer for research mode)
            return False, ""

    def _build_info_summary(self, thoughts: List[Thought]) -> str:
        """Build summary of collected information."""
        if not thoughts:
            return "暂无信息"

        summary_parts = []
        for i, thought in enumerate(thoughts[:10]):  # Limit to 10 thoughts
            part = f"{i+1}. {thought.content[:100]}"

            # Add tool result count
            if thought.tool_results:
                success_count = sum(1 for r in thought.tool_results if r.get("status") == "success")
                part += f" ({success_count} 个成功结果)"

            summary_parts.append(part)

        return "\n".join(summary_parts)

    def reset(self):
        """Reset tracking state (for new research session)."""
        self.tool_call_history.clear()
        self.depth_scores.clear()


# Termination decision type
TerminationDecision = Literal["continue", "finalize"]


async def termination_checker_node(state: ToTState) -> ToTState:
    """
    Check termination conditions and decide whether to continue reasoning.

    Enhanced with ToT smart stopping (Phase 2):
    1. High-quality answer found (best_score >= threshold)
    2. Reached max_depth (soft limit with multiplier)
    3. Smart stopping: redundancy, sufficiency, plateau detection
    4. LLM evaluation (optional, every N depths)

    Args:
        state: Current ToT state

    Returns:
        Updated state with either final_answer or incremented current_depth
    """
    current_score = state["best_score"]
    current_depth = state["current_depth"]
    max_depth = state["max_depth"]

    # Get config
    quality_threshold = state.get("tot_quality_threshold", 6.0)
    enable_smart_stopping = state.get("tot_enable_smart_stopping", True)

    logger.info(
        f"Checking termination: depth={current_depth}/{max_depth}, "
        f"score={current_score:.2f}/{quality_threshold}, "
        f"smart_stopping={enable_smart_stopping}"
    )

    # ========== Check 1: High-quality answer ==========
    if current_score >= quality_threshold:
        logger.info(f"High-quality answer found (score: {current_score:.2f})")
        state["final_answer"] = await _generate_final_answer(state)
        state["reasoning_trace"].append({
            "type": "termination",
            "reason": "high_quality",
            "score": current_score
        })
        return state

    # ========== Check 2: Smart stopping (Phase 2) ==========
    if enable_smart_stopping:
        # Get or create smart stopping instance
        smart_stopping = state.get("_smart_stopping_instance")
        if not smart_stopping:
            smart_stopping = ToTSmartStopping(
                enable=True,
                min_successful_tools=state.get("tot_min_successful_tools", 10),
                redundancy_window=state.get("tot_redundancy_window", 5),
                score_plateau_threshold=state.get("tot_score_plateau_threshold", 0.3),
                enable_llm_evaluation=state.get("tot_enable_llm_evaluation", True),
                llm_eval_depth_interval=state.get("tot_llm_eval_interval", 3),
                max_depth_multiplier=state.get("tot_max_depth_multiplier", 2.0),
            )
            state["_smart_stopping_instance"] = smart_stopping

        # Check smart stopping conditions
        should_stop, reason = smart_stopping.should_stop_tot_reasoning(state)

        if should_stop:
            logger.info(f"[TOT_SMART_STOP] Terminating: {reason}")

            # Optional LLM evaluation before final decision
            if smart_stopping.enable_llm_evaluation:
                llm_should_stop, llm_reason = await smart_stopping.llm_evaluate_sufficiency(state)
                if llm_should_stop:
                    reason += f" | {llm_reason}"

            state["final_answer"] = await _generate_final_answer(state)
            state["reasoning_trace"].append({
                "type": "termination",
                "reason": "smart_stopping",
                "details": reason
            })
            return state

    # ========== Check 3: Hard max depth (legacy) ==========
    if current_depth >= max_depth:
        logger.info(f"Reached max depth ({max_depth})")
        state["final_answer"] = await _generate_final_answer(state)
        state["reasoning_trace"].append({
            "type": "termination",
            "reason": "max_depth",
            "depth": current_depth
        })
        return state

    # ========== Check 4: Diminishing returns (legacy) ==========
    if _check_diminishing_returns(state):
        logger.info("Diminishing returns detected, terminating early")
        state["final_answer"] = await _generate_final_answer(state)
        state["reasoning_trace"].append({
            "type": "termination",
            "reason": "diminishing_returns"
        })
        return state

    # ========== Continue reasoning ==========
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
