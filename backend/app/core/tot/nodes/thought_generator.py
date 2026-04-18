"""
Enhanced Thought Generator Node

Generates diverse candidate thoughts with branching support.
Phase 3: Multi-beam generation + backtracking regeneration.
"""

import asyncio
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.core.tot.state import ToTState, Thought, get_thought_map
from app.core.tot.utils import content_similarity as _content_similarity, tool_calls_signature as _tool_calls_signature

logger = logging.getLogger(__name__)


async def thought_generator_node(state: ToTState) -> ToTState:
    """
    Generate multiple diverse candidate thoughts using LLM.

    Phase 3 增强:
    - beam_width 在 state 中时使用多束生成（depth > 0 为每个活跃束生成 k 个子节点）
    - 支持 needs_regeneration 回溯重生成（用不同策略 + 反思 prompt）
    - 当 beam_width 未设置时退化为原有单束生成（向后兼容）

    Args:
        state: Current ToT state

    Returns:
        Updated state with new thoughts added
    """
    current_depth = state["current_depth"]
    user_query = state["user_query"]
    branching_factor = state.get("branching_factor", 3)
    beam_width = state.get("beam_width")

    # ---- Phase 3: 回溯重生成路由 ----
    needs_regeneration = state.get("needs_regeneration", [])
    if needs_regeneration:
        logger.info(f"[Generator] Regeneration requested for beams: {needs_regeneration}")
        return await _regenerate_for_beams(state, needs_regeneration)

    # ---- Phase 3: 多束生成路由 ----
    active_beams = state.get("active_beams", [])
    if beam_width and current_depth > 0 and active_beams:
        logger.info(
            f"[Generator] Multi-beam mode: {len(active_beams)} beams, "
            f"generating {branching_factor} children each at depth {current_depth}"
        )
        return await _generate_multi_beam_extensions(state)

    # ---- 原有单束生成逻辑（向后兼容 + depth 0） ----
    return await _generate_single_beam(state)


# ---------------------------------------------------------------------------
# Phase 3: 多束扩展生成
# ---------------------------------------------------------------------------

async def _generate_multi_beam_extensions(state: ToTState) -> ToTState:
    """为所有活跃束的尖端生成 k 个子节点。

    每个 beam 独立调用 LLM（可并行），使用不同的 variant。
    """
    llm_with_tools = state.get("llm_with_tools", state["llm"])
    current_depth = state["current_depth"]
    user_query = state["user_query"]
    branching_factor = state.get("branching_factor", 3)
    active_beams = state.get("active_beams", [])

    all_new_thoughts = []
    gen_start = time.time()
    thought_map = get_thought_map(state["thoughts"])

    async def _generate_for_beam(beam_idx: int, beam: List[str]) -> List[Thought]:
        """为单个 beam 生成子节点。"""
        parent_id = beam[-1]
        parent_thoughts = [thought_map[tid] for tid in beam if tid in thought_map]

        # 每个 beam 使用不同 variant
        variant_index = (current_depth + beam_idx) % 3

        from app.core.tot.prompt_composer import compose_system_prompt
        existing_branches_summary = _collect_existing_branches_summary(state)

        system_prompt = compose_system_prompt(
            base_system_prompt=state.get("system_prompt", ""),
            node_role="generator",
            domain_profile=state.get("domain_profile"),
            variant=variant_index,
            tools=state.get("tools"),
            prompt_level="full",
            enrichment={"existing_branches_summary": existing_branches_summary} if existing_branches_summary else None,
        )

        prompt = _generate_combined_extension_prompt(
            user_query, parent_thoughts, branching_factor,
            existing_branches_summary=existing_branches_summary,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ]

        logger.info(f"[Generator-Beam{beam_idx}] Generating {branching_factor} children for beam tip {parent_id}")

        try:
            response = await llm_with_tools.ainvoke(messages)

            new_thoughts = _parse_or_create_thoughts(
                response, parent_id=parent_id, depth=current_depth
            )

            logger.info(f"[Generator-Beam{beam_idx}] Generated {len(new_thoughts)} thoughts")
            return new_thoughts

        except Exception as e:
            logger.error(f"[Generator-Beam{beam_idx}] Error: {e}")
            return _generate_fallback_thoughts(
                user_query, current_depth, parent_id, branching_factor
            )

    # 并行为所有 beam 生成子节点
    tasks = [
        _generate_for_beam(beam_idx, beam)
        for beam_idx, beam in enumerate(active_beams)
    ]
    results = await asyncio.gather(*tasks)

    for beam_thoughts in results:
        all_new_thoughts.extend(beam_thoughts)

    elapsed = time.time() - gen_start

    # 补充不足的 thoughts（每个 beam 不足 branching_factor 个时补 fallback）
    # 按 parent_id 分组统计
    parent_counts: Dict[str, int] = {}
    for t in all_new_thoughts:
        parent_counts[t.parent_id] = parent_counts.get(t.parent_id, 0) + 1

    for beam in active_beams:
        parent_id = beam[-1]
        current_count = parent_counts.get(parent_id, 0)
        if current_count < branching_factor:
            fallback = _generate_fallback_thoughts(
                user_query, current_depth, parent_id,
                branching_factor - current_count
            )
            all_new_thoughts.extend(fallback)

    # 去重
    unique_thoughts = _deduplicate_thoughts(all_new_thoughts)

    logger.info(
        f"[Generator] Multi-beam total: {len(unique_thoughts)} thoughts for "
        f"{len(active_beams)} beams at depth {current_depth} ({elapsed:.1f}s)"
    )

    # tot_logger
    if "tot_logger" in state:
        state["tot_logger"].log_generation(
            depth=current_depth,
            count=len(unique_thoughts),
            variant=f"multi_beam_{len(active_beams)}",
            prompt_length=0,  # 多次调用，不单独记录
            duration=elapsed,
            token_usage=None,
        )

    # Add to reasoning trace
    state["reasoning_trace"].append({
        "type": "thoughts_generated",
        "depth": current_depth,
        "count": len(unique_thoughts),
        "thoughts": [t.model_dump() for t in unique_thoughts],
        "beam_mode": True,
        "beam_count": len(active_beams),
    })

    # 不在这里 extend thoughts，由 add_thoughts reducer 合并新增部分
    # 原来 state["thoughts"].extend(unique_thoughts) + return state
    # 导致 reducer left+right 时翻倍（left 已含新 thoughts，right 也含）
    state["thoughts"] = unique_thoughts  # 只返回新增部分，reducer 会 left + right
    return state


# ---------------------------------------------------------------------------
# Phase 3: 回溯重生成
# ---------------------------------------------------------------------------

async def _regenerate_for_beams(state: ToTState, beam_indices: List[int]) -> ToTState:
    """为回溯 beam 重新生成分支。使用不同策略 + 反思上下文。"""
    llm_with_tools = state.get("llm_with_tools", state["llm"])
    active_beams = state.get("active_beams", [])
    current_depth = state["current_depth"]
    user_query = state["user_query"]
    branching_factor = state.get("branching_factor", 3)

    all_new_thoughts = []
    thought_map = get_thought_map(state["thoughts"])

    for beam_idx in beam_indices:
        if beam_idx >= len(active_beams):
            continue
        beam = active_beams[beam_idx]
        parent_id = beam[-1]

        # 收集旧分支摘要（已被标记为 pruned）
        old_children = [
            t for t in state["thoughts"]
            if t.parent_id == parent_id and t.status == "pruned"
        ]
        old_summaries = [
            f"  - {t.content[:60]}... (score={t.evaluation_score:.1f})"
            for t in old_children
        ]
        failure_context = "\n".join(old_summaries)

        # 使用不同的 variant（强制换策略）
        variant_index = (current_depth + beam_idx + 1) % 3

        from app.core.tot.prompt_composer import compose_system_prompt
        existing_branches_summary = _collect_existing_branches_summary(state)

        system_prompt = compose_system_prompt(
            base_system_prompt=state.get("system_prompt", ""),
            node_role="generator",
            domain_profile=state.get("domain_profile"),
            variant=variant_index,
            tools=state.get("tools"),
            prompt_level="full",
            enrichment={"existing_branches_summary": existing_branches_summary} if existing_branches_summary else None,
        )

        parent_thoughts = [thought_map[tid] for tid in beam if tid in thought_map]

        prompt = _generate_combined_extension_prompt(
            user_query, parent_thoughts, branching_factor,
            existing_branches_summary=existing_branches_summary,
        )

        # 追加反思重生成上下文
        if failure_context:
            prompt += f"""

=== 反思重生成 ===
Previous attempts from this node ALL scored below threshold:
{failure_context}

These approaches failed. You MUST generate COMPLETELY DIFFERENT strategies.
Avoid the tools and reasoning angles used above.
Think from a fundamentally different perspective."""

        try:
            response = await llm_with_tools.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt)
            ])

            new_thoughts = _parse_or_create_thoughts(
                response, parent_id=parent_id, depth=current_depth
            )

            all_new_thoughts.extend(new_thoughts)
            logger.info(f"[Regenerate-Beam{beam_idx}] Generated {len(new_thoughts)} new thoughts")

        except Exception as e:
            logger.error(f"[Regenerate-Beam{beam_idx}] Error: {e}")
            all_new_thoughts.extend(
                _generate_fallback_thoughts(user_query, current_depth, parent_id, branching_factor)
            )

    # 清除回溯标记（防止无限循环）
    state["needs_regeneration"] = []

    # 去重
    unique_thoughts = _deduplicate_thoughts(all_new_thoughts)

    logger.info(
        f"[Regenerate] Total {len(unique_thoughts)} new thoughts for {len(beam_indices)} beams"
    )

    state["reasoning_trace"].append({
        "type": "thoughts_regenerated",
        "depth": current_depth,
        "beam_indices": beam_indices,
        "count": len(unique_thoughts),
        "thoughts": [t.model_dump() for t in unique_thoughts],
    })

    # 只返回新增部分，由 add_thoughts reducer 合并
    state["thoughts"] = unique_thoughts
    return state


# ---------------------------------------------------------------------------
# 原有单束生成逻辑（向后兼容 + depth 0）
# ---------------------------------------------------------------------------

async def _generate_single_beam(state: ToTState) -> ToTState:
    """
    Generate multiple diverse candidate thoughts using LLM (original single-beam logic).

    当 beam_width 未设置，或 depth == 0 时使用此路径。
    """
    llm_with_tools = state.get("llm_with_tools", state["llm"])
    current_depth = state["current_depth"]
    user_query = state["user_query"]
    branching_factor = state.get("branching_factor", 3)

    logger.info(f"Generating {branching_factor} thoughts at depth {current_depth} (single-beam mode)")

    # Build generation prompt based on depth
    domain_profile = state.get("domain_profile")
    if current_depth == 0:
        prompt = _generate_combined_root_prompt(user_query, branching_factor, domain_profile)
    else:
        thought_map = get_thought_map(state["thoughts"])
        best_path = state.get("best_path", [])
        parent_thoughts = [thought_map[tid] for tid in best_path if tid in thought_map]
        prompt = _generate_combined_extension_prompt(user_query, parent_thoughts, branching_factor)

    all_new_thoughts = []

    try:
        from app.core.tot.prompt_composer import compose_system_prompt

        # Phase 0: variant 参数修复
        if current_depth == 0:
            variant_index = 0
        else:
            variant_index = (current_depth + hash(state.get("best_path", [""])[-1])) % 3

        existing_branches_summary = _collect_existing_branches_summary(state)

        system_prompt = compose_system_prompt(
            base_system_prompt=state.get("system_prompt", ""),
            node_role="generator",
            domain_profile=state.get("domain_profile"),
            variant=variant_index,
            tools=state.get("tools"),
            prompt_level="full",
            enrichment={"existing_branches_summary": existing_branches_summary} if existing_branches_summary else None,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ]

        logger.info(f"[TOT_GENERATOR] Sending prompt to LLM with tools")
        logger.info(f"[TOT_GENERATOR] System prompt length: {len(system_prompt)}")
        logger.info(f"[TOT_GENERATOR] User prompt: {prompt[:200]}...")

        start_time = time.time()
        response = await llm_with_tools.ainvoke(messages)
        elapsed = time.time() - start_time

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
        _parent_id = state["best_path"][-1] if state["best_path"] else None
        all_new_thoughts = _parse_or_create_thoughts(
            response, parent_id=_parent_id, depth=current_depth
        )
        if not all_new_thoughts:
            logger.warning(f"[TOT_GENERATOR] No thoughts parsed from response!")
        else:
            logger.info(f"[TOT_GENERATOR] Parsed {len(all_new_thoughts)} thoughts")

        logger.info(f"Generated {len(all_new_thoughts)} thoughts from single prompt")

        if "tot_logger" in state:
            state["tot_logger"].log_generation(
                depth=current_depth,
                count=len(all_new_thoughts),
                variant="combined",
                prompt_length=len(system_prompt) + len(prompt),
                duration=elapsed,
                token_usage=response.usage_metadata if hasattr(response, 'usage_metadata') else None,
            )

    except Exception as e:
        logger.error(f"Error generating thoughts: {e}")
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

    # BUG FIX (Fix 8): visual skill injection
    if current_depth == 0:
        _inject_visual_skill_if_needed(user_query, unique_thoughts)

    logger.info(f"Total unique thoughts generated at depth {current_depth}: {len(unique_thoughts)}")

    # Add to reasoning trace for streaming
    state["reasoning_trace"].append({
        "type": "thoughts_generated",
        "depth": current_depth,
        "count": len(unique_thoughts),
        "thoughts": [t.model_dump() for t in unique_thoughts]
    })

    # 只返回新增部分，由 add_thoughts reducer 合并
    state["thoughts"] = unique_thoughts

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
- terminal: Execute shell commands (requires "command" parameter)"""

    # BUG FIX: 注入 skill 提示，让 LLM 知道可以调用 skill 生图等
    # 原代码没有 skill 提示，导致 LLM 直接用 python_repl 生成代码而不是调用 skill
    try:
        from app.core.tot.skill_orchestrator import build_skill_hints
        skill_hints = build_skill_hints()
        base_prompt += "\n" + skill_hints + "\n"
    except Exception:
        pass  # skill 加载失败时仍使用基础提示

    base_prompt += """

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


def _generate_combined_root_prompt(query: str, count: int, domain_profile: dict | None = None) -> str:
    """
    Generate a single combined prompt for root-level thoughts.

    Args:
        query: User query
        count: Number of thoughts to generate
        domain_profile: Optional domain profile for required_tools enforcement

    Returns:
        Single prompt asking for all thoughts at once
    """
    # Fix 7: 根据 domain_profile.required_tools 动态注入工具调用要求
    required_tools = (domain_profile or {}).get("required_tools", [])
    if required_tools:
        tool_requirement = (
            f"\nIMPORTANT: This domain REQUIRES tool calls. "
            f"You MUST call at least one of: {', '.join(required_tools)}\n"
        )
    else:
        tool_requirement = ""

    # Phase 0: 为每个分支指定不同的框架+角色组合（三重分化）
    from app.core.tot.prompt_composer import _REASONING_FRAMEWORKS, _EXPERT_ROLES
    branch_requirements = []
    for i in range(count):
        framework = _REASONING_FRAMEWORKS[i % len(_REASONING_FRAMEWORKS)]
        role = _EXPERT_ROLES[(i + 1) % len(_EXPERT_ROLES)]
        branch_requirements.append(
            f"Approach {i+1}: 框架='{framework}' 角色='{role}'"
        )

    requirements_text = "\n".join(branch_requirements)

    return f"""User query: "{query}"

{tool_requirement}
CRITICAL INSTRUCTION: You MUST generate exactly {count} SEPARATE tool calls, one for each approach.

{requirements_text}

Available tools:
- search_kb: Search the knowledge base for relevant information
  Example: search_kb(query="quantum computing", top_k=5)

- fetch_url: Fetch content from a URL
  Example: fetch_url(url="https://arxiv.org/search/?query=AI")

- read_file: Read a local file
  Example: read_file(path="document.txt")

- python_repl: Execute Python code for analysis
  Example: python_repl(code="print('analysis')")

- terminal: Execute shell commands
  Example: terminal(command="ls -la")

YOUR TASK - Generate {count} different tool calls for this query:

Each approach should use a DIFFERENT tool or different parameters to ensure diversity.

IMPORTANT:
- DO NOT just describe what you would do - ACTUALLY CALL THE TOOLS
- Each tool call must be complete with all required arguments
- Make sure each approach is meaningfully different from the others"""


def _generate_combined_extension_prompt(
    query: str, parent_thoughts: List[Thought], count: int,
    existing_branches_summary: str = "",
) -> str:
    """
    Generate a single combined prompt for extending existing thoughts.

    Args:
        query: User query
        parent_thoughts: Thoughts on current best path
        count: Number of thoughts to generate
        existing_branches_summary: 已有分支摘要（反对机制）

    Returns:
        Single prompt asking for all thoughts at once
    """
    parent_context = "\n".join([
        f"{i+1}. {t.content}" for i, t in enumerate(parent_thoughts)
    ])

    # Phase 0: 为每个分支指定不同的框架+角色组合
    from app.core.tot.prompt_composer import _REASONING_FRAMEWORKS, _EXPERT_ROLES
    branch_requirements = []
    for i in range(count):
        framework = _REASONING_FRAMEWORKS[i % len(_REASONING_FRAMEWORKS)]
        role = _EXPERT_ROLES[(i + 1) % len(_EXPERT_ROLES)]
        branch_requirements.append(
            f"Approach {i+1}: 框架='{framework}' 角色='{role}'"
        )
    requirements_text = "\n".join(branch_requirements)

    # Phase 0: 反对机制提示
    opposition_hint = ""
    if existing_branches_summary:
        opposition_hint = f"""
=== 已有分支摘要（你 MUST NOT 重复这些思路）===
{existing_branches_summary}
新分支必须与已有思路显著不同。"""

    return f"""User query: "{query}"

Previous reasoning steps (our current best path):
{parent_context}
{opposition_hint}

Based on the reasoning path above, determine the next steps.

{requirements_text}

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


def _parse_or_create_thoughts(
    response,           # AIMessage
    parent_id: str | None,
    depth: int,
) -> List[Thought]:
    """统一解析 LLM 响应为 Thought 对象。

    有 tool_calls → 调用 _create_thoughts_from_tool_calls
    无 tool_calls → 调用 _parse_thoughts（纯文本解析）
    """
    content = response.content or ""
    tool_calls = getattr(response, "tool_calls", None) or []

    if tool_calls:
        return _create_thoughts_from_tool_calls(tool_calls, content, parent_id, depth)
    else:
        return _parse_thoughts(content, parent_id, depth)


# def _tool_calls_signature(tool_calls: Optional[List[Dict[str, Any]]]) -> tuple:
#     """Build a hashable signature from tool_calls for dedup comparison.
#     [已迁移到 app.core.tot.utils.tool_calls_signature]
#     """
#     if not tool_calls:
#         return ()
#     parts = []
#     for tc in sorted(tool_calls, key=lambda x: x.get("name", "")):
#         name = tc.get("name", "")
#         args = tc.get("args", {})
#         path_val = args.get("path", "")
#         query_val = args.get("query", "")
#         parts.append((name, path_val, query_val))
#     return tuple(parts)


def _deduplicate_thoughts(thoughts: List[Thought]) -> List[Thought]:
    """
    Remove duplicate thoughts based on content similarity.

    Thoughts with different tool_calls signatures are never considered duplicates,
    even if their text content is similar.

    Args:
        thoughts: List of thoughts to deduplicate

    Returns:
        List of unique thoughts
    """
    unique_thoughts: List[Thought] = []
    seen: List[tuple] = []  # list of (content, tc_signature)

    for thought in thoughts:
        content_lower = thought.content.lower().strip()
        tc_sig = _tool_calls_signature(thought.tool_calls)

        is_duplicate = False
        for seen_content, seen_tc_sig in seen:
            # 不同工具调用 → 不算重复
            if tc_sig != seen_tc_sig:
                continue
            # 相同工具调用 → 检查内容相似度
            if _content_similarity(content_lower, seen_content) > 0.8:
                is_duplicate = True
                break

        if not is_duplicate:
            unique_thoughts.append(thought)
            seen.append((content_lower, tc_sig))

    return unique_thoughts


# def _content_similarity(content1: str, content2: str) -> float:
#     """Calculate similarity between two thought contents.
#     [已迁移到 app.core.tot.utils.content_similarity]
#     """
#     words1 = set(content1.split())
#     words2 = set(content2.split())
#     if not words1 or not words2:
#         return 0.0
#     intersection = words1.intersection(words2)
#     union = words1.union(words2)
#     return len(intersection) / len(union) if union else 0.0


def _generate_fallback_thoughts(
    query: str, depth: int, parent_id: str | None = None, count: int = 3
) -> List[Thought]:
    """
    Generate fallback thoughts when parsing fails.

    Each fallback thought includes a tool call to ensure research mode
    actually uses tools for information gathering.
    """
    # Define fallback strategies with their corresponding tools
    fallback_strategies = [
        {
            "content": f"Analyze the query systematically: {query}",
            "tool": "search_kb",
            "args": {"query": query, "top_k": 5}
        },
        {
            "content": f"Break down into key components: {query}",
            "tool": "search_kb",
            "args": {"query": query[:100] if len(query) > 100 else query, "top_k": 3}
        },
        {
            "content": f"Consider multiple perspectives: {query}",
            "tool": "fetch_url",
            "args": {"url": f"https://arxiv.org/search/?query={query[:50]}&searchtype=all"}
        },
        {
            "content": f"Research relevant information: {query}",
            "tool": "search_kb",
            "args": {"query": f"{query} research latest", "top_k": 10}
        },
        {
            "content": f"Synthesize available knowledge: {query}",
            "tool": "search_kb",
            "args": {"query": query, "top_k": 7}
        }
    ]

    thoughts = []
    for i in range(min(count, len(fallback_strategies))):
        strategy_config = fallback_strategies[i]
        thoughts.append(Thought(
            id=f"thought_{uuid.uuid4().hex[:8]}",
            parent_id=parent_id,
            content=strategy_config["content"],
            tool_calls=[{
                "name": strategy_config["tool"],
                "args": strategy_config["args"]
            }],
            status="pending"
        ))

    return thoughts


def _inject_visual_skill_if_needed(user_query: str, thoughts: list) -> None:
    """Fix 8: 如果查询涉及图示/画图但所有 thought 都没有 read_file skill tool_call，
    强制注入一个调用 chart-plotter 或 geometry-plotter skill 的 thought。

    直接修改 thoughts 列表（in-place）。
    """
    # 检测关键词
    visual_keywords = ["图示", "示意图", "画", "图", "图表", "绘制", "绘图",
                       "diagram", "chart", "plot", "graph", "illustration", "visual"]
    query_lower = user_query.lower()
    needs_visual = any(kw in query_lower for kw in visual_keywords)
    if not needs_visual:
        return

    # 检查是否已有 read_file 调用 SKILL.md 的 thought
    has_skill_call = False
    for t in thoughts:
        if t.tool_calls:
            for tc in t.tool_calls:
                if tc.get("name") == "read_file":
                    path = tc.get("args", {}).get("path", "")
                    if "skill" in path.lower():
                        has_skill_call = True
                        break
        if has_skill_call:
            break

    if has_skill_call:
        return  # 已有 skill 调用，无需注入

    # 决定用哪个 skill
    geometry_keywords = ["几何", "定理", "证明", "勾股", "geometry", "theorem", "proof", "triangle"]
    if any(kw in query_lower for kw in geometry_keywords):
        skill_path = "data/skills/geometry-plotter/SKILL.md"
        skill_desc = "Generate geometric diagram"
    else:
        skill_path = "data/skills/chart-plotter/SKILL.md"
        skill_desc = "Generate chart/plot"

    logger.info(f"[Fix 8] Injecting visual skill thought: {skill_path}")
    thoughts.append(Thought(
        id=f"thought_{uuid.uuid4().hex[:8]}",
        parent_id=None,
        content=f"Use skill to generate visual: {skill_desc}",
        tool_calls=[{
            "name": "read_file",
            "args": {"path": skill_path}
        }],
        status="pending"
    ))


def _collect_existing_branches_summary(state: ToTState) -> str:
    """收集 state 中已评估 thoughts 的摘要，用于反对机制（Phase 0）。"""
    current_depth = state.get("current_depth", 0)
    if current_depth == 0:
        return ""  # root 层无需反对机制

    evaluated_thoughts = [t for t in state["thoughts"] if t.status in ("evaluated", "done")]
    summaries = []
    for t in evaluated_thoughts[-6:]:  # 最多取最近 6 个
        summary = t.content[:80] + "..." if len(t.content) > 80 else t.content
        summaries.append(f"- [{t.id}] {summary}")
    return "\n".join(summaries)