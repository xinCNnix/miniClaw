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
from app.core.llm import get_default_llm, create_current_llm

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

    def __init__(self, llm: BaseChatModel | None = None):
        """
        Initialize the memory extractor.

        Args:
            llm: Optional LLM instance. If not provided, uses current active LLM.
        """
        self.llm = llm or create_current_llm()

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

        # Call LLM
        try:
            result = await self._call_llm(system_prompt, conversation_text)
        except Exception as e:
            logger.error(f"LLM extraction failed for session {session_id}: {e}")
            # Return empty result on failure
            return MemoryExtractionResult(
                memories=[],
                summary="",
                topics=[],
            )

        # Parse and validate result
        extraction_result = self._parse_extraction_result(result, session_id)

        logger.info(
            f"Extracted {len(extraction_result.memories)} memories "
            f"from session {session_id}"
        )

        return extraction_result

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
                # Extract important information from tool outputs
                tool_name = msg.get("name", msg.get("tool_name", "unknown"))
                tool_output = content

                # Only include important tools in memory extraction
                if self._is_important_tool(tool_name):
                    summarized = self._summarize_tool_output(tool_name, tool_output)
                    if summarized:
                        lines.append(f"[Tool: {tool_name}]\n{summarized}")

        return "\n".join(lines)

    def _is_important_tool(self, tool_name: str) -> bool:
        """
        Check if a tool output is important enough to include in memory.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool output should be extracted
        """
        # Tools that produce important, persistent information
        important_tools = {
            # Research & information retrieval
            "terminal",  # Can run arxiv_search and other info tools
            "fetch",     # Web content retrieval
            "arxiv",     # Academic paper search

            # Knowledge tools
            "search_knowledge_base",
            "read_file",

            # Data analysis
            "python_repl",  # Analysis results
        }

        # Check if tool name contains any important keyword
        tool_lower = tool_name.lower()
        for important in important_tools:
            if important in tool_lower:
                return True

        return False

    def _summarize_tool_output(self, tool_name: str, tool_output: str) -> str:
        """
        Summarize tool output for memory extraction.

        Args:
            tool_name: Name of the tool
            tool_output: Raw tool output

        Returns:
            Summarized output (truncated if too long)
        """
        if not tool_output or not tool_output.strip():
            return ""

        # Clean up output
        output = tool_output.strip()

        # For terminal output, try to extract structured data
        if "terminal" in tool_name.lower():
            # Check if it's JSON output (e.g., from arxiv_search)
            if output.startswith("{") and output.endswith("}"):
                try:
                    import json
                    data = json.loads(output)
                    # Extract key information from structured output
                    if "papers" in data:
                        paper_count = len(data.get("papers", []))
                        return f"Retrieved {paper_count} papers from arXiv"
                    elif "total_results" in data:
                        return f"Query returned {data.get('returned', 0)} results"
                except json.JSONDecodeError:
                    pass

            # For other terminal output, limit length
            max_length = 500
            if len(output) > max_length:
                return output[:max_length] + "\n...[truncated]"
            return output

        # For other tools, truncate very long outputs
        max_length = 1000
        if len(output) > max_length:
            return output[:max_length] + "\n...[truncated]"

        return output

    def _build_extraction_prompt(self) -> str:
        """
        Build the system prompt for memory extraction.

        Returns:
            System prompt string
        """
        return """You are a memory extraction assistant. Your task is to analyze conversations and extract key information about the user and important research results.

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
   - Research findings (e.g., "retrieved 20 papers on agent long-term memory from arXiv")
   - Important data retrieved (e.g., "found 5 relevant academic papers on topic X")

3. **Context** (type: "context")
   - Project goals
   - Constraints or limitations
   - Deadlines or timeframes
   - Current problems or challenges
   - Research topics being investigated

4. **Patterns** (type: "pattern")
   - Recurring requests
   - Common workflows
   - Frequently asked topics
   - Research interests

Special attention to tool outputs:
- When you see "[Tool: terminal]" or similar markers, extract the key information
- For research results (e.g., arXiv papers), note the topic and paper count
- For data retrieval, note what information was found
- These are important "fact" or "context" memories worth preserving

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
            # Return empty result
            return MemoryExtractionResult(
                memories=[],
                summary="",
                topics=[],
            )

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
        _extractor_instance = MemoryExtractor()

    return _extractor_instance


def reset_memory_extractor() -> None:
    """
    Reset the global memory extractor to force recreation on next access.

    This should be called when LLM configuration is updated to ensure
    the new configuration is picked up immediately.
    """
    global _extractor_instance
    _extractor_instance = None
