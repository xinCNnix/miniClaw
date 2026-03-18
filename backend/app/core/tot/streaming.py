"""
ToT Event Streaming Module

Enhanced streaming events for Tree of Thoughts reasoning.
"""

import logging
from typing import Dict, Any, AsyncIterator

from app.core.tot.state import ToTState, Thought

logger = logging.getLogger(__name__)


class ToTEventStreamer:
    """
    Streams ToT reasoning events to frontend.

    Event types:
    - tot_reasoning_start: ToT reasoning started
    - tot_thoughts_generated: New thoughts generated
    - tot_thoughts_evaluated: Thoughts evaluated with scores
    - tot_best_path_updated: Best path changed
    - tot_tools_executed: Tools executed for thoughts
    - tot_reasoning_complete: ToT reasoning completed
    """

    @staticmethod
    async def stream_tot_reasoning(
        state: ToTState,
        graph_state: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream ToT reasoning events from graph state.

        Args:
            state: ToT state
            graph_state: Current graph execution state

        Yields:
            SSE event dicts
        """
        # Check reasoning trace for new events
        if "reasoning_trace" not in graph_state:
            return

        trace = graph_state["reasoning_trace"]

        # Stream all trace events
        for trace_event in trace:
            event = ToTEventStreamer._convert_trace_to_sse(trace_event, graph_state)
            if event:
                yield event

    @staticmethod
    def _convert_trace_to_sse(
        trace_event: Dict[str, Any],
        graph_state: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """
        Convert a trace event to SSE format.

        Args:
            trace_event: Trace event from reasoning_trace
            graph_state: Current graph state

        Returns:
            SSE event dict or None
        """
        event_type = trace_event.get("type")

        if event_type == "thoughts_generated":
            return {
                "type": "tot_thoughts_generated",
                "depth": trace_event.get("depth", 0),
                "count": trace_event.get("count", 0),
                "thoughts": [
                    {
                        "id": t.get("id"),
                        "content": t.get("content"),
                        "parent_id": t.get("parent_id")
                    }
                    for t in trace_event.get("thoughts", [])
                ]
            }

        elif event_type == "thoughts_evaluated":
            return {
                "type": "tot_thoughts_evaluated",
                "best_path": trace_event.get("best_path", []),
                "best_score": trace_event.get("best_score", 0.0)
            }

        elif event_type == "thought_execution":
            return {
                "type": "tot_tools_executed",
                "thought_id": trace_event.get("thought_id"),
                "content": trace_event.get("content"),
                "tool_count": trace_event.get("tool_count", 0)
            }

        elif event_type == "termination":
            return {
                "type": "tot_termination",
                "reason": trace_event.get("reason"),
                "score": trace_event.get("score"),
                "depth": trace_event.get("depth")
            }

        return None

    @staticmethod
    def create_reasoning_start_event(max_depth: int) -> Dict[str, Any]:
        """Create event signaling start of ToT reasoning."""
        return {
            "type": "tot_reasoning_start",
            "mode": "tot",
            "max_depth": max_depth
        }

    @staticmethod
    def create_reasoning_complete_event(
        final_answer: str,
        best_path: list,
        total_thoughts: int
    ) -> Dict[str, Any]:
        """Create event signaling completion of ToT reasoning."""
        return {
            "type": "tot_reasoning_complete",
            "final_answer": final_answer,
            "best_path": best_path,
            "total_thoughts": total_thoughts
        }

    @staticmethod
    def create_tree_update_event(thoughts: list[Thought]) -> Dict[str, Any]:
        """
        Create event with full tree structure for visualization.

        Args:
            thoughts: List of all thoughts

        Returns:
            Tree update event
        """
        tree = ToTEventStreamer._build_tree_structure(thoughts)

        return {
            "type": "tot_tree_update",
            "tree": tree
        }

    @staticmethod
    def _build_tree_structure(thoughts: list[Thought]) -> list[Dict]:
        """
        Build hierarchical tree structure from flat thoughts list.

        Args:
            thoughts: List of all thoughts

        Returns:
            Hierarchical tree structure
        """
        # Build lookup map
        thought_map = {t.id: t for t in thoughts}

        # Build tree recursively
        def build_node(thought_id: str) -> Dict:
            thought = thought_map.get(thought_id)
            if not thought:
                return None

            # Find children
            children = [
                build_node(t.id)
                for t in thoughts
                if t.parent_id == thought_id
            ]
            children = [c for c in children if c is not None]

            return {
                "id": thought.id,
                "content": thought.content,
                "parent_id": thought.parent_id,
                "score": thought.evaluation_score,
                "status": thought.status,
                "children": children
            }

        # Find root thoughts (no parent)
        roots = [
            build_node(t.id)
            for t in thoughts
            if t.parent_id is None
        ]

        return [r for r in roots if r is not None]


async def stream_tot_events(
    state: ToTState,
    graph_state: Dict[str, Any]
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream ToT reasoning events (convenience wrapper).

    Args:
        state: ToT state
        graph_state: Current graph state

    Yields:
        SSE event dicts
    """
    streamer = ToTEventStreamer()
    async for event in streamer.stream_tot_reasoning(state, graph_state):
        yield event
