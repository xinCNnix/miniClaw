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
from app.core.smart_stopping import (
    should_stop_before_execution,
    should_stop_after_execution,
)
from app.core.performance_tracker import track_performance, get_performance_tracker, track_async
from app.core.tracking_context import get_request_id, get_session_id

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
        llm: Optional[BaseChatModel] = None,
        llm_provider: LLMProvider = "qwen",
    ):
        """
        Initialize AgentManager.

        Args:
            tools: List of available tools
            llm: LLM instance (优先使用)
            llm_provider: LLM provider (如果 llm 未提供)
        """
        self.tools = tools
        self.llm_provider = llm_provider

        # 如果未提供 LLM，从 provider 创建
        if llm is None:
            self.llm = create_llm(llm_provider)
        else:
            self.llm = llm

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
        request_id = get_request_id()

        try:
            logger.info(f"[RID:{request_id}] === Agent astream START ===")
            logger.debug(f"[RID:{request_id}] Messages count: {len(messages)}")
            logger.debug(f"[RID:{request_id}] System prompt length: {len(system_prompt)} chars")

            # Get settings early (needed before smart stopping reset)
            settings = get_settings()

            # 智能停止已在 SmartToolStopping 类中管理状态

            self.system_prompt = system_prompt
            lc_messages = self._convert_messages(messages, system_prompt)

            yield {"type": "thinking_start"}
            logger.info(f"[RID:{request_id}] Thinking...")

            # Get max_tool_rounds from settings
            max_tool_rounds = settings.max_tool_rounds

            # 🔧 新增：性能追踪
            perf_tracker = get_performance_tracker()

            # Multi-round tool calling loop
            round_count = 0
            while round_count < max_tool_rounds:
                llm_start = time.time()

                # === 流式响应开关 ===
                use_streaming = settings.enable_streaming_response

                if use_streaming:
                    # 流式模式：只使用 astream()，不调用 ainvoke()
                    # 收集完整的响应用于后续工具调用检查
                    full_response_chunks = []
                    all_content = []  # 收集所有文本内容
                    chunk_count = 0

                    async for chunk in self.llm_with_tools.astream(lc_messages):
                        chunk_count += 1
                        # 收集所有 chunks
                        full_response_chunks.append(chunk)

                        # 🔧 新增：记录每个 chunk 的属性
                        if chunk_count == 1 or chunk_count % 10 == 0:  # 每10个chunk记录一次
                            logger.debug(f"[LLM_STREAM] Chunk {chunk_count}: "
                                       f"has_content={hasattr(chunk, 'content')}, "
                                       f"has_tool_calls={hasattr(chunk, 'tool_calls')}, "
                                       f"has_tool_call_chunks={hasattr(chunk, 'tool_call_chunks')}")

                        # 收集文本内容
                        if hasattr(chunk, 'content') and chunk.content:
                            all_content.append(chunk.content)
                            # 输出文本增量（实时显示 LLM tokens）
                            yield {
                                "type": "content_delta",
                                "content": chunk.content,
                            }

                        # 输出工具调用片段（让用户看到工具调用的过程）
                        if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                            logger.debug(f"[TOOL_CALL_CHUNKS] Received {len(chunk.tool_call_chunks)} chunks")
                            for idx, tc in enumerate(chunk.tool_call_chunks):
                                # 🔧 修复：处理 args 为 None 的情况
                                # tc.get('args', '') 在 args=None 时仍返回 None，需要使用 or
                                args_value = tc.get('args') or ''
                                logger.debug(f"[TOOL_CALL_CHUNK {idx}] "
                                           f"index={tc.get('index')}, "
                                           f"name={tc.get('name')}, "
                                           f"args_len={len(args_value)}")
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

                    # 构建完整 response 对象
                    if full_response_chunks:
                        logger.debug(f"[LLM_RESPONSE] Total chunks received: {len(full_response_chunks)}")

                        # 从所有 chunks 中找到第一个包含有效 tool_calls 的 chunk
                        # 修复：最后一个 chunk 可能没有 tool_calls
                        response_with_tool_calls = None
                        for idx, chunk in enumerate(full_response_chunks):
                            if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                                # 检查是否有有效的 tool_calls（非空名称）
                                valid_calls = [tc for tc in chunk.tool_calls if tc.get('name')]
                                if valid_calls:
                                    response_with_tool_calls = chunk
                                    logger.debug(f"[TOOL_CALLS] Found at chunk {idx}: {len(valid_calls)} calls")
                                    # 🔧 新增：记录每个 tool_call 的详细信息
                                    for j, tc in enumerate(valid_calls):
                                        logger.debug(f"[TOOL_CALL {j}] name={tc.get('name')}, "
                                                   f"args={tc.get('args')}, id={tc.get('id')}")
                                    break

                        # 如果没找到有 tool_calls 的 chunk，使用最后一个 chunk
                        if response_with_tool_calls is None:
                            response_with_tool_calls = full_response_chunks[-1]
                            logger.warning(f"[TOOL_CALLS] No chunk with tool_calls found, using last chunk")

                        response = response_with_tool_calls

                        # 获取 tool_calls（优先使用找到的有 tool_calls 的 chunk）
                        tool_calls_to_use = getattr(response, 'tool_calls', [])

                        logger.debug(f"[ASSEMBLY] tool_calls count: {len(tool_calls_to_use)}")

                        # 🔧 修复：即使 all_content 为空，也要处理 tool_calls 的 args 组装
                        # 这解决了 LLM 只返回工具调用而没有文本内容时，args 为空导致验证失败的问题
                        if tool_calls_to_use:
                            for i, tc in enumerate(tool_calls_to_use):
                                tc_args = tc.get('args')
                                logger.debug(f"[ASSEMBLY] Tool {i}: name={tc.get('name')}, "
                                           f"has_args={tc_args is not None}, args_empty={tc_args == {}}")

                                if not tc.get('args') or tc.get('args') == {}:
                                    logger.warning(f"[ASSEMBLY] Tool {i} ({tc.get('name')}) has empty args, attempting assembly")
                                    # 从 tool_call_chunks 组装 args
                                    args_parts = []
                                    for chunk_idx, chunk in enumerate(full_response_chunks):
                                        if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                                            for tcc in chunk.tool_call_chunks:
                                                if tcc.get('index') == i and tcc.get('args'):
                                                    args_parts.append(tcc['args'])
                                                    logger.debug(f"[ASSEMBLY] Found args part at chunk {chunk_idx}: "
                                                               f"len={len(tcc['args'])}")

                                    logger.debug(f"[ASSEMBLY] Total args parts for tool {i}: {len(args_parts)}")

                                    if args_parts:
                                        args_str = ''.join(args_parts)
                                        logger.debug(f"[ASSEMBLY] Raw args string for tool {i}: {args_str}")
                                        try:
                                            import json
                                            parsed_args = json.loads(args_str)
                                            tool_calls_to_use[i]['args'] = parsed_args
                                            logger.info(f"[ASSEMBLY] ✓ Successfully assembled args for tool {i}: {parsed_args}")
                                        except json.JSONDecodeError as e:
                                            logger.error(f"[ASSEMBLY] ✗ Failed to parse args for tool {i}: {e}")
                                            logger.error(f"[ASSEMBLY] Raw parts: {args_parts}")
                                    else:
                                        logger.error(f"[ASSEMBLY] ✗ No args parts found for tool {i}, args will remain {{}}")

                        # 确保包含完整的 content（合并所有文本）
                        from langchain_core.messages import AIMessage
                        merged_content = ''.join(all_content) if all_content else ""

                        # 创建新的 AIMessage
                        response = AIMessage(
                            content=merged_content,
                            tool_calls=tool_calls_to_use,
                            additional_kwargs=getattr(response, 'additional_kwargs', {}),
                        )
                        logger.debug(f"[DEBUG] Merged content length: {len(merged_content)}, chunks: {len(all_content)}, tool_calls: {len(tool_calls_to_use)}")
                    else:
                        # 如果没有 chunks（异常情况），使用空响应
                        from langchain_core.messages import AIMessage
                        response = AIMessage(content="")
                else:
                    # 非流式模式：只使用 ainvoke()，不使用流式
                    response = await self.llm_with_tools.ainvoke(lc_messages)

                    # 输出完整内容
                    if hasattr(response, 'content') and response.content:
                        yield {
                            "type": "content_delta",
                            "content": response.content,
                        }
                # === 流式响应开关结束 ===

                llm_duration = time.time() - llm_start

                # 🔧 新增：性能追踪 - 记录LLM调用耗时
                perf_tracker._record_success(
                    f"llm_round_{round_count + 1}",
                    llm_duration
                )

                logger.info(f"[Round {round_count + 1}] LLM response received in {llm_duration:.2f}s")

                # Check if LLM wants to call tools
                if not hasattr(response, 'tool_calls') or not response.tool_calls:
                    logger.info(f"[Round {round_count + 1}] No tool calls, returning final response")
                    # Debug: Log response content
                    if hasattr(response, 'content'):
                        content_len = len(response.content) if response.content else 0
                        logger.info(f"[Round {round_count + 1}] Response content length: {content_len}")
                        if content_len > 0:
                            logger.info(f"[Round {round_count + 1}] Response content preview: {str(response.content)[:200]}")
                        else:
                            logger.warning(f"[Round {round_count + 1}] Response content is EMPTY!")
                            # 如果 LLM 没有返回任何内容，生成一个默认响应
                            logger.warning(f"[Round {round_count + 1}] LLM returned empty response, this might indicate a prompt or model issue")
                    else:
                        logger.warning(f"[Round {round_count + 1}] Response has no content attribute")
                    break

                # Has tool calls - execute them
                tool_calls = response.tool_calls
                logger.info(f"[Round {round_count + 1}] Tool calls requested: {len(tool_calls)}")

                # === 智能停止检查（工具执行前）===
                # 检查是否应该停止工具调用（简单问候、冗余检测等）
                for tool_call in tool_calls:
                    tool_name = tool_call.get('name', '')
                    tool_args = tool_call.get('args', {})

                    should_stop, stop_reason = should_stop_before_execution(
                        settings=settings,
                        round_count=round_count,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        user_message=messages[-1].get('content', '') if messages else ''
                    )

                    if should_stop:
                        logger.warning(f"[SMART_STOP] {stop_reason}")
                        logger.warning(f"[SMART_STOP] 强制停止工具调用，生成最终响应")

                        # 生成最终响应（不使用工具）
                        final_response = await self.llm.ainvoke(lc_messages)
                        if hasattr(final_response, 'content') and final_response.content:
                            yield {
                                "type": "content_delta",
                                "content": final_response.content,
                            }
                        return  # 退出循环
                # === 智能停止检查结束 ===

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

                # === Phase 2: 并发工具执行 ===
                # Check if we should use concurrent execution
                use_concurrent = settings.enable_parallel_tool_execution

                if use_concurrent and len(valid_tool_calls) > 1:
                    # Concurrent execution for multiple tools
                    logger.info(f"[Round {round_count + 1}] Using CONCURRENT execution for {len(valid_tool_calls)} tools")

                    async for event in self._execute_tools_concurrent(valid_tool_calls, lc_messages):
                        yield event

                else:
                    # Serial execution (original behavior)
                    if len(valid_tool_calls) > 1:
                        logger.info(f"[Round {round_count + 1}] Using SERIAL execution for {len(valid_tool_calls)} tools")

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

                        # 🔧 新增：性能追踪 - 记录工具执行开始时间
                        tool_start = time.time()

                        try:
                            tool_output = await self._aexecute_tool(tool_name, tool_args)

                            # 🔧 新增：性能追踪 - 记录工具执行耗时
                            tool_duration = time.time() - tool_start
                            perf_tracker._record_success(f"tool_{tool_name}", tool_duration)

                            logger.info(f"[Round {round_count + 1}] Tool {tool_name} completed in {tool_duration:.2f}s")

                            yield {
                                "type": "tool_output",
                                "tool_name": tool_name,
                                "output": str(tool_output),
                                "status": "success",
                            }
                        except Exception as e:
                            # 🔧 新增：性能追踪 - 记录工具执行失败
                            tool_duration = time.time() - tool_start
                            perf_tracker._record_failure(f"tool_{tool_name}", tool_duration, str(e))

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
                # === Phase 2 并发执行结束 ===

                # Increment round count and continue
                round_count += 1
                logger.info(f"[Round {round_count}] Completed, checking if more tools needed...")

                # === 智能停止检查（工具执行后）===
                # 每隔 N 轮让 LLM 评估是否应该停止
                if settings.enable_smart_stopping:
                    should_stop, stop_reason = await should_stop_after_execution(
                        settings=settings,
                        round_count=round_count,
                        user_message=messages[-1].get('content', '') if messages else '',
                        conversation_messages=lc_messages,
                        llm=self.llm
                    )

                    if should_stop:
                        logger.info(f"[SMART_STOP] {stop_reason}")
                        logger.info(f"[SMART_STOP] 停止工具调用，生成最终响应")

                        # 生成最终响应
                        final_response = await self.llm.ainvoke(lc_messages)
                        if hasattr(final_response, 'content') and final_response.content:
                            yield {
                                "type": "content_delta",
                                "content": final_response.content,
                            }
                        return  # 退出循环
                # === 智能停止检查结束 ===

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

            # 🔧 新增：性能追踪 - 输出性能摘要
            perf_summary = perf_tracker.get_summary()
            if perf_summary:
                logger.info(f"[PERF_SUMMARY] Total: {total_duration:.2f}s")
                for op_name, stats in perf_summary.items():
                    logger.info(
                        f"[PERF_SUMMARY] {op_name}: "
                        f"count={stats['count']}, "
                        f"avg={stats['avg_duration']:.2f}s, "
                        f"max={stats['max_duration']:.2f}s, "
                        f"success_rate={stats['success_rate']:.1f}%"
                    )

            logger.info(f"[RID:{request_id}] === Agent astream COMPLETE in {total_duration:.2f}s ===")

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

    async def _execute_tool_with_tracking(
        self,
        tool_call: dict,
    ) -> dict:
        """
        Execute a single tool with performance tracking.

        Args:
            tool_call: Tool call dict with 'name', 'args', 'id'

        Returns:
            Dict with 'output', 'duration', 'tool_name', 'tool_id', 'status'
        """
        import time
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]

        start = time.time()
        try:
            result = await self._aexecute_tool(tool_name, tool_args)
            duration = time.time() - start

            logger.info(f"Tool {tool_name} completed in {duration:.2f}s")

            return {
                "output": result,
                "duration": duration,
                "tool_name": tool_name,
                "tool_id": tool_id,
                "status": "success",
            }
        except Exception as e:
            duration = time.time() - start
            logger.error(f"Tool {tool_name} failed after {duration:.2f}s: {e}")

            return {
                "output": str(e),
                "duration": duration,
                "tool_name": tool_name,
                "tool_id": tool_id,
                "status": "error",
            }

    async def _execute_tools_concurrent(
        self,
        tool_calls: List[dict],
        lc_messages: List,
    ) -> AsyncIterator[dict]:
        """
        Execute multiple tools concurrently using asyncio.gather.

        Args:
            tool_calls: List of tool call dicts with 'name', 'args', 'id'
            lc_messages: LangChain message list (for adding tool results)

        Yields:
            Events for tool execution progress and results
        """
        import asyncio

        tool_count = len(tool_calls)
        logger.info(f"[CONCURRENT] Starting concurrent execution of {tool_count} tools")

        # Emit start event
        yield {
            "type": "concurrent_execution_start",
            "tool_count": tool_count,
            "mode": "concurrent",
        }

        # Execute all tools concurrently
        results = await asyncio.gather(
            *[self._execute_tool_with_tracking(tc) for tc in tool_calls],
            return_exceptions=True
        )

        # Process results
        for idx, result in enumerate(results):
            # Handle unexpected exceptions
            if isinstance(result, Exception):
                logger.error(f"[CONCURRENT] Tool {idx} raised exception: {result}")
                yield {
                    "type": "tool_output",
                    "tool_name": tool_calls[idx]["name"],
                    "output": str(result),
                    "status": "error",
                }
                # Add error message to conversation
                lc_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_calls[idx]["id"]
                    )
                )
                continue

            # Process normal result
            tool_name = result["tool_name"]
            tool_id = result["tool_id"]
            status = result["status"]
            output = result["output"]
            duration = result["duration"]

            # Emit tool call event (for compatibility)
            yield {
                "type": "tool_call",
                "tool_calls": [{
                    "id": tool_id,
                    "name": tool_name,
                    "arguments": tool_calls[idx]["args"],
                }]
            }

            # Emit tool output event
            yield {
                "type": "tool_output",
                "tool_name": tool_name,
                "output": str(output),
                "status": status,
                "duration": duration,
            }

            # Add result to conversation history
            lc_messages.append(
                ToolMessage(
                    content=str(output),
                    tool_call_id=tool_id
                )
            )

        # Emit completion event
        yield {
            "type": "concurrent_execution_complete",
            "tool_count": tool_count,
            "mode": "concurrent",
        }

        logger.info(f"[CONCURRENT] All {tool_count} tools executed")

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
    llm: Optional[BaseChatModel] = None,
    llm_provider: LLMProvider = "qwen",
) -> AgentManager:
    """
    Factory function to create an AgentManager.

    Args:
        tools: List of available tools
        llm: LLM instance (优先使用)
        llm_provider: LLM provider (如果 llm 未提供)

    Returns:
        Configured AgentManager
    """
    # 如果未提供 LLM，从 provider 创建
    if llm is None:
        from app.core.llm import create_llm
        llm = create_llm(llm_provider)

    return AgentManager(tools=tools, llm=llm)
