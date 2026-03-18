"""
智能停止功能 - 紧急修复

这个模块实现智能工具停止机制，防止无限制的工具调用循环
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SmartToolStopping:
    """
    智能工具停止机制

    功能：
    1. 检测冗余工具调用（同样的工具重复调用）
    2. 评估信息充分性（是否已经有足够信息回答）
    3. 强制停止不必要的工具调用
    """

    def __init__(
        self,
        redundancy_window: int = 3,
        sufficiency_interval: int = 2,
        enable: bool = True
    ):
        """
        初始化智能停止机制

        Args:
            redundancy_window: 检测冗余的窗口大小
            sufficiency_interval: 评估充分性的间隔
            enable: 是否启用
        """
        self.redundancy_window = redundancy_window
        self.sufficiency_interval = sufficiency_interval
        self.enable = enable

        # 追踪工具调用历史
        self.tool_history: List[str] = []

    def should_stop_tool_calling(
        self,
        round_count: int,
        tool_name: str,
        tool_args: Dict,
        user_message: str,
        current_round_time: float
    ) -> tuple[bool, str]:
        """
        判断是否应该停止工具调用

        Returns:
            (should_stop, reason)
        """
        if not self.enable:
            return False, ""

        # 检查 1: 简单问候不应该调用工具
        if self._is_simple_greeting(user_message):
            if round_count == 0 and tool_name:
                return True, "简单问候不需要工具调用"

        # 检查 2: 检测冗余工具调用
        if self._is_redundant_tool_call(tool_name, tool_args):
            return True, f"工具 {tool_name} 重复调用（最近 {self.redundancy_window} 轮内已使用）"

        # 检查 3: 评估信息充分性
        if round_count >= self.sufficiency_interval:
            if self._has_sufficient_info(round_count, tool_name):
                return True, f"已执行 {round_count} 轮，信息已充分，应该生成回答"

        # 检查 4: 避免无限探索
        if round_count >= 5:
            return True, f"已达到 {round_count} 轮工具调用，避免过度探索"

        return False, ""

    def _is_simple_greeting(self, message: str) -> bool:
        """检测是否为简单问候"""
        message_lower = message.lower().strip()

        # 简单问候关键词
        greetings = [
            "你好", "hi", "hello", "嗨", "早上好", "下午好", "晚上好",
            "在吗", "在不在", "你是谁", "what's up", "sup"
        ]

        # 去除空格和标点
        import re
        clean_message = re.sub(r'[^\w\u4e00-\u9fff]', '', message_lower)

        for greeting in greetings:
            if greeting in clean_message:
                return True

        return False

    def _is_redundant_tool_call(self, tool_name: str, tool_args: Dict) -> bool:
        """检测冗余工具调用"""
        # 添加到历史
        self.tool_history.append(tool_name)

        # 检查窗口内是否重复
        recent_tools = self.tool_history[-self.redundancy_window:]

        # 同一个工具在窗口内使用超过 2 次
        if recent_tools.count(tool_name) > 2:
            logger.warning(f"[SMART_STOP] 检测到冗余工具调用: {tool_name}")
            return True

        return False

    def _has_sufficient_info(self, round_count: int, current_tool: str) -> bool:
        """评估是否已有足够信息"""
        # 如果已经执行了 3 轮以上的工具调用
        if round_count >= 3:
            # 如果当前还在"探索类"工具（terminal, read_file）
            exploring_tools = ["terminal", "read_file", "search_kb"]
            if current_tool in exploring_tools:
                logger.warning(f"[SMART_STOP] 过度探索：第 {round_count} 轮仍在使用探索类工具")
                return True

        return False


# 便捷函数
def should_stop_tool_calling(
    settings,
    round_count: int,
    tool_name: str,
    tool_args: Dict,
    user_message: str,
    current_round_time: float
) -> tuple[bool, str]:
    """
    包装函数，便于在 agent.py 中调用
    """
    if not settings.enable_smart_stopping:
        return False, ""

    stopper = SmartToolStopping(
        redundancy_window=settings.redundancy_detection_window,
        sufficiency_interval=settings.sufficiency_evaluation_interval,
        enable=True
    )

    return stopper.should_stop_tool_calling(
        round_count, tool_name, tool_args, user_message, current_round_time
    )
