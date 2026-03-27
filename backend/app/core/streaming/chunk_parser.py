"""
Chunk parser for extracting events from LLM streaming responses.

This module parses LLM chunks and converts them into structured events.
It does NOT rely on tool_call_chunks, instead using complete tool_calls.
"""

from typing import Any, List
from langchain_core.messages import AIMessage

from app.core.streaming.events import StreamEvent, StreamEventType


class ChunkParser:
    """
    Parser for LLM streaming chunks.

    This parser extracts text and tool calls from LLM chunks and converts
    them into structured StreamEvent objects. It does NOT use tool_call_chunks,
    avoiding the complexity of merging partial chunks.
    """

    def __init__(self) -> None:
        """Initialize the chunk parser."""
        self._buffer = ""

    def feed(self, chunk: Any) -> List[StreamEvent]:
        """
        Parse a chunk and return a list of events.

        Args:
            chunk: A chunk from LLM streaming response (typically AIMessage)

        Returns:
            List of StreamEvent objects extracted from the chunk

        Note:
            This method does NOT use tool_call_chunks. It only processes
            complete tool_calls to avoid the complexity of merging partial chunks.
            TOOL_CALL_START events are NOT generated here; they are handled
            by the coordinator to avoid duplicates.
        """
        events = []

        # Extract text content
        if hasattr(chunk, 'content') and chunk.content:
            events.append(StreamEvent(
                type=StreamEventType.TEXT_DELTA,
                data={"content": chunk.content}
            ))

        # Note: Tool calls are NOT converted to events here to avoid duplicates.
        # The coordinator handles tool call events after streaming completes.

        return events

    def reset(self) -> None:
        """Reset the parser state (clear buffer)."""
        self._buffer = ""
