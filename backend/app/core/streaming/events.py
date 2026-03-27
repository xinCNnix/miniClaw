"""
Event type definitions for the streaming response system.

This module defines the event types and data structures used throughout
the event-driven streaming architecture.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Any


class StreamEventType(str, Enum):
    """Stream event types for the event-driven architecture."""

    # LLM events
    TEXT_DELTA = "text_delta"
    THINKING_START = "thinking_start"

    # Tool events
    TOOL_CALL_START = "tool_call_start"
    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_EXECUTION_COMPLETE = "tool_execution_complete"
    TOOL_EXECUTION_ERROR = "tool_execution_error"

    # Control events
    DONE = "done"
    ERROR = "error"


@dataclass
class StreamEvent:
    """
    A streaming event that flows through the event bus.

    Attributes:
        type: The event type from StreamEventType enum
        data: Event-specific data as a dictionary
    """

    type: StreamEventType
    data: dict[str, Any]

    def to_sse_dict(self) -> dict:
        """
        Convert event to SSE (Server-Sent Events) format.

        Returns:
            Dictionary compatible with existing SSE format
        """
        # Convert internal event types to frontend-compatible types
        type_mapping = {
            "text_delta": "content_delta",  # Frontend expects content_delta
            "thinking_start": "thinking_start",
            "tool_call_start": "tool_call",
            "tool_execution_start": "tool_call",
            "tool_execution_complete": "tool_output",
            "tool_execution_error": "error",
            "done": "done",
            "error": "error",
        }

        original_type = self.type.value
        frontend_type = type_mapping.get(self.type.value, self.type.value)

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        if original_type != frontend_type:
            logger.info(f"[Event type conversion] {original_type} -> {frontend_type}")

        return {"type": frontend_type, **self.data}

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"StreamEvent(type={self.type.value}, data={self.data})"
