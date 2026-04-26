"""Reward model for computing scalar rewards for RL training."""

import asyncio
import logging

from langchain_core.language_models import BaseChatModel
# [DEAD CODE] 以下导入仅在已注释的 SEMANTIC_REWARD_PROMPT 和 chain 中使用
# from langchain_core.output_parsers import StrOutputParser
# from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.memory.auto_learning.reflection.models import ReflectionResult, RewardResult

logger = logging.getLogger(__name__)


# [DEAD CODE] SEMANTIC_REWARD_PROMPT 已弃用：compute_reward 现在直接使用 quality_score/10.0
# 保留以备参考
# SEMANTIC_REWARD_PROMPT = ChatPromptTemplate.from_template("""
# 你是一个AI Agent执行质量评估专家。请评估以下Agent执行的质量。
#
# 用户查询: {user_query}
#
# Agent输出: {agent_output}
#
# 反思分析:
# - 任务完成: {completed}
# - 问题: {problems}
# - 建议: {suggestions}
#
# 请评估执行质量并给出一个-1.0到1.0之间的评分：
# - 1.0: 完美执行，完全满足需求
# - 0.5 到 0.9: 良好执行，有小问题
# - 0.0 到 0.4: 基本满足，有明显问题
# - -0.5 到 -0.1: 执行失败，但有部分正确
# - -1.0: 完全失败
#
# 只返回一个数字（例如：0.75），不要其他内容：
# """)


class RewardModel:
    """Computes scalar reward for RL training.

    This model combines semantic evaluation (LLM-based) with manual
    reward shaping to compute a scalar reward for RL training.

    Attributes:
        llm: The LLM instance for semantic evaluation
        semantic_prompt: Prompt for semantic reward evaluation
        timeout: Timeout in seconds for LLM calls
    """

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        # [DEAD CODE] semantic_prompt 参数已弃用
        # semantic_prompt: ChatPromptTemplate = SEMANTIC_REWARD_PROMPT,
        timeout: int = 20,
    ) -> None:
        """Initialize RewardModel.

        Args:
            llm: Optional LLM instance. If None, creates default LLM
            timeout: Timeout in seconds for LLM calls (default: 20)

        Examples:
            >>> model = RewardModel()
            >>> reward = await model.compute_reward(
            ...     user_query="What is the weather?",
            ...     agent_output="The weather is sunny.",
            ...     reflection=reflection_result,
            ...     tool_metrics=tool_metrics
            ... )
        """
        self.llm = llm or self._get_default_llm()
        # [DEAD CODE] self.semantic_prompt 已弃用
        # self.semantic_prompt = semantic_prompt
        self.timeout = timeout

        # [DEAD CODE] self.chain 已弃用：compute_reward 现在使用 quality_score/10.0
        # self.chain = self.semantic_prompt | self.llm | StrOutputParser()

        logger.info(
            f"RewardModel initialized with LLM: {type(self.llm).__name__}, "
            f"timeout: {timeout}s"
        )

    def _get_default_llm(self) -> BaseChatModel:
        """Get default LLM instance.

        Returns:
            Configured ChatOpenAI instance
        """
        try:
            # Try to import from miniclaw
            from app.core.llm import get_default_llm as miniclaw_get_llm

            return miniclaw_get_llm()
        except ImportError:
            # Fallback: create a simple ChatOpenAI instance
            logger.warning(
                "miniclaw LLM module not available, using default ChatOpenAI."
            )
            settings = get_settings()

            api_key = getattr(settings, "openai_api_key", None)
            base_url = getattr(settings, "openai_base_url", None)
            model = getattr(settings, "openai_model", "gpt-4o-mini")

            return ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=0.1,
                max_tokens=50,
            )

    async def compute_reward(
        self,
        user_query: str,
        agent_output: str,
        reflection: ReflectionResult,
        tool_metrics,
    ) -> RewardResult:
        """Compute reward (-1.0 to 1.0).

        Combines semantic reward (LLM-based) and shaping reward (manual)
        to compute the total reward.

        **Phase 3.3 Update:** Now binds to quality_score from reflection.

        Formula:
        - semantic_reward = reflection.quality_score / 10.0 (normalized to [0, 1])
        - Apply failure type penalties
        - total_reward = semantic_reward * 0.7 + shaping_reward * 0.3

        Args:
            user_query: Original user query
            agent_output: Agent's output response
            reflection: Reflection analysis result (must include quality_score)
            tool_metrics: ToolMetrics instance

        Returns:
            RewardResult with total reward and breakdown

        Raises:
            asyncio.TimeoutError: If LLM call times out
            ValueError: If reward parsing fails

        Examples:
            >>> model = RewardModel()
            >>> reward = await model.compute_reward(
            ...     user_query="What is the weather?",
            ...     agent_output="The weather is sunny.",
            ...     reflection=reflection_result,
            ...     tool_metrics=tool_metrics
            ... )
            >>> print(reward.total_reward)
            0.75
        """
        # ============================================================
        # Step 1: Compute semantic reward (based on quality_score)
        # ============================================================

        semantic_reward = reflection.quality_score / 10.0  # Normalize to [0, 1]

        # Apply failure type penalties
        if reflection.failure_type == "tool_error":
            semantic_reward *= 0.5  # Tool error penalty
        elif reflection.failure_type == "planning_error":
            semantic_reward *= 0.7  # Planning error penalty
        elif reflection.failure_type == "information_gap":
            semantic_reward *= 0.8  # Information gap minor penalty

        # ============================================================
        # Step 2: Compute shaping reward (manual)
        # ============================================================

        shaping_reward, breakdown = self._compute_shaping_reward(
            reflection, tool_metrics
        )

        # ============================================================
        # Step 3: Combine rewards
        # ============================================================

        total_reward = semantic_reward * 0.7 + shaping_reward * 0.3

        # Clamp to [-1.0, 1.0]
        total_reward = max(-1.0, min(1.0, total_reward))

        # Add breakdown
        breakdown["quality_score"] = reflection.quality_score
        breakdown["failure_type"] = reflection.failure_type
        breakdown["semantic_reward"] = semantic_reward
        breakdown["shaping_reward"] = shaping_reward
        breakdown["total_reward"] = total_reward

        logger.info(
            f"Reward computed: total={total_reward:.3f}, "
            f"semantic={semantic_reward:.3f}, shaping={shaping_reward:.3f}, "
            f"quality_score={reflection.quality_score:.1f}, "
            f"failure_type={reflection.failure_type}"
        )

        return RewardResult(
            total_reward=total_reward,
            semantic_reward=semantic_reward,
            shaping_reward=shaping_reward,
            breakdown=breakdown,
        )

    # [DEAD CODE] _compute_semantic_reward 已弃用：compute_reward 现在直接使用 quality_score/10.0
    # 保留以备参考
    # async def _compute_semantic_reward(
    #     self,
    #     user_query: str,
    #     agent_output: str,
    #     reflection: ReflectionResult,
    # ) -> float:
    #     """Compute semantic reward using LLM."""
    #     try:
    #         problems_str = "; ".join(reflection.problems) if reflection.problems else "无"
    #         suggestions_str = (
    #             "; ".join(reflection.suggestions) if reflection.suggestions else "无"
    #         )
    #         result_str = await asyncio.wait_for(
    #             self.chain.ainvoke(
    #                 {
    #                     "user_query": user_query,
    #                     "agent_output": agent_output,
    #                     "completed": "是" if reflection.completed else "否",
    #                     "problems": problems_str,
    #                     "suggestions": suggestions_str,
    #                 }
    #             ),
    #             timeout=self.timeout,
    #         )
    #         reward = float(result_str.strip())
    #         reward = max(-1.0, min(1.0, reward))
    #         logger.debug(f"Semantic reward: {reward:.3f}")
    #         return reward
    #     except asyncio.TimeoutError:
    #         logger.warning("Semantic reward computation timed out")
    #         return 0.5 if reflection.completed else 0.0
    #     except (ValueError, IndexError) as e:
    #         logger.warning(f"Failed to parse semantic reward: {e}")
    #         return 0.5 if reflection.completed else 0.0
    #     except Exception as e:
    #         logger.error(f"Semantic reward computation failed: {e}", exc_info=True)
    #         return 0.5 if reflection.completed else 0.0

    def _compute_shaping_reward(
        self,
        reflection: ReflectionResult,
        tool_metrics,
    ) -> tuple[float, dict]:
        """Compute manual shaping reward.

        **Phase 3.3 Update:** Improved tool metrics calculation.

        Formula:
        shaping_reward = (
            tool_success_rate * 0.5 +
            tool_diversity_bonus * 0.3 +
            success_bonus * 0.2
        )

        Args:
            reflection: Reflection analysis result
            tool_metrics: ToolMetrics instance

        Returns:
            Tuple of (shaping_reward, breakdown_dict)
        """
        breakdown = {}

        # 1. Tool success rate (0.5 weight)
        if tool_metrics.total_calls > 0:
            success_rate = tool_metrics.successful_calls / tool_metrics.total_calls
        else:
            success_rate = 0.5  # No tools used, neutral default
        breakdown["tool_success_rate"] = success_rate * 0.5

        # 2. Tool diversity bonus (0.3 weight)
        # Reward using multiple different tools
        unique_tools = len(set(tool_metrics.tool_names)) if hasattr(tool_metrics, 'tool_names') else 1
        diversity_bonus = min(unique_tools * 0.1, 0.3)
        breakdown["tool_diversity_bonus"] = diversity_bonus

        # 3. Success bonus (0.2 weight)
        success_bonus = 1.0 if reflection.completed else 0.0
        breakdown["success_bonus"] = success_bonus * 0.2

        # Compute total shaping reward
        shaping_reward = (
            success_rate * 0.5 +
            diversity_bonus +
            success_bonus * 0.2
        )

        logger.debug(f"Shaping reward: {shaping_reward:.3f}, breakdown: {breakdown}")

        return shaping_reward, breakdown

    def compute_meta_policy_reward(
        self,
        advice: dict,
        actual_action: str,
        actual_tool: str | None,
        actual_skill: str | None,
        tool_success: bool,
        recent_tools: list,
        round_count: int,
        max_rounds: int,
        task_completed: bool,
    ) -> dict:
        """Compute reward for meta policy tool/skill decisions.

        Args:
            advice: Meta policy advice dict (action_type, tool, skill, confidence)
            actual_action: LLM's actual action type (CALL_TOOL/CALL_SKILL/THINK/FINISH)
            actual_tool: Tool actually used, or None
            actual_skill: Skill actually used, or None
            tool_success: Whether the tool call succeeded
            recent_tools: List of recent tool call names (for repeat detection)
            round_count: Current execution round
            max_rounds: Maximum allowed rounds
            task_completed: Whether the task completed successfully

        Returns:
            Dict with total, tool_reward, skill_reward, episode_reward
        """
        tool_reward = self._compute_tool_reward(actual_tool, tool_success, recent_tools)
        skill_reward = self._compute_skill_reward(actual_skill, tool_success, advice)
        episode_reward = self._compute_episode_reward(round_count, max_rounds, task_completed)

        total = (tool_reward + skill_reward) * 0.6 + episode_reward * 0.4

        return {
            "total": total,
            "tool_reward": tool_reward,
            "skill_reward": skill_reward,
            "episode_reward": episode_reward,
        }

    def _compute_tool_reward(
        self,
        actual_tool: str | None,
        tool_success: bool,
        recent_tools: list,
    ) -> float:
        """Compute tool selection reward.

        +1.0: Tool succeeded
        -1.0: Tool failed
        -0.3: Tool was recently repeated (indicates stuck loop)
        """
        if actual_tool is None:
            return 0.0

        if not tool_success:
            return -1.0

        # Repeat detection
        if actual_tool in recent_tools[-3:]:
            return -0.3

        return 1.0

    def _compute_skill_reward(
        self,
        actual_skill: str | None,
        tool_success: bool,
        advice: dict,
    ) -> float:
        """Compute skill selection reward.

        +1.5: Skill used and succeeded (skills are higher value than raw tools)
        -0.5: Skill used but failed
        -1.0: Skill suggested but not used (missed opportunity)
        -0.3: Skill used for simple task (overkill)
        """
        if actual_skill is None:
            # Check if a skill was suggested but not used
            if advice.get("skill") and advice.get("action_type") == "CALL_SKILL":
                return -1.0  # Missed opportunity
            return 0.0

        if not tool_success:
            return -0.5

        return 1.5

    def _compute_episode_reward(
        self,
        round_count: int,
        max_rounds: int,
        task_completed: bool,
    ) -> float:
        """Compute episode-level reward.

        +5.0: Task completed
        -2.0: Task not completed
        -3.0: Exceeded max rounds
        """
        if task_completed:
            return 5.0
        if round_count >= max_rounds:
            return -3.0
        return -2.0


__all__ = ["RewardModel"]
