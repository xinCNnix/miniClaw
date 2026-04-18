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

# Image embedding for tool output (graceful fallback)
try:
    from app.core.streaming.image_embedder import embed_output_images, embed_output_images_v2
except ImportError:
    def embed_output_images(x: str) -> str: return x
    def embed_output_images_v2(x: str, max_age_seconds: int = 60) -> tuple[str, list[dict]]: return x, []

from app.core.llm import create_llm, LLMProvider
from app.config import get_settings
from app.logging_config import get_agent_logger
from app.core.smart_stopping import should_stop_tool_calling

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
        _last_tool_calls: list[dict] = []  # 工具调用追踪（供反思评估使用）

        try:
            logger.info("=== Agent astream START ===")
            logger.debug(f"Messages count: {len(messages)}")
            logger.debug(f"System prompt length: {len(system_prompt)} chars")

            # Get settings early (needed before smart stopping reset)
            settings = get_settings()

            # 重置智能停止的历史记录（新对话开始）
            if settings.enable_smart_stopping:
                from app.core.smart_stopping import SmartToolStopping
                SmartToolStopping().reset_history()

            self.system_prompt = system_prompt
            lc_messages = self._convert_messages(messages, system_prompt)

            yield {"type": "thinking_start"}
            logger.info("Thinking...")

            # Get max_tool_rounds from settings
            max_tool_rounds = settings.max_tool_rounds

            # === TCA injection ===
            _tca_injection_text = ""
            try:
                if getattr(settings, "enable_tca", False):
                    from app.core.meta_policy.tca_helpers import get_tca_decision
                    from app.core.meta_policy.capability_map import CapabilityMap

                    _cap_map = CapabilityMap.from_core_tools()
                    user_msg = messages[-1].get("content", "") if messages else ""
                    _tca_decision = get_tca_decision(user_msg, cap_map=_cap_map)
                    if _tca_decision and _tca_decision.get("injection_text"):
                        _tca_injection_text = _tca_decision["injection_text"]
                        lc_messages.append(SystemMessage(content=_tca_injection_text))
                        logger.info("[TCA] Agent injection applied")
            except Exception as e:
                logger.debug(f"[TCA] Agent enrichment failed: {e}")

            # === Meta Policy injection ===
            _meta_policy_strategy_type = "baseline"
            try:
                if getattr(settings, "enable_meta_policy", False):
                    from app.core.meta_policy.meta_policy_helpers import get_meta_policy_decision
                    from app.core.meta_policy.capability_map import CapabilityMap

                    _cap_map_mp = CapabilityMap.from_core_tools()
                    user_msg = messages[-1].get("content", "") if messages else ""
                    _mp_decision = get_meta_policy_decision(user_msg, cap_map=_cap_map_mp)
                    if _mp_decision and _mp_decision.get("injection_text"):
                        lc_messages.append(SystemMessage(content=_mp_decision["injection_text"]))
                        _meta_policy_strategy_type = _mp_decision.get("strategy_type", "baseline")
                        logger.info("[MetaPolicy] Agent injection applied: %s", _mp_decision.get("action_type"))
            except Exception as e:
                logger.debug(f"[MetaPolicy] Agent enrichment failed: {e}")

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

                    async for chunk in self.llm_with_tools.astream(lc_messages):
                        # 收集所有 chunks
                        full_response_chunks.append(chunk)

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

                    # 构建完整 response 对象
                    if full_response_chunks:
                        # 从所有 chunks 中找到第一个包含有效 tool_calls 的 chunk
                        # 修复：最后一个 chunk 可能没有 tool_calls
                        response_with_tool_calls = None
                        for chunk in full_response_chunks:
                            if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                                # 检查是否有有效的 tool_calls（非空名称）
                                valid_calls = [tc for tc in chunk.tool_calls if tc.get('name')]
                                if valid_calls:
                                    response_with_tool_calls = chunk
                                    logger.debug(f"[DEBUG] Found chunk with tool_calls: {len(valid_calls)} calls")
                                    break

                        # 如果没找到有 tool_calls 的 chunk，使用最后一个 chunk
                        if response_with_tool_calls is None:
                            response_with_tool_calls = full_response_chunks[-1]
                            logger.debug(f"[DEBUG] No chunk with tool_calls found, using last chunk")

                        response = response_with_tool_calls

                        # 确保包含完整的 content（合并所有文本）
                        if all_content:
                            from langchain_core.messages import AIMessage
                            merged_content = ''.join(all_content)

                            # 获取 tool_calls（优先使用找到的有 tool_calls 的 chunk）
                            tool_calls_to_use = getattr(response, 'tool_calls', [])

                            # 如果 tool_calls 的 args 是空的，尝试从 tool_call_chunks 组装
                            if tool_calls_to_use:
                                for i, tc in enumerate(tool_calls_to_use):
                                    if not tc.get('args') or tc.get('args') == {}:
                                        # 从 tool_call_chunks 组装 args
                                        args_parts = []
                                        for chunk in full_response_chunks:
                                            if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                                                for tcc in chunk.tool_call_chunks:
                                                    if tcc.get('index') == i and tcc.get('args'):
                                                        args_parts.append(tcc['args'])

                                        if args_parts:
                                            args_str = ''.join(args_parts)
                                            try:
                                                import json
                                                parsed_args = json.loads(args_str)
                                                tool_calls_to_use[i]['args'] = parsed_args
                                                logger.debug(f"[DEBUG] Assembled args for tool {i}: {parsed_args}")
                                            except json.JSONDecodeError as e:
                                                logger.warning(f"[DEBUG] Failed to parse args for tool {i}: {e}")

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

                # === 智能停止检查 ===
                # 检查是否应该停止工具调用（简单问候、冗余检测等）
                for tool_call in tool_calls:
                    tool_name = tool_call.get('name', '')
                    tool_args = tool_call.get('args', {})

                    should_stop, stop_reason = should_stop_tool_calling(
                        settings=settings,
                        round_count=round_count,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        user_message=messages[-1].get('content', '') if messages else '',
                        current_round_time=llm_duration
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
                        # 追踪并发工具调用结果（供反思评估使用）
                        if event.get("type") == "tool_output":
                            _last_tool_calls.append({
                                "name": event.get("tool_name", "unknown"),
                                "success": event.get("status") == "success",
                                "duration": event.get("duration", 0.0),
                            })
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

                        try:
                            # Guard against empty tool arguments (LLM sometimes sends {} for python_repl etc.)
                            if not tool_args or tool_args == {}:
                                raise ValueError(
                                    f"Tool '{tool_name}' requires arguments but received none. "
                                    f"Please provide the required parameters."
                                )
                            tool_start = time.time()
                            tool_output = await self._aexecute_tool(tool_name, tool_args)
                            tool_duration = time.time() - tool_start
                            tool_output_str, gen_images = embed_output_images_v2(str(tool_output))

                            logger.info(f"[Round {round_count + 1}] Tool {tool_name} completed, {len(gen_images)} image(s)")

                            _last_tool_calls.append({
                                "name": tool_name,
                                "success": True,
                                "duration": tool_duration,
                            })

                            yield {
                                "type": "tool_output",
                                "tool_name": tool_name,
                                "output": tool_output_str,
                                "status": "success",
                                "generated_images": gen_images if gen_images else None,
                            }
                        except Exception as e:
                            logger.error(f"[Round {round_count + 1}] Tool {tool_name} failed: {e}")

                            _last_tool_calls.append({
                                "name": tool_name,
                                "success": False,
                                "duration": 0.0,
                            })

                            yield {
                                "type": "tool_output",
                                "tool_name": tool_name,
                                "output": str(e),
                                "status": "error",
                            }

                        # Add tool result to conversation
                        # Strip base64 data URIs for LLM context — LLM doesn't need raw image data
                        llm_facing_output = tool_output_str
                        if "data:image/" in llm_facing_output:
                            import re
                            llm_facing_output = re.sub(
                                r'!\[[^\]]*\]\(data:image/[^)]{100,}\)',
                                '[图片已生成]',
                                llm_facing_output
                            )
                        lc_messages.append(ToolMessage(
                            content=llm_facing_output,
                            tool_call_id=tool_id
                        ))
                # === Phase 2 并发执行结束 ===

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

            # === TCA post-execution data recording ===
            try:
                if getattr(settings, "enable_tca", False):
                    from app.core.meta_policy.tca_helpers import record_tca_episode

                    user_msg = messages[-1].get("content", "") if messages else ""
                    record_tca_episode(
                        query=user_msg,
                        tool_calls=_last_tool_calls,
                        plan_steps=round_count,
                        task_completed=round_count < max_tool_rounds,
                    )
            except Exception as e:
                logger.debug(f"[TCA] Agent post-execution recording failed: {e}")

            # === Meta Policy post-execution data recording ===
            try:
                if getattr(settings, "enable_meta_policy", False):
                    from app.core.meta_policy.meta_policy_helpers import record_meta_policy_episode

                    user_msg = messages[-1].get("content", "") if messages else ""
                    record_meta_policy_episode(
                        query=user_msg,
                        tool_calls=_last_tool_calls,
                        plan_steps=round_count,
                        task_completed=round_count < max_tool_rounds,
                    )
            except Exception as e:
                logger.debug(f"[MetaPolicy] Agent post-execution recording failed: {e}")

            # === 反思评估（Phase 3.2）===
            if getattr(settings, "enable_agent_reflection", False):
                try:
                    from app.core.reflection.helpers import evaluate_and_correct

                    # 收集完整的 agent 输出
                    agent_output = ""
                    user_query = messages[-1].get("content", "") if messages else ""

                    # 从最近的 content_delta 提取输出（简化方式：用 LLM 最后响应）
                    if hasattr(locals().get("response"), "content"):
                        agent_output = response.content or ""

                    if agent_output:
                        result = await evaluate_and_correct(
                            user_query=user_query,
                            agent_output=agent_output,
                            tool_calls=_last_tool_calls,
                            execution_time=total_duration,
                            execution_mode="normal",
                        )
                        logger.info(
                            f"[reflection] Agent reflection: quality={result.quality_score:.1f}, "
                            f"should_correct={result.should_correct}"
                        )
                        if result.should_correct and result.correction:
                            yield {
                                "type": "self_correction",
                                "correction": result.correction,
                                "quality_score": result.quality_score,
                            }
                except Exception as e:
                    logger.warning(f"[reflection] Post-execution reflection failed: {e}")

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
            result_str, gen_images = embed_output_images_v2(str(result))
            duration = time.time() - start

            logger.info(f"Tool {tool_name} completed in {duration:.2f}s, {len(gen_images)} image(s)")

            return {
                "output": result_str,
                "generated_images": gen_images if gen_images else None,
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

            # Emit tool output event (with generated_images from v2)
            output_str = str(output)
            gen_images = result.get("generated_images")
            if gen_images:
                logger.info("[Agent] %s generated %d image(s)", tool_name, len(gen_images))
            yield {
                "type": "tool_output",
                "tool_name": tool_name,
                "output": output_str,
                "status": status,
                "duration": duration,
                "generated_images": gen_images,
            }

            # Add result to conversation history (strip base64 for LLM)
            llm_output = output_str
            if "data:image/" in llm_output:
                import re
                llm_output = re.sub(
                    r'!\[[^\]]*\]\(data:image/[^)]{100,}\)',
                    '[图片已生成]',
                    llm_output
                )
            lc_messages.append(
                ToolMessage(
                    content=llm_output,
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
