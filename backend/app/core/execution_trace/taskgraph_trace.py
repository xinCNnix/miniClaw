"""
TaskGraphTrace — TaskGraph 模式执行轨迹记录。

继承 BaseExecutionTrace，添加 TaskGraph 特有的生命周期日志方法。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.execution_trace.base import BaseExecutionTrace

logger = logging.getLogger(__name__)


class TaskGraphTrace(BaseExecutionTrace):
    """TaskGraph 模式执行轨迹"""

    def __init__(self):
        super().__init__()
        self.task_events: List[Dict[str, Any]] = []
        self.graph_summary: Dict[str, Any] = {}

    def log_graph_built(self, graph: Any, tokens: int = 0) -> None:
        """记录 TaskGraph 生成完成"""
        self.task_events.append({
            "event": "graph_built",
            "task_count": len(graph.nodes) if hasattr(graph, "nodes") else 0,
            "tokens": tokens,
        })
        self.total_prompt_tokens += tokens

    def log_task_scheduled(self, task_id: str, score: float = 0.0) -> None:
        """记录 task 被调度"""
        self.task_events.append({"event": "task_scheduled", "task_id": task_id, "score": score})

    def log_task_executed(self, task_id: str, tool_calls: List, tokens: int = 0) -> None:
        """记录 task 执行完成"""
        self.task_events.append({
            "event": "task_executed",
            "task_id": task_id,
            "tool_count": len(tool_calls),
            "tokens": tokens,
        })
        self.total_prompt_tokens += tokens

    def log_task_verified(self, task_id: str, verdict: Any) -> None:
        """记录 task 验证结果"""
        self.task_events.append({
            "event": "task_verified",
            "task_id": task_id,
            "passed": getattr(verdict, "passed", False),
            "layer": getattr(verdict, "verification_layer", ""),
        })

    def log_task_patched(self, task_id: str, patch: Any) -> None:
        """记录 task 修补"""
        self.task_events.append({
            "event": "task_patched",
            "task_id": task_id,
            "patch_type": getattr(patch, "patch_type", ""),
        })

    def log_micro_tot(self, task_id: str, candidates: List, best_score: float = 0.0) -> None:
        """记录 MicroToT 触发"""
        self.task_events.append({
            "event": "micro_tot",
            "task_id": task_id,
            "candidate_count": len(candidates),
            "best_score": best_score,
        })

    def log_artifact_created(self, artifact: Any) -> None:
        """记录 artifact 创建"""
        self.task_events.append({
            "event": "artifact_created",
            "artifact_id": getattr(artifact, "id", ""),
            "artifact_type": getattr(artifact, "artifact_type", ""),
        })

    def log_graph_done(self, graph: Any, total_tokens: int = 0, total_time: float = 0.0) -> None:
        """记录 graph 执行完成"""
        self.graph_summary = {
            "total_tasks": len(graph.nodes) if hasattr(graph, "nodes") else 0,
            "total_tokens": total_tokens,
            "total_time": total_time,
        }

    def get_summary(self) -> dict:
        """返回 JSON 可序列化的执行摘要"""
        return {
            "mode": "taskgraph",
            "user_question": self.user_question,
            "duration_seconds": (self.end_time or 0) - self.start_time if self.start_time else 0,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tool_calls": self.total_tool_calls,
            "task_events": self.task_events,
            "graph_summary": self.graph_summary,
            "tools": [t.model_dump() if hasattr(t, "model_dump") else str(t) for t in self.tools],
        }
