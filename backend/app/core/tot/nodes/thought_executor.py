"""
Thought Executor Node

Executes tool calls for selected thoughts.
Phase 4: Beam-aware execution — all active beams, sequential tool plan,
         dead-end pruning, image deferral.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List

from langchain_core.tools import BaseTool

from app.core.tot.state import ToTState, Thought, get_thought_map

# Skill orchestrator integration (optional — graceful fallback)
try:
    from app.core.tot.skill_orchestrator import is_skill_file, extract_skill_name, execute_skill_from_skillmd, _register_embedded_images
    _SKILL_ORCHESTRATOR_AVAILABLE = True
except ImportError:
    _SKILL_ORCHESTRATOR_AVAILABLE = False

# SkillPolicy gate (optional — graceful fallback)
try:
    from app.core.tot.nodes.skill_policy import check_skill_policy_gate
    _SKILL_POLICY_AVAILABLE = True
except ImportError:
    _SKILL_POLICY_AVAILABLE = False

# Image embedding for tool output (graceful fallback)
try:
    from app.core.streaming.image_embedder import embed_output_images_v2
except ImportError:
    def embed_output_images_v2(x: str, max_age_seconds: int = 60) -> tuple[str, list[dict]]: return x, []

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 4: 依赖型工具集 — 前序失败时跳过
# ---------------------------------------------------------------------------

_DEPENDENT_TOOLS = {
    "python_repl",    # 依赖搜索/读取的结果来分析
    "write_file",     # 依赖前序产生的数据来写入
    "terminal",       # 可能依赖前序产生的数据
}


def _should_skip_due_to_prior_failure(tool_name: str, results_so_far: List[Dict]) -> bool:
    """判断当前步骤是否应因前序失败而跳过。"""
    if not results_so_far:
        return False
    has_failure = any(
        r.get("status") in ("error", "skipped")
        for r in results_so_far
    )
    if not has_failure:
        return False
    return tool_name in _DEPENDENT_TOOLS


# ---------------------------------------------------------------------------
# Phase 4: 死路剪枝 — 在 executor 内部执行完工具后调用
# ---------------------------------------------------------------------------

def _dead_end_prune_executed(thought: Thought) -> bool:
    """判断执行完工具后的 thought 是否为死路。"""
    # 检查 tool_results: 是否全部 error
    if thought.tool_results:
        all_failed = all(
            r.get("status") in ("error", "skipped") for r in thought.tool_results
        )
        if all_failed:
            return True
    # 检查局部循环: error_count >= 2 且无任何 artifact
    if thought.local_error_count >= 2 and not thought.artifacts:
        return True
    return False


# ---------------------------------------------------------------------------
# Phase 4: 主执行节点
# ---------------------------------------------------------------------------

async def thought_executor_node(state: ToTState) -> ToTState:
    """
    Execute tool calls for thoughts.

    Phase 4 增强:
    - beam_width 设置时执行所有活跃束上的 pending thoughts
    - 按 tool_calls 列表顺序依次执行（多步计划），带依赖跳过
    - 执行完后进行死路剪枝
    - beam 模式下延迟图片嵌入（仅提取路径，最终 synthesize 时嵌入）

    当 beam_width 未设置时，退化为原有 best_path 执行。
    """
    tools = state["tools"]
    all_thoughts = state["thoughts"]
    user_query = state.get("user_query", "")
    beam_width = state.get("beam_width")

    # ---- 收集待执行的 thoughts ----
    if beam_width:
        # Phase 4: 收集所有活跃束上的 pending thoughts
        active_beams = state.get("active_beams", [])
        all_beam_ids = set(tid for beam in active_beams for tid in beam)
        thought_map = get_thought_map(all_thoughts)
        pending_execution = [
            thought_map[tid] for tid in all_beam_ids
            if tid in thought_map
            and thought_map[tid].tool_calls
            and not thought_map[tid].tool_results
            and thought_map[tid].status in ("pending", "evaluated")
        ] if active_beams else [
            t for t in all_thoughts
            if t.tool_calls and not t.tool_results
            and t.status in ("pending", "evaluated")
        ]
    else:
        # 原有: 只执行 best_path 上的 thoughts
        best_path_ids = set(state["best_path"])
        thought_map = get_thought_map(all_thoughts)
        best_thoughts = [thought_map[tid] for tid in best_path_ids if tid in thought_map]
        pending_execution = [
            t for t in best_thoughts
            if t.tool_calls and not t.tool_results
        ]

    if not pending_execution:
        logger.info("No tools to execute")
        return state

    logger.info(f"Executing tool plans for {len(pending_execution)} thoughts (beam_mode={'on' if beam_width else 'off'})")

    exec_start = time.time()
    tool_records = []
    max_time_per_node = state.get("max_time_per_node", 30.0)

    for thought in pending_execution:
        thought.status = "executing"
        node_start = time.time()
        results = []

        # ---- 按序执行 tool_calls（多步计划） ----
        if beam_width and len(thought.tool_calls) > 1:
            # Phase 4: 顺序执行（带依赖跳过 + 超时）
            results = await _execute_tool_plan_sequential(
                thought, tools, user_query, max_time_per_node, node_start
            )
        else:
            # 原有: 并行执行所有 tool_calls
            try:
                results = await _execute_tools_concurrent(
                    thought.tool_calls, tools, user_query,
                )
            except Exception as e:
                logger.error(f"Error executing tools for thought {thought.id}: {e}")
                results = [{"error": str(e), "status": "error"}]

        # ---- 存储结果 ----
        thought.tool_results = results
        thought.local_done = True
        thought.local_step_count = len([r for r in results if r.get("status") != "skipped"])
        thought.local_error_count = len([r for r in results if r.get("status") == "error"])

        # ---- 收集 artifacts ----
        _collect_artifacts(thought, results)

        # ---- 死路剪枝 ----
        if _dead_end_prune_executed(thought):
            thought.status = "pruned"
            logger.info(f"[Prune-DeadEnd] Thought {thought.id} marked as dead-end")
        else:
            thought.status = "done"

        # ---- 图片延迟嵌入 ----
        if beam_width:
            _extract_and_defer_images(thought, state)
        else:
            # 原有: 直接嵌入图片
            pass  # _execute_single_tool 中已调用 embed_output_images_v2

        # ---- Research mode: 同步到 raw_sources ----
        if state.get("task_mode") == "research":
            raw_sources = list(state.get("raw_sources") or [])
            for r in results:
                if r.get("status") == "success":
                    raw_sources.append({
                        "source_id": f"tool_{thought.id}",
                        "source_text": str(r.get("result", "")),
                        "source_type": "tool_output",
                    })
            state["raw_sources"] = raw_sources

        # ---- reasoning trace ----
        gen_images_for_trace = []
        for r in results:
            if isinstance(r, dict) and r.get("generated_images"):
                gen_images_for_trace.extend(r["generated_images"])

        state["reasoning_trace"].append({
            "type": "thought_execution",
            "thought_id": thought.id,
            "content": thought.content,
            "total_steps": len(thought.tool_calls),
            "executed_steps": thought.local_step_count,
            "errors": thought.local_error_count,
            "generated_images": gen_images_for_trace,
        })

        # ---- tool_records for tot_logger ----
        for tc in (thought.tool_calls or []):
            tool_records.append({
                "tool_name": tc.get("name", "unknown"),
                "args_summary": str(tc.get("args", {}))[:200],
                "cached": False,
                "duration_ms": int((time.time() - node_start) * 1000),
                "success": thought.status != "pruned",
                "error": None,
            })

        logger.info(
            f"[Executor] Thought {thought.id}: "
            f"{thought.local_step_count}/{len(thought.tool_calls)} steps, "
            f"{thought.local_error_count} errors, status={thought.status}"
        )

    # ---- tot_logger ----
    if "tot_logger" in state and tool_records:
        state["tot_logger"].log_execution(
            depth=state.get("current_depth", 0),
            tool_calls=tool_records,
            cache_hits=0,
            cache_misses=len(tool_records),
            duration=time.time() - exec_start,
        )

    return state


# ---------------------------------------------------------------------------
# Phase 4: 按序执行多步工具计划
# ---------------------------------------------------------------------------

async def _execute_tool_plan_sequential(
    thought: Thought,
    tools: List[BaseTool],
    user_query: str,
    max_time_per_node: float,
    node_start: float,
) -> List[Dict[str, Any]]:
    """按序执行 thought.tool_calls 中的多步工具计划。"""
    results = []
    tool_map = {tool.name: tool for tool in tools}

    for step_idx, tool_call in enumerate(thought.tool_calls):
        # 超时检查
        elapsed = time.time() - node_start
        if elapsed > max_time_per_node:
            logger.warning(
                f"[Executor] Thought {thought.id}: timeout at step "
                f"{step_idx}/{len(thought.tool_calls)} ({elapsed:.1f}s)"
            )
            results.append({
                "tool": tool_call.get("name", "unknown"),
                "error": f"Timeout after {elapsed:.1f}s",
                "status": "error",
            })
            break

        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})

        # 依赖检查
        if _should_skip_due_to_prior_failure(tool_name, results):
            logger.info(
                f"[Executor] Thought {thought.id}: skipping step {step_idx} "
                f"({tool_name}) due to prior failure"
            )
            results.append({
                "tool": tool_name,
                "error": "Skipped: prior step failed",
                "status": "skipped",
            })
            continue

        # 执行工具
        try:
            if tool_name not in tool_map:
                results.append({"tool": tool_name, "error": f"Tool not found: {tool_name}", "status": "error"})
                continue

            tool = tool_map[tool_name]
            result_str, gen_images = await _execute_single_tool(tool, tool_args, user_query)

            entry = {"tool": tool_name, "result": result_str, "status": "success"}
            if gen_images:
                entry["generated_images"] = gen_images
            results.append(entry)

        except Exception as e:
            logger.error(f"[Executor] Thought {thought.id} step {step_idx} ({tool_name}): {e}")
            results.append({"tool": tool_name, "error": str(e), "status": "error"})

    return results


# ---------------------------------------------------------------------------
# Phase 4: 辅助函数
# ---------------------------------------------------------------------------

def _collect_artifacts(thought: Thought, results: List[Dict]) -> None:
    """从工具执行结果中收集有价值的产物。"""
    for r in results:
        if r.get("status") == "success" and r.get("result"):
            thought.artifacts.append({
                "tool": r.get("tool", "unknown"),
                "content": str(r["result"])[:500],
            })


def _extract_and_defer_images(thought: Thought, state: ToTState) -> None:
    """探索阶段: 提取图片路径但不嵌入。"""
    for r in (thought.tool_results or []):
        result_text = str(r.get("result", ""))
        paths = re.findall(r'(?:outputs[/\\]|data[/\\]outputs[/\\])\S+\.(?:png|jpg|jpeg|svg)', result_text)
        if paths:
            logger.info("[DeferImages] Thought %s: found %d image path(s): %s", thought.id, len(paths), paths)
            state.setdefault("deferred_image_paths", []).extend(paths)
        else:
            logger.debug("[DeferImages] Thought %s: no image paths in result (%d chars)", thought.id, len(result_text))


# ---------------------------------------------------------------------------
# 原有工具执行函数（保持不变）
# ---------------------------------------------------------------------------

async def _execute_tools_concurrent(
    tool_calls: List[Dict[str, Any]],
    tools: List[BaseTool],
    user_query: str = "",
) -> List[Dict[str, Any]]:
    """
    Execute multiple tool calls in parallel.
    """
    tool_map = {tool.name: tool for tool in tools}

    tasks = []
    errors = []

    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})

        if tool_name in tool_map:
            task = _execute_single_tool(tool_map[tool_name], tool_args, user_query)
            tasks.append((tool_name, task))
        else:
            logger.warning(f"Tool not found: {tool_name}")
            errors.append({
                "tool": tool_name,
                "error": f"Tool not found: {tool_name}",
                "status": "error"
            })

    results = errors.copy()

    if tasks:
        completed = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True
        )

        for (tool_name, _), outcome in zip(tasks, completed):
            if isinstance(outcome, Exception):
                results.append({
                    "tool": tool_name,
                    "error": str(outcome),
                    "status": "error"
                })
            else:
                result_str, gen_images = outcome
                entry: Dict[str, Any] = {
                    "tool": tool_name,
                    "result": result_str,
                    "status": "success",
                }
                if gen_images:
                    entry["generated_images"] = gen_images
                results.append(entry)

    return results


async def _execute_single_tool(tool: BaseTool, args: Dict[str, Any], user_query: str = "") -> tuple[Any, list[dict]]:
    """
    Execute a single tool with error handling.

    If read_file reads a SKILL.md, auto-detect and execute the skill via skill_orchestrator.
    """
    # Check cache before execution
    try:
        from app.core.tot.cache import get_global_cache
        cache = get_global_cache()
        cached = cache.get(tool.name, args)
        if cached is not None:
            logger.info(f"[CACHE_HIT] {tool.name} with args={list(args.keys())}")
            return cached.get("result", ""), cached.get("generated_images", [])
    except Exception:
        pass

    # === SkillPolicy gate (pre-gate before legacy skill_orchestrator) ===
    if _SKILL_POLICY_AVAILABLE and tool.name == "read_file":
        path = args.get("path", "")
        if is_skill_file(path):
            skill_name = extract_skill_name(path)
            if skill_name:
                logger.info(
                    "[ThoughtExecutor] SkillPolicy gate: read_file(SKILL.md) detected for '%s', "
                    "query=%s", skill_name, user_query[:80],
                )
                try:
                    from app.api.chat import get_agent_manager
                    from app.config import get_settings
                    from pathlib import Path as _Path
                    am = get_agent_manager()
                    skills_dir = _Path(get_settings().skills_dir)
                    tool_plan = await check_skill_policy_gate(
                        skill_name, user_query, am.tools, am.llm, skills_dir,
                    )
                    if tool_plan:
                        # Execute all compiled tool plan steps
                        logger.info(
                            "[ThoughtExecutor] SkillPolicy compiled '%s' → %d step(s): %s",
                            skill_name, len(tool_plan),
                            [s.get("tool", "?") for s in tool_plan],
                        )
                        result, images = await _execute_compiled_skill_plan(
                            tool_plan, am.tools, user_query,
                        )
                        _cache_tool_result(tool.name, args, result, images)
                        return result, images
                    else:
                        logger.info(
                            "[ThoughtExecutor] SkillPolicy gate not passed for '%s', "
                            "falling through to legacy path",
                            skill_name,
                        )
                except Exception as e:
                    logger.warning(
                        "[ThoughtExecutor] SkillPolicy gate failed for '%s': %s, "
                        "falling back to legacy", skill_name, e,
                    )
                # GATE not passed or error → fall through to legacy skill_orchestrator

    # Skill auto-detection (legacy fallback)
    if _SKILL_ORCHESTRATOR_AVAILABLE and tool.name == "read_file":
        path = args.get("path", "")
        if is_skill_file(path):
            skill_name = extract_skill_name(path)
            if skill_name:
                logger.info(
                    "[ThoughtExecutor] Legacy path: SKILL.md read for '%s', "
                    "auto-executing via skill_orchestrator", skill_name,
                )
                try:
                    skill_content_result = await tool.ainvoke(args)
                except AttributeError:
                    skill_content_result = tool.invoke(args)
                skill_content = str(skill_content_result)

                try:
                    from app.api.chat import get_agent_manager
                    am = get_agent_manager()
                    skill_result = await execute_skill_from_skillmd(
                        skill_name=skill_name,
                        skill_content=skill_content,
                        user_query=user_query,
                        tools=am.tools,
                        llm=am.llm,
                    )
                    result_str = skill_result.get("result", "")
                    gen_images = skill_result.get("generated_images") or []
                    _cache_tool_result(tool.name, args, result_str, gen_images)
                    if gen_images:
                        logger.info("[ThoughtExecutor] Skill '%s' generated %d image(s)", skill_name, len(gen_images))
                    return result_str, gen_images
                except Exception as e:
                    logger.error("[ThoughtExecutor] Skill '%s' execution failed: %s", skill_name, e)
                    return f"Skill '{skill_name}' execution failed: {str(e)}", []

    try:
        result = await tool.ainvoke(args)
        result_str = str(result)
        logger.info(
            "[SingleTool] %s result: %d chars, preview: %s",
            tool.name, len(result_str), result_str[:200],
        )
        result_str, gen_images = embed_output_images_v2(result_str)
        if gen_images:
            logger.info("[ThoughtExecutor] %s generated %d image(s)", tool.name, len(gen_images))
        else:
            logger.info("[SingleTool] %s: embed_output_images_v2 found 0 images", tool.name)
        _cache_tool_result(tool.name, args, result_str, gen_images)
        return result_str, gen_images

    except AttributeError:
        try:
            result = tool.invoke(args)
            result_str = str(result)
            logger.info(
                "[SingleTool-fallback] %s result: %d chars, preview: %s",
                tool.name, len(result_str), result_str[:200],
            )
            result_str, gen_images = embed_output_images_v2(result_str)
            if gen_images:
                logger.info("[ThoughtExecutor] %s generated %d image(s)", tool.name, len(gen_images))
            else:
                logger.info("[SingleTool-fallback] %s: embed_output_images_v2 found 0 images", tool.name)
            _cache_tool_result(tool.name, args, result_str, gen_images)
            return result_str, gen_images
        except Exception as e:
            raise Exception(f"Tool execution failed: {str(e)}")

    except Exception as e:
        raise Exception(f"Tool execution failed: {str(e)}")


def _cache_tool_result(tool_name: str, args: Dict[str, Any], result: Any, gen_images: list) -> None:
    """Store tool result in global cache (best-effort)."""
    try:
        from app.core.tot.cache import get_global_cache
        cache = get_global_cache()
        cache.set(tool_name, args, {
            "result": result,
            "generated_images": gen_images,
        })
    except Exception:
        pass


async def _execute_compiled_skill(
    compiled: Dict[str, Any],
    tools: List[BaseTool],
    user_query: str,
) -> tuple[Any, list[dict]]:
    """Execute a single compiled skill tool call.

    Args:
        compiled: {"tool": tool_name, "args": tool_args}
        tools: Available tools list.
        user_query: User query string.

    Returns:
        (result_str, generated_images) tuple.
    """
    tool_name = compiled["tool"]
    tool_args = compiled["args"]

    # [DEBUG-LOG] Log the actual code being executed for python_repl
    if tool_name == "python_repl" and "code" in tool_args:
        code_preview = tool_args["code"][:500]
        logger.info(
            "[CompiledSkill] python_repl code (%d chars):\n---\n%s\n---",
            len(tool_args["code"]), code_preview,
        )

    tool_map = {t.name: t for t in tools}
    target_tool = tool_map.get(tool_name)
    if not target_tool:
        raise RuntimeError(f"Compiled tool '{tool_name}' not found in available tools")

    try:
        result = await target_tool.ainvoke(tool_args)
    except AttributeError:
        result = target_tool.invoke(tool_args)

    result_str = str(result)
    # [DEBUG-LOG] Log raw result before image embedding
    logger.info(
        "[CompiledSkill] %s raw result: %d chars, preview: %s",
        tool_name, len(result_str), result_str[:300],
    )
    # [DEBUG-LOG] Check for file paths in result
    import re as _re
    file_paths = _re.findall(
        r'(?:outputs?[/\\]|data[/\\]outputs?[/\\])\S+\.(?:png|jpg|jpeg|svg|webp)',
        result_str, _re.IGNORECASE,
    )
    if file_paths:
        logger.info("[CompiledSkill] Found file paths in result: %s", file_paths)
    else:
        logger.info("[CompiledSkill] No image file paths found in result")

    result_str, gen_images = embed_output_images_v2(result_str)
    # [DEBUG-LOG] Log image embedding results
    logger.info(
        "[CompiledSkill] embed_output_images_v2: %d images found, result now %d chars",
        len(gen_images), len(result_str),
    )
    if _SKILL_ORCHESTRATOR_AVAILABLE:
        _register_embedded_images(result_str)
    if gen_images:
        logger.info("[ThoughtExecutor] Compiled skill via %s generated %d image(s)", tool_name, len(gen_images))
    return result_str, gen_images


async def _execute_compiled_skill_plan(
    tool_plan: List[Dict[str, Any]],
    tools: List[BaseTool],
    user_query: str,
) -> tuple[str, list[dict]]:
    """Execute a multi-step compiled skill tool_plan.

    Args:
        tool_plan: List of {"tool": tool_name, "args": tool_args}
        tools: Available tools list.
        user_query: User query string.

    Returns:
        (combined_result_str, all_generated_images) tuple.
    """
    all_results = []
    all_images = []

    logger.info("[CompiledPlan] Starting %d step(s) for skill plan", len(tool_plan))
    for step_idx, step in enumerate(tool_plan):
        logger.info(
            "[CompiledPlan] Step %d/%d: tool=%s, args_keys=%s",
            step_idx + 1, len(tool_plan),
            step.get("tool", "?"), list(step.get("args", {}).keys()),
        )
        try:
            result_str, gen_images = await _execute_compiled_skill(step, tools, user_query)
            all_results.append(result_str)
            all_images.extend(gen_images)
        except Exception as e:
            logger.error("[ThoughtExecutor] Compiled skill plan step failed: %s", e)
            all_results.append(f"Error: {e}")

    combined = "\n".join(all_results)
    if _SKILL_ORCHESTRATOR_AVAILABLE:
        _register_embedded_images(combined)
    return combined, all_images


# OLD: 同步执行 fallback（保留）
def _execute_tools_sync(
    tool_calls: List[Dict[str, Any]],
    tools: List[BaseTool]
) -> List[Dict[str, Any]]:
    """
    Synchronous version of tool execution (fallback).
    """
    tool_map = {tool.name: tool for tool in tools}
    results = []

    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})

        if tool_name in tool_map:
            try:
                tool = tool_map[tool_name]
                result = tool.invoke(tool_args)
                results.append({
                    "tool": tool_name,
                    "result": result,
                    "status": "success"
                })
            except Exception as e:
                logger.error(f"Error executing tool {tool_name}: {e}")
                results.append({
                    "tool": tool_name,
                    "error": str(e),
                    "status": "error"
                })
        else:
            results.append({
                "tool": tool_name,
                "error": f"Tool not found: {tool_name}",
                "status": "error"
            })

    return results
