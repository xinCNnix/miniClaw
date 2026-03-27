"""
Agent Components

模块化的 Agent 组件，用于重构 astream 方法。

Components:
- ToolCallAssembler: 组装工具调用
- AgentStreamCoordinator: 协调流式响应
- ToolExecutionStrategy: 工具执行策略
- ToolRoundExecutor: 工具轮次执行
- SmartStoppingChecker: 智能停止检查
- ErrorTracker: 错误追踪

Author: Task 3.1 Implementation
Created: 2026-03-22
"""

from .error_tracker import ErrorTracker
from .round_executor import ToolRoundExecutor
from .stopping_checker import SmartStoppingChecker
from .stream_coordinator import AgentStreamCoordinator
from .tool_assembler import ToolCallAssembler
from .tool_execution import (
    ConcurrentExecutionStrategy,
    SerialExecutionStrategy,
    ToolExecutionStrategy,
)

__all__ = [
    "ToolCallAssembler",
    "AgentStreamCoordinator",
    "ToolExecutionStrategy",
    "SerialExecutionStrategy",
    "ConcurrentExecutionStrategy",
    "ToolRoundExecutor",
    "SmartStoppingChecker",
    "ErrorTracker",
]
