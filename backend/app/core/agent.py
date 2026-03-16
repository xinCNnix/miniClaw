"""
Agent Module - Simplified LangChain Agent Wrapper

This module provides the core Agent functionality using direct LLM tool calling.
"""

import json
import asyncio
import logging
import time
from typing import List, Any, AsyncIterator, Iterator, Optional, Dict
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.llm import create_llm, LLMProvider
from app.config import get_settings
from app.logging_config import get_agent_logger

# Multi-round tool calling configuration
MAX_TOOL_ROUNDS = 10  # Maximum rounds of tool calling (prevents infinite loops)

# Get logger for agent execution
agent_logger = get_agent_logger("agent.executor")
logger = logging.getLogger(__name__)


class AgentManager:
    """
    Simplified Agent Manager that uses direct LLM tool calling.
    """

    def __init__(
        self,
        tools: List[BaseTool],
        llm_provider: LLMProvider = "qwen",
    ):
        """
        Initialize AgentManager.

        Args:
            tools: List of available tools
            llm_provider: LLM provider to use
        """
        self.tools = tools
        self.llm_provider = llm_provider
        self.llm = create_llm(llm_provider)
        self.system_prompt = ""

        # Bind tools to LLM
        self.llm_with_tools = self.llm.bind_tools(tools)

    def create_agent(
        self,
        system_prompt: str,
    ):
        """
        Initialize the agent with system prompt.

        Args:
            system_prompt: System prompt for the agent
        """
        self.system_prompt = system_prompt
        return self

    def invoke(
        self,
        messages: List[dict],
        system_prompt: str,
    ) -> dict:
        """
        Invoke the agent with messages (synchronous).

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: System prompt for the agent

        Returns:
            Agent response dict
        """
        self.system_prompt = system_prompt
        lc_messages = self._convert_messages(messages, system_prompt)

        response = self.llm_with_tools.invoke(lc_messages)

        # Handle tool calls if present
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # Add the assistant message with tool_calls to conversation history
            # This is REQUIRED by OpenAI API standard - tool messages must follow
            # a message with tool_calls
            lc_messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call.get('name', '')
                # Skip empty tool names
                if not tool_name:
                    logger.warning(f"Skipping tool call with empty name")
                    continue

                tool_args = tool_call.get('args', {})
                tool_output = self._execute_tool(tool_name, tool_args)

                # Add tool message to conversation
                lc_messages.append(ToolMessage(
                    content=str(tool_output),
                    tool_call_id=tool_call.get('id', '')
                ))

            # Get final response after tool execution
            response = self.llm_with_tools.invoke(lc_messages)

        return {
            "role": "assistant",
            "content": response.content if hasattr(response, 'content') else str(response),
        }

    async def ainvoke(
        self,
        messages: List[dict],
        system_prompt: str,
    ) -> dict:
        """
        Async version of invoke.
        """
        self.system_prompt = system_prompt
        lc_messages = self._convert_messages(messages, system_prompt)

        response = await self.llm_with_tools.ainvoke(lc_messages)

        # Handle tool calls if present
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # Add the assistant message with tool_calls to conversation history
            # This is REQUIRED by OpenAI API standard - tool messages must follow
            # a message with tool_calls
            lc_messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call.get('name', '')
                # Skip empty tool names
                if not tool_name:
                    logger.warning(f"Skipping tool call with empty name")
                    continue

                tool_args = tool_call.get('args', {})
                tool_output = await self._aexecute_tool(tool_name, tool_args)

                lc_messages.append(ToolMessage(
                    content=str(tool_output),
                    tool_call_id=tool_call.get('id', '')
                ))

            response = await self.llm_with_tools.ainvoke(lc_messages)

        return {
            "role": "assistant",
            "content": response.content if hasattr(response, 'content') else str(response),
        }

    def stream(
        self,
        messages: List[dict],
        system_prompt: str,
    ) -> Iterator[dict]:
        """
        Stream agent responses.

        Args:
            messages: List of message dicts
            system_prompt: System prompt for the agent

        Yields:
            Event dicts with 'type' and 'data'
        """
        try:
            self.system_prompt = system_prompt
            lc_messages = self._convert_messages(messages, system_prompt)

            yield {"type": "thinking_start"}

            # Get response
            response = self.llm_with_tools.invoke(lc_messages)

            # Handle tool calls
            if hasattr(response, 'tool_calls') and response.tool_calls:
                # Add the assistant message with tool_calls to conversation history
                # This is REQUIRED by OpenAI API standard - tool messages must follow
                # a message with tool_calls
                lc_messages.append(response)

                for tool_call in response.tool_calls:
                    tool_name = tool_call.get('name', '')
                    # Skip empty tool names
                    if not tool_name:
                        logger.warning(f"Skipping tool call with empty name")
                        continue

                    tool_args = tool_call.get('args', {})

                    yield {
                        "type": "tool_call",
                        "tool_calls": [{
                            "id": tool_call.get('id', ''),
                            "name": tool_name,
                            "arguments": tool_args,
                        }]
                    }

                    try:
                        tool_output = self._execute_tool(tool_name, tool_args)
                        yield {
                            "type": "tool_output",
                            "tool_name": tool_name,
                            "output": str(tool_output),
                            "status": "success",
                        }
                    except Exception as e:
                        yield {
                            "type": "tool_output",
                            "tool_name": tool_name,
                            "output": str(e),
                            "status": "error",
                        }

                    lc_messages.append(ToolMessage(
                        content=str(tool_output),
                        tool_call_id=tool_call.get('id', '')
                    ))

                # Get final response
                response = self.llm_with_tools.invoke(lc_messages)

            # Yield content
            if hasattr(response, 'content') and response.content:
                yield {
                    "type": "content_delta",
                    "content": response.content,
                }

        except Exception as e:
            yield {
                "type": "error",
                "error": str(e),
            }

        yield {"type": "done"}

    async def astream(
        self,
        messages: List[dict],
        system_prompt: str,
    ) -> AsyncIterator[dict]:
        """
        Async stream agent responses.
        """
        start_time = time.time()

        try:
            logger.info("=== Agent astream START ===")
            logger.debug(f"Messages count: {len(messages)}")
            logger.debug(f"System prompt length: {len(system_prompt)} chars")

            self.system_prompt = system_prompt
            lc_messages = self._convert_messages(messages, system_prompt)

            yield {"type": "thinking_start"}
            logger.info("Thinking...")

            # Get max_tool_rounds from settings
            settings = get_settings()
            max_tool_rounds = settings.max_tool_rounds

            # Multi-round tool calling loop
            round_count = 0
            while round_count < max_tool_rounds:
                llm_start = time.time()

                # === Phase 1: 流式获取 LLM 响应 ===
                # 先使用 astream() 获取增量响应，实现实时输出
                async for chunk in self.llm_with_tools.astream(lc_messages):
                    # 输出文本增量（实时显示 LLM tokens）
                    if hasattr(chunk, 'content') and chunk.content:
                        yield {
                            "type": "content_delta",
                            "content": chunk.content,
                        }

                    # 输出工具调用片段（让用户看到工具调用的过程）
                    if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                        for tc in chunk.tool_call_chunks:
                            # 工具名称片段
                            if tc.get("name"):
                                yield {
                                    "type": "tool_call_chunk",
                                    "tool_name": tc["name"],
                                    "tool_id": tc.get("index"),
                                }
                            # 工具参数片段（增量显示）
                            if tc.get("args"):
                                yield {
                                    "type": "tool_args_chunk",
                                    "args": tc["args"],
                                    "tool_id": tc.get("index"),
                                }

                # 获取完整响应用于检查工具调用
                response = await self.llm_with_tools.ainvoke(lc_messages)
                llm_duration = time.time() - llm_start
                # === Phase 1 流式输出结束 ===

                logger.info(f"[Round {round_count + 1}] LLM response received in {llm_duration:.2f}s")

                # Check if LLM wants to call tools
                if not hasattr(response, 'tool_calls') or not response.tool_calls:
                    logger.info(f"[Round {round_count + 1}] No tool calls, returning final response")
                    break

                # Has tool calls - execute them
                tool_calls = response.tool_calls
                logger.info(f"[Round {round_count + 1}] Tool calls requested: {len(tool_calls)}")

                # Add assistant message to conversation history
                lc_messages.append(response)

                # Execute all tools in this round
                # Filter out invalid tool calls (empty names)
                valid_tool_calls = []
                for idx, tool_call in enumerate(tool_calls):
                    # DEBUG: Log raw tool_call structure
                    logger.debug(f"[DEBUG] Raw tool_call {idx}: type={type(tool_call)}, content={tool_call}")

                    tool_name = tool_call.get('name', '')
                    tool_args = tool_call.get('args', {})
                    tool_id = tool_call.get('id', '')

                    # DEBUG: Log extracted values
                    logger.debug(f"[DEBUG] Extracted - name={tool_name}, args={tool_args}, id={tool_id}")

                    # Skip tool calls with empty names
                    if not tool_name:
                        logger.warning(f"[Round {round_count + 1}] Skipping tool call {idx+1} with empty name")
                        continue

                    valid_tool_calls.append({
                        'name': tool_name,
                        'args': tool_args,
                        'id': tool_id
                    })

                # Execute only valid tool calls
                for idx, tc in enumerate(valid_tool_calls):
                    tool_name = tc['name']
                    tool_args = tc['args']
                    tool_id = tc['id']

                    logger.info(f"[Round {round_count + 1}] Executing tool {idx+1}/{len(valid_tool_calls)}: {tool_name}")

                    yield {
                        "type": "tool_call",
                        "tool_calls": [{
                            "id": tool_id,
                            "name": tool_name,
                            "arguments": tool_args,
                        }]
                    }

                    try:
                        tool_output = await self._aexecute_tool(tool_name, tool_args)

                        logger.info(f"[Round {round_count + 1}] Tool {tool_name} completed")

                        yield {
                            "type": "tool_output",
                            "tool_name": tool_name,
                            "output": str(tool_output),
                            "status": "success",
                        }
                    except Exception as e:
                        logger.error(f"[Round {round_count + 1}] Tool {tool_name} failed: {e}")
                        yield {
                            "type": "tool_output",
                            "tool_name": tool_name,
                            "output": str(e),
                            "status": "error",
                        }

                    # Add tool result to conversation
                    lc_messages.append(ToolMessage(
                        content=str(tool_output),
                        tool_call_id=tool_id
                    ))

                # Increment round count and continue
                round_count += 1
                logger.info(f"[Round {round_count}] Completed, checking if more tools needed...")

            # Check if we hit the max rounds limit
            if round_count >= max_tool_rounds:
                logger.error(f"⚠️  Exceeded max tool rounds ({max_tool_rounds}), forcing completion")
                yield {
                    "type": "warning",
                    "message": f"Reached maximum tool execution rounds ({max_tool_rounds})"
                }

                # Get final response from LLM after all tool executions
                # Use LLM WITHOUT tools to force text generation instead of more tool calls
                logger.info("Getting final response after max tool rounds...")
                try:
                    final_response = await self.llm.ainvoke(lc_messages)
                    if hasattr(final_response, 'content') and final_response.content:
                        logger.info(f"Final response: {len(final_response.content)} chars")
                        yield {
                            "type": "content_delta",
                            "content": final_response.content,
                        }
                    else:
                        logger.warning("LLM returned no content after max rounds")
                        yield {
                            "type": "error",
                            "error": "Agent exceeded maximum tool execution rounds but could not generate a response"
                        }
                except Exception as e:
                    logger.error(f"Failed to get final response: {e}")
                    yield {
                        "type": "error",
                        "error": f"Failed to generate response after tool execution: {str(e)}"
                    }

            total_duration = time.time() - start_time
            logger.info(f"=== Agent astream COMPLETE in {total_duration:.2f}s ===")

        except Exception as e:
            logger.error(f"Agent astream error: {e}", exc_info=True)
            yield {
                "type": "error",
                "error": str(e),
            }

        yield {"type": "done"}

    def _convert_messages(
        self,
        messages: List[dict],
        system_prompt: str,
    ) -> List:
        """Convert message dicts to LangChain message objects."""
        lc_messages = [SystemMessage(content=system_prompt)]

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))

        return lc_messages

    def _execute_tool(self, name: str, arguments: dict) -> Any:
        """Execute a tool synchronously."""
        logger.debug(f"Executing tool (sync): {name} with args: {arguments}")
        tool = self._get_tool_by_name(name)
        if tool:
            # Use LangChain's standard invoke method (new API)
            result = tool.invoke(arguments)
            logger.debug(f"Tool {name} result size: {len(str(result))} chars")
            return result
        raise ValueError(f"Tool not found: {name}")

    async def _aexecute_tool(self, name: str, arguments: dict) -> Any:
        """Execute a tool asynchronously."""
        logger.debug(f"Executing tool (async): {name} with args: {arguments}")
        logger.debug(f"Arguments type: {type(arguments)}, keys: {arguments.keys() if isinstance(arguments, dict) else 'N/A'}")
        tool = self._get_tool_by_name(name)
        if tool:
            # Use LangChain's standard ainvoke method (new API)
            result = await tool.ainvoke(arguments)
            logger.debug(f"Tool {name} result size: {len(str(result))} chars")
            return result
        raise ValueError(f"Tool not found: {name}")

    def _get_tool_by_name(self, name: str) -> Optional[BaseTool]:
        """Get tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_available_tools(self) -> List[dict]:
        """Get list of available tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self.tools
        ]


def create_agent_manager(
    tools: List[BaseTool],
    llm_provider: LLMProvider = "qwen",
) -> AgentManager:
    """
    Factory function to create an AgentManager.

    Args:
        tools: List of available tools
        llm_provider: LLM provider

    Returns:
        Configured AgentManager
    """
    return AgentManager(tools=tools, llm_provider=llm_provider)
