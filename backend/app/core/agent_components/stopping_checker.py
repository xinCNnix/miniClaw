"""
Smart Stopping Checker

检查 Agent 是否应提前终止。

Author: Task 3.1 Implementation
"""

import logging
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class SmartStoppingChecker:
    """
    智能停止检查器

    职责：
    - 检查工具执行结果
    - 评估任务完成度
    - 决定是否应提前终止
    - 生成最终响应（如果需要停止）
    """

    def __init__(self, llm: Any, max_rounds: int = 3) -> None:
        """
        初始化检查器

        Args:
            llm: LLM 实例（用于停止判断）
            max_rounds: 最大轮次限制
        """
        self.llm = llm
        self.max_rounds = max_rounds
        logger.info(f"[STOPPING] Initialized SmartStoppingChecker (max_rounds={max_rounds})")

    async def check_before_execution(
        self,
        tool_calls: list[dict],
        settings: Any,
        round_num: int,
        user_message: str
    ) -> tuple[bool, str]:
        """
        工具执行前检查是否应该停止

        Args:
            tool_calls: 工具调用列表
            settings: 配置对象
            round_num: 当前轮次
            user_message: 用户消息

        Returns:
            (should_stop, reason)
        """
        from app.core.smart_stopping import should_stop_before_execution

        for tool_call in tool_calls:
            tool_name = tool_call.get('name', '')
            tool_args = tool_call.get('args', {})

            should_stop, stop_reason = should_stop_before_execution(
                settings=settings,
                round_count=round_num,
                tool_name=tool_name,
                tool_args=tool_args,
                user_message=user_message
            )

            if should_stop:
                logger.warning(f"[SMART_STOP] {stop_reason}")
                logger.warning(f"[SMART_STOP] Forcing stop before execution")
                return True, stop_reason

        return False, ""

    async def check_and_respond(
        self,
        tool_calls: list[dict],
        settings: Any,
        round_num: int,
        user_message: str,
        messages: list[dict]
    ) -> AsyncIterator[dict]:
        """
        检查是否应该停止，如果需要则生成最终响应

        Args:
            tool_calls: 工具调用列表
            settings: 配置对象
            round_num: 当前轮次
            user_message: 用户消息
            messages: LangChain 消息列表

        Yields:
            事件字典（仅当需要停止时）
        """
        should_stop, reason = await self.check_before_execution(
            tool_calls, settings, round_num, user_message
        )

        if should_stop:
            # 生成最终响应
            try:
                final_response = await self.llm.ainvoke(messages)
                if hasattr(final_response, 'content') and final_response.content:
                    yield {
                        "type": "content_delta",
                        "content": final_response.content,
                    }
            except Exception as e:
                logger.error(f"[STOPPING] Failed to generate final response: {e}")
                yield {
                    "type": "error",
                    "error": f"Failed to generate response: {str(e)}"
                }
        # 如果不停止，不 yield 任何内容

    async def should_stop(
        self,
        messages: list[dict],
        tool_results: list[dict],
        round_num: int
    ) -> tuple[bool, str]:
        """
        检查是否应停止

        Args:
            messages: 对话消息历史
            tool_results: 工具执行结果列表
            round_num: 当前轮次

        Returns:
            (should_stop, reason) - 是否停止及原因
        """
        # 检查 1: 是否达到最大轮次（优先检查）
        if round_num >= self.max_rounds:
            return True, "max_rounds_reached"

        # 检查 2: 是否有严重错误
        if self._has_critical_errors(tool_results):
            return True, "critical_errors"

        # 检查 3: 任务是否完成
        if self._is_task_complete(tool_results):
            return True, "task_complete"

        # 检查 4: 使用现有 SmartStopping 系统
        try:
            from app.core.smart_stopping import SmartStoppingChecker as ExistingChecker
            checker = ExistingChecker(self.llm)
            result = await checker.check(messages, tool_results)

            if result.should_stop:
                return True, result.reason or "smart_stopping_triggered"
        except Exception as e:
            logger.warning(f"[STOPPING] Failed to check smart stopping: {e}")

        # 默认继续
        return False, "continue"

    def _has_critical_errors(self, tool_results: list[dict]) -> bool:
        """
        检查是否有严重错误

        Args:
            tool_results: 工具执行结果

        Returns:
            是否有严重错误
        """
        for result in tool_results:
            if result.get("status") == "error":
                error = result.get("error", "")
                # 检查是否为严重错误
                if self._is_critical_error(error):
                    logger.error(f"[STOPPING] Critical error detected: {error}")
                    return True
        return False

    def _is_critical_error(self, error: str) -> bool:
        """
        判断错误是否为严重错误

        Args:
            error: 错误消息

        Returns:
            是否为严重错误
        """
        # 定义严重错误列表
        critical_patterns = [
            "authentication",
            "permission",
            "access denied",
            "fatal",
        ]
        error_lower = error.lower()
        return any(pattern in error_lower for pattern in critical_patterns)

    def _is_task_complete(self, tool_results: list[dict]) -> bool:
        """
        检查任务是否完成

        Args:
            tool_results: 工具执行结果

        Returns:
            任务是否完成
        """
        # 任务完成的判断需要更保守
        # 目前只检查是否所有工具都成功且有明确的完成信号
        if not tool_results:
            return False

        # 检查是否有明确的完成信号
        for result in tool_results:
            if result.get("status") == "success":
                output = str(result.get("output", "") or result.get("result", ""))
                # 检查是否包含完成信号
                if any(signal in output.lower() for signal in [
                    "task complete",
                    "done",
                    "finished",
                    "completed",
                    "success"
                ]):
                    return True

        # 默认不认为任务完成（需要更明确的信号）
        return False
