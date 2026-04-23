"""
ToT Event Streaming Module

Enhanced streaming events for Tree of Thoughts reasoning.
"""

import logging
import re
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
                "best_score": trace_event.get("best_score", 0.0),
                # Phase 8: beam fields for frontend visualization
                "active_beams": trace_event.get("active_beams", []),
                "beam_scores": trace_event.get("beam_scores", []),
            }

        elif event_type == "thought_execution":
            # Phase 8: enhanced with step counts

            # Strip base64/SVG blobs from content to prevent MemoryError
            # (tool results may contain embedded image data)
            raw_content = trace_event.get("content", "")
            if isinstance(raw_content, str):
                raw_content = re.sub(
                    r'data:image/[^;]+;base64,[A-Za-z0-9+/=\n]+',
                    '[image data removed]',
                    raw_content,
                )
                # Also strip large inline SVG blocks
                raw_content = re.sub(
                    r'<svg[^>]*>.*?</svg>',
                    '[SVG removed]',
                    raw_content,
                    flags=re.DOTALL,
                )

            event = {
                "type": "tot_tools_executed",
                "thought_id": trace_event.get("thought_id"),
                "content": raw_content,
                "tool_count": trace_event.get("tool_count", trace_event.get("total_steps", 0)),
                # Phase 8: step details for local loop visualization
                "total_steps": trace_event.get("total_steps", 0),
                "executed_steps": trace_event.get("executed_steps", 0),
                "errors": trace_event.get("errors", 0),
            }
            # [IMAGE_UNIFY] Don't send generated_images in SSE events.
            # Images render inline via synthesis_node's _resolve_image_refs.
            # generated_images = trace_event.get("generated_images", [])
            # if generated_images:
            #     event["generated_images"] = generated_images
            return event

        # Phase 8: backtracking events
        elif event_type == "backtrack":
            return {
                "type": "tot_backtrack",
                "reason": trace_event.get("reason"),
                "depth": trace_event.get("depth"),
                "beam_idx": trace_event.get("beam_idx"),
                "from_root": trace_event.get("from_root"),
                "to_root": trace_event.get("to_root"),
            }

        # Phase 8: regeneration events
        elif event_type == "thoughts_regenerated":
            return {
                "type": "tot_thoughts_regenerated",
                "depth": trace_event.get("depth", 0),
                "beam_indices": trace_event.get("beam_indices", []),
                "count": trace_event.get("count", 0),
            }

        elif event_type == "termination":
            return {
                "type": "tot_termination",
                "reason": trace_event.get("reason"),
                "score": trace_event.get("score"),
                "depth": trace_event.get("depth")
            }

        # Post-execution re-evaluation events
        elif event_type == "post_execution_re_evaluated":
            return {
                "type": "tot_re_evaluated",
                "thoughts_updated": trace_event.get("thoughts_updated", 0),
                "best_score": trace_event.get("best_score", 0.0),
                "score_before": trace_event.get("score_before", 0.0),
                "details": trace_event.get("details", []),
            }

        # --- Research-mode SSE events ---

        elif event_type == "research_evidence_extracted":
            return {
                "type": "tot_research_evidence",
                "evidence_count": trace_event.get("evidence_count", 0),
                "sources_processed": trace_event.get("sources_processed", 0),
            }

        elif event_type == "research_coverage_update":
            return {
                "type": "tot_research_coverage",
                "score": trace_event.get("score", 0.0),
                "topics": trace_event.get("topics", []),
            }

        elif event_type == "research_contradiction":
            return {
                "type": "tot_research_contradiction",
                "contradictions": trace_event.get("contradictions", []),
            }

        elif event_type == "research_draft_update":
            return {
                "type": "tot_research_draft",
                "draft_length": trace_event.get("draft_length", 0),
                "round": trace_event.get("round", 0),
            }

        elif event_type == "research_citation_fetch":
            return {
                "type": "tot_research_citation",
                "targets": trace_event.get("targets", []),
                "new_sources": trace_event.get("new_sources", 0),
            }

        return None

    @staticmethod
    def create_reasoning_start_event(
        max_depth: int,
        task_mode: str = "standard",
        task_type: str = "generic",
    ) -> Dict[str, Any]:
        """Create event signaling start of ToT reasoning."""
        return {
            "type": "tot_reasoning_start",
            "mode": "tot",
            "max_depth": max_depth,
            "task_mode": task_mode,
            "task_type": task_type,
        }

    @staticmethod
    def create_reasoning_complete_event(
        final_answer: str,
        best_path: list,
        total_thoughts: int
    ) -> Dict[str, Any]:
        """Create event signaling completion of ToT reasoning.

        Fix 4: Only sends final_answer_length and final_answer_preview (first 200 chars)
        to avoid bloating the SSE event with the full answer (which is already
        delivered via content_delta).
        """
        return {
            "type": "tot_reasoning_complete",
            "final_answer_length": len(final_answer),
            "final_answer_preview": final_answer[:200] + ("..." if len(final_answer) > 200 else ""),
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

        Deduplicates by thought ID to prevent exponential growth
        if the reducer accidentally duplicates entries.
        """
        # Deduplicate by id (keep first occurrence)
        seen_ids: set[str] = set()
        unique: list[Thought] = []
        for t in thoughts:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                unique.append(t)

        if len(unique) < len(thoughts):
            logger.warning(
                "[TreeUpdate] Deduplicated thoughts: %d → %d",
                len(thoughts), len(unique),
            )

        # Build lookup map from deduplicated list
        thought_map = {t.id: t for t in unique}

        # Build tree recursively
        def build_node(thought_id: str) -> Dict:
            thought = thought_map.get(thought_id)
            if not thought:
                return None

            # Find children from deduplicated list
            children = [
                build_node(t.id)
                for t in unique
                if t.parent_id == thought_id
            ]
            children = [c for c in children if c is not None]

            return {
                "id": thought.id,
                "content": thought.content,
                "parent_id": thought.parent_id,
                "score": thought.evaluation_score,
                "status": thought.status,
                "tool_calls": [
                    {"name": tc.get("name", ""), "args": tc.get("args", {})}
                    for tc in thought.tool_calls
                ] if thought.tool_calls else [],
                "children": children
            }

        # Find root thoughts (no parent)
        roots = [
            build_node(t.id)
            for t in unique
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
