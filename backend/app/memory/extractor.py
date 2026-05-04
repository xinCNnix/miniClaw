"""
Memory Extractor - LLM-based memory extraction from conversations.

This module uses LLM to extract structured memories from conversation history.
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.memory import Memory, MemoryExtractionResult
from app.memory.session import get_session_manager
from app.core.llm import get_default_llm

logger = logging.getLogger(__name__)


class MemoryExtractor:
    """
    Extract structured memories from conversations using LLM.

    This class analyzes conversation text and extracts:
    - User preferences (coding style, communication patterns, tool preferences)
    - Important facts (project details, tech stack, domain knowledge)
    - Context (project goals, constraints, deadlines)
    - Patterns (recurring requests, common workflows)
    """

    def __init__(self, llm: BaseChatModel | None = None, max_retries: int = 2):
        """
        Initialize the memory extractor.

        Args:
            llm: Optional LLM instance. If not provided, uses default LLM.
            max_retries: Maximum number of retries when JSON parsing fails.
        """
        self.llm = llm or get_default_llm()
        self.max_retries = max_retries

    async def extract(
        self,
        session_id: str,
        max_messages: int = 20,
    ) -> MemoryExtractionResult:
        """
        Extract memories from a conversation session.

        Args:
            session_id: Session ID to extract memories from
            max_messages: Maximum number of recent messages to analyze

        Returns:
            MemoryExtractionResult containing extracted memories, summary, and topics

        Raises:
            ValueError: If session not found or has no messages
        """
        # Get conversation history
        session_manager = get_session_manager()
        session = session_manager.load_session(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        messages = session.get("messages", [])

        if not messages:
            raise ValueError(f"Session has no messages: {session_id}")

        # Take only recent messages
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages

        # Build conversation text
        conversation_text = self._format_conversation(recent_messages)

        # Build extraction prompt
        system_prompt = self._build_extraction_prompt()

        # Retry loop for LLM call and parsing
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                # Call LLM
                result = await self._call_llm(system_prompt, conversation_text)

                # Parse and validate result
                extraction_result = self._parse_extraction_result(result, session_id)

                # If we got here, parsing succeeded
                if attempt > 0:
                    logger.info(f"Memory extraction succeeded on retry {attempt + 1} (model={self.llm.model_name})")

                logger.info(
                    f"Extracted {len(extraction_result.memories)} memories "
                    f"from session {session_id} (model={self.llm.model_name})"
                )

                return extraction_result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Memory extraction attempt {attempt + 1}/{self.max_retries + 1} "
                    f"(model={self.llm.model_name}) failed: {e}"
                )

                if attempt < self.max_retries:
                    # Wait a bit before retrying (exponential backoff)
                    import asyncio
                    wait_time = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s...
                    await asyncio.sleep(wait_time)
                else:
                    # All retries exhausted
                    logger.error(
                        f"Memory extraction failed after {self.max_retries + 1} attempts "
                        f"(model={self.llm.model_name}): {e}"
                    )
                    break

        # Return empty result on failure after all retries
        return MemoryExtractionResult(
            memories=[],
            summary="",
            topics=[],
        )

    def _format_conversation(self, messages: List[Dict]) -> str:
        """
        Format messages as readable conversation text.

        Args:
            messages: List of message dictionaries

        Returns:
            Formatted conversation string
        """
        lines = []

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # 处理 multimodal 消息（content 为列表时提取 text 部分）
            if isinstance(content, list):
                text_parts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                content = " ".join(text_parts) if text_parts else ""
            elif not isinstance(content, str):
                content = str(content)

            # 剥离 assistant 消息中的 thinking tokens，避免干扰提取
            if role == "assistant" and isinstance(content, str):
                import re
                content = re.sub(r'<think\b[^>]*>.*?</think\s*>', '', content, flags=re.DOTALL).strip()

            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
            elif role == "tool":
                # Skip tool messages for memory extraction
                continue

        return "\n".join(lines)

    def _build_extraction_prompt(self) -> str:
        """
        Build the system prompt for memory extraction.

        Returns:
            System prompt string
        """
        return """You are a JSON generator that extracts user information from conversations.

CRITICAL: You MUST output ONLY a single valid JSON object. No thinking, no explanation, no markdown.

Extract these types of memories:
- "preference": User preferences (coding style, tools, communication style)
- "fact": Important facts (project details, tech stack, role, background)
- "context": Context (project goals, constraints, current challenges)
- "pattern": Recurring requests or common workflows

Output EXACTLY this JSON structure (no other text):
{"memories": [{"type": "preference", "content": "description", "confidence": 0.9}, {"type": "fact", "content": "description", "confidence": 0.8}], "summary": "brief conversation summary", "topics": ["topic1", "topic2"]}

Rules:
- confidence: 0.0-1.0 float
- content: max 200 chars per item
- summary: max 500 chars
- topics: 3-5 items
- Be conservative: only extract high-confidence information
- If nothing worth extracting, return: {"memories": [], "summary": "", "topics": []}"""

    async def _call_llm(self, system_prompt: str, conversation_text: str) -> str:
        """
        Call LLM to extract memories.

        Args:
            system_prompt: System prompt for extraction
            conversation_text: Formatted conversation text

        Returns:
            LLM response string

        Raises:
            Exception: If LLM call fails
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Analyze this conversation:\n\n{conversation_text}"),
        ]

        response = await self.llm.ainvoke(messages)
        return response.content

    def _parse_extraction_result(
        self,
        llm_output: str,
        session_id: str,
    ) -> MemoryExtractionResult:
        """
        Parse LLM output into MemoryExtractionResult.

        Args:
            llm_output: Raw LLM response
            session_id: Session ID for timestamp generation

        Returns:
            Parsed MemoryExtractionResult

        Raises:
            ValueError: If JSON parsing fails
        """
        # Try to extract JSON from response
        import re
        json_str = llm_output.strip()

        # 剥离 thinking tokens（MiniMax/Qwen 等模型可能返回 <think...</think）
        json_str = re.sub(r'<think\b[^>]*>.*?</think\s*>', '', json_str, flags=re.DOTALL).strip()
        # 剥离 [FINAL] 等框架标记
        json_str = re.sub(r'\[FINAL\]', '', json_str).strip()

        # Remove markdown code blocks if present
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            # Find content between code blocks (skip first line with ```)
            start_idx = 1  # Skip the first ``` line
            # Find end
            end_idx = len(lines)
            for i in range(start_idx, len(lines)):
                if lines[i].strip().startswith("```"):
                    end_idx = i
                    break
            json_str = "\n".join(lines[start_idx:end_idx]).strip()

        # 如果开头不是 {，尝试从文本中提取第一个 JSON 对象
        if not json_str.startswith("{"):
            match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if match:
                json_str = match.group(0)

        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM output as JSON (model={self.llm.model_name}): {e}")
            logger.warning(f"LLM raw output (first 500 chars): {llm_output[:500]}")
            # Raise exception to trigger retry
            raise ValueError(f"JSON parsing failed: {e}") from e

        # Parse memories
        memories = []
        timestamp = datetime.now().isoformat()

        for item in data.get("memories", []):
            try:
                memory = Memory(
                    type=item["type"],
                    content=item["content"],
                    confidence=float(item.get("confidence", 0.5)),
                    timestamp=timestamp,
                    session_id=session_id,
                )
                memories.append(memory)
            except Exception as e:
                logger.warning(f"Failed to parse memory item: {e}")
                continue

        return MemoryExtractionResult(
            memories=memories,
            summary=data.get("summary", ""),
            topics=data.get("topics", []),
        )


# Singleton instance
_extractor_instance: MemoryExtractor | None = None


def get_memory_extractor() -> MemoryExtractor:
    """
    Get the global memory extractor instance.

    Returns:
        MemoryExtractor instance
    """
    global _extractor_instance

    if _extractor_instance is None:
        from app.config import get_settings
        settings = get_settings()
        _extractor_instance = MemoryExtractor(
            max_retries=settings.memory_extraction_max_retries
        )

    return _extractor_instance


def reset_memory_extractor() -> None:
    """
    Reset the global memory extractor to force recreation on next access.

    This should be called when configuration is updated.
    """
    global _extractor_instance
    _extractor_instance = None
