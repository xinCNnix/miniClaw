"""
Async event bus for streaming response system.

This module implements an asynchronous event bus that supports:
- Event queuing and dispatching
- Publisher-subscriber pattern
- Async event processing
"""

import asyncio
from typing import Callable, Awaitable, List, Any
from collections import defaultdict
from app.core.streaming.events import StreamEvent, StreamEventType


class EventBus:
    """
    Asynchronous event bus for streaming events.

    This bus manages event distribution from producers to consumers
    using the publisher-subscriber pattern.
    """

    def __init__(self) -> None:
        """Initialize the event bus."""
        # Subscribers: event_type -> list of handlers
        self._subscribers: dict[
            StreamEventType,
            List[Callable[[StreamEvent], Awaitable[None]]]
        ] = defaultdict(list)

        # Event queue for async processing
        self._queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

        # Processing task
        self._processing_task: asyncio.Task[None] | None = None

        # Flag to stop processing
        self._stopped = False

    def subscribe(
        self,
        event_type: StreamEventType,
        handler: Callable[[StreamEvent], Awaitable[None]]
    ) -> None:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: The type of event to subscribe to
            handler: Async handler function that receives the event
        """
        self._subscribers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: StreamEventType,
        handler: Callable[[StreamEvent], Awaitable[None]]
    ) -> None:
        """
        Unsubscribe a handler from events.

        Args:
            event_type: The event type to unsubscribe from
            handler: The handler to remove
        """
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    async def publish(self, event: StreamEvent) -> None:
        """
        Publish an event to the bus.

        Args:
            event: The event to publish
        """
        await self._queue.put(event)

    async def start(self) -> None:
        """Start the event processing loop."""
        if self._processing_task is None:
            self._stopped = False  # Reset stop flag
            self._processing_task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop the event processing loop."""
        self._stopped = True
        # Send sentinel to stop the loop
        await self._queue.put(None)
        if self._processing_task:
            await self._processing_task
            self._processing_task = None

    async def _process_loop(self) -> None:
        """
        Main event processing loop.

        This runs continuously, pulling events from the queue
        and dispatching them to subscribers.
        """
        while not self._stopped:
            event = await self._queue.get()

            # Check for sentinel (stop signal)
            if event is None:
                break

            # Dispatch to all subscribers for this event type
            handlers = self._subscribers.get(event.type, [])
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    # Log error but continue processing other handlers
                    # TODO: Add proper logging
                    print(f"Error in event handler: {e}")

    async def publish_batch(self, events: List[StreamEvent]) -> None:
        """
        Publish multiple events in batch.

        Args:
            events: List of events to publish
        """
        for event in events:
            await self.publish(event)

    def clear_subscribers(self) -> None:
        """Clear all subscribers (useful for testing)."""
        self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        """Get total number of subscribers across all event types."""
        return sum(len(handlers) for handlers in self._subscribers.values())

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
