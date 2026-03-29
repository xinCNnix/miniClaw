"""LangGraph node functions for pattern memory."""

import logging
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool

from auto_learning.memory import get_pattern_memory

logger = logging.getLogger(__name__)


class PatternState(dict[str, Any]):
    """State for pattern learning graph.

    This state is passed between nodes in the pattern learning graph.
    It follows the same pattern as miniclaw's ToTState.

    Attributes:
        user_query: User's input query
        messages: List of LangChain messages
        retrieved_patterns: List of retrieved relevant patterns
        extracted_pattern: Newly extracted pattern
        tools: List of available tools
        llm: Base LLM instance
        llm_with_tools: LLM with tools bound
        system_prompt: System prompt for LLM
        final_answer: Final answer from agent
    """

    # Input
    user_query: str
    messages: list[BaseMessage]

    # Pattern Memory
    retrieved_patterns: list[str]  # Retrieved relevant patterns
    extracted_pattern: Optional[str]  # Extracted new pattern

    # Agent Context
    tools: list[BaseTool]
    llm: BaseChatModel
    llm_with_tools: BaseChatModel
    system_prompt: str

    # Results
    final_answer: Optional[str]


async def retrieve_patterns_node(state: PatternState) -> PatternState:
    """Retrieve relevant patterns and inject into system prompt.

    This node:
    1. Retrieves relevant patterns from pattern memory
    2. Injects them into the system prompt
    3. Updates the state

    Args:
        state: Current graph state

    Returns:
        Updated state with retrieved patterns and modified system prompt
    """
    logger.info(f"Retrieving patterns for query: {state['user_query'][:50]}...")

    try:
        # Get pattern memory
        memory = get_pattern_memory()

        # Retrieve top K patterns
        patterns = memory.get_top_patterns(state["user_query"], top_k=3)

        # Extract pattern descriptions
        pattern_descriptions = [p["description"] for p in patterns]

        state["retrieved_patterns"] = pattern_descriptions

        # Inject patterns into system prompt
        if pattern_descriptions:
            pattern_text = "\n".join([f"• {p}" for p in pattern_descriptions])
        else:
            pattern_text = "（暂无历史模式）"

        state["system_prompt"] = f"""你是一个主动学习的 Agent。

**历史提炼模式（必须优先参考）**：
{pattern_text}

当执行任务时，优先参考这些模式，避免重复犯错。"""

        logger.info(f"Retrieved {len(pattern_descriptions)} patterns")

    except Exception as e:
        logger.error(f"Failed to retrieve patterns: {e}", exc_info=True)
        # Use default system prompt if retrieval fails
        state["retrieved_patterns"] = []
        state["system_prompt"] = state.get("system_prompt", "You are a helpful AI assistant.")

    return state


async def agent_node(state: PatternState) -> PatternState:
    """Execute agent task with LLM and tools.

    This node:
    1. Invokes the LLM with tools
    2. Updates message history
    3. Extracts final answer

    Args:
        state: Current graph state

    Returns:
        Updated state with agent response
    """
    logger.info("Executing agent node")

    try:
        # Invoke LLM with tools
        response = await state["llm_with_tools"].ainvoke(state["messages"])

        # Update messages
        state["messages"].append(response)

        # Extract final answer
        if hasattr(response, "content"):
            state["final_answer"] = response.content
        else:
            state["final_answer"] = str(response)

        logger.info(f"Agent execution completed: {state['final_answer'][:100]}...")

    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        state["final_answer"] = f"Error: {str(e)}"

    return state


async def extract_pattern_node(state: PatternState) -> PatternState:
    """Extract pattern from execution result.

    This node:
    1. Extracts a pattern from the execution result
    2. Stores it in pattern memory
    3. Updates the state

    Args:
        state: Current graph state

    Returns:
        Updated state with extracted pattern
    """
    logger.info("Extracting pattern from execution result")

    try:
        # Get pattern memory
        memory = get_pattern_memory()

        # Extract and store pattern
        result = await memory.extract_and_store(
            situation=state["user_query"],
            outcome=state["final_answer"] or "No result",
            fix="Agent execution completed",
        )

        state["extracted_pattern"] = result.pattern

        logger.info(f"Successfully extracted pattern: {result.pattern[:100]}...")

    except Exception as e:
        logger.error(f"Pattern extraction failed: {e}", exc_info=True)
        state["extracted_pattern"] = None

    return state
