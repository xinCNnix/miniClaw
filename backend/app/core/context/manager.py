"""ContextManager — main orchestrator for context window switching."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.config import LLMConfig, settings
from app.core.context.models import ContextResult
from app.core.context.token_estimator import TokenEstimator
from app.core.context.message_selector import MessageSelector
from app.core.context.compressor import ContextCompressor
from app.core.context.snapshot import AgentSnapshot, SnapshotManager

logger = logging.getLogger(__name__)

_context_manager: ContextManager | None = None


def get_context_manager() -> ContextManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager


class ContextManager:
    """Orchestrates the three-tier context management strategy.

    1. Normal: MessageSelector picks messages within budget
    2. Compressed: ContextCompressor summarizes overflow
    3. Checkpoint: SnapshotManager saves state for resume
    """

    def __init__(self):
        self.token_estimator = TokenEstimator()
        self.message_selector = MessageSelector()
        self.compressor = ContextCompressor()
        self.snapshot_manager = SnapshotManager()

    async def prepare_context(
        self,
        session_messages: list[dict],
        current_message: dict,
        system_prompt: str,
        llm_config: LLMConfig,
        session_id: str = "",
    ) -> ContextResult:
        system_tokens = self.token_estimator.estimate_text_tokens(system_prompt)
        budget = self.token_estimator.get_available_budget(llm_config, system_tokens)

        logger.info(
            f"ContextManager: session={session_id}, context_window={llm_config.context_window}, "
            f"system_tokens={system_tokens}, message_budget={budget}"
        )

        selected, used = self.message_selector.select(
            session_messages, current_message, budget, self.token_estimator
        )

        if used <= budget:
            logger.info(f"ContextManager: session={session_id} normal — {len(selected)} msgs, {used} tokens")
            return ContextResult(messages=selected, action="normal")

        logger.warning(
            f"ContextManager: session={session_id} overflow — {used} tokens exceeds budget {budget}, "
            f"triggering compression"
        )

        target_ratio = max(budget / used, 0.1) if used > 0 else 0.3
        compressed = await self.compressor.compress(
            selected,
            current_message.get("content", ""),
            self.token_estimator,
            target_ratio=target_ratio,
        )
        compressed_used = self.token_estimator.estimate_messages_tokens(compressed)

        if compressed and compressed[-1].get("content") != current_message.get("content"):
            compressed.append(current_message)
            compressed_used = self.token_estimator.estimate_messages_tokens(compressed)

        critical_threshold = budget * settings.context_window_critical_ratio

        if compressed_used <= critical_threshold:
            logger.info(
                f"ContextManager: session={session_id} compressed — "
                f"{len(compressed)} msgs, {compressed_used} tokens (threshold={critical_threshold:.0f})"
            )
            return ContextResult(messages=compressed, action="compressed")

        snapshot = self._create_snapshot(session_id, compressed)
        sid = self.snapshot_manager.save(snapshot)
        resume_messages = self._build_resume_context(snapshot, current_message)

        logger.warning(
            f"ContextManager: session={session_id} checkpoint — snapshot={sid}, "
            f"compressed={compressed_used} exceeds critical threshold={critical_threshold:.0f}"
        )
        return ContextResult(messages=resume_messages, action="checkpoint", checkpoint_id=sid)

    def _create_snapshot(self, session_id: str, compressed: list[dict]) -> AgentSnapshot:
        return AgentSnapshot(
            snapshot_id=f"snap-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            active_task=None,
            pending_tasks=[],
            world_state={},
            memory_refs={},
            conversation_summary=self._extract_summary(compressed),
            parent_snapshot_id=None,
            total_rounds=0,
        )

    def _extract_summary(self, messages: list[dict]) -> str:
        parts = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                parts.append(content[:200])
        return " ".join(parts)[:1000]

    def _build_resume_context(self, snapshot: AgentSnapshot, current_message: dict) -> list[dict]:
        resume_content = f"[上下文续跑] 这是之前任务的延续。\n已完成: {snapshot.conversation_summary}\n"
        if snapshot.active_task:
            resume_content += f"任务目标: {snapshot.active_task}\n"
        if snapshot.pending_tasks:
            resume_content += f"待完成: {', '.join(snapshot.pending_tasks)}\n"
        resume_content += "请继续执行未完成的任务。"
        return [{"role": "user", "content": resume_content}, current_message]
