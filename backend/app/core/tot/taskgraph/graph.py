"""
TaskGraph LangGraph 图定义。

8 个节点 + 条件路由:
skill_route → execute_skill → build_task_graph → schedule_next → execute_task → verify_task → handle_result → synthesize
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.graph import StateGraph, END

from app.core.tot.taskgraph.models import TaskGraphState
from app.core.tot.taskgraph import nodes
from app.core.tot.taskgraph import routing

logger = logging.getLogger(__name__)


def build_taskgraph_graph() -> StateGraph:
    """构建 TaskGraph LangGraph 状态图"""
    graph = StateGraph(TaskGraphState)

    # 添加节点
    graph.add_node("skill_route", nodes.skill_route_node)
    graph.add_node("execute_skill", nodes.execute_skill_node)
    graph.add_node("build_task_graph", nodes.build_task_graph_node)
    graph.add_node("schedule_next", nodes.schedule_next_node)
    graph.add_node("execute_task", nodes.execute_task_node)
    graph.add_node("verify_task", nodes.verify_task_node)
    graph.add_node("handle_result", nodes.handle_result_node)
    graph.add_node("synthesize", nodes.synthesize_node)

    # 入口
    graph.set_entry_point("skill_route")

    # 条件路由: skill 匹配结果
    graph.add_conditional_edges(
        "skill_route",
        routing.route_skill,
        {
            "skill_hit": "execute_skill",
            "skill_miss": "build_task_graph",
            "skill_weak": "execute_skill",
        },
    )

    # skill 执行结果
    graph.add_conditional_edges(
        "execute_skill",
        routing.route_skill_result,
        {
            "synthesize": "synthesize",
            "build_task_graph": "build_task_graph",
        },
    )

    # build_task_graph → schedule_next
    graph.add_edge("build_task_graph", "schedule_next")

    # 调度路由
    graph.add_conditional_edges(
        "schedule_next",
        routing.route_schedule,
        {
            "execute_task": "execute_task",
            "synthesize": "synthesize",
        },
    )

    # 执行 → 验证 → 处理
    graph.add_edge("execute_task", "verify_task")
    graph.add_edge("verify_task", "handle_result")

    # 处理结果 → 回到调度
    graph.add_edge("handle_result", "schedule_next")

    # synthesize → END
    graph.add_edge("synthesize", END)

    return graph


def compile_taskgraph_graph() -> Any:
    """编译并返回可执行的 graph"""
    return build_taskgraph_graph().compile()
