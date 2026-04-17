"""
Executor node - executes plan steps with mixed batch/layered-parallel mode.

Batch mode (<=3 steps): Uses AgentManager to execute all steps at once.
Layered-parallel mode (>3 steps): Builds a DAG from depends_on, then
executes layers in order. Steps within the same layer that use safe tools
run in parallel via asyncio.gather(); unsafe tools run serially.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage

from app.config import get_settings
from app.core.agent import create_agent_manager
from app.core.llm import create_llm
from app.core.llm_retry import retry_llm_call
from app.core.perv.json_repair import repair_json_or_none
from app.core.perv.prompts import build_executor_messages
from app.core.perv.pevr_logger import PEVRLogger, extract_token_usage
from app.core.perv.scheduler import (
    build_execution_layers,
    adjust_parallelism,
    ExecutionLayer,
)
from app.tools import CORE_TOOLS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evidence extraction helper
# ---------------------------------------------------------------------------


def _extract_evidence_refs(
    tool_name: str, tool_inputs: Dict[str, Any], status: str
) -> list[str]:
    """Extract lightweight reference citations from a tool call.

    Returns a list of short reference strings (URLs, file paths, queries)
    instead of the full tool output.  Keeps verifier/finalizer prompts small.
    """
    if status != "success":
        return []

    refs: list[str] = []

    if tool_name == "read_file":
        path = tool_inputs.get("path", "")
        if path:
            refs.append(f"file:{path}")
    elif tool_name == "write_file":
        path = tool_inputs.get("path", "")
        if path:
            refs.append(f"file:{path}")
    elif tool_name == "fetch_url":
        url = tool_inputs.get("url", "")
        if url:
            refs.append(url)
    elif tool_name == "search_kb":
        query = tool_inputs.get("query", "")
        if query:
            refs.append(f"kb:{query}")
    elif tool_name == "terminal":
        cmd = tool_inputs.get("command", "")
        if cmd:
            refs.append(f"cmd:{cmd[:80]}")
    elif tool_name == "python_repl":
        code = tool_inputs.get("code", "")
        if code:
            refs.append(f"python:{code[:60]}")
    else:
        refs.append(
            f"{tool_name}("
            f"{', '.join(f'{k}={str(v)[:30]}' for k, v in tool_inputs.items())})"
        )

    return refs


# ---------------------------------------------------------------------------
# Input resolution helper
# ---------------------------------------------------------------------------


def _resolve_inputs(
    step: dict,
    step_outputs: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve $output_key references in step inputs.

    If an input value starts with '$', it is treated as a reference to
    a previous step's output via output_key.
    e.g. "$out_s1" -> step_outputs["out_s1"]
    """
    raw_inputs = step.get("inputs", step.get("input", {}))
    if not isinstance(raw_inputs, dict):
        return raw_inputs if raw_inputs else {}

    resolved: Dict[str, Any] = {}
    for key, value in raw_inputs.items():
        if isinstance(value, str) and value.startswith("$"):
            ref_key = value[1:]
            if ref_key in step_outputs:
                resolved[key] = str(step_outputs[ref_key])
            else:
                logger.warning(
                    "[PEVR Executor] Unresolved ref '%s' in step %s",
                    value,
                    step.get("id", "?"),
                )
                resolved[key] = value  # Keep as-is
        else:
            resolved[key] = value
    return resolved


# ---------------------------------------------------------------------------
# Main executor node
# ---------------------------------------------------------------------------


async def executor_node(state: dict) -> dict:
    """Execute the current plan using mixed batch/layered-parallel mode.

    - <=3 steps: batch mode via AgentManager.astream()
    - >3 steps: layered-parallel mode with DAG scheduling

    Args:
        state: Current PlannerState dictionary.

    Returns:
        Dictionary with new ``observations``, updated ``step_cursor``,
        ``step_outputs``, and ``consecutive_failures``.
    """
    task: str = state.get("task", "")
    plan: List[dict] = state.get("plan", [])
    prior_observations: List[dict] = state.get("observations", [])
    system_prompt: str = state.get("system_prompt", "")
    retry_count: int = state.get("retry_count", 0)
    step_cursor: int = state.get("step_cursor", 0)
    step_outputs: Dict[str, Any] = state.get("step_outputs", {})
    consecutive_failures: int = state.get("consecutive_failures", 0)
    pevr_log: PEVRLogger | None = state.get("_pevr_log")

    start_time = time.time()
    new_observations: List[Dict[str, Any]] = []
    aggregated_tokens: Dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    # Determine mode before try block so it is accessible in the return statement
    total_steps = len(plan)
    settings = get_settings()
    parallel_enabled: bool = getattr(settings, "perv_enable_parallel", True)
    mode = "batch" if total_steps <= 3 else "step"

    try:
        if not plan:
            logger.warning("[PEVR Executor] Empty plan, nothing to execute")
            return {"observations": []}

        # For replan: only execute from cursor onward
        remaining_steps = plan[step_cursor:]
        if not remaining_steps:
            logger.info(
                "[PEVR Executor] No remaining steps (cursor=%d)", step_cursor
            )
            return {"observations": []}

        logger.info(
            "[PEVR Executor] mode=%s plan=%d cursor=%d remaining=%d parallel=%s",
            mode,
            total_steps,
            step_cursor,
            len(remaining_steps),
            parallel_enabled,
        )

        if mode == "batch":
            new_observations = await _execute_batch(
                task=task,
                plan=plan,
                prior_observations=prior_observations,
                system_prompt=system_prompt,
            )
        else:
            # Step mode: use layered-parallel execution
            (
                new_observations,
                step_cursor,
                step_outputs,
                consecutive_failures,
                step_tokens,
            ) = await _execute_layered(
                task=task,
                plan=plan,
                cursor=step_cursor,
                step_outputs=step_outputs,
                system_prompt=system_prompt,
                consecutive_failures=consecutive_failures,
                parallel_enabled=parallel_enabled,
            )
            aggregated_tokens["prompt_tokens"] += step_tokens.get("prompt_tokens", 0)
            aggregated_tokens["completion_tokens"] += step_tokens.get("completion_tokens", 0)
            aggregated_tokens["total_tokens"] += step_tokens.get("total_tokens", 0)

        duration = time.time() - start_time
        success_count = sum(
            1 for o in new_observations if o.get("status") == "success"
        )
        error_count = sum(
            1 for o in new_observations if o.get("status") != "success"
        )

        logger.info(
            "[PEVR Executor] Completed %d tool calls (%d OK, %d fail) mode=%s (%.1fms)",
            len(new_observations),
            success_count,
            error_count,
            mode,
            duration * 1000,
        )

        if pevr_log:
            pevr_log.log_execution(
                loop_index=retry_count,
                observations=new_observations,
                duration_s=duration,
                token_usage=aggregated_tokens,
            )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            "[PEVR Executor] FAILED after %.1fms: %s",
            duration * 1000,
            e,
            exc_info=True,
        )
        new_observations = []
        if pevr_log:
            pevr_log.log_execution(
                loop_index=retry_count,
                observations=[],
                duration_s=duration,
                error=e,
                token_usage=aggregated_tokens,
            )
            pevr_log.log_node_error(
                "executor",
                e,
                f"plan_steps={len(plan)}",
            )

    result: Dict[str, Any] = {"observations": new_observations}
    if mode == "step":
        result["step_cursor"] = step_cursor
        result["step_outputs"] = step_outputs
        result["consecutive_failures"] = consecutive_failures
    return result


# ---------------------------------------------------------------------------
# Batch mode
# ---------------------------------------------------------------------------


async def _execute_batch(
    task: str,
    plan: List[dict],
    prior_observations: List[dict],
    system_prompt: str,
) -> List[Dict[str, Any]]:
    """Batch mode: execute all plan steps via AgentManager.

    Uses AgentManager.astream() with natural language instructions so the LLM
    uses LangChain function calling (not JSON text output) to invoke tools.
    """
    # Build natural language prompt — NOT the "Interpreter Mode" JSON prompt
    # which would cause the LLM to output text instead of tool calls.
    import json as _json

    steps_text = "\n".join(
        f"{i + 1}. [{s.get('tool', '?')}] "
        f"{s.get('description', s.get('purpose', ''))} "
        f"— inputs: {_json.dumps(s.get('inputs', s.get('input', {})), ensure_ascii=False)}"
        for i, s in enumerate(plan)
    )

    obs_text = ""
    if prior_observations:
        obs_items = "\n".join(
            f"- {obs.get('step_id', '?')}: {str(obs.get('result', ''))[:200]}"
            for obs in prior_observations
        )
        obs_text = f"\n## Previous Results\n{obs_items}\n"

    user_msg = (
        f"Execute the following plan steps in order using the available tools.\n\n"
        f"## Task\n{task}\n\n"
        f"## Steps\n{steps_text}\n"
        f"{obs_text}\n"
        f"For each step, call the specified tool with the given inputs. "
        f"Execute ALL steps and report results."
    )

    messages = [{"role": "user", "content": user_msg}]
    logger.debug(
        "[PEVR Executor] Batch mode: built natural-language prompt (%d chars, %d steps)",
        len(user_msg),
        len(plan),
    )

    settings = get_settings()
    agent = create_agent_manager(
        tools=CORE_TOOLS,
        llm_provider=settings.llm_provider,
    )

    new_observations: List[Dict[str, Any]] = []
    steps_completed = 0
    error_count = 0

    async for event in agent.astream(messages, system_prompt):
        event_type = event.get("type", "unknown")

        if event_type == "tool_call":
            tool_calls = event.get("tool_calls", [])
            for tc in tool_calls:
                logger.debug(
                    "[PEVR Executor] Tool call: %s args=%s",
                    tc.get("name", "?"),
                    str(tc.get("arguments", {}))[:100],
                )

        elif event_type == "tool_output":
            tool_name = event.get("tool_name", "unknown")
            status = event.get("status", "error")
            output = event.get("output", "")

            step_id = f"step_{steps_completed + 1}"
            if steps_completed < len(plan):
                step_id = plan[steps_completed].get("id", step_id)

            observation: Dict[str, Any] = {
                "step_id": step_id,
                "tool": tool_name,
                "input": {},
                "status": status,
                "result": output,
                "evidence": _extract_evidence_refs(
                    tool_name, event.get("args", {}), status
                ),
            }
            new_observations.append(observation)
            steps_completed += 1

            if status == "success":
                logger.debug(
                    "[PEVR Executor]   %s: %s OK (%d chars)",
                    step_id,
                    tool_name,
                    len(output),
                )
            else:
                error_count += 1
                logger.warning(
                    "[PEVR Executor]   %s: %s FAILED: %s",
                    step_id,
                    tool_name,
                    str(output)[:200],
                )

        elif event_type == "error":
            logger.error(
                "[PEVR Executor] Agent stream error: %s",
                event.get("error", "unknown"),
            )

    return new_observations


# ---------------------------------------------------------------------------
# Layered-parallel mode (replaces old step-by-step)
# ---------------------------------------------------------------------------


async def _execute_layered(
    task: str,
    plan: List[dict],
    cursor: int,
    step_outputs: Dict[str, Any],
    system_prompt: str,
    consecutive_failures: int,
    parallel_enabled: bool = True,
) -> Tuple[
    List[Dict[str, Any]],
    int,
    Dict[str, Any],
    int,
    Dict[str, int],
]:
    """Layered-parallel mode: build DAG layers and execute them.

    If parallel_enabled is True, uses DAG scheduler to identify parallelizable
    steps and runs safe tools in parallel within each layer.
    If parallel_enabled is False or DAG building fails, falls back to serial
    step-by-step execution.

    Returns:
        (observations, new_cursor, step_outputs, consecutive_failures, token_usage)
    """
    remaining_steps = plan[cursor:]
    agg_tokens: Dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    if not parallel_enabled:
        # Fallback to original step-by-step serial execution
        return await _execute_step_by_step(
            task=task,
            plan=plan,
            cursor=cursor,
            step_outputs=step_outputs,
            system_prompt=system_prompt,
            consecutive_failures=consecutive_failures,
        )

    # Build DAG execution layers
    try:
        raw_layers = build_execution_layers(remaining_steps)
        layers = adjust_parallelism(raw_layers)
    except ValueError as e:
        # Circular dependency or invalid DAG — fallback to serial
        logger.warning(
            "[PEVR Executor] DAG build failed (%s), falling back to serial",
            e,
        )
        return await _execute_step_by_step(
            task=task,
            plan=plan,
            cursor=cursor,
            step_outputs=step_outputs,
            system_prompt=system_prompt,
            consecutive_failures=consecutive_failures,
        )

    if not layers:
        return [], cursor, step_outputs, consecutive_failures, agg_tokens

    logger.info(
        "[PEVR Executor] DAG layers: %d layers, max parallelism=%d",
        len(layers),
        max(len(l.steps) for l in layers),
    )

    all_observations: List[Dict[str, Any]] = []
    max_consecutive = 3

    for layer in layers:
        if consecutive_failures >= max_consecutive:
            logger.error(
                "[PEVR Executor] Aborting: %d consecutive failures",
                consecutive_failures,
            )
            break

        logger.debug(
            "[PEVR Executor] Layer %d: %d steps %s",
            layer.layer_index,
            len(layer.steps),
            layer.step_ids,
        )

        if len(layer.steps) == 1:
            # Single step — execute directly
            obs_list, step_outputs, consecutive_failures, tokens = (
                await _execute_single_step(
                    step=layer.steps[0],
                    step_outputs=step_outputs,
                )
            )
            all_observations.extend(obs_list)
        else:
            # Multiple steps — execute in parallel
            obs_list, step_outputs, consecutive_failures, tokens = (
                await _execute_parallel_steps(
                    steps=layer.steps,
                    step_outputs=step_outputs,
                )
            )
            all_observations.extend(obs_list)

        agg_tokens["prompt_tokens"] += tokens.get("prompt_tokens", 0)
        agg_tokens["completion_tokens"] += tokens.get("completion_tokens", 0)
        agg_tokens["total_tokens"] += tokens.get("total_tokens", 0)

    # Update cursor to end of executed steps
    new_cursor = len(plan)

    return (
        all_observations,
        new_cursor,
        step_outputs,
        consecutive_failures,
        agg_tokens,
    )


async def _execute_single_step(
    step: dict,
    step_outputs: Dict[str, Any],
) -> Tuple[
    List[Dict[str, Any]],
    Dict[str, Any],
    int,
    Dict[str, int],
]:
    """Execute a single step by directly invoking its tool.

    Bypasses LLM for speed — directly resolves inputs and calls the tool.

    Returns:
        (observations, step_outputs, consecutive_failures_delta, token_usage)
    """
    step_id = step.get("id", "?")
    tool_name = step.get("tool", "")
    tool_inputs = _resolve_inputs(step, step_outputs)
    tokens: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    logger.debug(
        "[PEVR Executor] Single step: %s tool=%s",
        step_id,
        tool_name,
    )

    try:
        tool_result = await _invoke_tool(tool_name, tool_inputs)

        output_key = step.get("output_key", "")
        if output_key:
            step_outputs[output_key] = tool_result

        obs: Dict[str, Any] = {
            "step_id": step_id,
            "tool": tool_name,
            "input": tool_inputs,
            "status": "success",
            "result": str(tool_result),
            "evidence": _extract_evidence_refs(tool_name, tool_inputs, "success"),
        }
        logger.debug(
            "[PEVR Executor]   %s: %s OK (%d chars)",
            step_id,
            tool_name,
            len(str(tool_result)),
        )
        return [obs], step_outputs, 0, tokens

    except Exception as e:
        logger.error(
            "[PEVR Executor]   %s: %s FAILED: %s",
            step_id,
            tool_name,
            str(e)[:200],
        )
        obs: Dict[str, Any] = {
            "step_id": step_id,
            "tool": tool_name,
            "input": tool_inputs,
            "status": "fail",
            "result": str(e),
            "evidence": [],
        }
        return [obs], step_outputs, 1, tokens


async def _execute_parallel_steps(
    steps: List[dict],
    step_outputs: Dict[str, Any],
) -> Tuple[
    List[Dict[str, Any]],
    Dict[str, Any],
    int,
    Dict[str, int],
]:
    """Execute multiple steps in parallel using asyncio.gather.

    Each step's tool is invoked directly (no LLM in the loop).
    Results are collected and merged into step_outputs.

    Args:
        steps: List of step dicts in the same execution layer.
        step_outputs: Shared dict for inter-step data passing.

    Returns:
        (observations, step_outputs, consecutive_failures, token_usage)
    """
    tokens: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    async def _run_one(step: dict) -> Dict[str, Any]:
        """Execute one step and return an observation dict."""
        step_id = step.get("id", "?")
        tool_name = step.get("tool", "")
        # Each parallel step gets a snapshot of current step_outputs
        local_outputs = dict(step_outputs)
        tool_inputs = _resolve_inputs(step, local_outputs)

        try:
            result = await _invoke_tool(tool_name, tool_inputs)
            output_key = step.get("output_key", "")
            if output_key:
                step_outputs[output_key] = result

            return {
                "step_id": step_id,
                "tool": tool_name,
                "input": tool_inputs,
                "status": "success",
                "result": str(result),
                "evidence": _extract_evidence_refs(tool_name, tool_inputs, "success"),
            }
        except Exception as e:
            logger.warning(
                "[PEVR Executor]   %s: %s FAILED (parallel): %s",
                step_id,
                tool_name,
                str(e)[:200],
            )
            return {
                "step_id": step_id,
                "tool": tool_name,
                "input": tool_inputs,
                "status": "fail",
                "result": str(e),
                "evidence": [],
            }

    logger.debug(
        "[PEVR Executor] Parallel: executing %d steps concurrently",
        len(steps),
    )

    results = await asyncio.gather(
        *[_run_one(step) for step in steps],
        return_exceptions=True,
    )

    observations: List[Dict[str, Any]] = []
    failures = 0
    for r in results:
        if isinstance(r, Exception):
            failures += 1
            observations.append({
                "step_id": "?",
                "tool": "",
                "input": {},
                "status": "fail",
                "result": str(r),
                "evidence": [],
            })
        elif isinstance(r, dict):
            observations.append(r)
            if r.get("status") == "fail":
                failures += 1

    return observations, step_outputs, failures, tokens


# ---------------------------------------------------------------------------
# Step-by-step mode (fallback for serial execution)
# ---------------------------------------------------------------------------


async def _execute_step_by_step(
    task: str,
    plan: List[dict],
    cursor: int,
    step_outputs: Dict[str, Any],
    system_prompt: str,
    consecutive_failures: int,
) -> Tuple[
    List[Dict[str, Any]],
    int,
    Dict[str, Any],
    int,
    Dict[str, int],
]:
    """Step-by-step mode: execute one step at a time with strict JSON output.

    This is the fallback path when parallel execution is disabled or
    DAG building fails.

    Returns:
        (observations, new_cursor, step_outputs, consecutive_failures, token_usage)
    """
    settings = get_settings()
    provider = settings.llm_provider
    llm = create_llm(provider)

    new_observations: List[Dict[str, Any]] = []
    max_consecutive = 3
    agg_tokens: Dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    for idx in range(cursor, len(plan)):
        step = plan[idx]
        step_id = step.get("id", f"s{idx + 1}")

        # Build messages for this single step
        messages = build_executor_messages(
            task=task,
            plan=[step],  # only current step
            observations=[],
            system_prompt=system_prompt,
            mode="step",
            tools=CORE_TOOLS,
        )

        logger.debug(
            "[PEVR Executor] Step mode: executing %s tool=%s",
            step_id,
            step.get("tool", "?"),
        )

        try:
            response = await retry_llm_call(
                coro_factory=lambda msgs=messages: llm.ainvoke(
                    [HumanMessage(content=msgs[-1]["content"])]
                    if len(msgs) == 1
                    else msgs
                ),
                context=f"pevr_executor_step_{step_id}",
            )

            # Aggregate token usage
            step_tokens = extract_token_usage(response)
            agg_tokens["prompt_tokens"] += step_tokens.get("prompt_tokens", 0)
            agg_tokens["completion_tokens"] += step_tokens.get("completion_tokens", 0)
            agg_tokens["total_tokens"] += step_tokens.get("total_tokens", 0)

            raw_content: str = getattr(response, "content", str(response))
            parsed = repair_json_or_none(raw_content)

            if not parsed or not isinstance(parsed, dict):
                raise ValueError(
                    f"Executor returned non-JSON for step {step_id}"
                )

            result_type = parsed.get("type", "")

            if result_type == "tool_call":
                tool_name = parsed.get("tool", step.get("tool", ""))
                tool_inputs = parsed.get("inputs", step.get("inputs", {}))
                save_as = parsed.get("save_as", step.get("output_key", ""))

                tool_result = await _invoke_tool(tool_name, tool_inputs)

                output_key = step.get("output_key", save_as)
                if output_key:
                    step_outputs[output_key] = tool_result

                obs = {
                    "step_id": step_id,
                    "tool": tool_name,
                    "input": tool_inputs,
                    "status": "success",
                    "result": str(tool_result),
                    "evidence": _extract_evidence_refs(
                        tool_name, tool_inputs, "success"
                    ),
                }
                new_observations.append(obs)
                consecutive_failures = 0

                logger.debug(
                    "[PEVR Executor]   %s: %s OK (%d chars)",
                    step_id,
                    tool_name,
                    len(str(tool_result)),
                )

            elif result_type == "step_result":
                summary = parsed.get("summary", "")
                outputs = parsed.get("outputs", {})
                output_key = step.get("output_key", "")
                if output_key and outputs:
                    step_outputs[output_key] = outputs

                obs = {
                    "step_id": step_id,
                    "tool": step.get("tool", ""),
                    "input": step.get("inputs", {}),
                    "status": "success",
                    "result": summary,
                    "evidence": _extract_evidence_refs(
                        step.get("tool", ""), step.get("inputs", {}), "success"
                    ),
                }
                new_observations.append(obs)
                consecutive_failures = 0

            elif result_type == "step_failed":
                error_msg = parsed.get("error_message", "Unknown error")
                error_type = parsed.get("error_type", "unexpected")
                consecutive_failures += 1

                obs = {
                    "step_id": step_id,
                    "tool": step.get("tool", ""),
                    "input": step.get("inputs", {}),
                    "status": "fail",
                    "result": error_msg,
                    "evidence": [],
                }
                new_observations.append(obs)

                logger.warning(
                    "[PEVR Executor]   %s FAILED: [%s] %s",
                    step_id,
                    error_type,
                    error_msg[:200],
                )

                if consecutive_failures >= max_consecutive:
                    logger.error(
                        "[PEVR Executor] Aborting: %d consecutive failures",
                        consecutive_failures,
                    )
                    cursor = idx + 1
                    break
            else:
                # Unknown result type — try direct tool call
                logger.warning(
                    "[PEVR Executor] Unknown result type '%s' for step %s, "
                    "attempting direct tool call",
                    result_type,
                    step_id,
                )
                tool_name = step.get("tool", "")
                tool_inputs = step.get("inputs", {})
                tool_result = await _invoke_tool(tool_name, tool_inputs)

                output_key = step.get("output_key", "")
                if output_key:
                    step_outputs[output_key] = tool_result

                obs = {
                    "step_id": step_id,
                    "tool": tool_name,
                    "input": tool_inputs,
                    "status": "success",
                    "result": str(tool_result),
                    "evidence": _extract_evidence_refs(
                        tool_name, tool_inputs, "success"
                    ),
                }
                new_observations.append(obs)
                consecutive_failures = 0

        except Exception as e:
            consecutive_failures += 1
            logger.error(
                "[PEVR Executor] Step %s exception: %s",
                step_id,
                e,
                exc_info=True,
            )
            obs = {
                "step_id": step_id,
                "tool": step.get("tool", ""),
                "input": step.get("inputs", {}),
                "status": "fail",
                "result": str(e),
                "evidence": [],
            }
            new_observations.append(obs)

            if consecutive_failures >= max_consecutive:
                cursor = idx + 1
                break

        cursor = idx + 1

    return new_observations, cursor, step_outputs, consecutive_failures, agg_tokens


# ---------------------------------------------------------------------------
# Tool invocation helper
# ---------------------------------------------------------------------------


async def _invoke_tool(
    tool_name: str, tool_inputs: Dict[str, Any]
) -> Any:
    """Find and invoke a core tool by name, with ExecutionCache deduplication."""
    for tool in CORE_TOOLS:
        if tool.name == tool_name:
            try:
                from app.core.execution_cache import get_global_execution_cache, NON_CACHEABLE_TOOLS

                use_cache = tool_name not in NON_CACHEABLE_TOOLS

                if use_cache:
                    cache = get_global_execution_cache()

                    async def _execute():
                        return await tool.ainvoke(tool_inputs)

                    result = await cache.aget_or_execute_tool(
                        tool_name, tool_inputs, _execute
                    )
                    return result
                else:
                    result = await tool.ainvoke(tool_inputs)
                    return result
            except Exception as e:
                logger.error(
                    "[PEVR Executor] Tool %s failed: %s",
                    tool_name,
                    e,
                )
                return f"Tool error: {e}"
    return f"Unknown tool: {tool_name}"
