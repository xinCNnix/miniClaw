"""Compresses conversation history via summarization."""
from __future__ import annotations

import logging
from datetime import datetime

from app.core.context.token_estimator import TokenEstimator

logger = logging.getLogger(__name__)

_SEGMENT_SIZE = 6


class ContextCompressor:
    """Compresses message history using extraction-based summarization."""

    async def compress(
        self,
        messages: list[dict],
        current_goal: str,
        estimator: TokenEstimator,
        target_ratio: float = 0.3,
    ) -> list[dict]:
        if not messages:
            return []

        segments = self._segment_messages(messages)
        logger.debug(f"Compressor: segmenting {len(messages)} msgs into {len(segments)} segments")
        compressed = []
        for i, segment in enumerate(segments):
            if not segment:
                continue
            summary = await self._summarize_segment(segment, current_goal)
            compressed.append({
                "role": "assistant",
                "content": f"[上下文优化] {summary}",
                "compressed": True,
                "timestamp": datetime.now().isoformat(),
            })
            logger.debug(f"Compressor: segment {i} ({len(segment)} msgs) → summary ({len(summary)} chars)")

        logger.info(f"Compressor: {len(messages)} msgs → {len(compressed)} compressed ({len(segments)} segments)")
        return compressed

    def _segment_messages(self, messages: list[dict]) -> list[list[dict]]:
        if not messages:
            return []
        segments: list[list[dict]] = []
        current: list[dict] = []
        for msg in messages:
            if msg.get("role") == "tool" or msg.get("tool_calls"):
                current.append(msg)
                if len(current) >= _SEGMENT_SIZE:
                    segments.append(current)
                    current = []
                continue
            current.append(msg)
            if len(current) >= _SEGMENT_SIZE:
                segments.append(current)
                current = []
        if current:
            segments.append(current)
        return segments

    async def _summarize_segment(self, messages: list[dict], goal: str) -> str:
        parts = []
        tool_names = []
        user_topics = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user" and content:
                user_topics.append(content[:80])
            elif role == "assistant":
                for tc in msg.get("tool_calls", []):
                    tool_names.append(tc.get("name", "unknown"))
                if content:
                    parts.append(content[:100])
        summary_parts = []
        if user_topics:
            summary_parts.append(f"用户问了: {'; '.join(user_topics[:3])}")
        if tool_names:
            summary_parts.append(f"调用了工具: {', '.join(tool_names)}")
        if parts:
            summary_parts.append(f"助手回复摘要: {'; '.join(parts[:3])}")
        if not summary_parts:
            return "之前的对话已完成"
        return "。".join(summary_parts)
