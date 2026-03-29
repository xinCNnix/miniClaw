"""
Event-driven streaming response system for multi-round tool calling.

This package provides an event-driven architecture to handle streaming responses
with multiple concurrent tool calls, replacing the complex chunk-based approach.
"""

from app.core.streaming.events import StreamEventType, StreamEvent

__all__ = [
    "StreamEventType",
    "StreamEvent",
]
