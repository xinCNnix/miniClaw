"""
Response aggregator for streaming response system.

This module aggregates events into SSE responses for the client.
"""

import asyncio
from typing import List, Dict, Any
from app.core.streaming.events import StreamEvent, StreamEventType
from app.core.streaming.event_bus import EventBus


class ResponseAggregator:
    """
    Aggregates streaming events into SSE responses.

    This aggregator subscribes to events on the event bus and
    converts them into SSE-compatible response dictionaries.
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the response aggregator.

        Args:
            event_bus: Event bus to subscribe to
        """
        self._event_bus = event_bus
        self._responses: List[Dict[str, Any]] = []
        self._is_streaming = False

    async def start_streaming(self) -> None:
        """Start streaming by subscribing to all events."""
        if self._is_streaming:
            return

        self._is_streaming = True
        self._responses.clear()

        # Subscribe to all event types
        self._event_bus.subscribe(StreamEventType.TEXT_DELTA, self._handle_text_delta)
        self._event_bus.subscribe(StreamEventType.TOOL_CALL_START, self._handle_tool_call_start)
        self._event_bus.subscribe(StreamEventType.TOOL_EXECUTION_START, self._handle_tool_execution_start)
        self._event_bus.subscribe(StreamEventType.TOOL_EXECUTION_COMPLETE, self._handle_tool_execution_complete)
        self._event_bus.subscribe(StreamEventType.TOOL_EXECUTION_ERROR, self._handle_tool_execution_error)
        self._event_bus.subscribe(StreamEventType.DONE, self._handle_done)
        self._event_bus.subscribe(StreamEventType.ERROR, self._handle_error)

    async def stop_streaming(self) -> None:
        """Stop streaming and unsubscribe from all events."""
        if not self._is_streaming:
            return

        self._is_streaming = False

        # Unsubscribe from all events
        self._event_bus.unsubscribe(StreamEventType.TEXT_DELTA, self._handle_text_delta)
        self._event_bus.unsubscribe(StreamEventType.TOOL_CALL_START, self._handle_tool_call_start)
        self._event_bus.unsubscribe(StreamEventType.TOOL_EXECUTION_START, self._handle_tool_execution_start)
        self._event_bus.unsubscribe(StreamEventType.TOOL_EXECUTION_COMPLETE, self._handle_tool_execution_complete)
        self._event_bus.unsubscribe(StreamEventType.TOOL_EXECUTION_ERROR, self._handle_tool_execution_error)
        self._event_bus.unsubscribe(StreamEventType.DONE, self._handle_done)
        self._event_bus.unsubscribe(StreamEventType.ERROR, self._handle_error)

    async def _handle_text_delta(self, event: StreamEvent) -> None:
        """Handle text delta event."""
        self._responses.append(event.to_sse_dict())

    async def _handle_tool_call_start(self, event: StreamEvent) -> None:
        """Handle tool call start event."""
        self._responses.append(event.to_sse_dict())

    async def _handle_tool_execution_start(self, event: StreamEvent) -> None:
        """Handle tool execution start event."""
        self._responses.append(event.to_sse_dict())

    async def _handle_tool_execution_complete(self, event: StreamEvent) -> None:
        """Handle tool execution complete event."""
        self._responses.append(event.to_sse_dict())

    async def _handle_tool_execution_error(self, event: StreamEvent) -> None:
        """Handle tool execution error event."""
        self._responses.append(event.to_sse_dict())

    async def _handle_done(self, event: StreamEvent) -> None:
        """Handle done event."""
        self._responses.append(event.to_sse_dict())

    async def _handle_error(self, event: StreamEvent) -> None:
        """Handle error event."""
        self._responses.append(event.to_sse_dict())

    def get_responses(self) -> List[Dict[str, Any]]:
        """
        Get all accumulated responses.

        Returns:
            List of SSE-compatible response dictionaries
        """
        return self._responses.copy()

    def clear_responses(self) -> None:
        """Clear all accumulated responses."""
        self._responses.clear()

    @property
    def is_streaming(self) -> bool:
        """Check if currently streaming."""
        return self._is_streaming

    @property
    def response_count(self) -> int:
        """Get number of accumulated responses."""
        return len(self._responses)
