"""
BeamSearchRouter — 决定每个 task 的执行模式。

路由优先级:
1. task.execution_mode 显式指定
2. thinking_mode + task_type 组合推断
3. tool_plan 工具复杂度推断
4. 默认 direct
"""
from __future__ import annotations

import logging

from app.core.tot.taskgraph.models import BeamConfig, TaskNode

logger = logging.getLogger(__name__)


class BeamSearchRouter:
    """决定每个 task 的执行模式并返回 beam search 配置"""

    def route(self, task: TaskNode, thinking_mode: str) -> str:
        """返回执行模式: "direct" | "beam_search" | "research" """
        # 1. 显式指定 beam_search/research（直接生效）
        if task.execution_mode in ("beam_search", "research"):
            return task.execution_mode

        # 2. thinking_mode + task_type 组合
        if thinking_mode == "exhaustive" and task.task_type in ("research", "analysis"):
            return "research"

        if thinking_mode in ("heuristic", "analytical"):
            if task.task_type in ("decision", "comparison", "brainstorm", "analysis"):
                return "beam_search"

        # 3. task_type 直接推断
        if task.task_type == "research":
            return "research"
        if task.task_type in ("decision", "comparison", "brainstorm"):
            return "beam_search"

        # 4. 工具复杂度
        if len(task.tool_plan) >= 3:
            return "beam_search"

        # 5. 默认 direct
        return "direct"

    def get_beam_config(self, thinking_mode: str) -> BeamConfig:
        """返回 thinking_mode 对应的 beam search 参数预设"""
        presets = {
            "heuristic": BeamConfig(
                beam_width=3, max_depth=3, timeout_seconds=900,
            ),
            "analytical": BeamConfig(
                beam_width=4, max_depth=4, timeout_seconds=1800,
            ),
            "exhaustive": BeamConfig(
                beam_width=4, max_depth=8, timeout_seconds=21600,
            ),
        }
        return presets.get(thinking_mode, BeamConfig())
