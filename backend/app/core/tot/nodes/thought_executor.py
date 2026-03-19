"""
Thought Executor Node

Executes tool calls for selected thoughts in the best path.

Phase 4 Enhancement: Integrated tool result caching
"""

import asyncio
import logging
from typing import List, Dict, Any

from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage

from app.core.tot.state import ToTState, Thought

logger = logging.getLogger(__name__)


async def thought_executor_node(state: ToTState) -> ToTState:
    """
    Execute tools for thoughts on the best path.

    This node:
    1. Identifies thoughts on the best path that haven't been executed
    2. Executes their tool calls in parallel where possible (with cache lookup)
    3. Stores results for use in subsequent reasoning
    4. Adds execution events to reasoning trace for streaming

    Phase 4: Enhanced with tool result caching

    Args:
        state: Current ToT state

    Returns:
        Updated state with tool execution results
    """
    tools = state["tools"]
    best_path_ids = state["best_path"]
    all_thoughts = state["thoughts"]

    # Get cache config
    enable_cache = state.get("tot_enable_cache", True)
    cache_ttl = state.get("tot_cache_ttl", 300)

    # Get or create cache
    cache = None
    if enable_cache:
        from app.core.tot.cache import get_global_cache
        cache = get_global_cache(ttl=cache_ttl, enabled=True)

    # Get thoughts on best path that need execution
    best_thoughts = [t for t in all_thoughts if t.id in best_path_ids]
    pending_execution = [
        t for t in best_thoughts
        if t.tool_calls and not t.tool_results
    ]

    if not pending_execution:
        logger.info("No tools to execute")
        return state

    logger.info(f"Executing tools for {len(pending_execution)} thoughts (cache: {enable_cache})")

    # Execute tools for each thought
    for thought in pending_execution:
        try:
            if thought.tool_calls:
                # Execute tool calls with cache
                results = await _execute_tools_with_cache(
                    thought.tool_calls,
                    tools,
                    cache
                )

                # Store results
                thought.tool_results = results

                logger.info(
                    f"Executed {len(thought.tool_calls)} tools for thought {thought.id}"
                )

                # Add to reasoning trace
                state["reasoning_trace"].append({
                    "type": "thought_execution",
                    "thought_id": thought.id,
                    "content": thought.content,
                    "tool_count": len(thought.tool_calls),
                    "results": results
                })

        except Exception as e:
            logger.error(f"Error executing tools for thought {thought.id}: {e}")
            thought.tool_results = [{
                "error": str(e),
                "status": "failed"
            }]

    # Log cache stats if enabled
    if cache and enable_cache:
        stats = cache.get_stats()
        logger.info(
            f"[CACHE_STATS] Hits: {stats['hits']}, "
            f"Misses: {stats['misses']}, "
            f"Hit Rate: {stats['hit_rate']:.1%}, "
            f"Size: {stats['size']}"
        )

    return state


async def _execute_tools_with_cache(
    tool_calls: List[Dict[str, Any]],
    tools: List[BaseTool],
    cache: Any = None
) -> List[Dict[str, Any]]:
    """
    Execute multiple tool calls with caching support (Phase 4).

    Checks cache before executing each tool call:
    1. If cached result exists and is fresh → use cache
    2. Otherwise → execute tool and cache result

    Args:
        tool_calls: List of tool call dicts with 'name' and 'args'
        tools: List of available BaseTool instances
        cache: Optional ToolResultCache instance

    Returns:
        List of result dicts
    """
    # Build tool lookup dict
    tool_map = {tool.name: tool for tool in tools}

    # Separate cached and uncached calls
    cached_results = []
    execution_tasks = []
    execution_indices = []  # Track original indices for proper ordering

    for idx, tool_call in enumerate(tool_calls):
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})

        # Check cache first
        if cache:
            cached_result = cache.get(tool_name, tool_args)
            if cached_result is not None:
                # Cache hit
                cached_results.append((idx, cached_result))
                continue

        # Cache miss or no cache
        if tool_name in tool_map:
            task = _execute_single_tool(tool_map[tool_name], tool_args)
            execution_tasks.append((idx, tool_name, task))
        else:
            # Tool not found
            cached_results.append((
                idx,
                {
                    "tool": tool_name,
                    "error": f"Tool not found: {tool_name}",
                    "status": "error"
                }
            ))

    # Execute uncached tools in parallel
    executed_results = []

    if execution_tasks:
        completed = await asyncio.gather(
            *[task for _, _, task in execution_tasks],
            return_exceptions=True
        )

        for (idx, tool_name, _), result in zip(execution_tasks, completed):
            if isinstance(result, Exception):
                result_dict = {
                    "tool": tool_name,
                    "error": str(result),
                    "status": "error"
                }
            else:
                result_dict = {
                    "tool": tool_name,
                    "result": result,
                    "status": "success"
                }

            # Cache the result
            if cache and result_dict.get("status") == "success":
                cache.set(tool_name, tool_args, result_dict)

            executed_results.append((idx, result_dict))

    # Merge cached and executed results in original order
    all_results = cached_results + executed_results
    all_results.sort(key=lambda x: x[0])  # Sort by original index

    return [result for _, result in all_results]


async def _execute_tools_concurrent(
    tool_calls: List[Dict[str, Any]],
    tools: List[BaseTool]
) -> List[Dict[str, Any]]:
    """
    Execute multiple tool calls in parallel (legacy, without cache).

    Args:
        tool_calls: List of tool call dicts with 'name' and 'args'
        tools: List of available BaseTool instances

    Returns:
        List of result dicts
    """
    return await _execute_tools_with_cache(tool_calls, tools, cache=None)


async def _execute_single_tool(tool: BaseTool, args: Dict[str, Any]) -> Any:
    """
    Execute a single tool with error handling.

    Args:
        tool: BaseTool instance
        args: Tool arguments

    Returns:
        Tool execution result
    """
    try:
        # Use tool's invoke method
        result = await tool.ainvoke(args)
        return result

    except AttributeError:
        # Tool doesn't support async, use sync
        try:
            result = tool.invoke(args)
            return result
        except Exception as e:
            raise Exception(f"Tool execution failed: {str(e)}")

    except Exception as e:
        raise Exception(f"Tool execution failed: {str(e)}")


def _execute_tools_sync(
    tool_calls: List[Dict[str, Any]],
    tools: List[BaseTool]
) -> List[Dict[str, Any]]:
    """
    Synchronous version of tool execution (fallback).

    Args:
        tool_calls: List of tool call dicts
        tools: List of available tools

    Returns:
        List of result dicts
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
