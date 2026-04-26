"""
Chat API - SSE Streaming Chat Endpoint

This module provides the main chat endpoint with SSE streaming support.
"""

import json
import re
import asyncio
import logging
import time
import uuid
from typing import AsyncIterator
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest, ChatEvent, ToolCall
from app.core.agent import create_agent_manager, AgentManager
from app.core.tools import get_registered_tools
from app.memory.prompts import build_system_prompt
from app.memory.session import get_session_manager
from app.skills.bootstrap import bootstrap_skills
# from app.logging_config import AgentExecutionLogger, get_agent_logger
from app.core.trajectory import AgentExecutionLogger
from app.logging_config import get_agent_logger
from app.core.tot.router import ToTOrchestrator

# Get logger for this module
logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency
def _get_perv_orchestrator(**kwargs):
    from app.core.perv.orchestrator import get_orchestrator
    return get_orchestrator(**kwargs)
agent_logger = get_agent_logger("api.chat")


router = APIRouter(tags=["chat"])


def _format_attachments(attachments: list[dict]) -> list[dict]:
    """Convert attachments to LLM multimodal content format.

    Frontend sends: [{type, content (data URL), mime_type, filename}]
    Returns: list of content blocks for the LLM.
    """
    content_blocks = []
    for att in attachments:
        category = att.get("type", "document")
        data_url = att.get("content", "")
        mime_type = att.get("mime_type", "")
        filename = att.get("filename", "")

        if category == "image":
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
        elif category == "audio":
            # Extract raw base64 from data URL
            base64_data = data_url.split(",", 1)[-1] if "," in data_url else data_url
            audio_format = mime_type.split("/")[-1] if "/" in mime_type else "wav"
            content_blocks.append({
                "type": "input_audio",
                "input_audio": {"data": base64_data, "format": audio_format},
            })
        else:
            # video/document: include as text description
            content_blocks.append({
                "type": "text",
                "text": f"[Attached file: {filename} ({mime_type})]",
            })
    return content_blocks

# Global agent manager (singleton)
_agent_manager: AgentManager = None
_current_provider: str = None


def get_agent_manager() -> AgentManager:
    """
    Get or create the global agent manager.

    This function implements hot-switching by checking if the configured
    provider has changed and recreating the agent manager if necessary.

    Returns:
        AgentManager instance

    Raises:
        HTTPException: If initialization fails
    """
    global _agent_manager, _current_provider

    try:
        from app.config import get_settings
        settings = get_settings()

        # Check if provider has changed (hot-switch support)
        if _current_provider != settings.llm_provider:
            import logging
            logging.info(f"=== LLM provider changed: {_current_provider} → {settings.llm_provider} ===")

            # Import tools directly
            from app.tools import CORE_TOOLS
            logging.info(f"Tools: {[t.name for t in CORE_TOOLS]}")

            # Recreate agent manager with new provider
            _agent_manager = create_agent_manager(
                tools=CORE_TOOLS,
                llm_provider=settings.llm_provider,
            )
            _current_provider = settings.llm_provider

            logging.info("=== Agent manager recreated successfully ===")

        elif _agent_manager is None:
            import logging
            logging.info(f"=== Creating agent manager ===")
            logging.info(f"Tools type: {type(CORE_TOOLS)}")
            logging.info(f"Tools: {[t.name for t in CORE_TOOLS]}")

            # Create agent manager
            logging.info(f"Creating agent with provider: {settings.llm_provider}")

            _agent_manager = create_agent_manager(
                tools=CORE_TOOLS,
                llm_provider=settings.llm_provider,
            )
            _current_provider = settings.llm_provider

            logging.info("=== Agent manager created successfully ===")

        return _agent_manager

    except Exception as e:
        import traceback
        logging.error(f"=== Failed to create agent manager ===")
        logging.error(f"Error: {e}")
        logging.error(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize agent: {str(e)}",
        )


def reset_agent_manager() -> None:
    """
    Reset the global agent manager to force recreation on next access.

    This should be called when LLM configuration is updated to ensure
    the new configuration is picked up immediately.
    """
    global _agent_manager, _current_provider
    _agent_manager = None
    _current_provider = None

    # Also reset memory manager to ensure it uses the new LLM
    try:
        from app.memory.memory_manager import reset_memory_manager
        reset_memory_manager()
    except Exception as e:
        logger.warning(f"Failed to reset memory manager: {e}")

    # 重置 memory retriever（持有 RAG 引擎引用）
    try:
        from app.memory.retriever_factory import reset_memory_retriever
        reset_memory_retriever()
    except Exception as e:
        logger.warning(f"Failed to reset memory retriever: {e}")

    # 重置统一评估器（缓存了 LLM 实例）
    try:
        from app.core.reflection.evaluator import reset_unified_evaluator
        reset_unified_evaluator()
    except Exception as e:
        logger.warning(f"Failed to reset unified evaluator: {e}")


def format_sse_event(event: ChatEvent) -> str:
    """
    Format a chat event as SSE message.

    Args:
        event: Chat event

    Returns:
        SSE formatted string

    Examples:
        >>> event = ChatEvent(type="thinking_start")
        >>> sse = format_sse_event(event)
        >>> print(sse)
        data: {"type": "thinking_start"}\n\n
    """
    event_dict = event.model_dump(exclude_none=True)
    return f"data: {json.dumps(event_dict, ensure_ascii=False)}\n\n"


def _classify_conversation_type(content: str) -> str:
    """
    Classify conversation type without exposing specific content.

    Returns type labels like "Weather Query", "Code Generation", etc.

    Args:
        content: Conversation content to classify

    Returns:
        Type label string
    """
    content_lower = content.lower()

    # Weather query pattern
    if any(kw in content_lower for kw in ["天气", "weather", "温度", "temperature"]):
        return "Weather Information Query"

    # Code generation pattern
    if any(kw in content_lower for kw in ["代码", "code", "函数", "function", "class"]):
        return "Code Generation Task"

    # Data analysis pattern
    if any(kw in content_lower for kw in ["分析", "analyze", "统计", "statistics", "数据"]):
        return "Data Analysis Task"

    # Academic paper search
    if any(kw in content_lower for kw in ["论文", "paper", "arxiv", "文献"]):
        return "Academic Paper Search"

    # File operation
    if any(kw in content_lower for kw in ["文件", "file", "读取", "read", "写入", "write"]):
        return "File Operation Task"

    return "General Conversation"


def detect_task_boundary(msg1: dict, msg2: dict) -> bool:
    """
    Detect if there is a task boundary between two messages.

    A task boundary exists when:
    1. Time gap > 5 minutes (conversation break)
    2. Explicit topic switch (weather → paper search)

    Args:
        msg1: First message
        msg2: Second message

    Returns:
        True if task boundary detected, False otherwise
    """
    from datetime import datetime

    # Check 1: Time gap
    try:
        time1 = datetime.fromisoformat(msg1.get("timestamp", ""))
        time2 = datetime.fromisoformat(msg2.get("timestamp", ""))
        time_diff = (time2 - time1).total_seconds()

        if time_diff > 300:  # 5 minutes
            logger.info(f"Task boundary detected: time gap {time_diff}s")
            return True
    except Exception:
        pass  # Skip if timestamp parsing fails

    # Check 2: Topic switch keywords
    content1 = msg1.get("content", "").lower()
    content2 = msg2.get("content", "").lower()

    # Define topic categories
    weather_keywords = ["天气", "weather", "温度", "temperature", " climates"]
    paper_keywords = ["论文", "paper", "arxiv", "文献", "article"]
    code_keywords = ["代码", "code", "函数", "function", "programming"]
    file_keywords = ["文件", "file", "读取", "read", "write", "directory"]

    # Check for cross-category switches
    def has_keywords(content, keywords):
        return any(kw in content for kw in keywords)

    # Weather → Non-weather
    if has_keywords(content1, weather_keywords) and not has_keywords(content2, weather_keywords):
        logger.info("Task boundary: weather → other topic")
        return True

    # Non-weather → Weather
    if not has_keywords(content1, weather_keywords) and has_keywords(content2, weather_keywords):
        # Only if it's been a while (not a quick follow-up)
        try:
            time1 = datetime.fromisoformat(msg1.get("timestamp", ""))
            time2 = datetime.fromisoformat(msg2.get("timestamp", ""))
            if (time2 - time1).total_seconds() > 60:  # 1 minute
                logger.info("Task boundary: other topic → weather (after gap)")
                return True
        except Exception:
            pass

    # Paper/Code/File switches
    if (has_keywords(content1, paper_keywords) and has_keywords(content2, code_keywords)) or \
       (has_keywords(content1, code_keywords) and has_keywords(content2, paper_keywords)):
        logger.info("Task boundary: paper ↔ code")
        return True

    return False


async def chat_stream_generator(
    request: ChatRequest,
    agent: AgentManager,
    system_prompt: str,
) -> AsyncIterator[str]:
    """
    Generate SSE stream for chat response.

    Args:
        request: Chat request
        agent: Agent manager
        system_prompt: System prompt

    Yields:
        SSE formatted strings
    """
    # Start execution logging
    with AgentExecutionLogger(f"chat_{request.session_id}") as exec_logger:
        try:
            logger.info(f"New chat request - Session: {request.session_id}")

            # Clear stale image tracking for fresh session
            from app.core.streaming.image_embedder import clear_reported_images
            clear_reported_images()
            logger.info(f"User message: {request.message[:200]}...")

            # Send thinking start event
            yield format_sse_event(
                ChatEvent(type="thinking_start")
            )

            # Load or create session
            session_manager = get_session_manager()
            session = session_manager.load_session(request.session_id)

            if session is None:
                session = session_manager.create_session(
                    session_id=request.session_id,
                    metadata=request.context,
                )

            # Prepare messages
            messages = []

            # Get session history
            session_messages = session.get("messages", [])

            # === INTELLIGENT CONTEXT PRUNING ===
            # Strategy: Use task boundary detection to prune irrelevant history
            #
            # 1. Check if there's a task boundary in recent history
            # 2. If boundary found, only keep messages AFTER the boundary
            # 3. If no boundary, keep last 3 messages
            #
            # This ensures LLM doesn't see "Beijing weather" when asking "Shanghai weather"

            MAX_CONTEXT_MESSAGES = 3
            recent_messages = session_messages[-MAX_CONTEXT_MESSAGES:] if len(session_messages) > MAX_CONTEXT_MESSAGES else session_messages

            # Check for task boundary in recent messages
            boundary_index = -1  # -1 means no boundary found
            for i in range(len(recent_messages) - 1, 0, -1):
                if i < len(recent_messages) - 1:  # Not the last message
                    if detect_task_boundary(recent_messages[i], recent_messages[i + 1]):
                        boundary_index = i
                        logger.info(f"Task boundary found at index {i}, pruning earlier history")
                        break

            # Prune messages based on boundary
            if boundary_index >= 0:
                # Keep only messages after the boundary
                recent_messages = recent_messages[boundary_index + 1:]
                logger.info(f"Pruned to {len(recent_messages)} messages after boundary")
            else:
                # No boundary: keep recent messages as-is
                logger.debug(f"No task boundary, keeping {len(recent_messages)} recent messages")

            for i, msg in enumerate(recent_messages):
                if msg["role"] in ["user", "assistant"]:
                    # Check if this is the last message (current question)
                    is_last_message = (i == len(recent_messages) - 1)

                    if is_last_message:
                        # CURRENT MESSAGE: Use full content - this is what LLM should focus on
                        message_dict = {
                            "role": msg["role"],
                            "content": msg["content"],
                        }
                        logger.debug(f"Loading current message: {msg['content'][:50]}...")

                        # Add images if present (only for current message)
                        if msg.get("images"):
                            # Format content for vision models
                            content_list = [{"type": "text", "text": msg["content"]}]
                            for img in msg["images"]:
                                content_list.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{img['mime_type']};base64,{img['content']}"}
                                })
                            message_dict["content"] = content_list
                    else:
                        # HISTORICAL MESSAGE: Abstract to type only - prevents interference
                        # Don't show "Beijing weather" - show "Weather Information Query" instead
                        # Don't include images for historical messages
                        message_type = _classify_conversation_type(msg.get("content", ""))
                        message_dict = {
                            "role": msg["role"],
                            "content": f"[COMPLETED_TASK] {message_type} - Task finished, ignore details",
                        }
                        logger.debug(f"Abstracted historical message to: {message_type}")

                    messages.append(message_dict)

            # Add current message
            current_message = {
                "role": "user",
                "content": request.message,
            }
            # Add attachments from current request if present
            if request.attachments:
                content_list = [{"type": "text", "text": request.message}]
                content_list.extend(_format_attachments(request.attachments))
                current_message["content"] = content_list
            messages.append(current_message)

            # Log input
            exec_logger.set_user_question(request.message)
            exec_logger.log_input(messages, system_prompt)

            # Stream agent response
            logger.info("Starting agent stream...")
            event_count = 0
            tool_call_count = 0
            assistant_message_parts = []  # Collect assistant response for saving
            collected_images = []  # Collect generated_images from tool outputs

            # ── 直接流式输出（无自动 PERV 重路由）──
            # === Watchdog: 注册 run ===
            from app.core.watchdog import get_registry as _wd_get_reg
            _wd_registry = _wd_get_reg()
            _wd_run_id = str(uuid.uuid4())
            _wd_info = _wd_registry.register(_wd_run_id, session_id=request.session_id)
            _wd_cancel = _wd_info.cancel_event
            yield format_sse_event(ChatEvent(type="run_id", run_id=_wd_run_id))

            async for event in agent.astream(
                messages=messages,
                system_prompt=system_prompt,
                cancel_event=_wd_cancel,
                run_id=_wd_run_id,
            ):
                event_count += 1

                # Log each event
                event_type = event.get("type", "unknown")
                logger.debug(f"Agent event #{event_count}: {event_type}")

                if event_type == "tool_call":
                    tool_call_count += 1
                    tool_calls = event.get("tool_calls", [])
                    for tc in tool_calls:
                        tc_name = tc.get("name", "unknown")
                        tc_args = tc.get("arguments", {})
                        exec_logger.log_tool_call(tc_name, tc_args)
                        logger.info(f"Tool call: {tc_name}")

                elif event_type == "tool_output":
                    tool_name = event.get("tool_name", "unknown")
                    output = event.get("output", "")
                    status = event.get("status", "unknown")
                    success = status == "success"
                    tool_duration = event.get("duration", 0.0)
                    exec_logger.log_tool_result(tool_name, output, success, duration=tool_duration)
                    logger.info(f"Tool output: {tool_name} - {status} ({tool_duration:.2f}s)")
                    # Collect structured generated_images from v2 pipeline
                    gen_images = event.get("generated_images")
                    if gen_images:
                        _seen = {img["media_id"] for img in collected_images}
                        collected_images.extend(img for img in gen_images if img["media_id"] not in _seen and not _seen.add(img["media_id"]))
                    # Legacy compat: collect base64-embedded images
                    if output and "data:image/" in output:
                        assistant_message_parts.append(f"\n\n{output}\n\n")

                elif event_type == "content_delta":
                    content = event.get("content", "")
                    logger.debug(f"Content delta: {len(content)} chars")
                    if content:
                        assistant_message_parts.append(content)

                elif event_type == "execution_summary":
                    # Feed metrics into logger (don't forward to client)
                    summary = event
                    exec_logger.log_token_usage(
                        prompt_tokens=summary.get("total_prompt_tokens", 0),
                        completion_tokens=summary.get("total_completion_tokens", 0),
                        total_tokens=summary.get("total_tokens", 0),
                    )
                    for rm in summary.get("rounds", []):
                        exec_logger.start_round()
                        exec_logger.log_round_metrics(
                            llm_duration=rm.get("llm_duration", 0.0),
                            tool_duration=rm.get("tool_duration", 0.0),
                            tool_count=rm.get("tool_count", 0),
                            prompt_tokens=rm.get("prompt_tokens", 0),
                            completion_tokens=rm.get("completion_tokens", 0),
                            total_tokens=rm.get("total_tokens", 0),
                        )
                    logger.info(
                        f"[Chat] Execution summary: "
                        f"{summary.get('total_duration', 0):.2f}s total, "
                        f"{summary.get('total_rounds', 0)} rounds, "
                        f"{summary.get('total_tokens', 0)} tokens"
                    )
                    # Forward to client so frontend can display
                    yield format_sse_event(ChatEvent(**event))
                    continue

                yield format_sse_event(ChatEvent(**event))

            logger.info(f"[Chat] Stream: {tool_call_count} tool_calls, {len(collected_images)} images collected")

            # [IMAGE_UNIFY] Append image markdown refs to content so ReactMarkdown renders inline
            if collected_images and not any(
                img.get("api_url", "") in "".join(assistant_message_parts)
                for img in collected_images
            ):
                from app.core.streaming.image_embedder import build_image_markdown
                image_md = build_image_markdown(collected_images)
                if image_md:
                    yield format_sse_event(ChatEvent(
                        type="content_delta",
                        content=image_md,
                    ))

            # Save user message to session
            session_manager.add_message(
                session_id=request.session_id,
                role="user",
                content=request.message,
                images=request.attachments,
            )

            # Save assistant response to session (if any)
            if assistant_message_parts:
                assistant_full_response = "".join(assistant_message_parts)
                # Resolve any remaining media path references
                try:
                    from app.core.media import resolve_media
                    from app.core.media.watcher import scan_and_register
                    scan_and_register(max_age_seconds=120)
                    if collected_images:
                        # Images already tracked via generated_images pipeline;
                        # just register files without re-resolving text paths
                        logger.info("[Media] Skipping resolve_media (images via generated_images pipeline)")
                    else:
                        assistant_full_response = resolve_media(
                            assistant_full_response,
                            session_id=request.session_id or ""
                        )
                        logger.info("[Media] Resolved media in assistant response")
                except Exception as e:
                    logger.warning(f"[Media] resolve_media failed: {e}")
                # Strip base64 data URIs before saving to session
                save_content = re.sub(
                    r'data:image/[a-zA-Z+]+;base64,[A-Za-z0-9+/=\n]+',
                    '[图片已生成]',
                    assistant_full_response,
                )
                save_content = re.sub(
                    r'!\[[^\]]*\]\(data:image/[^)]{100,}\)',
                    '[图片已生成]',
                    save_content,
                )
                # Build session message with generated_images
                session_msg = {
                    "role": "assistant",
                    "content": save_content,
                }
                if collected_images:
                    session_msg["generated_images"] = collected_images
                session_manager.add_message(
                    session_id=request.session_id,
                    **session_msg,
                )
                logger.info(
                    "[Chat] Session saved: %d images, content %d→%d chars",
                    len(collected_images), len(assistant_full_response), len(save_content),
                )
            else:
                logger.warning("No assistant response to save")

            # Trigger background memory extraction (non-blocking)
            try:
                from app.config import get_settings
                settings = get_settings()

                if settings.enable_memory_extraction:
                    asyncio.create_task(
                        _background_memory_extraction(request.session_id)
                    )
            except Exception as e:
                import logging
                logging.warning(f"Failed to trigger memory extraction: {e}")

            # Send done event
            _wd_registry.set_result(_wd_run_id, {"status": "completed"})
            yield format_sse_event(
                ChatEvent(type="done")
            )

        except Exception as e:
            # Send error event
            try:
                _wd_registry.set_error(_wd_run_id, str(e))
            except Exception:
                pass
            yield format_sse_event(
                ChatEvent(
                    type="error",
                    error=str(e),
                )
            )


async def tot_stream_generator(
    request: ChatRequest,
    orchestrator: ToTOrchestrator,
    system_prompt: str,
) -> AsyncIterator[str]:
    """Tier 1: ToT 流生成器。enable_tot=True 强制走 ToT。"""
    assistant_parts = []
    collected_images = []

    # ── Load session history (mirrors chat_stream_generator logic) ──
    session_manager = get_session_manager()
    session = session_manager.load_session(request.session_id)
    session_messages = session.get("messages", []) if session else []

    tot_messages = []
    MAX_CONTEXT_MESSAGES = 3
    recent_messages = session_messages[-MAX_CONTEXT_MESSAGES:] if len(session_messages) > MAX_CONTEXT_MESSAGES else session_messages

    for msg in recent_messages:
        if msg["role"] in ("user", "assistant"):
            content_preview = msg["content"][:300] if msg["content"] else ""
            # Safety: strip base64 and image URLs so LLM doesn't reuse old images
            content_preview = re.sub(
                r'data:image/[a-zA-Z+]+;base64,[A-Za-z0-9+/=\n]{50,}',
                '[图片]', content_preview,
            )
            content_preview = re.sub(
                r'!\[[^\]]*\]\([^)]*(?:/api/media/|data:image/)[^)]*\)',
                '[图片已生成]', content_preview,
            )
            content_preview = re.sub(
                r'http://localhost:\d+/api/media/[a-f0-9]+',
                '[图片]', content_preview,
            )
            tot_messages.append({"role": msg["role"], "content": content_preview})

    # Append current user message
    tot_messages.append({"role": "user", "content": request.message})

    try:
        # === Watchdog: 注册 ToT run ===
        from app.core.watchdog import get_registry as _wd_get_reg
        _wd_registry = _wd_get_reg()
        _wd_run_id = str(uuid.uuid4())
        _wd_info = _wd_registry.register(_wd_run_id, session_id=request.session_id)
        _wd_cancel = _wd_info.cancel_event
        yield format_sse_event(ChatEvent(type="run_id", run_id=_wd_run_id))

        async for event in orchestrator.process_request(
            messages=tot_messages,
            system_prompt=system_prompt,
            enable_tot=True,
            cancel_event=_wd_cancel,
            run_id=_wd_run_id,
        ):
            event_type = event.get("type", "unknown")

            if event_type == "content_delta":
                assistant_parts.append(event.get("content", ""))
            # elif event_type == "tool_output":
            #     # [DEPRECATED] ToT 模式下 tool_output 事件极少触发，图片通过 tot_tools_executed 独立传输
            #     # 保留此路径可能导致图片重复（同时出现在 assistantContent 和 collected_images）
            #     gen_images = event.get("generated_images")
            #     if gen_images:
            #         collected_images.extend(gen_images)
            #     output = event.get("output", "")
            #     if output and "data:image/" in output:
            #         assistant_parts.append(f"\n\n{output}\n\n")
            # [IMAGE_UNIFY] Don't collect images from tot_tools_executed.
            # Images render inline via synthesis_node's _resolve_image_refs.
            elif event_type == "tot_tools_executed":
                pass

            yield format_sse_event(ChatEvent(**event))

    except Exception as e:
        logger.error("[ToT] Stream error: %s", e, exc_info=True)
        yield format_sse_event(ChatEvent(type="error", error=str(e)))

    # Session 保存（复用图片管线逻辑）
    session_manager = get_session_manager()
    session_manager.add_message(
        session_id=request.session_id, role="user",
        content=request.message, images=request.attachments,
    )
    if assistant_parts:
        assistant_full_response = "".join(assistant_parts)
        try:
            from app.core.media import resolve_media
            from app.core.media.watcher import scan_and_register
            scan_and_register(max_age_seconds=120)
            if not collected_images:
                assistant_full_response = resolve_media(
                    assistant_full_response,
                    session_id=request.session_id or ""
                )
        except Exception as e:
            logger.warning(f"[Media] resolve_media failed: {e}")
        save_content = re.sub(
            r'data:image/[a-zA-Z+]+;base64,[A-Za-z0-9+/=\n]+',
            '[图片已生成]', assistant_full_response,
        )
        save_content = re.sub(
            r'!\[[^\]]*\]\(data:image/[^)]{100,}\)',
            '[图片已生成]', save_content,
        )
        session_msg = {"role": "assistant", "content": save_content}
        if collected_images:
            session_msg["generated_images"] = collected_images
        session_manager.add_message(session_id=request.session_id, **session_msg)
    # Memory extraction
    try:
        if get_settings().enable_memory_extraction:
            asyncio.create_task(_background_memory_extraction(request.session_id))
    except Exception:
        pass


@router.post("")
async def chat(request: ChatRequest):
    """
    Main chat endpoint with SSE streaming support.

    This endpoint streams the Agent's response in real-time using Server-Sent Events.

    ## Request Format
    ```json
    {
      "message": "查询一下北京的天气",
      "session_id": "main_session",
      "stream": true
    }
    ```

    ## SSE Events
    The response streams Server-Sent Events with the following types:

    - **thinking_start**: Agent is starting to think
    - **tool_call**: Agent is calling a tool
      ```json
      {
        "type": "tool_call",
        "tool_calls": [
          {
            "id": "call_abc123",
            "name": "fetch_url",
            "args": {"url": "..."}
          }
        ]
      }
      ```

    - **content_delta**: Content chunk
      ```json
      {
        "type": "content_delta",
        "content": "北京今天的天气..."
      }
      ```

    - **done**: Response complete
      ```json
      {
        "type": "done"
      }
      ```

    - **error**: Error occurred
      ```json
      {
        "type": "error",
        "error": "Error message"
      }
      ```

    ## Example Usage

    **With curl:**
    ```bash
    curl -N http://localhost:8002/api/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "Hello", "stream": true}'
    ```

    **With JavaScript:**
    ```javascript
    const eventSource = new EventSource('http://localhost:8002/api/chat');

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log(data.type, data);
    };

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      eventSource.close();
    };
    ```

    Args:
        request: Chat request

    Returns:
        StreamingResponse with SSE events

    Raises:
        HTTPException: If agent initialization fails
    """
    # 请求入口日志（即使后续操作阻塞也能记录）
    logger.info("[Chat] Request received: session=%s, message=%s", request.session_id, request.message[:100])

    # Ensure skills are loaded
    bootstrap_skills()

    # === Retrieve relevant conversation history via semantic search ===
    recent_history = ""
    try:
        from app.config import get_settings
        settings = get_settings()

        # Only trigger semantic search for substantial queries (not simple greetings)
        message_len = len(request.message.strip())
        is_substantial_query = (
            message_len > 20 and  # At least 20 characters
            not request.message.strip() in ["你好", "hello", "hi", "嗨", "您好"] and  # Not simple greetings
            "?" in request.message or "？" in request.message or  # Questions
            any(word in request.message.lower() for word in ["如何", "怎么", "什么", "为什么", "how", "what", "why", "how to"])  # Complex queries
        )

        # Check embedding model status before semantic search
        if settings.enable_semantic_search and is_substantial_query:
            from app.core.embedding_manager import get_embedding_manager, EmbeddingLoadStatus
            embedding_manager = get_embedding_manager()
            status_info = embedding_manager.get_status()

            if status_info["status"] != EmbeddingLoadStatus.READY:
                if status_info["status"] == EmbeddingLoadStatus.LOADING:
                    logger.info("Embedding model still loading, skipping semantic search")
                elif status_info["status"] == EmbeddingLoadStatus.FAILED:
                    logger.warning(f"Embedding model failed to load: {status_info.get('error')}, skipping semantic search")
                # Skip semantic search, don't block user request
                is_substantial_query = False

        if settings.enable_semantic_search and is_substantial_query:
            from app.memory.memory_manager import get_memory_manager
            memory_manager = get_memory_manager()

            # Search with relevance threshold
            relevant = await memory_manager.search_relevant_history(
                request.message,
                top_k=3
            )

            # Filter by relevance score (if available) and content quality
            if relevant:
                filtered_results = []
                for r in relevant:
                    content = r.get('content', '').strip()
                    # Skip very short or low-quality content
                    if len(content) > 50 and not content.startswith(('测试', 'test', 'Test')):
                        # Only include if has reasonable relevance (similarity > 0.3 if available)
                        similarity = r.get('similarity', 1.0)
                        if similarity > 0.5:  # Increased threshold to reduce weak matches
                            filtered_results.append(r)

                if filtered_results:
                    # Format with pattern type only (no specific content)
                    formatted_entries = []
                    for idx, r in enumerate(filtered_results, 1):
                        similarity = r.get('similarity', 0.0)
                        session_id = r.get('metadata', {}).get('session_id', 'unknown')
                        content = r['content']

                        # Extract pattern type (no specific values)
                        entry_type = _classify_conversation_type(content)

                        entry = f"""---
📜 **Historical Pattern #{idx}**
   👤 Session: {session_id}
   🎯 Relevance: {similarity:.1%}
   📋 Pattern Type: {entry_type}

   ⚠️  This is a PAST conversation pattern. Extract the approach, NOT specific values.
"""
                        formatted_entries.append(entry)

                    recent_history = "\n".join(formatted_entries)
                    import logging
                    logging.info(f"Found {len(filtered_results)} relevant conversation chunks for query: {request.message[:50]}")
    except Exception as e:
        import logging
        logging.warning(f"Semantic search failed: {e}")

    # Build system prompt
    try:
        # Wiki retrieval (if enabled)
        wiki_memory_context = ""
        settings = get_settings()

        # --- Memory Engine retrieval path (Phase 5) ---
        if getattr(settings, "enable_memory_engine", False):
            try:
                from app.memory.engine.graph import get_memory_engine
                engine = get_memory_engine()
                # Use retrieval chain
                result = await engine["retrieve"].ainvoke({
                    "query": request.message,
                    "session_id": request.session_id or "",
                    "user_id": "",
                })
                wiki_memory_context = result.get("memory_context", "")
                logger.info(
                    f"[MemoryEngine] Retrieval complete, context_len={len(wiki_memory_context)}"
                )
            except Exception as e:
                logger.warning(f"MemoryEngine retrieval failed, falling back: {e}")
                # Fall through to standard retrieval below
                if settings.enable_wiki:
                    try:
                        from app.memory.wiki.retriever import get_wiki_retriever
                        wiki_retriever = get_wiki_retriever()
                        wiki_memory_context = await wiki_retriever.retrieve_with_fallback(request.message)
                    except Exception as e2:
                        logging.warning(f"Wiki retrieval fallback failed: {e2}")
        elif settings.enable_wiki:
            try:
                from app.memory.wiki.retriever import get_wiki_retriever
                wiki_retriever = get_wiki_retriever()
                wiki_memory_context = await wiki_retriever.retrieve_with_fallback(request.message)
            except Exception as e:
                import logging
                logging.warning(f"Wiki retrieval failed: {e}")

        system_prompt = build_system_prompt(
            session_data={
                "user_context": request.context,
                "conversation_context": recent_history,      # prompts.py 期望的 key
                "semantic_history": recent_history,           # prompts.py 期望的 key
                "wiki_memory_context": wiki_memory_context,   # Wiki 长期记忆
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build system prompt: {str(e)}",
        )

    # Get agent manager
    agent = get_agent_manager()
    settings = get_settings()
    user_context = request.context or {}
    logger.info("[Routing] Request received: message=%s, context=%s", request.message[:50], user_context)
    research_mode = user_context.get("research_mode")
    deep_planning = user_context.get("deep_planning", False)

    # ── Tier 1: ToT（深度研究模式 → 100% ToT）──
    if research_mode and research_mode in settings.thinking_modes:
        try:
            tc = settings.thinking_modes[research_mode]
            tot_depth = tc.get("depth", settings.tot_max_depth)
            tot_branching = tc.get("branching", settings.tot_branching_factor)
            custom_branching = user_context.get("branching_factor")
            if custom_branching:
                tot_branching = int(custom_branching)
            custom_depth = user_context.get("depth")
            if custom_depth:
                tot_depth = int(custom_depth)

            logger.info("[Routing] Tier 1: ToT (research=%s, depth=%d, branching=%d)",
                        research_mode, tot_depth, tot_branching)

            orchestrator = ToTOrchestrator(
                agent_manager=agent,
                max_depth=tot_depth,
                branching_factor=tot_branching,
            )
            return StreamingResponse(
                tot_stream_generator(request, orchestrator, system_prompt),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        except Exception as e:
            logger.error("[Routing] ToT failed, falling to Tier 3: %s", e, exc_info=True)
            # 异常 → 直接降级到 Tier 3

    # ── Tier 2: PERV（深度规划模式，用户手动触发）──
    elif deep_planning:
        try:
            perv_orch = _get_perv_orchestrator(
                agent_manager=agent,
                session_id=request.session_id or "default",
            )
            logger.info("[Routing] Tier 2: PERV Deep Planning (user-triggered)")

            # === Watchdog: 注册 PERV run ===
            from app.core.watchdog import get_registry as _wd_get_reg
            _wd_registry = _wd_get_reg()
            _wd_run_id = str(uuid.uuid4())
            _wd_info = _wd_registry.register(_wd_run_id, session_id=request.session_id)
            _wd_cancel = _wd_info.cancel_event

            async def _perv_stream():
                """PERV 深度规划模式流（用户主动触发，不自动降级）。"""
                assistant_parts = []
                collected_images = []

                yield format_sse_event(ChatEvent(type="run_id", run_id=_wd_run_id))

                async for event in perv_orch.process_request(
                    [{"role": "user", "content": request.message}],
                    system_prompt,
                    force_mode="plan_execute",
                    cancel_event=_wd_cancel,
                    run_id=_wd_run_id,
                ):
                    et = event.get("type", "")
                    if et == "content_delta":
                        assistant_parts.append(event.get("content", ""))
                    elif et == "tool_output":
                        gi = event.get("generated_images")
                        if gi:
                            _seen = {img["media_id"] for img in collected_images}
                            collected_images.extend(img for img in gi if img["media_id"] not in _seen and not _seen.add(img["media_id"]))
                        out = event.get("output", "")
                        if out and "data:image/" in out:
                            assistant_parts.append(f"\n\n{out}\n\n")
                    elif et == "pevr_execution_complete":
                        gi = event.get("generated_images")
                        if gi:
                            _seen = {img["media_id"] for img in collected_images}
                            new_imgs = [img for img in gi if img["media_id"] not in _seen]
                            collected_images.extend(new_imgs)
                            if new_imgs:
                                logger.info("[PERV] Collected %d image(s) from pevr_execution_complete", len(new_imgs))

                    yield format_sse_event(ChatEvent(**event))

                # PERV 完成 → 保存 session
                session_manager = get_session_manager()
                session_manager.add_message(
                    session_id=request.session_id, role="user",
                    content=request.message, images=request.attachments,
                )
                if assistant_parts:
                    full_resp = "".join(assistant_parts)
                    try:
                        from app.core.media import resolve_media
                        from app.core.media.watcher import scan_and_register
                        scan_and_register(max_age_seconds=120)
                        if not collected_images:
                            full_resp = resolve_media(full_resp, session_id=request.session_id or "")
                    except Exception as e:
                        logger.warning(f"[Media] resolve_media failed: {e}")
                    save_content = re.sub(
                        r'data:image/[a-zA-Z+]+;base64,[A-Za-z0-9+/=\n]+',
                        '[图片已生成]', full_resp,
                    )
                    save_content = re.sub(
                        r'!\[[^\]]*\]\(data:image/[^)]{100,}\)',
                        '[图片已生成]', save_content,
                    )
                    session_msg = {"role": "assistant", "content": save_content}
                    if collected_images:
                        session_msg["generated_images"] = collected_images
                    session_manager.add_message(session_id=request.session_id, **session_msg)
                try:
                    if get_settings().enable_memory_extraction:
                        asyncio.create_task(_background_memory_extraction(request.session_id))
                except Exception:
                    pass

            return StreamingResponse(
                _perv_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        except Exception as e:
            logger.error("[Routing] PERV Deep Planning failed, falling to Tier 3: %s", e, exc_info=True)

    # ── Tier 3: 普通 Agent（兜底）──
    logger.info("[Routing] Tier 3: Normal agent")
    return StreamingResponse(
        chat_stream_generator(request, agent, system_prompt),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/health")
async def health_check():
    """
    Health check endpoint for the chat API.

    Returns status information about the chat service.

    ## Response
    ```json
    {
      "status": "healthy",
      "agent_initialized": true,
      "skills_loaded": 2
    }
    ```

    Returns:
        Health status dict
    """
    from app.skills.bootstrap import bootstrap_skills

    # Try to initialize agent
    try:
        agent = get_agent_manager()
        agent_initialized = True
    except Exception:
        agent_initialized = False

    # Count skills
    try:
        bootstrap = bootstrap_skills()
        bootstrap.scan_skills()
        skills_count = bootstrap.get_skill_count()
    except Exception:
        skills_count = 0

    return {
        "status": "healthy" if agent_initialized else "degraded",
        "agent_initialized": agent_initialized,
        "skills_loaded": skills_count,
    }


async def _background_memory_extraction(session_id: str) -> None:
    """
    Background task to extract and store memories from a conversation.

    This task runs asynchronously after the chat response is sent,
    ensuring that memory extraction doesn't block the chat response.

    Args:
        session_id: Session ID to extract memories from
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from app.memory.memory_manager import get_memory_manager
        memory_manager = get_memory_manager()

        result = await memory_manager.extract_and_store(session_id)

        if result.memories:
            logger.info(
                f"Background memory extraction completed for {session_id}: "
                f"{len(result.memories)} memories extracted"
            )

        # Memory Engine ingest path (Phase 5)
        from app.config import get_settings
        settings = get_settings()
        if getattr(settings, "enable_memory_engine", False):
            try:
                from app.memory.engine.graph import get_memory_engine
                import hashlib
                import json
                import time

                engine = get_memory_engine()

                # Build events from session messages
                from app.memory.session import get_session_manager
                session_mgr = get_session_manager()
                session_data = session_mgr.load_session(session_id)
                messages = session_data.get("messages", []) if session_data else []

                events = []
                for msg in messages[-20:]:  # Last 20 messages
                    payload = {
                        "role": msg.get("role", "unknown"),
                        "content": msg.get("content", "")[:500],
                    }
                    events.append({
                        "event_type": msg.get("role", "unknown"),
                        "source_type": "conversation",
                        "payload": payload,
                        "ts": msg.get("timestamp", time.time()),
                    })

                if events:
                    await engine["ingest"].ainvoke({
                        "session_id": session_id,
                        "new_events": events,
                    })
                    logger.info(f"[MemoryEngine] Ingested {len(events)} events for session {session_id}")

            except Exception as e:
                logger.warning(f"MemoryEngine ingest failed for {session_id}: {e}")

    except Exception as e:
        logger.error(f"Background memory extraction failed for {session_id}: {e}", exc_info=True)


# === Watchdog: 取消和状态查询端点 ===

from pydantic import BaseModel


class CancelRequest(BaseModel):
    run_id: str


@router.post("/cancel")
async def cancel_run(request: CancelRequest):
    """取消正在运行的 Agent 执行。"""
    from app.core.watchdog import get_registry
    registry = get_registry()
    info = registry.get(request.run_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Run {request.run_id} 不存在")
    if info.is_terminal:
        return {"success": True, "message": f"Run 已处于 {info.status} 状态"}
    registry.request_cancel(request.run_id)
    logger.info(f"[Watchdog] 用户请求取消 run {request.run_id}")
    return {"success": True, "message": "Cancel requested"}


@router.get("/runs/{run_id}")
async def get_run_status(run_id: str):
    """查询指定 run 的状态。"""
    from app.core.watchdog import get_registry
    registry = get_registry()
    info = registry.get(run_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} 不存在")
    return info.to_dict()


@router.get("/runs")
async def list_active_runs():
    """列出所有活跃的 run。"""
    from app.core.watchdog import get_registry
    registry = get_registry()
    return {"runs": [r.to_dict() for r in registry.list_active()]}

