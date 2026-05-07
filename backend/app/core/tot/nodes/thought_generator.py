"""
Enhanced Thought Generator Node

Generates diverse candidate thoughts with branching support.
Phase 3: Multi-beam generation + backtracking regeneration.
"""

import asyncio
import logging
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.core.tot.state import ToTState, Thought, get_thought_map
from app.core.tot.utils import content_similarity as _content_similarity, tool_calls_signature as _tool_calls_signature

logger = logging.getLogger(__name__)


def _build_history_summary(state: ToTState) -> str:
    """Build a compact conversation history summary from state['messages']."""
    chat_history = state.get("messages", [])
    if not chat_history:
        return ""
    lines = []
    for msg in chat_history:
        role = "用户" if msg.type == "human" else "助手"
        content = msg.content[:200] if msg.content else ""
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


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
    task_mode = state.get("task_mode", "standard")

    # ---- Research mode: increment round counter ----
    if task_mode == "research" and current_depth > 0:
        research_round = state.get("research_round", 0)
        state["research_round"] = research_round + 1
        logger.info(f"[Research] Round incremented to {state['research_round']}")

    # ---- Phase 3: 回溯重生成路由 ----
    needs_regeneration = state.get("needs_regeneration", [])
    if needs_regeneration:
        logger.info(f"[Generator] Regeneration requested for beams: {needs_regeneration}")
        return await _regenerate_for_beams(state, needs_regeneration)

    # ---- Research mode: use planner prompts ----
    if task_mode == "research":
        return await _generate_research_plans(state)

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
        _history_summary = _build_history_summary(state)

        system_prompt = compose_system_prompt(
            base_system_prompt=state.get("system_prompt", ""),
            node_role="generator",
            domain_profile=state.get("domain_profile"),
            variant=variant_index,
            tools=state.get("tools"),
            prompt_level="full",
            enrichment={"existing_branches_summary": existing_branches_summary, "chat_history": _history_summary} if (existing_branches_summary or _history_summary) else None,
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

    # Safety: if active_beams is empty, fall back to best_path
    if not active_beams:
        best_path = state.get("best_path", [])
        if best_path:
            active_beams = [best_path]
            state["active_beams"] = active_beams
            logger.warning("[Regenerate] active_beams was empty, fell back to best_path")
        else:
            logger.error("[Regenerate] No active_beams and no best_path, cannot regenerate")
            state["thoughts"] = []
            state["needs_regeneration"] = []
            return state

    for beam_idx in beam_indices:
        if beam_idx >= len(active_beams):
            logger.warning("[Regenerate] beam_idx=%d >= len(active_beams)=%d, skipping", beam_idx, len(active_beams))
            continue
        beam = active_beams[beam_idx]
        parent_id = beam[-1]
        logger.info("[Regenerate] beam_idx=%d, beam=%s, parent_id=%s", beam_idx, beam, parent_id)
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
        _history_summary = _build_history_summary(state)

        system_prompt = compose_system_prompt(
            base_system_prompt=state.get("system_prompt", ""),
            node_role="generator",
            domain_profile=state.get("domain_profile"),
            variant=variant_index,
            tools=state.get("tools"),
            prompt_level="full",
            enrichment={"existing_branches_summary": existing_branches_summary, "chat_history": _history_summary} if (existing_branches_summary or _history_summary) else None,
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

    # 补充不足的 thoughts（每个 beam 不足 branching_factor 个时补 fallback）
    parent_counts: Dict[str, int] = {}
    for t in all_new_thoughts:
        parent_counts[t.parent_id] = parent_counts.get(t.parent_id, 0) + 1

    for beam_idx in beam_indices:
        if beam_idx >= len(active_beams):
            continue
        beam = active_beams[beam_idx]
        parent_id = beam[-1]
        current_count = parent_counts.get(parent_id, 0)
        if current_count < branching_factor:
            fallback = _generate_fallback_thoughts(
                user_query, current_depth, parent_id,
                branching_factor - current_count
            )
            all_new_thoughts.extend(fallback)
            logger.info(
                f"[Regenerate-Beam{beam_idx}] Padded with {len(fallback)} fallback thoughts "
                f"({current_count} → {current_count + len(fallback)})"
            )

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
        _history_summary = _build_history_summary(state)

        system_prompt = compose_system_prompt(
            base_system_prompt=state.get("system_prompt", ""),
            node_role="generator",
            domain_profile=state.get("domain_profile"),
            variant=variant_index,
            tools=state.get("tools"),
            prompt_level="full",
            enrichment={"existing_branches_summary": existing_branches_summary, "chat_history": _history_summary} if (existing_branches_summary or _history_summary) else None,
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

    # Visual skill injection: upstream of SkillPolicy gate.
    # Generator injects read_file(SKILL.md) → executor-side SkillPolicy gate → compile & execute
    _inject_visual_skill_if_needed(unique_thoughts, user_query)

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


# ---------------------------------------------------------------------------
# Research mode: planner-based generation
# ---------------------------------------------------------------------------

async def _generate_research_plans(state: ToTState) -> ToTState:
    """Research mode: generate candidate research plans using planner prompts.

    Uses get_first_round_planner_prompt() for round 0 (no prior evidence)
    and get_planner_prompt() for subsequent rounds (with evidence feedback).
    """
    llm = state["llm"]
    user_query = state["user_query"]
    current_depth = state["current_depth"]
    branching_factor = state.get("branching_factor", 3)
    research_round = state.get("research_round", 0)

    from app.core.tot.research.prompts import (
        get_first_round_planner_prompt,
        get_planner_prompt,
        parse_json_output,
    )
    from app.core.tot.research.evidence_utils import format_evidence_for_prompt

    # Build user prompt based on round
    if research_round == 0:
        prompt = get_first_round_planner_prompt(user_query)
        logger.info(f"[Research-Planner] First round (depth={current_depth})")
    else:
        evidence_summary = format_evidence_for_prompt(state.get("evidence_store", []))
        coverage_map_raw = state.get("coverage_map")
        coverage_map = json.dumps(coverage_map_raw, ensure_ascii=False) if coverage_map_raw else "{}"
        contradictions_raw = state.get("contradictions")
        contradictions = json.dumps(contradictions_raw, ensure_ascii=False) if contradictions_raw else "[]"
        max_depth = state.get("max_depth", 5)
        remaining_rounds = str(max(0, max_depth - research_round))

        prompt = get_planner_prompt(
            user_query=user_query,
            evidence_summary=evidence_summary,
            coverage_map=coverage_map,
            contradictions=contradictions,
            remaining_rounds=remaining_rounds,
        )
        logger.info(
            f"[Research-Planner] Round {research_round} "
            f"(evidence={len(state.get('evidence_store', []))}, "
            f"remaining={remaining_rounds})"
        )

    from app.core.tot.prompt_composer import compose_system_prompt
    system_prompt = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="generator",
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="full",
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt),
    ]

    gen_start = time.time()
    all_new_thoughts = []
    elapsed = 0.0

    try:
        response = await llm.ainvoke(messages)
        elapsed = time.time() - gen_start
        content = response.content or ""

        logger.info(f"[Research-Planner] Response received ({len(content)} chars, {elapsed:.1f}s)")

        parsed = parse_json_output(content)
        plans = []
        if "_array" in parsed:
            plans = parsed["_array"]
        elif parsed:
            plans = [parsed]

        _parent_id = state["best_path"][-1] if state.get("best_path") else None
        all_new_thoughts = _convert_plans_to_thoughts(plans, _parent_id, current_depth, branching_factor)

        if not all_new_thoughts:
            logger.warning("[Research-Planner] No plans parsed, using fallback")
            all_new_thoughts = _generate_fallback_thoughts(
                user_query, current_depth,
                state["best_path"][-1] if state.get("best_path") else None,
                branching_factor,
            )

    except Exception as e:
        elapsed = time.time() - gen_start
        logger.error(f"[Research-Planner] Error: {e}")
        all_new_thoughts = _generate_fallback_thoughts(
            user_query, current_depth,
            state["best_path"][-1] if state.get("best_path") else None,
            branching_factor,
        )

    unique_thoughts = _deduplicate_thoughts(all_new_thoughts)

    logger.info(
        f"[Research-Planner] Generated {len(unique_thoughts)} plan-thoughts "
        f"at depth {current_depth}, round {research_round}"
    )

    state["reasoning_trace"].append({
        "type": "thoughts_generated",
        "depth": current_depth,
        "count": len(unique_thoughts),
        "thoughts": [t.model_dump() for t in unique_thoughts],
        "research_round": research_round,
        "plan_mode": True,
    })

    if "tot_logger" in state:
        state["tot_logger"].log_generation(
            depth=current_depth,
            count=len(unique_thoughts),
            variant=f"research_planner_r{research_round}",
            prompt_length=0,
            duration=elapsed,
            token_usage=None,
        )

    state["thoughts"] = unique_thoughts
    return state


def _convert_plans_to_thoughts(
    plans: list, parent_id: str | None, depth: int, max_count: int
) -> list:
    """Convert parsed research plans to Thought objects with tool_calls.

    Each plan's queries are mapped to search_kb tool calls.
    """
    thoughts = []

    for plan in plans[:max_count]:
        plan_id = plan.get("plan_id", f"P{len(thoughts) + 1}")
        goal = plan.get("goal", "")
        gap = plan.get("missing_gap", "")
        queries = plan.get("queries", [])

        content_parts = [f"[{plan_id}] {goal}"]
        if gap:
            content_parts.append(f"Gap: {gap}")
        content = " | ".join(content_parts)

        tool_calls = []
        for query in queries[:3]:
            if isinstance(query, str) and query.strip():
                tool_calls.append({
                    "name": "search_kb",
                    "args": {"query": query.strip(), "top_k": 5},
                })

        thoughts.append(Thought(
            id=f"thought_{uuid.uuid4().hex[:8]}",
            parent_id=parent_id,
            content=content,
            tool_calls=tool_calls,
            status="pending",
        ))

    return thoughts


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


def _get_skill_hints_for_prompt() -> str:
    """动态生成包含 skills 的工具列表，用于 user prompt。

    Returns:
        格式化的工具 + skill 提示文本。
    """
    try:
        from app.core.tot.skill_orchestrator import build_skill_hints
        return build_skill_hints()
    except Exception:
        # 回退到基础工具列表
        return """Available tools:
- search_kb: Search the knowledge base
- fetch_url: Fetch content from a URL
- read_file: Read a local file
- python_repl: Execute Python code
- terminal: Execute shell commands"""


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

    # 动态生成包含 skills 的工具列表
    skill_hints = _get_skill_hints_for_prompt()

    return f"""User query: "{query}"

{tool_requirement}
CRITICAL INSTRUCTION: You MUST generate exactly {count} SEPARATE tool calls, one for each approach.

{requirements_text}

{skill_hints}

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

    # 动态生成包含 skills 的工具列表
    skill_hints = _get_skill_hints_for_prompt()

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

{skill_hints}

IMPORTANT: If you need to use tools, call them directly with proper arguments.
For example:
- search_kb(query="specific topic")
- fetch_url(url="https://example.com")
- read_file(path="data/skills/arxiv-search/SKILL.md")  # 触发 skill 自动执行

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


def _inject_visual_skill_if_needed(thoughts: List[Thought], user_query: str) -> None:
    """Inject read_file(SKILL.md) tool calls for visual skills when the query suggests them.

    This is upstream of SkillPolicy gate in the executor:
    generator injects read_file(SKILL.md) → executor-side SkillPolicy gate → compile & execute.

    Without this injection, SkillPolicy never triggers because the LLM may not generate
    a read_file(SKILL.md) tool call on its own for visual tasks.
    """
    visual_keywords = [
        "画", "图表", "柱状图", "折线图", "饼图", "散点图", "plot", "chart",
        "graph", "draw", "diagram", "可视化", "visualization", "geometry",
        "几何", "svg", "几何图形",
    ]
    query_lower = user_query.lower()
    needs_visual = any(kw in query_lower for kw in visual_keywords)
    if not needs_visual:
        return

    # Try to discover visual skills dynamically
    visual_skill_names: List[str] = []
    try:
        from app.skills.loader import SkillLoader
        available = SkillLoader().list_available_skills()
        for skill_name, skill_info in available.items():
            tags = skill_info.get("tags", []) if isinstance(skill_info, dict) else []
            name_lower = skill_name.lower()
            if any(t in name_lower for t in ("plotter", "chart", "diagram", "geometry", "draw", "visual")):
                visual_skill_names.append(skill_name)
    except Exception:
        # Fallback to known visual skills
        visual_skill_names = ["chart-plotter", "diagram-plotter", "geometry-plotter"]

    if not visual_skill_names:
        return

    # Pick the most relevant visual skill based on query
    skill_name = visual_skill_names[0]
    for candidate in visual_skill_names:
        if "chart" in user_query.lower() or "柱状" in user_query or "折线" in user_query:
            if "chart" in candidate:
                skill_name = candidate
                break
        elif "diagram" in user_query.lower() or "图示" in user_query or "流程图" in user_query:
            if "diagram" in candidate:
                skill_name = candidate
                break
        elif "geometry" in user_query.lower() or "几何" in user_query:
            if "geometry" in candidate:
                skill_name = candidate
                break

    # Check if any thought already has a read_file for this skill
    already_injected = any(
        any(
            tc.get("name") == "read_file" and skill_name in tc.get("args", {}).get("path", "")
            for tc in (t.tool_calls or [])
        )
        for t in thoughts
    )
    if already_injected:
        return

    # Inject a read_file(SKILL.md) tool call into the first thought without tools
    for thought in thoughts:
        if not thought.tool_calls:
            thought.tool_calls = [{
                "name": "read_file",
                "args": {"path": f"data/skills/{skill_name}/SKILL.md"},
            }]
            thought.content = f"[Auto-injected] Load visual skill '{skill_name}' for: {user_query[:100]}"
            logger.info(
                "[Generator] Injected read_file(SKILL.md) for visual skill '%s' into thought %s",
                skill_name, thought.id,
            )
            return

    # All thoughts have tools — add a new thought
    new_thought = Thought(
        id=f"thought_{uuid.uuid4().hex[:8]}",
        parent_id=thoughts[0].parent_id if thoughts else None,
        content=f"[Auto-injected] Load visual skill '{skill_name}' for: {user_query[:100]}",
        tool_calls=[{"name": "read_file", "args": {"path": f"data/skills/{skill_name}/SKILL.md"}}],
        status="pending",
    )
    thoughts.append(new_thought)
    logger.info(
        "[Generator] Added new thought with read_file(SKILL.md) for visual skill '%s'",
        skill_name,
    )


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