"""ContextManager — 60-60-80 阈值模型的上下文管理。

阈值模型说明：
- ratio < 60%: 正常运行，使用 MessageSelector 选择消息
- ratio ≥ 60% 且首次: 压缩一次，使用 StateExtractor + CompressionSummarizer
- ratio ≥ 60% 已压缩: 继续正常运行，不再重复压缩
- ratio ≥ 80%: 切换 (checkpoint)，保存快照并填充真实状态

每个 session 独立追踪压缩状态，确保 60% 压缩只触发一次。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.config import LLMConfig, settings
from app.core.context.models import (
    ContextResult, ExtractedState, SessionState,
)
from app.core.context.token_estimator import TokenEstimator
from app.core.context.message_selector import MessageSelector
from app.core.context.state_extractor import StateExtractor
from app.core.context.compression_summarizer import CompressionSummarizer
from app.core.context.snapshot import AgentSnapshot, SnapshotManager

logger = logging.getLogger(__name__)

_context_manager: ContextManager | None = None


def get_context_manager() -> ContextManager:
    """获取全局 ContextManager 单例。

    延迟初始化，首次调用时创建实例。

    Returns:
        ContextManager 单例实例。
    """
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager


class ContextManager:
    """60-60-80 阈值模型上下文管理。

    根据消息 token 占用比例决定动作：
    - ratio < compression_ratio (60%): 正常运行
    - ratio ≥ compression_ratio 且首次: 压缩一次
    - ratio ≥ compression_ratio 已压缩: 继续运行
    - ratio ≥ switch_ratio (80%): 切换 (checkpoint)
    """

    def __init__(self):
        self.token_estimator = TokenEstimator()
        self.message_selector = MessageSelector()
        self.state_extractor = StateExtractor()
        self.summarizer = CompressionSummarizer()
        self.snapshot_manager = SnapshotManager()
        # session 级状态追踪，key 为 session_id
        self._session_states: dict[str, SessionState] = {}

    def _get_session_state(self, session_id: str) -> SessionState:
        """获取或创建 session 级状态。

        空 session_id 用 _default 兜底，确保每个 session 独立追踪。

        Args:
            session_id: 会话 ID。

        Returns:
            该 session 的 SessionState 实例。
        """
        if not session_id:
            session_id = "_default"
        if session_id not in self._session_states:
            self._session_states[session_id] = SessionState()
        return self._session_states[session_id]

    async def prepare_context(
        self,
        session_messages: list[dict],
        current_message: dict,
        system_prompt: str,
        llm_config: LLMConfig,
        session_id: str = "",
    ) -> ContextResult:
        """准备上下文消息，根据 token 占用比例决定动作。

        工作流程：
        1. 估算 system prompt token 和可用预算
        2. 计算当前消息的 token 占用比例
        3. 根据阈值决定动作（正常/压缩/checkpoint）

        Args:
            session_messages: 会话历史消息列表。
            current_message: 当前用户消息。
            system_prompt: 系统提示词。
            llm_config: LLM 配置对象。
            session_id: 会话 ID（用于独立追踪压缩状态）。

        Returns:
            ContextResult 包含处理后的消息和元数据。
        """
        # ① 估算 token
        system_tokens = self.token_estimator.estimate_text_tokens(system_prompt)
        budget = self.token_estimator.get_available_budget(llm_config, system_tokens)
        all_messages = session_messages + [current_message]
        total_tokens = self.token_estimator.estimate_messages_tokens(all_messages)
        ratio = total_tokens / budget if budget > 0 else float('inf')

        session_state = self._get_session_state(session_id)
        session_state.last_ratio = ratio

        logger.info(
            f"ContextManager: session={session_id}, ratio={ratio:.2f}, "
            f"tokens={total_tokens}, budget={budget}, "
            f"compression_count={session_state.compression_count}"
        )

        compression_threshold = settings.context_window_compression_ratio
        switch_threshold = settings.context_window_switch_ratio

        # ④ ratio ≥ 80%: 切换 (checkpoint)
        if ratio >= switch_threshold:
            return await self._handle_checkpoint(
                session_messages, current_message, session_id, session_state, llm_config,
            )

        # ② ratio ≥ 60% 且首次: 压缩
        if ratio >= compression_threshold and session_state.compression_count == 0:
            return await self._handle_compression(
                session_messages, current_message, session_id, session_state, llm_config,
                budget_used_ratio=ratio,
            )

        # ③ 正常 (ratio < 60% 或已压缩过)
        selected, used = self.message_selector.select(
            session_messages, current_message, budget, self.token_estimator,
        )
        return ContextResult(
            messages=selected,
            action="normal",
            compression_count=session_state.compression_count,
            budget_used_ratio=ratio,
        )

    async def _handle_compression(
        self,
        session_messages: list[dict],
        current_message: dict,
        session_id: str,
        session_state: SessionState,
        llm_config: LLMConfig,
        budget_used_ratio: float = 0.0,
    ) -> ContextResult:
        """处理首次压缩。

        使用 StateExtractor 从历史消息中提取结构化状态，
        然后用 CompressionSummarizer 生成状态头。
        保留最后 4 条原始消息以维持上下文连贯性。

        Args:
            session_messages: 会话历史消息。
            current_message: 当前用户消息。
            session_id: 会话 ID。
            session_state: 会话级状态。
            llm_config: LLM 配置。
            budget_used_ratio: 预算使用比例。

        Returns:
            compressed 类型的 ContextResult。
        """
        # 提取结构化状态
        state = self.state_extractor.extract(session_messages)
        # 生成状态头消息
        summary_msg = await self.summarizer.summarize(state, session_messages, llm_config)

        # 保留最后 4 条原始消息 + 当前消息
        last_n = session_messages[-4:] if len(session_messages) >= 4 else list(session_messages)
        result_messages = [summary_msg] + last_n + [current_message]

        # 更新 session 状态
        session_state.compression_count = 1
        session_state.last_state = state

        logger.info(
            f"ContextManager: session={session_id} compressed — "
            f"state_header={len(state.tasks_completed)} completed, "
            f"{len(state.tasks_pending)} pending"
        )

        return ContextResult(
            messages=result_messages,
            action="compressed",
            compression_count=1,
            budget_used_ratio=budget_used_ratio,
            state_header=state,
        )

    async def _handle_checkpoint(
        self,
        session_messages: list[dict],
        current_message: dict,
        session_id: str,
        session_state: SessionState,
        llm_config: LLMConfig,
    ) -> ContextResult:
        """处理 80% 切换 (checkpoint)。

        当消息占用超过 80% 时触发 checkpoint：
        1. 标记已压缩，防止后续再触发 compression
        2. 提取结构化状态
        3. 生成状态头
        4. 创建并保存快照
        5. 保留最后 4 条原始消息

        Args:
            session_messages: 会话历史消息。
            current_message: 当前用户消息。
            session_id: 会话 ID。
            session_state: 会话级状态。
            llm_config: LLM 配置。

        Returns:
            checkpoint 类型的 ContextResult。
        """
        # 标记已压缩，防止 checkpoint 后再触发 compression
        session_state.compression_count = max(session_state.compression_count, 1)

        # 提取状态并生成摘要
        state = self.state_extractor.extract(session_messages)
        summary_msg = await self.summarizer.summarize(state, session_messages, llm_config)
        summary_text = summary_msg.get("content", "")

        # 创建快照并保存
        snapshot = self._create_snapshot(session_id, state, summary_text, len(session_messages))
        sid = self.snapshot_manager.save(snapshot)

        # 保留最后 4 条原始消息 + 当前消息
        last_n = session_messages[-4:] if len(session_messages) >= 4 else list(session_messages)
        result_messages = [summary_msg] + last_n + [current_message]

        logger.warning(
            f"ContextManager: session={session_id} checkpoint — snapshot={sid}"
        )

        return ContextResult(
            messages=result_messages,
            action="checkpoint",
            checkpoint_id=sid,
            compression_count=session_state.compression_count,
            budget_used_ratio=session_state.last_ratio,
            state_header=state,
        )

    def _create_snapshot(
        self,
        session_id: str,
        state: ExtractedState,
        summary: str,
        total_rounds: int = 0,
    ) -> AgentSnapshot:
        """从 ExtractedState 填充快照字段。

        将提取的结构化状态映射到快照的各个字段：
        - active_task: 优先取 in_progress，其次取 pending 的第一个
        - world_state: 包含已修改和已读取的文件列表
        - conversation_summary: 状态摘要

        Args:
            session_id: 会话 ID。
            state: 提取的结构化状态。
            summary: 状态摘要文本。
            total_rounds: 总消息数。

        Returns:
            填充了真实数据的 AgentSnapshot。
        """
        # 优先取进行中的任务，其次取待完成的任务
        active_task = (
            state.tasks_in_progress[0] if state.tasks_in_progress
            else (state.tasks_pending[0] if state.tasks_pending else None)
        )
        return AgentSnapshot(
            snapshot_id=f"snap-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            active_task=active_task,
            pending_tasks=state.tasks_pending,
            world_state={
                "files_modified": [fc.path for fc in state.file_changes if fc.action in ("write", "create")],
                "files_read": [fc.path for fc in state.file_changes if fc.action == "read"],
            },
            memory_refs={},
            conversation_summary=summary,
            parent_snapshot_id=None,
            total_rounds=total_rounds // 2,
        )
