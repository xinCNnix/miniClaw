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
                    logger.info(f"Memory extraction succeeded on retry {attempt + 1}")

                logger.info(
                    f"Extracted {len(extraction_result.memories)} memories "
                    f"from session {session_id}"
                )

                return extraction_result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Memory extraction attempt {attempt + 1}/{self.max_retries + 1} failed: {e}"
                )

                if attempt < self.max_retries:
                    # Wait a bit before retrying (exponential backoff)
                    import asyncio
                    wait_time = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s...
                    await asyncio.sleep(wait_time)
                else:
                    # All retries exhausted
                    logger.error(
                        f"Memory extraction failed after {self.max_retries + 1} attempts: {e}"
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
        return """You are a memory extraction assistant. Your task is to analyze conversations and extract key information about the user.

Analyze the conversation and extract:

1. **User Preferences** (type: "preference")
   - Coding style preferences (e.g., "prefers TypeScript over JavaScript")
   - Communication style (e.g., "likes concise explanations")
   - Tool preferences (e.g., "prefers vim over emacs")
   - Workflow preferences

2. **Important Facts** (type: "fact")
   - Project details (e.g., "working on miniClaw project")
   - Technical stack (e.g., "uses Python 3.10+, FastAPI, Next.js")
   - Domain knowledge
   - Role or background

3. **Context** (type: "context")
   - Project goals
   - Constraints or limitations
   - Deadlines or timeframes
   - Current problems or challenges

4. **Patterns** (type: "pattern")
   - Recurring requests
   - Common workflows
   - Frequently asked topics

For each extracted item, provide:
- type: One of "preference", "fact", "context", "pattern"
- content: Clear description (max 200 chars)
- confidence: Float from 0.0 to 1.0 indicating certainty

Also provide:
- summary: Brief summary of the conversation (max 500 chars)
- topics: List of main topics discussed (3-5 items)

Return ONLY valid JSON in this exact format:
{
  "memories": [
    {"type": "preference", "content": "...", "confidence": 0.9},
    {"type": "fact", "content": "...", "confidence": 0.8}
  ],
  "summary": "...",
  "topics": ["topic1", "topic2", "topic3"]
}

Be conservative - only extract information you're confident about. If uncertain, use lower confidence score."""

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
        json_str = llm_output.strip()

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

        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM output as JSON: {e}")
            logger.debug(f"LLM output: {llm_output}")
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
