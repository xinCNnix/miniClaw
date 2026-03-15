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
            recent_tool_calls = []  # Track recent tool calls for redundancy detection

            # Store config values for efficiency
            enable_smart_stopping = settings.enable_smart_stopping
            redundancy_window = settings.redundancy_detection_window
            evaluation_interval = settings.sufficiency_evaluation_interval

            while round_count < max_tool_rounds:
                llm_start = time.time()
                response = await self.llm_with_tools.ainvoke(lc_messages)
                llm_duration = time.time() - llm_start

                logger.info(f"[Round {round_count + 1}] LLM response received in {llm_duration:.2f}s")

                # Check if LLM wants to call tools
                if not hasattr(response, 'tool_calls') or not response.tool_calls:
                    logger.info(f"[Round {round_count + 1}] No tool calls, returning final response")
                    # No more tool calls, yield content and break
                    if hasattr(response, 'content') and response.content:
                        logger.info(f"[Round {round_count + 1}] Yielding final content: {len(response.content)} chars")
                        yield {
                            "type": "content_delta",
                            "content": response.content,
                        }
                    break

                # Has tool calls - execute them
                tool_calls = response.tool_calls
                logger.info(f"[Round {round_count + 1}] Tool calls requested: {len(tool_calls)}")

                # Add assistant message to conversation history
                lc_messages.append(response)

                # Execute all tools in this round
                for idx, tool_call in enumerate(tool_calls):
                    tool_name = tool_call.get('name', '')
                    tool_args = tool_call.get('args', {})
                    tool_id = tool_call.get('id', '')

                    logger.info(f"[Round {round_count + 1}] Executing tool {idx+1}/{len(tool_calls)}: {tool_name}")

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
                        tool_call_id=tool_call.get('id', '')
                    ))

                # Increment round count and continue
                round_count += 1

                # Convert tool_calls to list format for tracking
                tool_calls_list = []
                for tc in tool_calls:
                    tool_calls_list.append({
                        'name': tc.get('name', ''),
                        'args': tc.get('args', {})
                    })
                recent_tool_calls.append(tool_calls_list)

                # Maintain sliding window for redundancy detection
                if len(recent_tool_calls) > redundancy_window:
                    recent_tool_calls.pop(0)

                # Redundancy detection
                if enable_smart_stopping and self._detect_redundancy(recent_tool_calls):
                    logger.warning(f"Detected redundant tool calls in last {len(recent_tool_calls)} rounds, forcing completion")
                    yield {
                        "type": "warning",
                        "message": "Stopped due to repetitive tool calls"
                    }
                    # Generate final response before breaking
                    logger.info("Getting final response after redundancy detection...")
                    try:
                        final_response = await self.llm.ainvoke(lc_messages)
                        if hasattr(final_response, 'content') and final_response.content:
                            logger.info(f"Final response: {len(final_response.content)} chars")
                            yield {
                                "type": "content_delta",
                                "content": final_response.content,
                            }
                            break  # Break after getting response
                        else:
                            logger.warning("LLM returned no content after redundancy detection")
                    except Exception as e:
                        logger.error(f"Failed to get final response: {e}")
                        yield {
                            "type": "error",
                            "error": f"Failed to generate response: {str(e)}"
                        }
                    break

                # Information sufficiency evaluation (based on interval to avoid frequent LLM calls)
                if enable_smart_stopping and round_count % evaluation_interval == 0:
                    should_continue = await self._evaluate_sufficiency(
                        lc_messages=lc_messages,
                        user_question=messages[0]['content'] if messages else ""
                    )

                    if not should_continue:
                        logger.info(f"LLM determined information is sufficient, stopping after {round_count} rounds")
                        yield {
                            "type": "info",
                            "message": f"Completed information gathering after {round_count} tool rounds"
                        }
                        # Generate final response before breaking
                        logger.info("Getting final response after sufficiency evaluation...")
                        try:
                            final_response = await self.llm.ainvoke(lc_messages)
                            if hasattr(final_response, 'content') and final_response.content:
                                logger.info(f"Final response: {len(final_response.content)} chars")
                                yield {
                                    "type": "content_delta",
                                    "content": final_response.content,
                                }
                                break  # Break after getting response
                            else:
                                logger.warning("LLM returned no content after sufficiency evaluation")
                        except Exception as e:
                            logger.error(f"Failed to get final response: {e}")
                            yield {
                                "type": "error",
                                "error": f"Failed to generate response: {str(e)}"
                            }
                        break

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
            result = tool._run(**arguments)
            logger.debug(f"Tool {name} result size: {len(str(result))} chars")
            return result
        raise ValueError(f"Tool not found: {name}")

    async def _aexecute_tool(self, name: str, arguments: dict) -> Any:
        """Execute a tool asynchronously."""
        logger.debug(f"Executing tool (async): {name} with args: {arguments}")
        tool = self._get_tool_by_name(name)
        if tool:
            if hasattr(tool, '_arun'):
                result = await tool._arun(**arguments)
            else:
                result = tool._run(**arguments)
            logger.debug(f"Tool {name} result size: {len(str(result))} chars")
            return result
        raise ValueError(f"Tool not found: {name}")

    def _get_tool_by_name(self, name: str) -> Optional[BaseTool]:
        """Get tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def _detect_redundancy(self, recent_tool_calls: list) -> bool:
        """
        检测最近的工具调用是否存在冗余模式。

        检测条件：
        1. 连续 N 轮调用了相同的工具
        2. 工具参数高度相似

        Args:
            recent_tool_calls: 最近 N 轮的工具调用列表

        Returns:
            True if redundancy detected, False otherwise
        """
        settings = get_settings()
        window_size = settings.redundancy_detection_window

        if len(recent_tool_calls) < window_size:
            return False

        # 提取所有工具调用
        all_calls = []
        for round_calls in recent_tool_calls:
            for call in round_calls:
                all_calls.append({
                    'name': call.get('name', ''),
                    'args': call.get('args', {})
                })

        if not all_calls:
            return False

        # 检测 1: 所有调用是否使用相同工具
        tool_names = [call['name'] for call in all_calls]
        if len(set(tool_names)) == 1:
            # 所有调用使用相同工具，检查参数
            first_args = all_calls[0]['args']
            similar_count = sum(
                1 for call in all_calls[1:]
                if self._args_similarity(first_args, call['args']) > 0.8
            )
            if similar_count >= len(all_calls) - 1:
                logger.warning(f"Redundancy detected: {len(all_calls)} identical calls to {tool_names[0]}")
                return True

        return False

    def _args_similarity(self, args1: dict, args2: dict) -> float:
        """
        计算两个工具参数的相似度。

        Returns:
            0.0 - 1.0 之间的相似度分数
        """
        # Both empty dicts are identical
        if not args1 and not args2:
            return 1.0

        # One empty, one not - different
        if not args1 or not args2:
            return 0.0

        keys1, keys2 = set(args1.keys()), set(args2.keys())
        if keys1 != keys2:
            return 0.0

        if not keys1:
            return 1.0

        # 计算每个键的值相似度
        similarities = []
        for key in keys1:
            val1, val2 = args1[key], args2[key]
            if val1 == val2:
                similarities.append(1.0)
            elif isinstance(val1, str) and isinstance(val2, str):
                # 字符串相似度（简单版本：检查是否有共同前缀）
                if val1 and val2:
                    common_prefix = 0
                    for c1, c2 in zip(val1, val2):
                        if c1 == c2:
                            common_prefix += 1
                        else:
                            break
                    similarity = common_prefix / max(len(val1), len(val2))
                    similarities.append(similarity)
                else:
                    similarities.append(0.0)
            else:
                similarities.append(0.0)

        return sum(similarities) / len(similarities) if similarities else 0.0

    async def _evaluate_sufficiency(self, lc_messages: list, user_question: str) -> bool:
        """
        评估当前收集的信息是否足以回答用户问题。

        Args:
            lc_messages: LangChain 消息列表
            user_question: 用户的原始问题

        Returns:
            True if should continue tool calling, False if sufficient
        """
        try:
            # 提取工具调用历史
            tool_history = self._format_tool_history(lc_messages)

            evaluation_prompt = f"""基于以下工具执行结果，评估是否已经足以回答用户问题。

用户问题：{user_question}

已收集的信息：
{tool_history}

请判断：
1. 是否已经收集到足够的信息来回答用户问题？
2. 如果不够，还需要什么信息？

回复格式（严格遵循）：
- 如果已足够：SUFFICIENT
- 如果需要继续：CONTINUE: <简短说明原因>

你的判断："""

            # 使用不带工具的 LLM 进行评估
            response = await self.llm.ainvoke([
                SystemMessage(content="你是一个信息评估专家。判断信息是否充足，避免过度收集。"),
                HumanMessage(content=evaluation_prompt)
            ])

            result = response.content.strip().upper()
            should_continue = not result.startswith("SUFFICIENT")

            logger.info(f"Sufficiency evaluation: {result[:100]}...")
            return should_continue

        except Exception as e:
            logger.error(f"Sufficiency evaluation failed: {e}")
            # 评估失败时保守地继续
            return True

    def _format_tool_history(self, lc_messages: list) -> str:
        """
        格式化工具调用历史为可读文本。

        Args:
            lc_messages: LangChain 消息列表

        Returns:
            格式化的工具调用历史
        """
        history_parts = []
        tool_count = 0

        for msg in lc_messages:
            if isinstance(msg, ToolMessage):
                tool_count += 1
                content = msg.content
                # 限制每个工具结果长度
                if len(content) > 500:
                    content = content[:500] + "...[truncated]"
                history_parts.append(f"工具 {tool_count}: {content}")

        if not history_parts:
            return "暂无工具调用结果"

        return "\n\n".join(history_parts)

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
