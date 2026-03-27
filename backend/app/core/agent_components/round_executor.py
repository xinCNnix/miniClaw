"""
Tool Round Executor

执行单轮工具调用。

Author: Task 3.1 Implementation
Created: 2026-03-22
"""

import logging
import time
from typing import Any, AsyncIterator

from langchain_core.messages import ToolMessage

from .tool_execution import SerialExecutionStrategy, ToolExecutionStrategy
from app.core.performance_tracker import get_performance_tracker

logger = logging.getLogger(__name__)


class ToolRoundExecutor:
    """
    工具轮次执行器

    职责：
    - 管理执行策略
    - 执行一轮工具调用（串行/并发）
    - 追踪执行结果
    - 产生流式事件
    """

    def __init__(
        self,
        strategy: ToolExecutionStrategy | None = None,
        tools_map: dict[str, Any] | None = None,
        tool_executor: Any = None
    ) -> None:
        """
        初始化执行器

        Args:
            strategy: 执行策略（默认串行）
            tools_map: 工具名称到工具实例的映射
            tool_executor: 实际的工具执行器（AgentManager._aexecute_tool）
        """
        self.strategy = strategy or SerialExecutionStrategy()
        self.tools_map = tools_map or {}
        self.tool_executor = tool_executor

    async def execute_round(
        self,
        tool_calls: list[dict],
        context: dict
    ) -> list[dict]:
        """
        执行一轮工具调用

        Args:
            tool_calls: 工具调用列表
            context: 执行上下文

        Returns:
            执行结果列表
        """
        logger.info(f"[EXECUTOR] Executing round: {len(tool_calls)} tools")

        # 使用策略执行
        results = await self.strategy.execute(tool_calls, context)

        # 记录结果
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = len(results) - success_count

        logger.info(f"[EXECUTOR] Round complete: {success_count} success, {error_count} errors")

        return results

    def set_strategy(self, strategy: ToolExecutionStrategy) -> None:
        """切换执行策略"""
        self.strategy = strategy
        logger.info(f"[EXECUTOR] Strategy changed to {strategy.__class__.__name__}")

    def select_execution_mode(
        self,
        tool_calls: list[dict],
        settings: Any
    ) -> str:
        """
        选择执行模式

        Args:
            tool_calls: 工具调用列表
            settings: 配置对象

        Returns:
            'concurrent' 或 'serial'
        """
        if settings.enable_parallel_tool_execution and len(tool_calls) > 1:
            return "concurrent"
        return "serial"

    async def execute_tools_serial(
        self,
        tool_calls: list[dict],
        lc_messages: list[dict],
        context: dict,
        error_tracker: Any = None
    ) -> AsyncIterator[dict]:
        """
        串行执行工具并产生流式事件

        这个方法包含所有串行执行逻辑，从 astream 移动到这里。

        Args:
            tool_calls: 工具调用列表
            lc_messages: LangChain 消息列表（将被修改）
            context: 执行上下文（包含 round_num）
            error_tracker: 错误追踪器

        Yields:
            流式事件字典
        """
        round_num = context.get("round_num", 0)
        perf_tracker = get_performance_tracker()

        for idx, tool_call in enumerate(tool_calls):
            tool_name = tool_call.get('name', '')
            tool_args = tool_call.get('args', {})
            tool_id = tool_call.get('id', '')

            # 🔧 Debug: Log tool_args type
            logger.debug(f"[Round {round_num + 1}] Tool call {idx+1}: name={tool_name}, args_type={type(tool_args).__name__}, args={tool_args}")

            # 🔧 Fix: Ensure args is a dict, not a string
            if isinstance(tool_args, str):
                try:
                    import json
                    tool_args = json.loads(tool_args)
                    logger.debug(f"[Round {round_num + 1}] Parsed tool_args from string to dict")
                except json.JSONDecodeError:
                    logger.error(f"[Round {round_num + 1}] Failed to parse tool_args as JSON: {tool_args}")
                    tool_args = {}

            if not tool_name:
                logger.warning(f"[Round {round_num + 1}] Skipping tool call {idx+1} with empty name")
                continue

            logger.info(f"[Round {round_num + 1}] Executing tool {idx+1}/{len(tool_calls)}: {tool_name}")

            yield {
                "type": "tool_call",
                "tool_calls": [{
                    "id": tool_id,
                    "name": tool_name,
                    "arguments": tool_args,
                }]
            }

            tool_start = time.time()
            tool_output = None  # Initialize before try block
            try:
                # 使用实际的工具执行器
                if self.tool_executor:
                    tool_output = await self.tool_executor(tool_name, tool_args)
                else:
                    # Fallback: 尝试从 context 获取
                    raise Exception("No tool executor available")

                tool_duration = time.time() - tool_start

                perf_tracker._record_success(f"tool_{tool_name}", tool_duration)
                logger.info(f"[Round {round_num + 1}] Tool {tool_name} completed in {tool_duration:.2f}s")

                yield {
                    "type": "tool_output",
                    "tool_name": tool_name,
                    "output": str(tool_output),
                    "status": "success",
                }
            except Exception as e:
                tool_duration = time.time() - tool_start
                perf_tracker._record_failure(f"tool_{tool_name}", tool_duration, str(e))
                if error_tracker:
                    error_tracker.track_error(e, {"tool": tool_name, "round": round_num})

                logger.error(f"[Round {round_num + 1}] Tool {tool_name} failed: {e}")
                yield {
                    "type": "tool_output",
                    "tool_name": tool_name,
                    "output": str(e),
                    "status": "error",
                }

            # 添加工具结果到对话历史
            lc_messages.append(ToolMessage(
                content=str(tool_output),
                tool_call_id=tool_id
            ))
