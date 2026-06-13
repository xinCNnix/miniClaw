"""
TaskGraphBuilder — 一次 LLM 调用生成任务 DAG。

流程:
1. 格式化 prompt（含 enrichment、skill_hints）
2. 调用 LLM
3. 解析 JSON
4. 为每个 task 自动生成 DoD
5. 构建 TaskGraph
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from app.core.tot.taskgraph.dod_generator import DoDGenerator
from app.core.tot.taskgraph.models import TaskGraph, TaskNode, ToolPlanItem
from app.core.tot.taskgraph.prompts.task_graph_builder import format_graph_prompt
from app.core.tot.profiles.base import DomainProfile
from app.core.tot.profiles.generic import GENERIC_PROFILE

logger = logging.getLogger(__name__)


class TaskGraphBuilder:
    """一次 LLM 调用生成 TaskGraph + DoD"""

    def __init__(self, llm: Any = None):
        self.llm = llm
        self.dod_generator = DoDGenerator()

    async def build(
        self,
        query: str,
        context: str,
        domain: Optional[DomainProfile],
        tool_list: str = "",
        skill_hints: str = "",
        enrichment_texts: Optional[Dict[str, str]] = None,
    ) -> TaskGraph:
        """生成 TaskGraph"""
        domain = domain or GENERIC_PROFILE
        domain_methods = "; ".join(domain.preferred_methods) if domain.preferred_methods else ""

        messages = format_graph_prompt(
            user_query=query,
            session_context=context,
            tool_list=tool_list,
            domain_methods=domain_methods,
            skill_hints=skill_hints,
            enrichment_texts=enrichment_texts,
        )

        response = await self.llm.ainvoke(messages)
        raw = response.content if hasattr(response, "content") else str(response)
        logger.info("[TG:graph_builder] LLM response length=%d, preview=%s",
                     len(raw), raw[:200])

        tasks = self._parse_graph_json(raw)
        logger.info("[TG:graph_builder] Parsed %d tasks from LLM response", len(tasks))

        for task in tasks:
            task.dod = self.dod_generator.generate(
                task.task_type, domain, task.tool_plan,
            )
            logger.info("[TG:graph_builder] task=%s title=%s deps=%s tools=%s",
                         task.id, task.title, task.dependencies,
                         [tp.tool_name for tp in task.tool_plan])
            for tp_idx, tp in enumerate(task.tool_plan):
                logger.info("[TG:graph_builder]   plan[%d]: tool=%s args=%s fallback=%s",
                            tp_idx, tp.tool_name, tp.args_template, tp.fallback)

        graph = TaskGraph()
        for t in tasks:
            graph.add_task(t)

        return graph

    def _parse_graph_json(self, raw: str) -> List[TaskNode]:
        """解析 LLM 返回的 JSON 为 TaskNode 列表"""
        json_str = raw.strip()
        if "```" in json_str:
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", json_str, re.DOTALL)
            if match:
                json_str = match.group(1).strip()

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.error("Failed to parse graph JSON: %s", raw[:200])
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                logger.info("[TG:graph_builder] Fallback JSON parse succeeded, length=%d", len(raw))
            else:
                raise

        tasks_data = data.get("tasks", [])
        tasks = []
        for td in tasks_data:
            tool_plan = [
                ToolPlanItem(
                    tool_name=tp.get("tool_name", "unknown"),
                    args_template=tp.get("args_template", {}),
                    fallback=tp.get("fallback"),
                )
                for tp in td.get("tool_plan", [])
            ]
            tasks.append(TaskNode(
                id=td.get("id", f"t{len(tasks)+1}"),
                title=td.get("title", ""),
                description=td.get("description", ""),
                dependencies=td.get("dependencies", []),
                execution_mode=td.get("execution_mode", "direct"),
                task_type=td.get("task_type", "generic"),
                tool_plan=tool_plan,
                priority=td.get("priority", 50),
                max_attempts=td.get("max_attempts", 3),
            ))

        return tasks
