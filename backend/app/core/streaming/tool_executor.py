"""
Concurrent tool executor for streaming response system.

This module executes tools concurrently while maintaining proper
error handling and event publishing.
"""

import asyncio
from typing import Any, Dict, List
from langchain_core.tools import BaseTool

from app.core.streaming.events import StreamEvent, StreamEventType
from app.core.streaming.event_bus import EventBus


class ToolExecutor:
    """
    Concurrent tool executor with event publishing.

    This executor runs tool calls asynchronously and publishes
    execution events to the event bus for streaming.
    """

    def __init__(self, event_bus: EventBus, tools: List[BaseTool]) -> None:
        """
        Initialize the tool executor.

        Args:
            event_bus: Event bus for publishing execution events
            tools: List of available tools
        """
        self._event_bus = event_bus
        self._tools = {tool.name: tool for tool in tools}

    async def execute_tool_call(
        self,
        tool_id: str,
        tool_name: str,
        tool_args: Dict[str, Any]
    ) -> Any:
        """
        Execute a single tool call.

        Args:
            tool_id: Unique identifier for this tool call
            tool_name: Name of the tool to execute
            tool_args: Arguments to pass to the tool

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool is not found
        """
        if tool_name not in self._tools:
            raise ValueError(f"Tool not found: {tool_name}")

        tool = self._tools[tool_name]

        # Publish execution start event
        await self._event_bus.publish(StreamEvent(
            type=StreamEventType.TOOL_EXECUTION_START,
            data={
                "id": tool_id,
                "tool_name": tool_name,
                "args": tool_args
            }
        ))

        try:
            # Execute the tool (may be sync or async)
            result = tool.invoke(tool_args)

            # Publish completion event
            # Keys "output" and "status" must match what chat.py expects
            await self._event_bus.publish(StreamEvent(
                type=StreamEventType.TOOL_EXECUTION_COMPLETE,
                data={
                    "id": tool_id,
                    "tool_name": tool_name,
                    "output": str(result),
                    "status": "success",
                }
            ))

            return result

        except Exception as e:
            # Publish error event
            # Use "output" key so chat.py can read the error message
            await self._event_bus.publish(StreamEvent(
                type=StreamEventType.TOOL_EXECUTION_ERROR,
                data={
                    "id": tool_id,
                    "tool_name": tool_name,
                    "output": str(e),
                    "status": "error",
                }
            ))
            raise

    async def execute_tool_calls_concurrently(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Any]:
        """
        Execute multiple tool calls concurrently.

        Args:
            tool_calls: List of tool call dictionaries with keys:
                       - id: tool call identifier
                       - name: tool name
                       - args: tool arguments

        Returns:
            List of tool execution results (in same order as input)
        """
        # Create tasks for concurrent execution
        tasks = [
            self.execute_tool_call(
                tool_id=tc["id"],
                tool_name=tc["name"],
                tool_args=tc["args"]
            )
            for tc in tool_calls
        ]

        # Execute all tools concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Separate results from exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Error already published in execute_tool_call
                final_results.append({"error": str(result)})
            else:
                final_results.append(result)

        return final_results

    def get_available_tools(self) -> List[str]:
        """
        Get list of available tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is available.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is available, False otherwise
        """
        return tool_name in self._tools
