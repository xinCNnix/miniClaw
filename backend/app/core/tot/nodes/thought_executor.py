"""
Thought Executor Node

Executes tool calls for selected thoughts in the best path.
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
    2. Executes their tool calls in parallel where possible
    3. Stores results for use in subsequent reasoning
    4. Adds execution events to reasoning trace for streaming

    Args:
        state: Current ToT state

    Returns:
        Updated state with tool execution results
    """
    tools = state["tools"]
    best_path_ids = state["best_path"]
    all_thoughts = state["thoughts"]

    # Get thoughts on best path that need execution
    best_thoughts = [t for t in all_thoughts if t.id in best_path_ids]
    pending_execution = [
        t for t in best_thoughts
        if t.tool_calls and not t.tool_results
    ]

    if not pending_execution:
        logger.info("No tools to execute")
        return state

    logger.info(f"Executing tools for {len(pending_execution)} thoughts")

    # Execute tools for each thought
    for thought in pending_execution:
        try:
            if thought.tool_calls:
                # Execute tool calls
                results = await _execute_tools_concurrent(
                    thought.tool_calls,
                    tools
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

    return state


async def _execute_tools_concurrent(
    tool_calls: List[Dict[str, Any]],
    tools: List[BaseTool]
) -> List[Dict[str, Any]]:
    """
    Execute multiple tool calls in parallel.

    Args:
        tool_calls: List of tool call dicts with 'name' and 'args'
        tools: List of available BaseTool instances

    Returns:
        List of result dicts
    """
    # Build tool lookup dict
    tool_map = {tool.name: tool for tool in tools}

    # Create execution tasks and collect errors for missing tools
    tasks = []
    errors = []

    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})

        if tool_name in tool_map:
            task = _execute_single_tool(tool_map[tool_name], tool_args)
            tasks.append((tool_name, task))
        else:
            logger.warning(f"Tool not found: {tool_name}")
            errors.append({
                "tool": tool_name,
                "error": f"Tool not found: {tool_name}",
                "status": "error"
            })

    # Execute in parallel
    results = errors.copy()  # Start with errors for missing tools

    if tasks:
        completed = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True
        )

        for (tool_name, _), result in zip(tasks, completed):
            if isinstance(result, Exception):
                results.append({
                    "tool": tool_name,
                    "error": str(result),
                    "status": "error"
                })
            else:
                results.append({
                    "tool": tool_name,
                    "result": result,
                    "status": "success"
                })

    return results


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
