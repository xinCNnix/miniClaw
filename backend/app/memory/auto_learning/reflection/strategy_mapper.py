"""Strategy mapper for Action ID to prompt template mapping.

This module provides a mapping between discrete action IDs and
strategy prompt templates for agent behavior control.
"""

import logging
import random

logger = logging.getLogger(__name__)


# Action ID → Prompt mapping
# 20 total strategies covering different aspects of agent behavior
ACTION_PROMPT_MAP = {
    0: "简洁直接地回答。",
    1: "分步骤详细解释。",
    2: "优先使用可用工具收集信息。",
    3: "回答前先彻底分析问题。",
    4: "尽可能提供多种解决方案。",
    5: "谨慎回答，验证信息。",
    6: "使用代码示例说明。",
    7: "关注实用的可执行方案。",
    8: "考虑边缘情况和潜在问题。",
    9: "提供相关历史背景。",
    10: "使用类比和比喻解释复杂概念。",
    11: "先给出高概概述，再深入细节。",
    12: "引用可靠来源和文档。",
    13: "提供可视化建议（图表、流程图）。",
    14: "考虑不同用户的技术水平。",
    15: "使用结构化格式（列表、表格）。",
    16: "主动提供替代方案。",
    17: "强调关键要点和注意事项。",
    18: "提供示例和使用场景。",
    19: "总结最佳实践和常见陷阱。",
}


class StrategyMapper:
    """Maps action IDs to strategy prompt templates.

    This class provides methods to convert discrete action IDs
    (from policy network) into natural language strategy prompts
    that guide agent behavior.

    Examples:
        >>> prompt = StrategyMapper.get_prompt(0)
        >>> print(prompt)
        '简洁直接地回答。'

        >>> action_id = StrategyMapper.sample_random()
        >>> print(f"Sampled action: {action_id}")
        Sampled action: 5
    """

    @staticmethod
    def get_prompt(action_id: int) -> str:
        """Get strategy prompt for action ID.

        Args:
            action_id: Action ID (0-19)

        Returns:
            Strategy prompt string

        Raises:
            ValueError: If action_id is out of range

        Examples:
            >>> prompt = StrategyMapper.get_prompt(0)
            >>> print(prompt)
            '简洁直接地回答。'
        """
        if action_id not in ACTION_PROMPT_MAP:
            raise ValueError(
                f"Invalid action_id: {action_id}. "
                f"Must be in range [0, {len(ACTION_PROMPT_MAP) - 1}]"
            )

        return ACTION_PROMPT_MAP[action_id]

    @staticmethod
    def sample_random() -> int:
        """Sample random action ID for exploration.

        Returns:
            Random action ID in range [0, 19]

        Examples:
            >>> action_id = StrategyMapper.sample_random()
            >>> print(f"Sampled action: {action_id}")
            Sampled action: 5
        """
        return random.randint(0, len(ACTION_PROMPT_MAP) - 1)

    @staticmethod
    def get_num_actions() -> int:
        """Get total number of actions.

        Returns:
            Total number of action strategies (20)

        Examples:
            >>> num = StrategyMapper.get_num_actions()
            >>> print(num)
            20
        """
        return len(ACTION_PROMPT_MAP)

    @staticmethod
    def list_strategies() -> dict[int, str]:
        """Get all action-prompt mappings.

        Returns:
            Dictionary mapping action IDs to prompts

        Examples:
            >>> strategies = StrategyMapper.list_strategies()
            >>> for action_id, prompt in strategies.items():
            ...     print(f"{action_id}: {prompt}")
        """
        return ACTION_PROMPT_MAP.copy()


# Convenience functions for quick access
def get_strategy_prompt(action_id: int) -> str:
    """Quick function to get strategy prompt.

    Args:
        action_id: Action ID (0-19)

    Returns:
        Strategy prompt string

    Examples:
        >>> prompt = get_strategy_prompt(0)
        >>> print(prompt)
        '简洁直接地回答。'
    """
    return StrategyMapper.get_prompt(action_id)


def sample_strategy_action() -> int:
    """Quick function to sample random action.

    Returns:
        Random action ID in range [0, 19]

    Examples:
        >>> action_id = sample_strategy_action()
        >>> print(f"Sampled action: {action_id}")
        Sampled action: 5
    """
    return StrategyMapper.sample_random()


__all__ = [
    "StrategyMapper",
    "ACTION_PROMPT_MAP",
    "get_strategy_prompt",
    "sample_strategy_action",
]
