"""
TaskScheduler — 确定性任务调度，不调用 LLM。

调度策略: priority(0.4) → 阻塞度(0.3) → aging(0.2) → 验证成本(0.1)
并行 batch: 资源不冲突的 READY 任务可以同时执行。
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Set

from app.core.tot.taskgraph.models import TaskGraph, TaskNode

logger = logging.getLogger(__name__)


class TaskScheduler:
    """确定性任务调度器"""

    def __init__(self, aging_enabled: bool = True):
        self.aging_enabled = aging_enabled
        self._creation_times: dict[str, float] = {}

    def pick_ready_task(self, graph: TaskGraph) -> Optional[TaskNode]:
        """从 READY 任务中选出最优的一个"""
        ready = graph.get_ready_tasks()
        if not ready:
            return None

        for t in ready:
            if t.id not in self._creation_times:
                self._creation_times[t.id] = time.time()

        scored = [(t, self._score(t, graph)) for t in ready]
        scored.sort(key=lambda x: -x[1])
        return scored[0][0]

    def pick_ready_batch(self, graph: TaskGraph, max_parallel: int = 4) -> List[TaskNode]:
        """返回一批可并行执行的 READY 任务"""
        ready = graph.get_ready_tasks()
        if not ready:
            return []

        for t in ready:
            if t.id not in self._creation_times:
                self._creation_times[t.id] = time.time()

        parallel_candidates = self._find_non_conflicting(ready, graph)
        return parallel_candidates[:max_parallel]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _score(self, task: TaskNode, graph: TaskGraph) -> float:
        """综合评分"""
        return (
            task.priority * 0.4
            + self._dependency_impact(task, graph) * 0.3
            + self._aging_bonus(task) * 0.2
            + self._verification_cost(task) * 0.1
        )

    def _dependency_impact(self, task: TaskNode, graph: TaskGraph) -> float:
        """阻塞度：被该任务阻塞的下游任务数，归一化到 0-100"""
        dependents = graph.get_dependents(task.id)
        count = len(dependents)
        visited = set(dependents)
        queue = list(dependents)
        while queue:
            did = queue.pop(0)
            for dep_id in graph.get_dependents(did):
                if dep_id not in visited:
                    visited.add(dep_id)
                    queue.append(dep_id)
                    count += 1
        return min(count * 10.0, 100.0)

    def _aging_bonus(self, task: TaskNode) -> float:
        """老化奖励：等待越久优先级越高（防饥饿）"""
        if not self.aging_enabled:
            return 0.0
        created = self._creation_times.get(task.id, time.time())
        elapsed = time.time() - created
        return min(elapsed / 10.0, 50.0)

    def _verification_cost(self, task: TaskNode) -> float:
        """验证成本：低成本先做（快速排除失败路径），归一化到 0-100"""
        tool_count = len(task.tool_plan)
        return max(0.0, 100.0 - tool_count * 20.0)

    def _find_non_conflicting(self, tasks: List[TaskNode], graph: TaskGraph) -> List[TaskNode]:
        """确保并行任务不写同一个文件、不争抢同一资源"""
        selected: List[TaskNode] = []
        used_resources: Set[str] = set()

        scored = [(t, self._score(t, graph)) for t in tasks]
        scored.sort(key=lambda x: -x[1])

        for task, _ in scored:
            resources = self._get_resources(task)
            if not resources.intersection(used_resources):
                selected.append(task)
                used_resources.update(resources)
        return selected

    def _get_resources(self, task: TaskNode) -> Set[str]:
        """获取任务涉及的资源标识（文件路径）"""
        resources: Set[str] = set()
        for item in task.tool_plan:
            path = item.args_template.get("path", "")
            if path:
                resources.add(f"file:{path}")
        return resources
