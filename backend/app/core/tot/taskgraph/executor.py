"""
TaskExecutor — 任务执行器，分发 direct/beam_search/research 三种模式。

direct 模式: 顺序执行 tool_plan 中的工具调用，记录每次工具调用的详细轨迹。
beam_search: 后续集成现有 ToT beam search 子图
research: 后续集成现有 ToT research 13 节点子图
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from app.core.tot.taskgraph.models import TaskNode, ToolPlanItem
from app.core.tot.taskgraph.trajectory import TaskGraphTrajectory, ToolCallTrace

# 单任务整体超时（秒），防止单个任务卡死整个管线
_TASK_TIMEOUT = 180

logger = logging.getLogger(__name__)

_DEPENDENT_TOOLS = {"python_repl", "write_file", "terminal"}

# 工具参数映射：当工具 A 的参数被错误传给工具 B 时，通过此表重映射
# key = 目标工具名, value = {源参数名: 目标参数名}
_TOOL_ARG_MAP: Dict[str, Dict[str, str]] = {
    "terminal": {"query": "command"},
    "search_kb": {"command": "query"},
}


def map_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """将参数映射为目标工具所需的参数名。

    当 MicroToT 或 patch 系统交换工具时，参数名可能不匹配。
    此函数按 _TOOL_ARG_MAP 进行重命名。
    """
    mapping = _TOOL_ARG_MAP.get(tool_name, {})
    if not mapping:
        return dict(args)
    mapped = {}
    for k, v in args.items():
        mapped[mapping.get(k, k)] = v
    return mapped


class TaskExecutor:
    """任务执行器"""

    def __init__(self, tools: Dict[str, Any] = None, trajectory: Optional[TaskGraphTrajectory] = None):
        self.tools = tools or {}
        self.trajectory = trajectory

    def route(self, task: TaskNode) -> str:
        """返回执行模式"""
        return task.execution_mode

    async def execute_direct(self, task: TaskNode) -> Dict[str, Any]:
        """direct 模式 — 顺序执行工具链，记录每次调用的轨迹"""
        start_time = time.time()
        tool_results: List[Dict[str, Any]] = []
        errors: List[str] = []
        tool_traces: List[ToolCallTrace] = []
        total_tokens = 0

        for idx, item in enumerate(task.tool_plan):
            args = map_tool_args(item.tool_name, {
                k: v for k, v in item.args_template.items() if k != "__patch_hints"
            })

            logger.info(
                "[TG:executor] task=%s step=%d/%d tool=%s args=%s",
                task.id, idx + 1, len(task.tool_plan), item.tool_name, args,
            )

            tool = self.tools.get(item.tool_name)
            if tool is None:
                if item.fallback:
                    logger.info("[TG:executor] tool=%s not found, trying fallback=%s",
                                item.tool_name, item.fallback)
                    tool = self.tools.get(item.fallback)
                if tool is None:
                    errors.append(f"工具不存在: {item.tool_name}")
                    tool_results.append({
                        "tool": item.tool_name,
                        "output": "",
                        "success": False,
                        "error": f"工具不存在: {item.tool_name}",
                    })
                    tool_traces.append(ToolCallTrace(
                        tool_name=item.tool_name,
                        args=args,
                        success=False,
                        error=f"工具不存在: {item.tool_name}",
                    ))
                    continue

            step_start = time.time()
            try:
                output = await tool.ainvoke(args)
                elapsed = time.time() - step_start
                output_str = str(output)
                logger.info(
                    "[TG:executor] task=%s step=%d tool=%s done in %.1fs output_len=%d preview=%s",
                    task.id, idx + 1, item.tool_name, elapsed,
                    len(output_str), output_str[:200],
                )
                tool_results.append({
                    "tool": item.tool_name,
                    "output": output_str,
                    "success": True,
                })
                tool_traces.append(ToolCallTrace(
                    tool_name=item.tool_name,
                    args=args,
                    output_preview=output_str[:500],
                    success=True,
                    duration_ms=elapsed * 1000,
                ))

                # 从工具响应中提取 token 用量（如果有的话）
                if hasattr(output, "usage_metadata") and output.usage_metadata:
                    total_tokens += output.usage_metadata.get("total_tokens", 0)
            except Exception as e:
                elapsed = time.time() - step_start
                logger.warning("[TG:executor] task=%s step=%d tool=%s FAILED in %.1fs: %s",
                               task.id, idx + 1, item.tool_name, elapsed, e)
                errors.append(str(e))
                tool_results.append({
                    "tool": item.tool_name,
                    "output": "",
                    "success": False,
                    "error": str(e),
                })
                tool_traces.append(ToolCallTrace(
                    tool_name=item.tool_name,
                    args=args,
                    success=False,
                    duration_ms=elapsed * 1000,
                    error=str(e),
                ))

        success = len(errors) == 0 and len(tool_results) > 0
        elapsed = time.time() - start_time

        return {
            "success": success,
            "tool_results": tool_results,
            "errors": errors,
            "tokens_used": total_tokens,
            "wallclock_seconds": round(elapsed, 3),
            "tool_traces": tool_traces,
        }
