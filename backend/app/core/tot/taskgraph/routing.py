"""
LangGraph 条件路由函数。

route_skill: skill 匹配结果路由
route_schedule: 调度路由（has_ready_task / graph_done）
route_result: 结果处理路由
"""
from __future__ import annotations

import logging
from typing import Dict

from app.core.tot.taskgraph.models import TaskGraph, TaskStatus

logger = logging.getLogger(__name__)


def route_skill(state: Dict) -> str:
    """Skill-first 路由: skill_hit / skill_miss / skill_weak"""
    skill_result = state.get("skill_result")
    if skill_result is None:
        logger.info("[TG:route_skill] → skill_miss (no result)")
        return "skill_miss"
    if getattr(skill_result, "success", False):
        logger.info("[TG:route_skill] → skill_hit")
        return "skill_hit"
    logger.info("[TG:route_skill] → skill_weak")
    return "skill_weak"


def route_skill_result(state: Dict) -> str:
    """Skill 执行结果路由: pass → synthesize, fail → build_task_graph"""
    skill_result = state.get("skill_result")
    if skill_result and getattr(skill_result, "success", False):
        logger.info("[TG:route_skill_result] → synthesize (skill success)")
        return "synthesize"
    logger.info("[TG:route_skill_result] → build_task_graph (skill fallback)")
    return "build_task_graph"


def route_schedule(state: Dict) -> str:
    """调度路由: has_ready_task → execute_task, graph_done → synthesize"""
    graph: TaskGraph = state.get("task_graph", TaskGraph())
    if graph.is_done():
        logger.info("[TG:route_schedule] → synthesize (graph done: %s)", graph.progress_summary())
        return "synthesize"
    current_ids = state.get("current_task_ids", [])
    if current_ids:
        logger.info("[TG:route_schedule] → execute_task (current_ids=%s)", current_ids)
        return "execute_task"
    ready = graph.get_ready_tasks()
    if ready:
        logger.info("[TG:route_schedule] → execute_task (ready=%d)", len(ready))
        return "execute_task"
    logger.warning(
        "[TG:route_schedule] → synthesize (no ready tasks, graph not done: %s)",
        graph.progress_summary(),
    )
    return "synthesize"


def route_result(state: Dict) -> str:
    """结果路由: 全部 pass → schedule_next, 有 fail → retry"""
    logger.info("[TG:route_result] → schedule_next")
    return "schedule_next"
