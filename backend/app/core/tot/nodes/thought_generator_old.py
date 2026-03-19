"""
Thought Generator Node

Generates candidate thoughts for Tree of Thoughts reasoning.
"""

import logging
import re
import uuid
from typing import List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.core.tot.state import ToTState, Thought

logger = logging.getLogger(__name__)


async def thought_generator_node(state: ToTState) -> ToTState:
    """
    Generate candidate thoughts using LLM.

    This node creates multiple thoughts (approaches) to solve the current problem.
    At depth 0, it generates initial approaches. At deeper levels, it extends
    existing reasoning paths.

    Args:
        state: Current ToT state

    Returns:
        Updated state with new thoughts added
    """
    llm = state["llm"]
    current_depth = state["current_depth"]
    user_query = state["user_query"]
    system_prompt = state.get("system_prompt", "")

    logger.info(f"Generating thoughts at depth {current_depth}")

    # Build generation prompt based on depth
    if current_depth == 0:
        # Root: Generate initial approaches
        prompt = _generate_root_prompt(user_query)
    else:
        # Non-root: Extend parent thoughts
        parent_thoughts = [t for t in state["thoughts"] if t.id in state["best_path"]]
        prompt = _generate_extension_prompt(user_query, parent_thoughts)

    # Generate thoughts using LLM
    try:
        messages = [
            SystemMessage(content=_get_generator_system_prompt()),
            HumanMessage(content=prompt)
        ]

        response = await llm.ainvoke(messages)

        # Parse response into Thought objects
        new_thoughts = _parse_thoughts(
            response.content,
            parent_id=state["best_path"][-1] if state["best_path"] else None,
            depth=current_depth
        )

        logger.info(f"Generated {len(new_thoughts)} thoughts at depth {current_depth}")

        # Add to reasoning trace for streaming
        state["reasoning_trace"].append({
            "type": "thoughts_generated",
            "depth": current_depth,
            "count": len(new_thoughts),
            "thoughts": [t.model_dump() for t in new_thoughts]
        })

        state["thoughts"].extend(new_thoughts)

    except Exception as e:
        logger.error(f"Error generating thoughts: {e}", exc_info=True)
        # Fallback: generate simple thoughts
        new_thoughts = _generate_fallback_thoughts(user_query, current_depth)
        state["thoughts"].extend(new_thoughts)

    return state


def _get_generator_system_prompt() -> str:
    """System prompt for thought generation."""
    return """You are an expert reasoning strategist. Your job is to generate diverse, actionable approaches to solve problems.

For each thought you generate:
1. Provide a clear description of the reasoning strategy
2. Identify which tools would be useful (terminal, python_repl, search_kb, fetch_url, etc.)
3. Explain why this approach might work
4. Keep thoughts concise but actionable

Aim for diversity in your suggestions - explore different angles and approaches."""


def _generate_root_prompt(query: str) -> str:
    """Generate prompt for root-level thought generation."""
    return f"""Given the user query: "{query}"

Generate 3-5 different initial approaches to solve this problem. For each approach, provide:

1. **Strategy**: Brief description of the reasoning strategy
2. **Tools**: Which tools to use (terminal, python_repl, search_kb, fetch_url, read_file, write_file)
3. **Rationale**: Why this approach might work

Format your response as a numbered list:

1. **Strategy**: [description]
   **Tools**: [list of tools]
   **Rationale**: [explanation]

2. **Strategy**: [description]
   ..."""


def _generate_extension_prompt(query: str, parent_thoughts: List[Thought]) -> str:
    """Generate prompt for extending existing thoughts."""
    parent_context = "\n".join([
        f"{i+1}. {t.content}" for i, t in enumerate(parent_thoughts)
    ])

    return f"""User query: "{query}"

Previous reasoning steps (the path we've taken so far):
{parent_context}

Based on this context, generate 2-3 next-step thoughts that extend this reasoning. Consider:

1. What information do we still need?
2. What tools can help us get it?
3. How can we refine or verify our approach?
4. What alternative angles should we explore?

Format as numbered list with Strategy, Tools, and Rationale for each thought."""


def _parse_thoughts(content: str, parent_id: str | None, depth: int) -> List[Thought]:
    """
    Parse LLM response into Thought objects.

    Args:
        content: LLM response content
        parent_id: Parent thought ID (for non-root thoughts)
        depth: Current reasoning depth

    Returns:
        List of parsed Thought objects
    """
    thoughts = []
    lines = content.strip().split('\n')

    current_thought = None
    strategy_lines = []
    tools_lines = []
    rationale_lines = []

    for line in lines:
        line = line.strip()

        # Detect numbered items (start of new thought)
        if re.match(r'^\d+\.', line) or re.match(r'^\d+\.\s*\*\*Strategy\*\*:', line):
            # Save previous thought if exists
            if current_thought:
                thoughts.append(_create_thought_from_parts(
                    strategy_lines, tools_lines, rationale_lines,
                    parent_id, depth
                ))

            # Start new thought
            current_thought = True
            strategy_lines = []
            tools_lines = []
            rationale_lines = []

            # Extract strategy from this line
            if "**Strategy**:" in line:
                strategy = line.split("**Strategy**:", 1)[1].strip()
                strategy_lines.append(strategy)

        elif line.startswith("**Strategy**:"):
            strategy_lines.append(line.split(":", 1)[1].strip())
        elif line.startswith("**Tools**:"):
            tools_lines.append(line.split(":", 1)[1].strip())
        elif line.startswith("**Rationale**:"):
            rationale_lines.append(line.split(":", 1)[1].strip())
        elif current_thought:
            # Continuation of current section
            if strategy_lines and not tools_lines and not rationale_lines:
                strategy_lines.append(line)
            elif tools_lines and not rationale_lines:
                tools_lines.append(line)
            elif rationale_lines:
                rationale_lines.append(line)

    # Save last thought
    if current_thought:
        thoughts.append(_create_thought_from_parts(
            strategy_lines, tools_lines, rationale_lines,
            parent_id, depth
        ))

    # Fallback: if no thoughts parsed, create simple thoughts
    if not thoughts:
        return _generate_fallback_thoughts(content, depth, parent_id)

    return thoughts


def _create_thought_from_parts(
    strategy: List[str],
    tools: List[str],
    rationale: List[str],
    parent_id: str | None,
    depth: int
) -> Thought:
    """Create a Thought from parsed components."""
    content = "Strategy: " + " ".join(strategy).strip()
    if rationale:
        content += " | Rationale: " + " ".join(rationale).strip()

    # Parse tool calls
    tool_calls = []
    if tools:
        tools_text = " ".join(tools).lower()
        available_tools = ["terminal", "python_repl", "search_kb", "fetch_url", "read_file", "write_file"]
        for tool in available_tools:
            if tool in tools_text:
                tool_calls.append({"name": tool, "args": {}})

    return Thought(
        id=f"thought_{uuid.uuid4().hex[:8]}",
        parent_id=parent_id,
        content=content,
        tool_calls=tool_calls,
        status="pending"
    )


def _generate_fallback_thoughts(
    query: str, depth: int, parent_id: str | None = None
) -> List[Thought]:
    """Generate fallback thoughts when parsing fails."""
    fallback_strategies = [
        f"Search knowledge base for information about: {query}",
        f"Use Python REPL to analyze data related to: {query}",
        f"Fetch relevant web content about: {query}",
    ]

    thoughts = []
    for i, strategy in enumerate(fallback_strategies[:3]):
        thoughts.append(Thought(
            id=f"thought_{uuid.uuid4().hex[:8]}",
            parent_id=parent_id,
            content=strategy,
            tool_calls=[{"name": "search_kb", "args": {"query": query}}],
            status="pending"
        ))

    return thoughts
