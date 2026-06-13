"""
ToTStateAdapter — TaskGraphState ↔ ToTState 双向映射。

纯数据转换层，负责:
- 将 TaskGraphState + TaskNode 映射为 ToTState 供 ToT 子图消费
- 将 ToT 子图输出提取为标准 execution result dict
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.core.tot.taskgraph.models import BeamConfig, TaskNode

logger = logging.getLogger(__name__)


class ToTStateAdapter:
    """TaskGraphState ↔ ToTState 双向映射"""

    def __init__(
        self,
        tg_state: Dict[str, Any],
        task: TaskNode,
        mode: str,
        beam_config: BeamConfig,
    ):
        self.tg_state = tg_state
        self.task = task
        self.mode = mode
        self.beam_config = beam_config

    @staticmethod
    def _ensure_langchain_messages(messages: list) -> list:
        """将 dict 格式的 messages 转换为 LangChain Message 对象。

        ToT 子图的 thought_generator 等节点使用 msg.type / msg.content 访问消息，
        但从 FastAPI 传入的 messages 是原始 dict，需要转换。
        """
        if not messages:
            return messages
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        converted = []
        for msg in messages:
            if hasattr(msg, "type"):
                # 已经是 LangChain Message 对象
                converted.append(msg)
                continue
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user" or role == "human":
                    converted.append(HumanMessage(content=content))
                elif role == "assistant" or role == "ai":
                    converted.append(AIMessage(content=content))
                elif role == "system":
                    converted.append(SystemMessage(content=content))
                else:
                    # 未知 role，默认当 HumanMessage
                    converted.append(HumanMessage(content=content))
            else:
                converted.append(msg)
        return converted

    def build_tot_state(self) -> Dict[str, Any]:
        """从 TaskGraphState + TaskNode 构建 ToTState dict"""
        tot_task_mode = "research" if self.mode == "research" else "standard"

        tot_state: Dict[str, Any] = {
            # 查询: 用 task 描述作为子查询
            "user_query": self.task.description,
            "session_context": self.tg_state.get("session_context", {}),
            "messages": self._ensure_langchain_messages(self.tg_state.get("messages", [])),
            # 推理树
            "thoughts": [],
            "current_depth": 0,
            "max_depth": self.beam_config.max_depth,
            "branching_factor": self.beam_config.branching_factor,
            # 最优路径
            "best_path": [],
            "best_score": 0.0,
            # 工具和 LLM
            "tools": self.tg_state.get("tools", []),
            "llm": self.tg_state.get("llm"),
            "llm_with_tools": self.tg_state.get("llm_with_tools"),
            "system_prompt": self.tg_state.get("system_prompt", ""),
            # Research 字段
            "research_sources": None,
            "research_stage": None,
            # 模式
            "task_mode": tot_task_mode,
            "task_type": self.task.task_type,
            "domain_profile": None,
            "tot_logger": None,
            "session_id": None,
            # Research 详细字段
            "evidence_store": self.tg_state.get("evidence_store", []),
            "coverage_map": None,
            "contradictions": [],
            "draft": None,
            "raw_sources": self.tg_state.get("raw_sources", []),
            "research_round": 0,
            "citation_chase_rounds": 0,
            "citation_chase_max": 2,
            "token_used": 0,
            "token_budget": self.task.budget.max_tokens,
            "prev_coverage_score": 0.0,
            "writer_min_delta": 0.15,
            # 结果
            "final_answer": None,
            "reasoning_trace": [],
            "fallback_to_simple": False,
            "tca_injection_text": self.tg_state.get("tca_injection_text", ""),
            "meta_policy_injection_text": self.tg_state.get("meta_policy_injection_text", ""),
            # Global Beam Search
            "active_beams": [],
            "beam_scores": [],
            "beam_width": self.beam_config.beam_width,
            "backtrack_count": 0,
            "regenerate_count": 0,
            "beam_switch_count": 0,
            "backtrack_score_threshold": 5.5,
            "needs_regeneration": [],
            "deferred_image_paths": [],
            "max_tool_steps_per_node": self.beam_config.max_tool_steps_per_node,
            "max_time_per_node": 30.0,
            # Enrichment
            "retrieved_patterns": self.tg_state.get("retrieved_patterns", []),
            "semantic_history": self.tg_state.get("semantic_history", ""),
        }
        return tot_state

    def extract_results(self, tot_output: Dict[str, Any]) -> Dict[str, Any]:
        """从 ToT 子图输出提取标准 execution result dict"""
        tool_results: List[Dict[str, Any]] = []
        errors: List[str] = []

        # 从 best_path 对应的 thoughts 中收集 tool_results
        thoughts = tot_output.get("thoughts", [])
        best_path_ids = set(tot_output.get("best_path", []))
        for thought in thoughts:
            tid = getattr(thought, "id", "")
            if tid in best_path_ids or not best_path_ids:
                tr_list = getattr(thought, "tool_results", [])
                if isinstance(tr_list, list):
                    tool_results.extend(tr_list)

        # 如果没有 tool_results，用 final_answer 作为输出
        final_answer = tot_output.get("final_answer", "")
        if not tool_results and final_answer:
            tool_results = [{"tool": "tot_subgraph", "output": final_answer, "success": True}]

        success = bool(tool_results) or bool(final_answer)
        if not success:
            errors.append("ToT 子图未产出有效结果")

        # 提取 artifacts（research 模式）
        artifacts_produced = []
        evidence = tot_output.get("evidence_store", [])
        if isinstance(evidence, dict):
            artifacts_produced = list(evidence.keys())
        elif isinstance(evidence, list):
            artifacts_produced = [item.get("id", str(i)) for i, item in enumerate(evidence) if isinstance(item, dict)]

        return {
            "success": success,
            "tool_results": tool_results,
            "errors": errors,
            "wallclock_seconds": 0,
            "tokens_used": 0,
            "artifacts_produced": artifacts_produced,
            "metadata": {
                "tot_final_answer": final_answer,
                "tot_best_score": tot_output.get("best_score", 0.0),
            },
        }
