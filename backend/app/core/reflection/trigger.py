"""
Reflection Trigger - 分层反思触发器

确保 LLM 微观评估和 Agent 宏观反思的触发时机不重叠。

设计原则：
1. LLM 微观评估：执行中、高频、仅用于决策（不持久化）
2. Agent 宏观反思：执行后、低频、写入记忆（持久化）

关键约束：
- 两种触发必须互斥，不能同时发生
- 微观评估专注于实时决策支持
- 宏观反思专注于长期学习和改进
"""

import logging
from typing import Literal, Optional

from app.core.tot.state import ToTState

logger = logging.getLogger(__name__)


TriggerType = Literal[
    "micro_evaluation",  # LLM 层：执行中的实时评估
    "macro_reflection",  # Agent 层：执行后的完整反思
]


class ReflectionTrigger:
    """
    反思触发器 - 确保分层不重叠

    职责：
    1. 判断何时触发 LLM 微观评估
    2. 判断何时触发 Agent 宏观反思
    3. 确保两种触发互斥

    触发规则：
    - LLM 微观评估：
      * 时机：执行过程中
      * 频率：高频（如每 3 层深度）
      * 目的：实时决策支持
      * 持久化：否

    - Agent 宏观反思：
      * 时机：执行完成后
      * 频率：低频（仅执行后或低质量时）
      * 目的：长期学习和改进
      * 持久化：是
    """

    def __init__(
        self,
        # 微观评估配置
        micro_eval_interval: int = 3,  # 每 N 层深度评估一次
        micro_eval_min_depth: int = 1,  # 最小深度才开始评估
        # 宏观反思配置
        macro_quality_threshold: float = 6.0,  # 质量低于此阈值触发反思
        macro_always_reflect_on_complete: bool = True,  # 执行完成后总是反思
    ):
        """
        初始化反思触发器

        Args:
            micro_eval_interval: 微观评估间隔（深度）
            micro_eval_min_depth: 微观评估最小深度
            macro_quality_threshold: 宏观反思质量阈值
            macro_always_reflect_on_complete: 执行完成后是否总是反思
        """
        self.micro_eval_interval = micro_eval_interval
        self.micro_eval_min_depth = micro_eval_min_depth
        self.macro_quality_threshold = macro_quality_threshold
        self.macro_always_reflect_on_complete = macro_always_reflect_on_complete

        logger.info(
            f"ReflectionTrigger initialized: "
            f"micro_interval={micro_eval_interval}, "
            f"macro_threshold={macro_quality_threshold}"
        )

    def should_trigger_micro_evaluation(
        self,
        current_depth: int,
        eval_interval: int | None = None,
    ) -> bool:
        """
        判断是否应触发 LLM 微观评估

        触发条件：
        1. 达到最小深度要求
        2. 当前深度是评估间隔的倍数

        特点：
        - 高频触发（如每 3 层）
        - 仅用于实时决策
        - 不写入记忆

        Args:
            current_depth: 当前深度
            eval_interval: 评估间隔（覆盖默认值）

        Returns:
            是否触发微观评估

        Examples:
            >>> trigger = ReflectionTrigger(micro_eval_interval=3)
            >>> trigger.should_trigger_micro_evaluation(0)
            False
            >>> trigger.should_trigger_micro_evaluation(3)
            True
            >>> trigger.should_trigger_micro_evaluation(4)
            False
        """
        interval = eval_interval or self.micro_eval_interval

        # 检查最小深度
        if current_depth < self.micro_eval_min_depth:
            logger.debug(
                f"Micro eval: depth {current_depth} < min {self.micro_eval_min_depth}, skip"
            )
            return False

        # 检查间隔
        should_trigger = current_depth % interval == 0

        if should_trigger:
            logger.info(
                f"[TRIGGER] Micro evaluation at depth {current_depth} "
                f"(interval: {interval})"
            )

        return should_trigger

    def should_trigger_macro_reflection(
        self,
        execution_complete: bool = False,
        quality_score: float | None = None,
        force_reflection: bool = False,
    ) -> bool:
        """
        判断是否应触发 Agent 宏观反思

        触发条件：
        1. 执行完成（execution_complete=True）
        2. 质量分数低于阈值（quality_score < threshold）
        3. 强制反思（force_reflection=True）

        特点：
        - 低频触发（仅执行后）
        - 写入记忆用于长期学习
        - 与微观评估互斥

        Args:
            execution_complete: 执行是否完成
            quality_score: 质量分数（可选）
            force_reflection: 强制反思（用于测试或特殊情况）

        Returns:
            是否触发宏观反思

        Examples:
            >>> trigger = ReflectionTrigger(macro_quality_threshold=6.0)
            >>> trigger.should_trigger_macro_reflection(execution_complete=True)
            True
            >>> trigger.should_trigger_macro_reflection(quality_score=4.0)
            True
            >>> trigger.should_trigger_macro_reflection(quality_score=7.0)
            False
        """
        # 强制反思（测试用）
        if force_reflection:
            logger.warning("[TRIGGER] Macro reflection: forced")
            return True

        # 执行完成后总是反思
        if execution_complete and self.macro_always_reflect_on_complete:
            logger.info("[TRIGGER] Macro reflection: execution complete")
            return True

        # 质量低于阈值时反思
        if quality_score is not None:
            if quality_score < self.macro_quality_threshold:
                logger.info(
                    f"[TRIGGER] Macro reflection: quality {quality_score:.2f} "
                    f"< threshold {self.macro_quality_threshold}"
                )
                return True

        return False

    def validate_no_overlap(
        self,
        micro_trigger: bool,
        macro_trigger: bool,
    ) -> bool:
        """
        验证微观和宏观触发不重叠

        Args:
            micro_trigger: 微观评估是否触发
            macro_trigger: 宏观反思是否触发

        Returns:
            是否有效（不重叠）

        Raises:
            ValueError: 如果检测到重叠
        """
        if micro_trigger and macro_trigger:
            raise ValueError(
                "CRITICAL: Micro and macro triggers cannot fire simultaneously! "
                "This violates the layered reflection design."
            )

        return True


# ============================================================================
# 单例模式
# ============================================================================

_trigger: ReflectionTrigger | None = None


def get_reflection_trigger() -> ReflectionTrigger:
    """获取反思触发器单例"""
    global _trigger
    if _trigger is None:
        from app.config import settings

        _trigger = ReflectionTrigger(
            micro_eval_interval=getattr(settings, "tot_llm_eval_interval", 3),
            micro_eval_min_depth=1,
            macro_quality_threshold=getattr(settings, "tot_quality_threshold", 6.0),
            macro_always_reflect_on_complete=True,
        )

    return _trigger


def reset_reflection_trigger():
    """重置反思触发器（主要用于测试）"""
    global _trigger
    _trigger = None
    logger.info("ReflectionTrigger reset")
