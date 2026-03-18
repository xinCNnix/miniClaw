"""
Enhanced Thought Generator Node

Generates diverse candidate thoughts with branching support.
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
    Generate multiple diverse candidate thoughts using LLM.

    Enhanced features:
    - Generates 3-5 thoughts per step (branching)
    - Encourages diversity in tool selection and reasoning
    - Maintains coherence with parent thoughts
    - Uses different prompt strategies for variety
    - Uses llm_with_tools to generate proper tool calls with arguments

    Args:
        state: Current ToT state

    Returns:
        Updated state with new thoughts added
    """
    llm_with_tools = state.get("llm_with_tools", state["llm"])  # Use LLM with tools if available
    current_depth = state["current_depth"]
    user_query = state["user_query"]
    branching_factor = state.get("branching_factor", 3)  # Get from state, default to 3

    logger.info(f"Generating {branching_factor} thoughts at depth {current_depth}")

    # OPTIMIZATION: Use single prompt to generate all thoughts at once
    # Build generation prompt based on depth
    if current_depth == 0:
        # Root: Generate diverse initial approaches
        prompt = _generate_combined_root_prompt(user_query, branching_factor)
    else:
        # Non-root: Extend with diverse alternatives
        parent_thoughts = [t for t in state["thoughts"] if t.id in state["best_path"]]
        prompt = _generate_combined_extension_prompt(user_query, parent_thoughts, branching_factor)

    # Generate thoughts using single prompt for efficiency
    all_new_thoughts = []

    try:
        messages = [
            SystemMessage(content=_get_generator_system_prompt(0)),
            HumanMessage(content=prompt)
        ]

        logger.info(f"[TOT_GENERATOR] Sending prompt to LLM with tools")
        logger.info(f"[TOT_GENERATOR] System prompt length: {len(_get_generator_system_prompt(0))}")
        logger.info(f"[TOT_GENERATOR] User prompt: {prompt[:200]}...")

        response = await llm_with_tools.ainvoke(messages)

        # DEBUG: Log response details
        logger.info(f"[TOT_GENERATOR] Response received")
        logger.info(f"[TOT_GENERATOR] Response type: {type(response)}")
        logger.info(f"[TOT_GENERATOR] Has tool_calls attr: {hasattr(response, 'tool_calls')}")

        if hasattr(response, 'tool_calls'):
            logger.info(f"[TOT_GENERATOR] Tool calls count: {len(response.tool_calls) if response.tool_calls else 0}")
            if response.tool_calls:
                for tc in response.tool_calls:
                    logger.info(f"[TOT_GENERATOR]   - Tool: {tc.get('name', 'unknown')}, Args: {tc.get('args', {})}")

        if hasattr(response, 'content'):
            logger.info(f"[TOT_GENERATOR] Response content length: {len(response.content) if response.content else 0}")
            logger.info(f"[TOT_GENERATOR] Response content preview: {str(response.content)[:300] if response.content else 'EMPTY'}...")

        # Parse response into Thought objects
        # If LLM made tool calls, extract them properly
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # LLM generated tool calls - create thoughts from them
            logger.info(f"[TOT_GENERATOR] Creating thoughts from {len(response.tool_calls)} tool calls")
            all_new_thoughts = _create_thoughts_from_tool_calls(
                response.tool_calls,
                response.content,
                parent_id=state["best_path"][-1] if state["best_path"] else None,
                depth=current_depth
            )
        else:
            # No tool calls, parse text response
            logger.warning(f"[TOT_GENERATOR] No tool calls in response! Parsing as text response.")
            all_new_thoughts = _parse_thoughts(
                response.content,
                parent_id=state["best_path"][-1] if state["best_path"] else None,
                depth=current_depth
            )

        logger.info(f"Generated {len(all_new_thoughts)} thoughts from single prompt")

    except Exception as e:
        logger.error(f"Error generating thoughts: {e}")
        # Generate fallback thoughts
        all_new_thoughts = _generate_fallback_thoughts(
            user_query, current_depth,
            state["best_path"][-1] if state["best_path"] else None,
            branching_factor
        )

    # Ensure we have at least branching_factor thoughts
    if len(all_new_thoughts) < branching_factor:
        fallback_thoughts = _generate_fallback_thoughts(
            user_query, current_depth,
            state["best_path"][-1] if state["best_path"] else None,
            branching_factor - len(all_new_thoughts)
        )
        all_new_thoughts.extend(fallback_thoughts)

    # Deduplicate thoughts based on content similarity
    unique_thoughts = _deduplicate_thoughts(all_new_thoughts)

    logger.info(f"Total unique thoughts generated at depth {current_depth}: {len(unique_thoughts)}")

    # Add to reasoning trace for streaming
    state["reasoning_trace"].append({
        "type": "thoughts_generated",
        "depth": current_depth,
        "count": len(unique_thoughts),
        "thoughts": [t.model_dump() for t in unique_thoughts]
    })

    state["thoughts"].extend(unique_thoughts)

    return state


def _get_generator_system_prompt(variant: int = 0) -> str:
    """
    Generate system prompt with different emphases for diversity.

    Args:
        variant: Which prompt variant to use (0-2)

    Returns:
        System prompt string
    """
    base_prompt = """You are an expert reasoning strategist. Your job is to solve problems by using available tools and reasoning.

CRITICAL INSTRUCTION:
You MUST use tools when they can help gather information or complete tasks.
When you need information, you MUST call the appropriate tool with the correct arguments.

Available tools:
- search_kb: Search the knowledge base for information (requires "query" parameter)
- fetch_url: Fetch content from a URL (requires "url" parameter)
- read_file: Read a local file (requires "path" parameter)
- python_repl: Execute Python code (requires "code" parameter)
- terminal: Execute shell commands (requires "command" parameter)

HOW TO USE TOOLS:
When you need to use a tool, respond with a tool call in this format:
<tool_call>
<tool_name>search_kb</tool_name>
<tool_arguments>{"query": "your search query here"}</tool_arguments>
</tool_call>

IMPORTANT: Always provide required arguments when calling tools."""

    variants = [
        base_prompt + """

Aim for: **Conservative, well-tested approaches** that are likely to succeed.
Focus on reliability and proven methods.""",

        base_prompt + """

Aim for: **Creative, innovative approaches** that explore novel angles.
Focus on outside-the-box thinking and alternative perspectives.""",

        base_prompt + """

Aim for: **Balanced approaches** that combine reliability with innovation.
Focus on practical solutions with some creative elements."""
    ]

    return variants[variant % len(variants)]


def _generate_combined_root_prompt(query: str, count: int) -> str:
    """
    Generate a single combined prompt for root-level thoughts.

    Args:
        query: User query
        count: Number of thoughts to generate

    Returns:
        Single prompt asking for all thoughts at once
    """
    return f"""User query: "{query}"

Generate {count} diverse initial approaches to answer this query.

For each approach, you should:
1. Think about what information or actions are needed
2. Use available tools to gather information or perform actions
3. Explain your reasoning

Available tools:
- search_kb: Search the knowledge base for relevant information
- fetch_url: Fetch content from a URL (requires a url parameter)
- read_file: Read a local file (requires a path parameter)
- python_repl: Execute Python code for analysis
- terminal: Execute shell commands

IMPORTANT: If you need to use tools, call them directly with the required arguments.
For example:
- To search the knowledge base: search_kb(query="quantum computing")
- To fetch a URL: fetch_url(url="https://example.com")
- To read a file: read_file(path="document.txt")

Provide your reasoning and use tools as needed."""


def _generate_combined_extension_prompt(query: str, parent_thoughts: List[Thought], count: int) -> str:
    """
    Generate a single combined prompt for extending existing thoughts.

    Args:
        query: User query
        parent_thoughts: Thoughts on current best path
        count: Number of thoughts to generate

    Returns:
        Single prompt asking for all thoughts at once
    """
    parent_context = "\n".join([
        f"{i+1}. {t.content}" for i, t in enumerate(parent_thoughts)
    ])

    return f"""User query: "{query}"

Previous reasoning steps (our current best path):
{parent_context}

Based on the reasoning path above, determine the next steps.

You should:
1. Use tools to gather more information if needed
2. Analyze previous results
3. Continue reasoning toward the answer

Available tools:
- search_kb: Search the knowledge base
- fetch_url: Fetch content from a URL (requires url parameter)
- read_file: Read a local file (requires path parameter)
- python_repl: Execute Python code
- terminal: Execute shell commands

IMPORTANT: If you need to use tools, call them directly with proper arguments.
For example:
- search_kb(query="specific topic")
- fetch_url(url="https://example.com")

Provide your next steps and use tools as appropriate."""


def _generate_diverse_root_prompts(query: str, count: int) -> List[str]:
    """
    Generate multiple prompts for root-level thought generation.

    Args:
        query: User query
        count: Number of prompts to generate

    Returns:
        List of diverse prompts
    """
    prompts = [
        f"""Given the user query: "{query}"

Generate 2-3 initial approaches that are **conservative and reliable**.
Focus on:
- Using well-established tools and methods
- Step-by-step, systematic approaches
- Proven strategies for this type of problem

Format as numbered list with Strategy, Tools, and Rationale for each.""",

        f"""Given the user query: "{query}"

Generate 2-3 initial approaches that are **creative and innovative**.
Focus on:
- Novel angles or perspectives
- Combining tools in unusual ways
- Thinking outside the box

Format as numbered list with Strategy, Tools, and Rationale for each.""",

        f"""Given the user query: "{query}"

Generate 1-2 initial approaches that are **balanced** (mix of conservative and creative).
Focus on:
- Practical solutions with some innovation
- Efficient use of available tools
- Best of both approaches

Format as numbered list with Strategy, Tools, and Rationale for each."""
    ]

    return prompts[:count]


def _generate_diverse_extension_prompts(
    query: str,
    parent_thoughts: List[Thought],
    count: int
) -> List[str]:
    """
    Generate multiple prompts for extending existing thoughts.

    Args:
        query: User query
        parent_thoughts: Thoughts on current best path
        count: Number of prompts to generate

    Returns:
        List of diverse prompts
    """
    parent_context = "\n".join([
        f"{i+1}. {t.content}" for i, t in enumerate(parent_thoughts)
    ])

    prompts = [
        f"""User query: "{query}"

Previous reasoning steps (our current path):
{parent_context}

Generate 2 next-step thoughts that **refine and improve** this path.
Consider:
- How can we make this approach more precise?
- What details or refinements are needed?
- How can we verify or validate our approach?

Format as numbered list.""",

        f"""User query: "{query}"

Previous reasoning steps (our current path):
{parent_context}

Generate 2 next-step thoughts that **explore alternatives** to this path.
Consider:
- What different approaches could we take?
- What tools or methods haven't we tried?
- How might a different strategy work better?

Format as numbered list.""",

        f"""User query: "{query}"

Previous reasoning steps (our current path):
{parent_context}

Generate 1-2 next-step thoughts that **synthesize** multiple approaches.
Consider:
- How can we combine different strategies?
- What hybrid approaches might work?
- How can we integrate multiple perspectives?

Format as numbered list."""
    ]

    return prompts[:count]


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
        return _generate_fallback_thoughts(content, depth, parent_id, 1)

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

    # NOTE: Don't create tool_calls with empty args anymore
    # Tool calls should only come from actual LLM tool_calls
    tool_calls = []

    return Thought(
        id=f"thought_{uuid.uuid4().hex[:8]}",
        parent_id=parent_id,
        content=content,
        tool_calls=tool_calls,
        status="pending"
    )


def _create_thoughts_from_tool_calls(
    tool_calls: List[dict],
    content: str,
    parent_id: str | None,
    depth: int
) -> List[Thought]:
    """
    Create thoughts from LLM-generated tool calls.

    Args:
        tool_calls: List of tool call dicts from LLM response
        content: LLM response content
        parent_id: Parent thought ID
        depth: Current depth

    Returns:
        List of Thought objects with proper tool_calls
    """
    thoughts = []

    # Create a thought for each tool call
    for tool_call in tool_calls:
        tool_name = tool_call.get('name', '')
        tool_args = tool_call.get('args', {})

        thought_content = f"Use {tool_name} to gather information"
        if content:
            thought_content += f": {content[:200]}"

        thoughts.append(Thought(
            id=f"thought_{uuid.uuid4().hex[:8]}",
            parent_id=parent_id,
            content=thought_content,
            tool_calls=[{"name": tool_name, "args": tool_args}],
            status="pending"
        ))

    # If no tool calls but has content, create a thought without tools
    if not thoughts and content:
        thoughts.append(Thought(
            id=f"thought_{uuid.uuid4().hex[:8]}",
            parent_id=parent_id,
            content=content,
            tool_calls=[],
            status="pending"
        ))

    return thoughts


def _deduplicate_thoughts(thoughts: List[Thought]) -> List[Thought]:
    """
    Remove duplicate thoughts based on content similarity.

    Args:
        thoughts: List of thoughts to deduplicate

    Returns:
        List of unique thoughts
    """
    unique_thoughts = []
    seen_contents = set()

    for thought in thoughts:
        # Simple deduplication based on content
        content_lower = thought.content.lower().strip()

        # Check for similar content
        is_duplicate = False
        for seen in seen_contents:
            if _content_similarity(content_lower, seen) > 0.8:
                is_duplicate = True
                break

        if not is_duplicate:
            unique_thoughts.append(thought)
            seen_contents.add(content_lower)

    return unique_thoughts


def _content_similarity(content1: str, content2: str) -> float:
    """
    Calculate similarity between two thought contents.

    Args:
        content1: First content
        content2: Second content

    Returns:
        Similarity score (0-1)
    """
    # Simple word-based similarity
    words1 = set(content1.split())
    words2 = set(content2.split())

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union) if union else 0.0


def _generate_fallback_thoughts(
    query: str, depth: int, parent_id: str | None = None, count: int = 3
) -> List[Thought]:
    """
    Generate fallback thoughts when parsing fails.

    NOTE: Fallback thoughts don't include tool calls - they just describe
    strategies. The LLM will need to generate actual tool calls.
    """
    fallback_strategies = [
        f"Analyze the query systematically: {query}",
        f"Break down into key components: {query}",
        f"Consider multiple perspectives: {query}",
        f"Research relevant information: {query}",
        f"Synthesize available knowledge: {query}"
    ]

    thoughts = []
    for i in range(min(count, len(fallback_strategies))):
        strategy = fallback_strategies[i]
        thoughts.append(Thought(
            id=f"thought_{uuid.uuid4().hex[:8]}",
            parent_id=parent_id,
            content=strategy,
            tool_calls=[],  # No tool calls - let LLM generate them
            status="pending"
        ))

    return thoughts
