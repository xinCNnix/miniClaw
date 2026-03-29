"""
Stream coordinator for event-driven streaming response system.

This module coordinates all streaming components:
- ChunkParser: Parses LLM chunks into events
- EventBus: Manages event distribution
- ToolExecutor: Executes tools concurrently
"""

import asyncio
import json
import logging
from typing import List, Any, AsyncIterator, Optional, Callable, Awaitable, Dict

from langchain_core.tools import BaseTool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage

from app.core.streaming.events import StreamEvent, StreamEventType
from app.core.streaming.chunk_parser import ChunkParser
from app.core.streaming.event_bus import EventBus
from app.core.streaming.tool_executor import ToolExecutor
from app.core.smart_stopping import (
    should_stop_before_execution,
    should_stop_after_execution,
    SmartToolStopping,
)
from app.core.streaming.error_handler import ErrorHandler, FatalError
from app.config import Settings

logger = logging.getLogger(__name__)


def _repair_truncated_json(args_str: str) -> dict | None:
    """
    Attempt to repair truncated JSON from incomplete streaming tool_call_chunks.

    LLM streaming may drop the final chunk containing closing characters,
    leaving unterminated strings or unclosed brackets.

    Returns:
        Parsed dict if repair succeeds, None otherwise.
    """
    s = args_str.rstrip()
    if not s:
        return None

    try:
        # Check if the issue is just an unclosed string (most common case)
        # Find the last complete key-value pair and truncate there
        quote_count = 0
        in_string = False
        escape_next = False
        last_complete_pos = -1

        for idx, ch in enumerate(s):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string:
                if ch == ',':
                    last_complete_pos = idx
                elif ch in ':{}[]':
                    last_complete_pos = idx

        if not in_string:
            # Not a string issue, try bracket completion
            brace_stack = []
            for ch in s:
                if ch in '{[':
                    brace_stack.append(ch)
                elif ch in '}]':
                    if brace_stack:
                        brace_stack.pop()
            # Close unclosed brackets
            while brace_stack:
                opener = brace_stack.pop()
                s += '}' if opener == '{' else ']'
            return json.loads(s)

        # We are inside a string - find the last "key": "value pair before truncation
        # Strategy: walk backwards to find the last comma or opening brace that starts a key-value
        repair = s

        # Find the key this truncated value belongs to
        # Look backwards for pattern: "key": "truncated_value
        last_colon = repair.rfind(':')
        if last_colon > 0:
            # Found the colon, now close the string and remove the incomplete value
            before_value = repair[:last_colon + 1].rstrip()
            repair = before_value

            # Close the string that was being written
            repair += ' ""'

            # Find if there's a comma before this key to know if we need a trailing comma
            before_key = repair[:repair.rfind('"')]
            # Look for comma between previous value and this key
            comma_search = before_key.rstrip()
            if comma_search and comma_search[-1] != ',' and comma_search[-1] != '{':
                # We need to add comma before the empty value
                repair = repair[:repair.rfind('"')]
                repair = comma_search.rstrip() + ', ""'
                # Re-add the closing
                pass  # already handled

        # Now close any unclosed brackets
        brace_stack = []
        in_str = False
        esc = False
        for ch in repair:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch in '{[':
                    brace_stack.append(ch)
                elif ch in '}]':
                    if brace_stack:
                        brace_stack.pop()

        while brace_stack:
            opener = brace_stack.pop()
            repair += '}' if opener == '{' else ']'

        try:
            result = json.loads(repair)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Fallback: simpler approach - just close string and brackets
        s += '"'
        brace_stack = []
        in_str = False
        esc = False
        for ch in s:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch in '{[':
                    brace_stack.append(ch)
                elif ch in '}]':
                    if brace_stack:
                        brace_stack.pop()
        while brace_stack:
            opener = brace_stack.pop()
            s += '}' if opener == '{' else ']'
        result = json.loads(s)
        if isinstance(result, dict):
            return result

    except (json.JSONDecodeError, IndexError, ValueError):
        return None


class StreamCoordinator:
    """
    Main coordinator for event-driven streaming responses.

    This coordinator orchestrates all components of the streaming system
    and replaces the complex astream logic in agent.py.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: List[BaseTool],
        max_rounds: int = 10,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize the stream coordinator.

        Args:
            llm: LLM instance with tools bound
            tools: List of available tools
            max_rounds: Maximum rounds of tool calling
            settings: Application settings (optional)
        """

        # Initialize error handler
        max_consecutive = getattr(settings, 'max_consecutive_tool_errors', 3) if settings else 3
        max_total = getattr(settings, 'max_total_tool_errors', 10) if settings else 10
        self.error_handler = ErrorHandler(
            max_consecutive_errors=max_consecutive,
            max_total_errors=max_total
        )

        # Initialize basic properties
        self.llm = llm
        self.tools = tools
        self.max_rounds = max_rounds
        self.settings = settings

        # Initialize components
        self.event_bus = EventBus()
        self.chunk_parser = ChunkParser()
        self.tool_executor = ToolExecutor(self.event_bus, tools)

        # Reflection callback support
        self._on_reflection_callback: Optional[Callable[[str], Awaitable[None]]] = None
        self._on_thought_complete_callback: Optional[Callable[[Dict], Awaitable[None]]] = None

        # Tool call history for similarity-based redundancy detection
        self._tool_call_history: list[dict] = []
        self._stopper: Optional[SmartToolStopping] = None

    def set_reflection_callback(
        self,
        callback: Callable[[str], Awaitable[None]]
    ) -> None:
        """
        Set reflection callback for ToT integration.

        Args:
            callback: Async callback function that receives reflection text
        """
        self._on_reflection_callback = callback

    def set_thought_complete_callback(
        self,
        callback: Callable[[Dict], Awaitable[None]]
    ) -> None:
        """
        Set thought complete callback for ToT integration.

        Args:
            callback: Async callback function that receives thought data
        """
        self._on_thought_complete_callback = callback

    async def astream(
        self,
        messages: List[Dict[str, Any]],
        callbacks: list | None = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream agent responses using event-driven architecture.

        This method replaces the complex astream logic in agent.py with
        a cleaner, event-driven approach.

        Args:
            messages: List of message dicts with 'role' and 'content'
            callbacks: Optional list of callback handlers (not currently used)

        Yields:
            Event dicts compatible with SSE format
        """
        # Start event bus
        await self.event_bus.start()

        # Create a queue to collect events from event bus
        event_queue: asyncio.Queue[Dict] = asyncio.Queue()

        # Subscribe to tool execution events
        async def tool_execution_handler(event: StreamEvent):
            """Yield tool execution events to the queue."""
            await event_queue.put(event.to_sse_dict())

        self.event_bus.subscribe(StreamEventType.TOOL_EXECUTION_START, tool_execution_handler)
        self.event_bus.subscribe(StreamEventType.TOOL_EXECUTION_COMPLETE, tool_execution_handler)
        self.event_bus.subscribe(StreamEventType.TOOL_EXECUTION_ERROR, tool_execution_handler)

        try:
            # Emit thinking start event
            await self.event_bus.publish(StreamEvent(
                type=StreamEventType.THINKING_START,
                data={}
            ))

            # Yield thinking start immediately
            yield {"type": "thinking_start"}

            logger.info("=== StreamCoordinator astream START ===")
            logger.debug(f"Messages count: {len(messages)}")

            # Multi-round tool calling loop
            round_count = 0
            lc_messages = self._convert_messages(messages)

            while round_count < self.max_rounds:
                round_start_time = asyncio.get_event_loop().time()
                logger.info(f"[Round {round_count + 1}] Starting LLM call")
                logger.info(f"[Round {round_count + 1}] Messages in context: {len(lc_messages)}")

                # Stream LLM response and parse chunks
                llm_response = None
                tool_calls_found = False
                full_response_chunks = []  # Collect all chunks for parameter assembly
                tool_call_chunks_list = []  # Collect tool_call_chunks for parameter assembly
                chunk_count = 0  # Track total chunks received
                text_delta_count = 0  # Track text delta chunks
                streaming_start_time = asyncio.get_event_loop().time()

                async for chunk in self.llm.astream(lc_messages):
                    chunk_count += 1
                    streaming_elapsed = asyncio.get_event_loop().time() - streaming_start_time

                    # Log chunk structure (INFO level for first few chunks)
                    if chunk_count <= 3:
                        logger.info(f"[Round {round_count + 1}] Chunk #{chunk_count} (elapsed: {streaming_elapsed:.2f}s)")
                        logger.info(f"[Round {round_count + 1}] Chunk type: {type(chunk).__name__}")
                        logger.info(f"[Round {round_count + 1}] Chunk attributes: {dir(chunk)}")
                        if hasattr(chunk, 'content'):
                            logger.info(f"[Round {round_count + 1}] Content length: {len(str(chunk.content)) if chunk.content else 0}")
                        if hasattr(chunk, 'tool_calls'):
                            logger.info(f"[Round {round_count + 1}] Has tool_calls: {hasattr(chunk, 'tool_calls')}, value: {chunk.tool_calls if hasattr(chunk, 'tool_calls') else 'N/A'}")
                        if hasattr(chunk, 'tool_call_chunks'):
                            logger.info(f"[Round {round_count + 1}] Has tool_call_chunks: {hasattr(chunk, 'tool_call_chunks')}, count: {len(chunk.tool_call_chunks) if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks else 0}")

                    # Collect all chunks
                    full_response_chunks.append(chunk)

                    # Parse chunk into events
                    events = self.chunk_parser.feed(chunk)
                    if chunk_count <= 3 or len(events) > 0:
                        logger.info(f"[Round {round_count + 1}] Chunk #{chunk_count}: ChunkParser returned {len(events)} events")

                    # Publish all events to bus and yield text deltas immediately
                    for event in events:
                        await self.event_bus.publish(event)
                        # Only yield text deltas immediately (tool calls will be yielded later)
                        if event.type == StreamEventType.TEXT_DELTA:
                            text_delta_count += 1
                            if text_delta_count <= 5:  # Log first 5 text deltas
                                logger.info(f"[Round {round_count + 1}] Text delta #{text_delta_count}: {event.data.get('content', '')[:50]}")
                            yield event.to_sse_dict()

                    # Collect tool_call_chunks for parameter assembly
                    if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                        # Log first few chunks with full structure
                        if len(tool_call_chunks_list) < 3:
                            for idx, tcc in enumerate(chunk.tool_call_chunks):
                                logger.debug(f"===== tool_call_chunk #{len(tool_call_chunks_list) + idx} =====")
                                logger.debug(f"Type: {type(tcc)}")
                                logger.debug(f"Content: {repr(tcc)}")
                                if isinstance(tcc, dict):
                                    logger.debug(f"Dict keys: {list(tcc.keys())}")
                                    logger.debug(f"name={tcc.get('name')}, args={tcc.get('args')}, id={tcc.get('id')}, index={tcc.get('index')}")
                                logger.debug(f"======================================")
                        tool_call_chunks_list.extend(chunk.tool_call_chunks)
                        logger.debug(f"Collected tool_call_chunks: {len(chunk.tool_call_chunks)} chunks, total={len(tool_call_chunks_list)}")

                    # Check if this chunk has tool calls (but don't yield yet)
                    if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                        tool_calls_found = True
                        logger.debug(f"Found chunk with tool_calls: {len(chunk.tool_calls)} tools")
                        # Keep the last chunk that has tool_calls
                        llm_response = chunk

                # Streaming completed - log summary
                streaming_total_time = asyncio.get_event_loop().time() - streaming_start_time
                logger.info(f"[Round {round_count + 1}] Streaming completed:")
                logger.info(f"  - Total chunks: {chunk_count}")
                logger.info(f"  - Text deltas: {text_delta_count}")
                logger.info(f"  - Tool call chunks: {len(tool_call_chunks_list)}")
                logger.info(f"  - Streaming time: {streaming_total_time:.2f}s")
                logger.info(f"  - Tool calls found: {tool_calls_found}")
                logger.info(f"  - llm_response set: {llm_response is not None}")

                if llm_response is None:
                    logger.warning(f"[Round {round_count + 1}] ⚠️ llm_response is None after streaming!")
                    logger.warning(f"[Round {round_count + 1}] This suggests LLM returned empty response or no tool calls")
                elif not hasattr(llm_response, 'tool_calls'):
                    logger.warning(f"[Round {round_count + 1}] ⚠️ llm_response doesn't have tool_calls attribute!")
                    logger.warning(f"[Round {round_count + 1}] llm_response type: {type(llm_response)}")
                    logger.warning(f"[Round {round_count + 1}] llm_response attributes: {dir(llm_response)}")

                # === Parameter Assembly from tool_call_chunks ===
                # When tool_calls.args is empty, assemble from tool_call_chunks
                if llm_response and hasattr(llm_response, 'tool_calls') and llm_response.tool_calls:
                    tool_calls_to_assemble = list(llm_response.tool_calls)
                    logger.info(f"[Round {round_count + 1}] ========== Parameter Assembly ==========")
                    logger.info(f"[Round {round_count + 1}] tool_call_chunks collected: {len(tool_call_chunks_list)}")
                    logger.info(f"[Round {round_count + 1}] tool_calls to assemble: {len(tool_calls_to_assemble)}")

                    # Log the ORIGINAL tool_calls structure
                    for i, tc in enumerate(tool_calls_to_assemble):
                        logger.debug(f"ORIGINAL Tool {i}:")
                        logger.debug(f"  Type: {type(tc)}")
                        logger.debug(f"  Repr: {repr(tc)}")
                        if isinstance(tc, dict):
                            logger.debug(f"  Dict keys: {list(tc.keys())}")
                            logger.debug(f"  name={repr(tc.get('name'))}, args={repr(tc.get('args'))}, id={repr(tc.get('id'))}")
                        else:
                            logger.debug(f"  Has name attr: {hasattr(tc, 'name')}")
                            logger.debug(f"  Has args attr: {hasattr(tc, 'args')}")
                            logger.debug(f"  Has id attr: {hasattr(tc, 'id')}")
                            if hasattr(tc, 'name'):
                                logger.debug(f"  name={repr(tc.name)}")
                            if hasattr(tc, 'args'):
                                logger.debug(f"  args={repr(tc.args)}")
                            if hasattr(tc, 'id'):
                                logger.debug(f"  id={repr(tc.id)}")

                    for i, tc in enumerate(tool_calls_to_assemble):
                        tc_name = tc.get('name', '') if isinstance(tc, dict) else (getattr(tc, 'name', '') if hasattr(tc, 'name') else '')
                        tc_args = tc.get('args') if isinstance(tc, dict) else (getattr(tc, 'args', None) if hasattr(tc, 'args') else None)
                        logger.debug(f"Tool {i}: name={tc_name}, args={tc_args}, has_args={bool(tc_args and tc_args != {})}")

                        # Assemble BOTH name and args from tool_call_chunks if needed
                        # Note: tool_call_chunks may contain name in some chunks and args in others
                        if (not tc_name or not tc_args or tc_args == {}):
                            logger.debug(f"Tool {i} has incomplete info, assembling from tool_call_chunks...")
                            logger.debug(f">>>>> NEW ID EXTRACTION CODE LOADED <<<<<")
                            args_parts = []
                            name_from_chunks = None
                            id_from_chunks = None

                            # Collect BOTH name, args and id from tool_call_chunks with matching index
                            for tcc in tool_call_chunks_list:
                                # Log the first chunk for debugging
                                if i == 0 and len(args_parts) == 0:
                                    logger.debug(f"===== Tool call chunk analysis =====")
                                    logger.debug(f"Type: {type(tcc)}")
                                    logger.debug(f"Repr: {repr(tcc)}")
                                    if hasattr(tcc, '__dict__'):
                                        logger.debug(f"__dict__: {tcc.__dict__}")
                                    try:
                                        logger.debug(f"Keys: {list(tcc.keys()) if isinstance(tcc, dict) else 'N/A'}")
                                    except:
                                        pass
                                    logger.debug(f"=====================================")

                                tcc_index = tcc.get('index') if isinstance(tcc, dict) else getattr(tcc, 'index', None)
                                if tcc_index == i:
                                    # Collect name if present (use dict access for consistency)
                                    tcc_name = tcc.get('name') if isinstance(tcc, dict) else (getattr(tcc, 'name', None) if hasattr(tcc, 'name') else None)
                                    if tcc_name and not name_from_chunks:  # Only set if not already found
                                        name_from_chunks = tcc_name
                                        logger.debug(f"  Found name in tool_call_chunk: {name_from_chunks}")

                                    # Collect id if present
                                    tcc_id = tcc.get('id') if isinstance(tcc, dict) else (getattr(tcc, 'id', None) if hasattr(tcc, 'id') else None)
                                    if tcc_id and not id_from_chunks:  # Only set if not already found
                                        id_from_chunks = tcc_id
                                        logger.debug(f"  Found id in tool_call_chunk: {id_from_chunks}")

                                    # Collect args if present
                                    tcc_args = tcc.get('args') if isinstance(tcc, dict) else None
                                    if not tcc_args and hasattr(tcc, 'get'):
                                        tcc_args = tcc.get('args')
                                    if tcc_args:
                                        args_parts.append(tcc_args)
                                        logger.debug(f"  Found args in tool_call_chunk: {str(tcc_args)[:50]}")

                            # Update name if found in chunks
                            if name_from_chunks and not tc_name:
                                tool_calls_to_assemble[i]['name'] = name_from_chunks
                                logger.debug(f"✅ Tool {i} name updated: {name_from_chunks}")

                            # Update id if found in chunks
                            if id_from_chunks and not tool_calls_to_assemble[i].get('id'):
                                tool_calls_to_assemble[i]['id'] = id_from_chunks
                                logger.debug(f"✅ Tool {i} id updated: {id_from_chunks}")

                            # Assemble args if found
                            logger.debug(f"Tool {i} collected {len(args_parts)} args parts")
                            if args_parts:
                                args_str = ''.join(args_parts)
                                logger.debug(f"Tool {i} assembled args string (len={len(args_str)}): {args_str[:200]}")
                                try:
                                    import json
                                    parsed_args = json.loads(args_str)
                                    # Update the tool_call in llm_response
                                    tool_calls_to_assemble[i]['args'] = parsed_args
                                    logger.debug(f"✅ Tool {i} args parsed: {parsed_args}")
                                except json.JSONDecodeError as e:
                                    logger.warning(f"[Round {round_count + 1}] Tool {i} JSON parse failed: {e}, attempting repair...")
                                    parsed_args = _repair_truncated_json(args_str)
                                    if parsed_args is not None:
                                        tool_calls_to_assemble[i]['args'] = parsed_args
                                        logger.info(f"[Round {round_count + 1}] ✅ Tool {i} JSON repaired, keys: {list(parsed_args.keys())}")
                                    else:
                                        logger.error(f"[Round {round_count + 1}] ❌ Tool {i} JSON repair failed, skipping")

                    # Update llm_response.tool_calls with assembled args
                    llm_response.tool_calls = tool_calls_to_assemble
                    logger.debug(f"========== Parameter assembly complete ==========")

                    # === Validate tool calls before yielding ===
                    validated_tool_calls = []
                    logger.info(f"[Round {round_count + 1}] Validating {len(llm_response.tool_calls)} tool calls...")

                    for i, tc in enumerate(llm_response.tool_calls):
                        tc_name = tc.get('name', '')
                        tc_args = tc.get('args', {})

                        logger.info(f"[Round {round_count + 1}] Tool call #{i}: name='{tc_name}', args_keys={list(tc_args.keys()) if isinstance(tc_args, dict) else 'N/A'}")

                        # Skip tool calls with empty arguments
                        if not tc_name or tc_args == {}:
                            logger.warning(f"[Round {round_count + 1}] Skipping tool call #{i}: empty name or args")
                            continue

                        # Ensure args is not empty dict
                        if not tc_args:
                            logger.warning(f"[Round {round_count + 1}] Tool '{tc_name}' has empty args, skipping")
                            continue

                        # Validate required fields against tool schema
                        required_ok = self._validate_required_fields(tc_name, tc_args)
                        if not required_ok:
                            logger.warning(f"[Round {round_count + 1}] Skipping tool call #{i} '{tc_name}': missing required fields in args")
                            continue

                        validated_tool_calls.append(tc)
                        logger.info(f"[Round {round_count + 1}] Tool call #{i} '{tc_name}' validated")

                    logger.info(f"[Round {round_count + 1}] Validated {len(validated_tool_calls)}/{len(llm_response.tool_calls)} tool calls")

                    if not validated_tool_calls:
                        logger.warning(f"[Round {round_count + 1}] ⚠️ No valid tool calls after validation, adding error context and continuing")
                        # Add tool result message so LLM knows the call failed and can retry
                        lc_messages.append({
                            "role": "tool",
                            "tool_call_id": llm_response.tool_calls[0].get('id', 'unknown'),
                            "content": "Error: Tool call arguments were invalid (JSON parse failure). Please retry with properly formatted arguments."
                        })
                        continue

                    # Replace with validated tool calls
                    llm_response.tool_calls = validated_tool_calls

                # Yield tool call events (once, after streaming completes)
                if tool_calls_found and llm_response and hasattr(llm_response, 'tool_calls') and llm_response.tool_calls:
                    logger.info(f"[Round {round_count + 1}] Yielding {len(llm_response.tool_calls)} tool_call events")
                    for i, tc in enumerate(llm_response.tool_calls):
                        logger.info(f"[Round {round_count + 1}] Yielding tool call #{i}: {tc.get('name')}")
                        # Use StreamEvent to ensure proper type conversion to frontend format
                        event = StreamEvent(
                            type=StreamEventType.TOOL_CALL_START,
                            data={
                                "tool_calls": [{  # Frontend expects array format
                                    "id": tc.get('id', ''),
                                    "name": tc.get('name', ''),
                                    "arguments": tc.get('args', {})  # Frontend expects "arguments" not "args"
                                }]
                            }
                        )
                        yield event.to_sse_dict()  # Converts "tool_call_start" to "tool_call"

                # If no tool calls found in chunks, use last chunk
                if llm_response is None:
                    # Get final response without tool calls
                    llm_response = await self.llm.ainvoke(lc_messages)

                logger.info(f"[Round {round_count + 1}] LLM response received")

                # Check if LLM wants to call tools
                if not hasattr(llm_response, 'tool_calls') or not llm_response.tool_calls:
                    logger.info(f"[Round {round_count + 1}] No tool calls, returning final response")
                    break

                # Has tool calls - execute them
                tool_calls = llm_response.tool_calls
                logger.info(f"[Round {round_count + 1}] Tool calls requested: {len(tool_calls)}")

                # === Smart stopping check (before execution) ===
                if self.settings:
                    # 首次创建共享的 stopper 实例（复用 _tool_call_history）
                    if self._stopper is None:
                        self._stopper = SmartToolStopping(
                            evaluation_interval=self.settings.sufficiency_evaluation_interval,
                            hard_limit=self.settings.max_tool_rounds,
                            enable=True,
                            similarity_threshold=getattr(self.settings, 'similarity_threshold', 0.8),
                            similarity_block_threshold=getattr(self.settings, 'similarity_block_threshold', 0.95),
                            similarity_check_limit=getattr(self.settings, 'similarity_check_limit', 3),
                            recent_tool_calls=self._tool_call_history,
                        )

                    for tool_call in tool_calls:
                        tool_name = tool_call.get('name', '')
                        tool_args = tool_call.get('args', {})

                        # 记录工具调用到历史
                        self._stopper.record_tool_call(tool_name, tool_args)

                        # 基本智能停止检查（问候检测等）
                        should_stop, stop_reason = should_stop_before_execution(
                            settings=self.settings,
                            round_count=round_count,
                            tool_name=tool_name,
                            tool_args=tool_args,
                            user_message=messages[-1].get('content', '') if messages else '',
                            tool_call_history=self._tool_call_history,
                        )

                        if should_stop:
                            logger.warning(f"[SMART_STOP] {stop_reason}")
                            try:
                                final_response = await self.llm.ainvoke(lc_messages)
                                if hasattr(final_response, 'content') and final_response.content:
                                    yield {
                                        "type": "content_delta",
                                        "content": final_response.content
                                    }
                            except Exception as e:
                                logger.error(f"Error emitting final response: {e}")
                            return

                        # 内容相似度冗余检测
                        should_block, reason, similarity = self._stopper.detect_redundant_tool_call(
                            tool_name, tool_args
                        )
                        if should_block:
                            yield {
                                "type": "redundancy_blocked",
                                "reason": reason,
                                "similarity": similarity,
                            }
                            logger.warning(f"[REDUNDANCY] 已阻止重复工具调用: {reason}")
                            return
                        if reason:
                            # 中高相似度：发出警告但不阻止
                            yield {
                                "type": "redundancy_warning",
                                "reason": reason,
                                "similarity": similarity,
                            }
                            logger.info(f"[REDUNDANCY] 相似度警告: {reason}")

                # Add assistant message to conversation
                lc_messages.append(llm_response)

                # Filter valid tool calls
                valid_tool_calls = []
                for idx, tool_call in enumerate(tool_calls):
                    tool_name = tool_call.get('name', '')
                    if not tool_name:
                        logger.warning(f"Skipping tool call with empty name")
                        continue

                    # Generate ID if missing (some LLM providers don't return tool call IDs)
                    tool_id = tool_call.get('id', '')
                    if not tool_id:
                        import uuid
                        tool_id = f"call_{uuid.uuid4().hex[:8]}"
                        logger.warning(f"Tool call missing ID, generated: {tool_id}")

                    valid_tool_calls.append({
                        'id': tool_id,
                        'name': tool_name,
                        'args': tool_call.get('args', {})
                    })

                # === Execute tools (concurrent or serial) ===
                use_concurrent = self.settings.enable_parallel_tool_execution if self.settings else False

                if use_concurrent and len(valid_tool_calls) > 1:
                    logger.info(f"[Round {round_count + 1}] Using CONCURRENT execution")
                    results = await self.tool_executor.execute_tool_calls_concurrently(valid_tool_calls)
                else:
                    logger.info(f"[Round {round_count + 1}] Using SERIAL execution")
                    results = []
                    for tc in valid_tool_calls:
                        try:
                            result = await self.tool_executor.execute_tool_call(
                                tool_id=tc['id'],
                                tool_name=tc['name'],
                                tool_args=tc['args']
                            )
                            results.append(result)
                            # Reset consecutive errors on success
                            self.error_handler.reset_consecutive_errors()

                        except Exception as e:
                            # Handle error with error handler
                            error_result = await self.error_handler.handle_tool_error(
                                tool_name=tc['name'],
                                error=e,
                                tool_args=tc['args']
                            )
                            results.append(error_result)

                            # Check for fatal error condition
                            fatal_error = await self.error_handler.check_fatal_error()
                            if fatal_error:
                                # Handle fatal error and terminate
                                async for event in self._handle_fatal_error(fatal_error):
                                    yield event
                                return  # Terminate execution

                # Add tool results to conversation
                for i, (tc, result) in enumerate(zip(valid_tool_calls, results)):
                    lc_messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tc['id']
                    ))

                # Round completion summary
                round_end_time = asyncio.get_event_loop().time()
                round_duration = round_end_time - round_start_time
                logger.info(f"[Round {round_count + 1}] Round completed in {round_duration:.2f}s")

                # Wait for event bus to process all events
                while self.event_bus.queue_size > 0:
                    await asyncio.sleep(0.001)

                # Drain event queue and yield tool execution events
                while not event_queue.empty():
                    try:
                        stream_event = event_queue.get_nowait()
                        # Convert StreamEvent to SSE dict
                        if hasattr(stream_event, 'to_sse_dict'):
                            yield stream_event.to_sse_dict()
                        else:
                            # Fallback for raw dict events
                            yield stream_event
                    except asyncio.QueueEmpty:
                        break

                # Increment round count
                round_count += 1

                # === Smart stopping check (after execution) ===
                if self.settings and self.settings.enable_smart_stopping:
                    should_stop, stop_reason = await should_stop_after_execution(
                        settings=self.settings,
                        round_count=round_count,
                        user_message=messages[-1].get('content', '') if messages else '',
                        conversation_messages=lc_messages,
                        llm=self.llm
                    )

                    if should_stop:
                        logger.info(f"[SMART_STOP] {stop_reason}")
                        try:
                            final_response = await self.llm.ainvoke(lc_messages)
                            if hasattr(final_response, 'content') and final_response.content:
                                yield {
                                    "type": "content_delta",
                                    "content": final_response.content
                                }
                        except Exception as e:
                            logger.error(f"Error emitting final response: {e}")
                        return

            # Emit final response
            try:
                logger.info("=== Emitting final text response ===")
                final_response = await self.llm.ainvoke(lc_messages)
                if hasattr(final_response, 'content') and final_response.content:
                    logger.info(f"Final response length: {len(final_response.content)} chars")
                    yield {
                        "type": "content_delta",
                        "content": final_response.content
                    }
                else:
                    logger.warning("Final response has no content")
            except Exception as e:
                logger.error(f"Error emitting final response: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"StreamCoordinator error: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")

            # Log context information
            logger.error(f"Context at error:")
            logger.error(f"  - Round: {round_count + 1}/{self.max_rounds}")
            logger.error(f"  - llm_response is None: {llm_response is None}")
            logger.error(f"  - tool_calls_found: {tool_calls_found}")
            logger.error(f"  - chunks received: {chunk_count}")
            logger.error(f"  - text deltas: {text_delta_count}")

            error_event = StreamEvent(
                type=StreamEventType.ERROR,
                data={"error": str(e)}
            )
            await self.event_bus.publish(error_event)
            yield error_event.to_sse_dict()

        finally:
            # Cleanup
            self.event_bus.unsubscribe(StreamEventType.TOOL_EXECUTION_START, tool_execution_handler)
            self.event_bus.unsubscribe(StreamEventType.TOOL_EXECUTION_COMPLETE, tool_execution_handler)
            self.event_bus.unsubscribe(StreamEventType.TOOL_EXECUTION_ERROR, tool_execution_handler)
            await self.event_bus.stop()

            # Emit done event
            done_event = StreamEvent(
                type=StreamEventType.DONE,
                data={}
            )
            await self.event_bus.publish(done_event)
            yield done_event.to_sse_dict()

    async def _emit_final_response(self, lc_messages: List[Any]) -> None:
        """
        Emit final text response after tool execution completes.

        Args:
            lc_messages: LangChain message list
        """
        try:
            final_response = await self.llm.ainvoke(lc_messages)
            if hasattr(final_response, 'content') and final_response.content:
                event = StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    data={"content": final_response.content}
                )
                await self.event_bus.publish(event)
                # Note: This won't yield directly, caller should handle if needed
        except Exception as e:
            logger.error(f"Error emitting final response: {e}")

    
    async def _handle_fatal_error(self, error: FatalError):
        """
        Handle fatal error and terminate execution

        Args:
            error: FatalError object
        """
        logger.error(f"FATAL ERROR: {error.message}")
        logger.error(f"Details: {error.details}")

        # Send error event to frontend
        error_event = StreamEvent(
            type=StreamEventType.ERROR,
            data=error.to_sse_dict()["data"]
        )
        await self.event_bus.publish(error_event)

        # Yield fatal_error event
        yield error.to_sse_dict()

        # Send done event with error status
        done_event = StreamEvent(
            type=StreamEventType.DONE,
            data={"status": "error", "error": error.message}
        )
        await self.event_bus.publish(done_event)
        yield done_event.to_sse_dict()

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Any]:
        """
        Convert message dicts to LangChain message format.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            List of LangChain message objects
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        lc_messages = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content', '')

            if role == 'system':
                lc_messages.append(SystemMessage(content=content))
            elif role == 'user':
                lc_messages.append(HumanMessage(content=content))
            elif role == 'assistant':
                lc_messages.append(AIMessage(content=content))
            # Tool messages are added during execution

        return lc_messages

    def _validate_required_fields(self, tool_name: str, tool_args: dict) -> bool:
        """
        Validate that all required fields from tool schema are present in args.

        Args:
            tool_name: Name of the tool to validate
            tool_args: Assembled tool arguments

        Returns:
            True if all required fields are present, False otherwise
        """
        tool = self.tool_executor._tools.get(tool_name)
        if not tool:
            logger.warning(f"Tool '{tool_name}' not found in executor, skipping schema validation")
            return True

        schema = getattr(tool, 'args_schema', None)
        if not schema:
            return True

        required_fields = set()
        for field_name, field_info in schema.model_fields.items():
            if field_info.is_required():
                required_fields.add(field_name)

        if not required_fields:
            return True

        missing = required_fields - set(tool_args.keys())
        if missing:
            logger.warning(f"Tool '{tool_name}' missing required fields: {missing} (have: {list(tool_args.keys())})")
            return False

        return True

    async def trigger_reflection(self, reflection_text: str) -> None:
        """
        Trigger reflection callback for ToT integration.

        Args:
            reflection_text: Reflection text to send to callback
        """
        if self._on_reflection_callback:
            await self._on_reflection_callback(reflection_text)

    async def trigger_thought_complete(self, thought_data: Dict[str, Any]) -> None:
        """
        Trigger thought complete callback for ToT integration.

        Args:
            thought_data: Thought data to send to callback
        """
        if self._on_thought_complete_callback:
            await self._on_thought_complete_callback(thought_data)
