"""
Request Router and ToT Orchestrator

Routes requests to simple agent or ToT agent based on task complexity.
"""

import asyncio
import logging
from typing import List, Dict, Any, AsyncIterator, Literal

from langchain_core.messages import BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from app.core.tot.state import ToTState, Thought
from app.core.tot.graph_builder import build_tot_graph
from app.core.agent import AgentManager

logger = logging.getLogger(__name__)


class TaskComplexityClassifier:
    """
    Classify incoming tasks by complexity to determine routing.

    Simple tasks go directly to the agent (fast).
    Complex tasks use ToT reasoning (thorough).
    """

    COMPLEXITY_KEYWORDS = {
        "high": [
            "deep research",
            "comprehensive analysis",
            "multi-step",
            "detailed investigation",
            "thorough review",
            "in-depth study"
        ],
        "medium": [
            "analyze",
            "compare",
            "evaluate",
            "explain",
            "investigate",
            "summarize"
        ],
        "low": [
            "simple",
            "quick",
            "basic",
            "brief",
            "what is",
            "how to"
        ]
    }

    def __init__(self, config: Dict[str, Any] | None = None):
        """
        Initialize classifier with optional config.

        Args:
            config: Configuration dict with thresholds
        """
        self.config = config or {}
        self.query_length_threshold = self.config.get("query_length_threshold", 200)
        self.multi_question_threshold = self.config.get("multi_question_threshold", 2)

    def classify(
        self,
        query: str,
        session_context: Dict[str, Any] | None = None
    ) -> Literal["simple", "complex"]:
        """
        Classify task complexity.

        Factors:
        1. Query length and complexity
        2. Presence of complexity keywords
        3. Multiple sub-questions
        4. Session context (follow-up vs new task)

        Args:
            query: User query text
            session_context: Optional session context

        Returns:
            "simple" or "complex"
        """
        query_lower = query.lower()
        session_context = session_context or {}

        # Factor 1: Check for high-complexity keywords
        for keyword in self.COMPLEXITY_KEYWORDS["high"]:
            if keyword in query_lower:
                logger.info(f"Classified as COMPLEX due to keyword: {keyword}")
                return "complex"

        # Factor 2: Check query length
        if len(query) > self.query_length_threshold:
            logger.info(f"Classified as COMPLEX due to length: {len(query)}")
            return "complex"

        # Factor 3: Check for multiple sub-questions
        question_count = query.count("?")
        if question_count >= self.multi_question_threshold:
            logger.info(f"Classified as COMPLEX due to {question_count} questions")
            return "complex"

        # Factor 4: Check for complex structures (lists, numbered items)
        lines = query.split("\n")
        if len(lines) > 3:
            # Check if it looks like a structured request
            numbered_lines = sum(1 for line in lines if line.strip().startswith(("1.", "2.", "3.", "-", "*")))
            if numbered_lines >= 2:
                logger.info("Classified as COMPLEX due to structured format")
                return "complex"

        # Default: simple
        logger.info("Classified as SIMPLE")
        return "simple"


class ToTOrchestrator:
    """
    Main orchestrator for Tree of Thoughts reasoning.

    Routes requests to simple agent or ToT agent based on complexity,
    and manages ToT execution with streaming.
    """

    def __init__(self, agent_manager: AgentManager, max_depth: int = 3, branching_factor: int = 3):
        """
        Initialize ToT Orchestrator.

        Args:
            agent_manager: Existing AgentManager instance
            max_depth: Maximum reasoning depth
            branching_factor: Branching factor for thought generation
        """
        self.agent_manager = agent_manager
        self.classifier = TaskComplexityClassifier()
        self.graph = None  # Lazy-loaded
        self.max_depth = max_depth
        self.branching_factor = branching_factor

    async def process_request(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        enable_tot: bool = False,
        max_depth: int = 3
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Route request to simple agent or ToT agent.

        Args:
            messages: User messages (list of {role, content} dicts)
            system_prompt: System prompt
            enable_tot: Force enable ToT regardless of complexity
            max_depth: Maximum reasoning depth for ToT

        Yields:
            SSE event dicts (same format as existing agent)
        """
        user_query = messages[-1]["content"] if messages else ""
        session_context = {}  # TODO: Extract from messages if needed

        # Classify task complexity
        if enable_tot:
            complexity = "complex"
        else:
            complexity = self.classifier.classify(user_query, session_context)

        logger.info(f"Routing {complexity} task")

        # Route based on complexity
        if complexity == "simple":
            # Use simple agent (existing fast path)
            async for event in self._stream_simple_agent(messages, system_prompt):
                yield event
        else:
            # Use ToT agent
            async for event in self._stream_tot_reasoning(
                user_query,
                messages,
                system_prompt,
                max_depth
            ):
                yield event

    async def _stream_simple_agent(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream using existing simple agent."""
        async for event in self.agent_manager.astream(messages, system_prompt):
            yield event

    async def _stream_tot_reasoning(
        self,
        query: str,
        messages: List[Dict[str, str]],
        system_prompt: str,
        max_depth: int
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute ToT reasoning with streaming."""
        # Initialize ToT state
        initial_state: ToTState = {
            "user_query": query,
            "session_context": {},
            "messages": [],  # Will be populated from messages
            "thoughts": [],
            "current_depth": 0,
            "max_depth": max_depth,
            "branching_factor": self.branching_factor,  # Use orchestrator's branching factor
            "best_path": [],
            "best_score": 0.0,
            "tools": self.agent_manager.tools,
            "llm": self.agent_manager.llm,  # Use base LLM for thought generation
            "llm_with_tools": self.agent_manager.llm_with_tools,  # LLM with tools for actual tool calling
            "system_prompt": system_prompt,
            "research_sources": None,
            "research_stage": None,
            "final_answer": None,
            "reasoning_trace": [],
            "fallback_to_simple": False
        }

        # Build LangGraph if not exists
        if not self.graph:
            self.graph = build_tot_graph()

        try:
            # Stream reasoning start
            from app.core.tot.streaming import ToTEventStreamer
            streamer = ToTEventStreamer()

            yield streamer.create_reasoning_start_event(max_depth)

            # Execute graph with streaming (no checkpointer, so no config needed)
            # Add timeout protection
            async with asyncio.timeout(36000):  # 36000 seconds timeout (10 hours)
                # Use astream() to get intermediate states for progress updates
                # LangGraph's astream() yields dicts like {node_name: state}
                final_state = None
                async for graph_output in self.graph.astream(initial_state):
                    # graph_output is a dict {node_name: state_dict}
                    if isinstance(graph_output, dict):
                        # Get the state from the dict
                        # If it's {node_name: state}, extract the state
                        # If it's already the state, use it directly
                        if len(graph_output) == 1:
                            # Likely {node_name: state} format
                            node_name = list(graph_output.keys())[0]
                            state = graph_output[node_name]
                        else:
                            # Likely the state itself
                            state = graph_output
                    else:
                        state = graph_output

                    final_state = state

                    # Stream detailed reasoning steps
                    async for sse_event in streamer.stream_tot_reasoning(initial_state, state):
                        yield sse_event

                    # Also send periodic tree updates
                    if "thoughts" in state and len(state["thoughts"]) > 0:
                        tree_update = streamer.create_tree_update_event(state["thoughts"])
                        yield tree_update

            # After graph completes, check if we have a final answer
            if final_state and final_state.get("final_answer"):
                logger.info(f"✓ Found final_answer in final_state, yielding content_delta")
                yield {
                    "type": "content_delta",
                    "content": final_state["final_answer"]
                }

                # Send completion event
                complete_event = streamer.create_reasoning_complete_event(
                    final_state["final_answer"],
                    final_state.get("best_path", []),
                    len(final_state.get("thoughts", []))
                )
                yield complete_event
            else:
                logger.warning(f"✗ No final_answer in final_state. Keys: {list(final_state.keys()) if final_state else 'None'}")
                # Fallback: generate simple answer
                fallback_answer = f"I've analyzed your query about: {user_query}\n\nBased on my Tree of Thoughts reasoning, I explored {len(final_state.get('thoughts', [])) if final_state else 0} thoughts. The best path scored {final_state.get('best_score', 0) if final_state else 0:.2f}."
                yield {
                    "type": "content_delta",
                    "content": fallback_answer
                }

        except asyncio.TimeoutError:
            logger.error("ToT execution timed out after 36000 seconds")
            yield {
                "type": "error",
                "error": "ToT execution timed out"
            }
        except Exception as e:
            logger.error(f"ToT reasoning error: {e}", exc_info=True)
            yield {
                "type": "error",
                "error": f"Reasoning error: {str(e)}"
            }

        # Final done event
        yield {"type": "done"}
