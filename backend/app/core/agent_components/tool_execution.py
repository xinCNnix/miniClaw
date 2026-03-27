"""
Tool Execution Strategies

定义工具执行策略：串行或并发。

Author: Task 3.1 Implementation
Created: 2026-03-22
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.core.exceptions import ToolExecutionError

logger = logging.getLogger(__name__)


class ToolExecutionStrategy(ABC):
    """工具执行策略接口"""

    @abstractmethod
    async def execute(
        self,
        tool_calls: list[dict],
        context: dict
    ) -> list[dict]:
        """
        执行工具并返回结果

        Args:
            tool_calls: 工具调用列表
            context: 执行上下文

        Returns:
            工具执行结果列表
        """
        pass


class SerialExecutionStrategy(ToolExecutionStrategy):
    """串行执行工具（逐个执行）"""

    async def execute(
        self,
        tool_calls: list[dict],
        context: dict
    ) -> list[dict]:
        """串行执行所有工具"""
        results = []

        for tool_call in tool_calls:
            try:
                result = await self._execute_single(tool_call, context)
                results.append({
                    "tool_call": tool_call,
                    "result": result,
                    "status": "success"
                })
                logger.info(f"[SERIAL] Tool {tool_call.get('name')} succeeded")

            except Exception as e:
                logger.error(f"[SERIAL] Tool {tool_call.get('name')} failed: {e}")
                results.append({
                    "tool_call": tool_call,
                    "error": str(e),
                    "status": "error"
                })

        return results

    async def _execute_single(
        self,
        tool_call: dict,
        context: dict
    ) -> Any:
        """
        执行单个工具

        TODO: Day 2 - 实现实际工具执行逻辑
        目前返回模拟结果
        """
        tool_name = tool_call.get('name')
        args = tool_call.get('args', {})

        # Validate tool name
        if not tool_name:
            raise ValueError("Tool name is required")

        logger.debug(f"[SERIAL] Executing {tool_name} with args: {args}")

        # TODO: 集成实际工具执行
        # from app.tools import get_tool_by_name
        # tool = get_tool_by_name(tool_name)
        # result = await tool.ainvoke(args)

        # Mock result for now
        await asyncio.sleep(0.01)  # Simulate async work
        return {"mock_result": f"Executed {tool_name}"}


class ConcurrentExecutionStrategy(ToolExecutionStrategy):
    """并发执行独立工具"""

    async def execute(
        self,
        tool_calls: list[dict],
        context: dict
    ) -> list[dict]:
        """
        并发执行工具

        策略：
        1. 检测工具依赖关系
        2. 并发执行独立工具
        3. 串行执行依赖工具
        """
        # 分离独立和依赖工具
        independent = self._find_independent_tools(tool_calls)
        dependent = self._find_dependent_tools(tool_calls)

        logger.info(f"[CONCURRENT] Independent: {len(independent)}, Dependent: {len(dependent)}")

        results = []

        # 并发执行独立工具
        if independent:
            independent_results = await asyncio.gather(*[
                self._execute_single_concurrent(tc, context)
                for tc in independent
            ], return_exceptions=True)

            for i, result in enumerate(independent_results):
                if isinstance(result, Exception):
                    results.append({
                        "tool_call": independent[i],
                        "error": str(result),
                        "status": "error"
                    })
                else:
                    results.append(result)

        # 串行执行依赖工具
        for tool_call in dependent:
            try:
                result = await self._execute_single(tool_call, context)
                results.append({
                    "tool_call": tool_call,
                    "result": result,
                    "status": "success"
                })
            except Exception as e:
                results.append({
                    "tool_call": tool_call,
                    "error": str(e),
                    "status": "error"
                })

        return results

    async def _execute_single_concurrent(
        self,
        tool_call: dict,
        context: dict
    ) -> dict:
        """并发执行单个工具"""
        try:
            result = await self._execute_single(tool_call, context)
            return {
                "tool_call": tool_call,
                "result": result,
                "status": "success"
            }
        except Exception as e:
            raise ToolExecutionError(
                f"Tool {tool_call.get('name')} failed",
                context={"tool_call": tool_call, "error": str(e)}
            ) from e

    async def _execute_single(
        self,
        tool_call: dict,
        context: dict
    ) -> Any:
        """执行单个工具（与 Serial 共享实现）"""
        # TODO: 实现实际工具执行
        tool_name = tool_call.get('name')

        # Validate tool name
        if not tool_name:
            raise ValueError("Tool name is required")

        await asyncio.sleep(0.01)
        return {"mock_result": f"Concurrent {tool_name}"}

    def _find_independent_tools(self, tool_calls: list[dict]) -> list[dict]:
        """查找独立工具（无依赖）"""
        # TODO: 实现依赖检测
        # 目前假设所有工具独立
        return tool_calls

    def _find_dependent_tools(self, tool_calls: list[dict]) -> list[dict]:
        """查找依赖工具"""
        # TODO: 实现依赖检测
        return []
