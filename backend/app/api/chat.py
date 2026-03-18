"""
Chat API - SSE Streaming Chat Endpoint

This module provides the main chat endpoint with SSE streaming support.
"""

import json
import asyncio
import logging
import time
import hashlib
from typing import AsyncIterator
from functools import lru_cache
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest, ChatEvent, ToolCall
from app.core.agent import create_agent_manager, AgentManager
from app.core.tools import get_registered_tools
from app.memory.prompts import build_system_prompt
from app.memory.session import get_session_manager
from app.skills.bootstrap import bootstrap_skills
from app.logging_config import AgentExecutionLogger, get_agent_logger

# Get logger for this module
logger = logging.getLogger(__name__)
agent_logger = get_agent_logger("api.chat")


router = APIRouter(tags=["chat"])

# Global agent manager (singleton)
_agent_manager: AgentManager = None
_current_llm_id: str = None


def reset_agent_manager() -> None:
    """
    Reset the global agent manager to force recreation on next access.

    This should be called when LLM configuration is updated to ensure
    the new configuration is picked up immediately.
    """
    global _agent_manager, _current_llm_id
    _agent_manager = None
    _current_llm_id = None

    # Also reset memory manager to ensure it uses the new LLM
    from app.memory.memory_manager import reset_memory_manager
    reset_memory_manager()


def get_agent_manager() -> AgentManager:
    """
    Get or create the global agent manager with current LLM.

    每次都重新加载当前 LLM 配置，确保前端设置与后端使用一致。
    """
    global _agent_manager, _current_llm_id

    try:
        from app.core.llm_config import get_current_llm_id, load_llm_config
        from app.core.llm import create_llm_from_config
        from app.tools import CORE_TOOLS

        # 获取当前 LLM ID
        current_llm_id = get_current_llm_id()

        # 检查是否需要重新创建 Agent Manager
        if _current_llm_id != current_llm_id or _agent_manager is None:
            import logging
            logging.info(f"=== LLM changed: {_current_llm_id} → {current_llm_id} ===")

            # 加载当前 LLM 配置
            llm_config = load_llm_config(current_llm_id)

            if llm_config is None:
                raise ValueError(f"Current LLM {current_llm_id} not found")

            # 创建 LLM 实例
            llm = create_llm_from_config(llm_config)

            # 创建 Agent Manager
            _agent_manager = create_agent_manager(
                tools=CORE_TOOLS,
                llm=llm,
            )
            _current_llm_id = current_llm_id

            logging.info(f"=== Agent Manager recreated with LLM: {current_llm_id} ===")

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
        except:
            pass

    # Paper/Code/File switches (with time gap check)
    if (has_keywords(content1, paper_keywords) and has_keywords(content2, code_keywords)) or \
       (has_keywords(content1, code_keywords) and has_keywords(content2, paper_keywords)):
        # Check time gap to avoid false positives for continuous workflows
        try:
            time1 = datetime.fromisoformat(msg1.get("timestamp", ""))
            time2 = datetime.fromisoformat(msg2.get("timestamp", ""))
            time_diff = (time2 - time1).total_seconds()

            # Only treat as task boundary if there's a significant time gap
            # This prevents false positives for continuous workflows (e.g., research → write doc)
            if time_diff > 300:  # 5 minutes
                logger.info(f"Task boundary: paper ↔ code (time gap: {time_diff}s)")
                return True
            else:
                logger.info(f"Paper ↔ code detected but time gap is short ({time_diff}s), treating as continuous workflow")
                return False
        except Exception as e:
            # If time parsing fails, be conservative and treat as boundary
            logger.warning(f"Failed to parse timestamps for paper/code boundary: {e}")
            logger.info("Task boundary: paper ↔ code (conservative)")
            return True

    return False


def _contains_chinese(text: str) -> bool:
    """
    Check if text contains Chinese characters.

    Args:
        text: Text to check

    Returns:
        True if text contains Chinese characters
    """
    return any('\u4e00' <= char <= '\u9fff' for char in text)


# ============================================================================
# Performance Optimization: Caching
# ============================================================================

# Semantic search cache with TTL support
_semantic_search_cache: dict = {}
_semantic_search_timestamps: dict = {}


def _get_query_hash(query: str) -> str:
    """Generate MD5 hash for query."""
    return hashlib.md5(query.encode('utf-8')).hexdigest()


def _get_cached_semantic_search(query: str, ttl: int = 300):
    """
    Get cached semantic search result if available and not expired.

    Args:
        query: Search query
        ttl: Time-to-live in seconds (default 5 minutes)

    Returns:
        Cached result or None
    """
    query_hash = _get_query_hash(query)
    current_time = time.time()

    if query_hash in _semantic_search_cache:
        timestamp = _semantic_search_timestamps.get(query_hash, 0)
        if current_time - timestamp < ttl:
            logger.debug(f"Semantic search cache hit for query: {query[:50]}...")
            return _semantic_search_cache[query_hash]
        else:
            # Cache expired
            del _semantic_search_cache[query_hash]
            del _semantic_search_timestamps[query_hash]
            logger.debug(f"Semantic search cache expired for query: {query[:50]}...")

    return None


def _set_cached_semantic_search(query: str, result):
    """
    Cache semantic search result with timestamp.

    Args:
        query: Search query
        result: Search result to cache
    """
    query_hash = _get_query_hash(query)
    _semantic_search_cache[query_hash] = result
    _semantic_search_timestamps[query_hash] = time.time()
    logger.debug(f"Cached semantic search result for query: {query[:50]}...")


def _clear_semantic_search_cache():
    """Clear all semantic search cache entries."""
    global _semantic_search_cache, _semantic_search_timestamps
    _semantic_search_cache.clear()
    _semantic_search_timestamps.clear()
    logger.info("Semantic search cache cleared")


# Conversation context cache with hash-based invalidation
_conversation_context_cache: dict = {}


def _get_context_hash(messages: list) -> str:
    """
    Generate hash for conversation context based on recent messages.

    Args:
        messages: List of messages

    Returns:
        Hash string
    """
    # Use last 10 messages for hash generation
    recent_messages = messages[-10:] if len(messages) > 10 else messages
    content = "".join(f"{m.get('role', '')}:{m.get('content', '')}" for m in recent_messages)
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def _get_cached_conversation_context(session_id: str, messages: list):
    """
    Get cached conversation context if available.

    Args:
        session_id: Session ID
        messages: Current messages list

    Returns:
        Cached context or None
    """
    current_hash = _get_context_hash(messages)
    cache_key = f"{session_id}:{current_hash}"

    if cache_key in _conversation_context_cache:
        logger.debug(f"Conversation context cache hit for session: {session_id}")
        return _conversation_context_cache[cache_key]

    return None


def _set_cached_conversation_context(session_id: str, messages: list, context: str):
    """
    Cache conversation context with hash-based key.

    Args:
        session_id: Session ID
        messages: Current messages list
        context: Context to cache
    """
    current_hash = _get_context_hash(messages)
    cache_key = f"{session_id}:{current_hash}"
    _conversation_context_cache[cache_key] = context

    # Limit cache size
    if len(_conversation_context_cache) > 64:
        # Remove oldest entry (first item)
        oldest_key = next(iter(_conversation_context_cache))
        del _conversation_context_cache[oldest_key]

    logger.debug(f"Cached conversation context for session: {session_id}")


def _extract_conversation_context(
    session_messages: list,
) -> str:
    """
    Extract conversation context from current session with complete recent turns.

    Strategy:
    1. Use task boundary detection to identify relevant history
    2. Include complete recent conversation turns (user + assistant)
    3. Preserve dialogue continuity for LLM understanding

    Args:
        session_messages: Current session's message list

    Returns:
        Context string with recent conversation turns
    """
    if not session_messages:
        return ""

    # Detect task boundary from the end
    boundary_index = -1
    for i in range(len(session_messages) - 1, 1, -1):
        if detect_task_boundary(session_messages[i-1], session_messages[i]):
            boundary_index = i
            logger.info(f"Task boundary found at index {i} in current session")
            break

    # Keep messages after boundary (current task sequence)
    if boundary_index >= 0:
        recent = session_messages[boundary_index:]
    else:
        # No boundary: all messages are part of current task sequence
        recent = session_messages

    if not recent:
        return ""

    # Extract complete conversation turns (user + assistant pairs)
    # Exclude the last message if it's a user message (current one being processed)
    context_messages = []
    last_is_user = recent and recent[-1].get("role") == "user"

    # Process messages in pairs
    i = 0
    while i < len(recent):
        msg = recent[i]

        # Skip if this is the current user message being processed
        if last_is_user and i == len(recent) - 1:
            break

        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            # Start a new turn
            context_messages.append({
                "type": "user",
                "content": content
            })
        elif role == "assistant" and context_messages:
            # Add to previous user message as response
            if context_messages[-1]["type"] == "user":
                context_messages[-1]["response"] = content
            else:
                # Orphan assistant message, add as separate entry
                context_messages.append({
                    "type": "assistant",
                    "content": content
                })

        i += 1

    if not context_messages:
        return ""

    # Build context string
    context_parts = ["# Recent Conversation (This Session)", ""]

    for idx, turn in enumerate(context_messages, 1):
        if turn["type"] == "user":
            context_parts.append(f"## Turn {idx}")
            context_parts.append(f"**User**: {turn['content']}")
            if "response" in turn:
                # Truncate long responses
                response = turn["response"]
                if len(response) > 500:
                    response = response[:500] + "..."
                context_parts.append(f"**Assistant**: {response}")
            context_parts.append("")

    # Detect language preference
    has_chinese = any(
        msg.get("role") == "user" and _contains_chinese(msg.get("content", ""))
        for msg in recent
    )
    if has_chinese:
        context_parts.append("## Communication Preference")
        context_parts.append("- User communicates in Chinese")
        context_parts.append("")

    return "\n".join(context_parts)


def _extract_key_info(content: str) -> str:
    """
    Extract key information from user message for context.

    For example:
    - "北京天气如何" → "查询北京天气"
    - "帮我分析foo.py文件" → "分析文件: foo.py"

    Args:
        content: User message content

    Returns:
        Key information string or None
    """
    import re

    # Weather queries
    weather_pattern = r"(?:北京|上海|广州|深圳|杭州|成都|重庆|武汉|西安|南京|天津|青岛|大连|厦门|苏州|无锡|宁波|济南|青岛|郑州|长沙|哈尔滨|沈阳|长春|石家庄|太原|呼和浩特|西安|兰州|银川|西宁|乌鲁木齐|拉萨|昆明|贵阳|南宁|海口|福州|合肥|南昌|济南|青岛)[省市]?的?天气"
    match = re.search(weather_pattern, content)
    if match:
        city = match.group(1)
        return f"查询{city}的天气"

    # File operations
    if "文件" in content or "file" in content.lower():
        file_match = re.search(r'["\']?([\w\-./]+\.(?:py|js|ts|txt|md|json|yaml|yml|html|css|java|cpp|c|go|rs|rb|php|sh|bash|zsh))["\']?', content)
        if file_match:
            filename = file_match.group(1)
            return f"操作文件: {filename}"

    # Paper search
    if "论文" in content or "paper" in content.lower() or "arxiv" in content.lower():
        # Extract paper title/topic
        if "关于" in content:
            topic_match = re.search(r"关于(.{2,20}?)(?:的论文|论文)", content)
            if topic_match:
                return f"搜索论文: {topic_match.group(1)}"

    return None  # No key info extracted


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
            logger.info(f"User message: {request.message[:200]}...")

            # Send thinking start event
            yield format_sse_event(
                ChatEvent(type="thinking_start")
            )

            # Load or create session
            session_manager = get_session_manager()
            session = session_manager.load_session(request.session_id)

            if session is None:
                # New session: create it
                session = session_manager.create_session(
                    session_id=request.session_id,
                    metadata=request.context,
                )
                logger.info(f"New session created: {request.session_id}")
            # Note: conversation_context is already extracted in the parent function
            # and included in system_prompt, no need to extract again here

            # === KEY DESIGN: messages list only contains current user message ===
            # Historical conversation is NOT included in messages to avoid confusion
            # Context is provided separately via system_prompt components
            messages = []

            # Add only the current user message
            current_message = {
                "role": "user",
                "content": request.message,
            }

            # Add images from current request if present
            if request.images:
                content_list = [{"type": "text", "text": request.message}]
                for img in request.images:
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{img['mime_type']};base64,{img['content']}"}
                    })
                current_message["content"] = content_list

            messages.append(current_message)
            logger.debug(f"Prepared messages list with {len(messages)} message(s): current user message only")

            # Log input
            exec_logger.log_input(messages, system_prompt)

            # Stream agent response
            logger.info("Starting agent stream...")
            event_count = 0
            tool_call_count = 0
            assistant_message_parts = []  # Collect assistant response for saving

            async for event in agent.astream(
                messages=messages,
                system_prompt=system_prompt,
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
                    exec_logger.log_tool_result(tool_name, output, success)
                    logger.info(f"Tool output: {tool_name} - {status}")

                elif event_type == "content_delta":
                    content = event.get("content", "")
                    logger.debug(f"Content delta: {len(content)} chars")
                    # Collect assistant response for saving
                    assistant_message_parts.append(content)
                    logger.debug(f"Content delta: {len(content)} chars")

                yield format_sse_event(
                    ChatEvent(**event)
                )

            logger.info(f"Agent stream completed. Total events: {event_count}, Tool calls: {tool_call_count}")

            # Save user message to session
            session_manager.add_message(
                session_id=request.session_id,
                role="user",
                content=request.message,
                images=request.images,
            )

            # Save assistant response to session (if any)
            if assistant_message_parts:
                assistant_full_response = "".join(assistant_message_parts)
                session_manager.add_message(
                    session_id=request.session_id,
                    role="assistant",
                    content=assistant_full_response,
                )
                logger.info(f"Saved assistant response: {len(assistant_full_response)} chars")
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
            yield format_sse_event(
                ChatEvent(type="done")
            )

        except Exception as e:
            # Send error event
            yield format_sse_event(
                ChatEvent(
                    type="error",
                    error=str(e),
                )
            )


async def tot_stream_generator(
    request: ChatRequest,
    orchestrator: any,
    system_prompt: str,
) -> AsyncIterator[str]:
    """
    Generate SSE stream for ToT-based chat response.

    Args:
        request: Chat request
        orchestrator: ToT orchestrator
        system_prompt: System prompt

    Yields:
        SSE formatted strings
    """
    from app.core.tot.streaming import ToTEventStreamer

    try:
        logger.info(f"=== ToT stream generator: New request - Session: {request.session_id} ===")
        logger.info(f"=== User message: {request.message[:100]}... ===")

        # Load or create session
        session_manager = get_session_manager()
        session = session_manager.load_session(request.session_id)

        if session is None:
            session = session_manager.create_session(
                session_id=request.session_id,
                metadata=request.context,
            )
            logger.info(f"=== New session created: {request.session_id} ===")

        # Prepare messages
        messages = [{"role": "user", "content": request.message}]
        logger.info(f"=== Prepared {len(messages)} message(s) ===")

        # Stream ToT reasoning
        assistant_message_parts = []
        event_count = 0

        logger.info("=== Starting orchestrator.process_request with enable_tot=True ===")
        async for event in orchestrator.process_request(
            messages=messages,
            system_prompt=system_prompt,
            enable_tot=True,
        ):
            event_count += 1
            event_type = event.get("type", "unknown")
            logger.debug(f"ToT event #{event_count}: {event_type}")

            # Yield SSE event
            yield format_sse_event(ChatEvent(**event))

            # Collect content
            if event.get("type") == "content_delta":
                assistant_message_parts.append(event.get("content", ""))

        logger.info(f"=== ToT stream completed. Total events: {event_count} ===")

        # Save messages to session
        session_manager.add_message(
            session_id=request.session_id,
            role="user",
            content=request.message,
            images=request.images,
        )

        if assistant_message_parts:
            assistant_full_response = "".join(assistant_message_parts)
            session_manager.add_message(
                session_id=request.session_id,
                role="assistant",
                content=assistant_full_response,
            )
            logger.info(f"=== Saved assistant response: {len(assistant_full_response)} chars ===")

        # Trigger background memory extraction
        try:
            from app.config import get_settings
            settings = get_settings()
            if settings.enable_memory_extraction:
                asyncio.create_task(
                    _background_memory_extraction(request.session_id)
                )
        except Exception as e:
            logger.warning(f"Failed to trigger memory extraction: {e}")

    except Exception as e:
        logger.error(f"=== ToT stream generator error: {e} ===")
        import traceback
        logger.error(f"=== Traceback: {traceback.format_exc()} ===")
        yield format_sse_event(
            ChatEvent(
                type="error",
                error=str(e),
            )
        )


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
    # EARLY DEBUG: Verify function is being called
    import sys
    with open("I:\\code\\miniclaw\\chat_entry.log", "a", encoding="utf-8") as f:
        f.write(f"ENTER: chat() function at {__file__}\n")
        f.write(f"Message: {request.message[:100]}\n")
        f.write(f"Python version: {sys.version}\n")
        f.write("-" * 50 + "\n")

    print(f"[EARLY DEBUG] chat() function called with message: {request.message[:50]}")
    logger.info(f"[EARLY DEBUG] chat() function called with message: {request.message[:50]}")

    # Ensure skills are loaded
    bootstrap_skills()

    # === Retrieve relevant conversation history via semantic search ===
    semantic_history = ""
    try:
        from app.config import get_settings
        # get_settings() always returns fresh instance (no caching)
        settings = get_settings()

        # Only trigger semantic search for substantial queries (not simple greetings)
        message_len = len(request.message.strip())
        is_substantial_query = (
            message_len > 20 and  # At least 20 characters
            not request.message.strip() in ["你好", "hello", "hi", "嗨", "您好"] and  # Not simple greetings
            ("?" in request.message or "？" in request.message or  # Questions
             any(word in request.message.lower() for word in ["如何", "怎么", "什么", "为什么", "how", "what", "why", "how to"]))  # Complex queries
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

            # Try cache first if enabled
            relevant = None
            if settings.enable_semantic_search_cache:
                relevant = _get_cached_semantic_search(
                    request.message,
                    ttl=settings.semantic_search_cache_ttl
                )

            # Cache miss or disabled - perform search
            if relevant is None:
                # Search with relevance threshold
                relevant = await memory_manager.search_relevant_history(
                    request.message,
                    top_k=3
                )

                # Cache the result if enabled
                if settings.enable_semantic_search_cache and relevant is not None:
                    _set_cached_semantic_search(request.message, relevant)

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
                    # Format with specific content (not just type)
                    formatted_entries = []
                    for idx, r in enumerate(filtered_results, 1):
                        similarity = r.get('similarity', 0.0)
                        session_id = r.get('metadata', {}).get('session_id', 'unknown')
                        content = r['content']

                        # Truncate content if too long (show first 200 chars)
                        preview = content[:200] + "..." if len(content) > 200 else content

                        entry = f"""---
## Segment #{idx}
**Session**: {session_id} | **Relevance**: {similarity:.1%}

**Content Preview**:
{preview}

⚠️ *This is a historical conversation segment. Use it to understand the user's expression style and needs. Do NOT assume you need to "continue" this conversation.*
"""
                        formatted_entries.append(entry)

                    semantic_history = "\n".join(formatted_entries)
                    logger.info(f"Found {len(filtered_results)} relevant conversation chunks for query: {request.message[:50]}")
    except Exception as e:
        logger.warning(f"Semantic search failed: {e}")

    # === Extract conversation context from current session ===
    conversation_context = ""
    try:
        session_manager = get_session_manager()
        session = session_manager.load_session(request.session_id)

        if session is not None:
            session_messages = session.get("messages", [])
            if session_messages:
                # Try cache first if enabled
                from app.config import get_settings
                settings = get_settings()

                if settings.enable_context_cache:
                    conversation_context = _get_cached_conversation_context(
                        request.session_id,
                        session_messages
                    )

                # Cache miss or disabled - extract context
                if conversation_context is None:
                    conversation_context = _extract_conversation_context(session_messages)
                    logger.debug(f"Extracted conversation context from session")

                    # Cache the result if enabled
                    if settings.enable_context_cache:
                        _set_cached_conversation_context(
                            request.session_id,
                            session_messages,
                            conversation_context
                        )

                logger.info(f"[DEBUG] conversation_context length: {len(conversation_context)} chars")
                if conversation_context:
                    logger.info(f"[DEBUG] conversation_context preview:\n{conversation_context[:500]}")
    except Exception as e:
        logger.warning(f"Failed to extract conversation context: {e}")

    # Build system prompt with new session data structure
    try:
        logger.info(f"[DEBUG] Building system prompt with conversation_context of {len(conversation_context)} chars")
        if conversation_context:
            logger.info(f"[DEBUG] conversation_context:\n{conversation_context}")

        system_prompt = build_system_prompt(
            session_data={
                "user_context": request.context,
                "conversation_context": conversation_context,  # Current session context
                "semantic_history": semantic_history,          # Semantic search results
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build system prompt: {str(e)}",
        )

    # Get agent manager
    agent = get_agent_manager()

    # Check if ToT should be enabled for this request
    from app.config import get_settings
    settings = get_settings()

    # Check if ToT is enabled globally or per-request
    # Pydantic model: request.enable_tot will be None if not provided in request
    request_enable_tot = request.enable_tot
    logger.info(f"=== DEBUG: request.enable_tot={request_enable_tot} ===")

    if request_enable_tot is not None:
        # Per-request setting overrides global setting
        enable_tot = request_enable_tot
        logger.info(f"=== ToT per-request setting: enable_tot={enable_tot} ===")
    else:
        # Use global setting
        enable_tot = settings.enable_tot
        logger.info(f"=== Using global ToT setting: enable_tot={enable_tot} ===")

    # Force write to file to verify execution
    with open("I:\\code\\miniclaw\\tot_debug.log", "a", encoding="utf-8") as f:
        f.write(f"[DEBUG] ToT Config: enable_tot={enable_tot}\n")

    print(f"[DEBUG] === ToT Config: enable_tot={enable_tot} ===")
    logger.info(f"=== ToT Config: enable_tot={enable_tot} ===")

    # Check if query complexity requires ToT
    should_use_tot = False

    # Check if research mode is requested and determine thinking mode
    research_mode = None
    thinking_config = None
    custom_branching = None

    if request.context:
        research_mode = request.context.get("research_mode", None)
        # Read custom branching factor if provided
        custom_branching = request.context.get("branching_factor", None)

        if research_mode in settings.thinking_modes:
            thinking_config = settings.thinking_modes[research_mode]
            # Use custom branching factor if provided, otherwise use default
            branching = custom_branching if custom_branching else thinking_config['branching']
            logger.info(f"=== Thinking mode: {thinking_config['name']} (depth={thinking_config['depth']}, branching={branching}) ===")
            if custom_branching:
                logger.info(f"=== Custom branching factor: {custom_branching} ===")

    # Check if ToT is explicitly enabled per-request (force mode)
    is_force_tot = False

    # request_enable_tot was already set above
    logger.info(f"=== DEBUG: request_enable_tot={request_enable_tot}, type={type(request_enable_tot)} ===")

    if request_enable_tot is not None:
        logger.info(f"=== DEBUG: request_enable_tot is not None, value={request_enable_tot} ===")
        # If user explicitly sets enable_tot=True, force ToT regardless of complexity
        if request_enable_tot:
            logger.info("=== DEBUG: Setting force mode ===")
            is_force_tot = True
            should_use_tot = True
            logger.info("=== ToT explicitly enabled via request parameter (force mode) ===")
        else:
            logger.info(f"=== DEBUG: request_enable_tot is False ===")
    else:
        logger.info("=== DEBUG: request_enable_tot is None, using global setting ===")

    # For global enable_tot setting, still check complexity
    if enable_tot and not is_force_tot:
        from app.core.tot.router import TaskComplexityClassifier
        classifier = TaskComplexityClassifier()
        complexity = classifier.classify(request.message)
        should_use_tot = (complexity == "complex")
        logger.info(f"=== Query: '{request.message[:50]}...' ===")
        logger.info(f"=== Complexity: {complexity}, should_use_tot: {should_use_tot} ===")

    if research_mode:
        should_use_tot = True
        logger.info(f"=== Research mode '{research_mode}' requested, enabling ToT ===")

    logger.info(f"=== Final decision: should_use_tot={should_use_tot} ===")

    # Use ToT orchestrator for complex queries, otherwise use standard agent
    if should_use_tot:
        logger.info("=== Using ToT Orchestrator for complex query ===")
        try:
            from app.core.tot.router import ToTOrchestrator
            from app.core.tot.streaming import ToTEventStreamer

            # Determine ToT parameters based on thinking mode
            tot_depth = thinking_config['depth'] if thinking_config else settings.tot_max_depth
            # Use custom branching factor if provided, otherwise use config default
            tot_branching = custom_branching if custom_branching else (
                thinking_config['branching'] if thinking_config else settings.tot_branching_factor
            )

            logger.info(f"=== Creating ToTOrchestrator with depth={tot_depth}, branching={tot_branching} ===")
            orchestrator = ToTOrchestrator(
                agent_manager=agent,
                max_depth=tot_depth,
                branching_factor=tot_branching
            )
            logger.info("=== ToTOrchestrator created successfully ===")

            logger.info("=== Starting tot_stream_generator ===")
            response = StreamingResponse(
                tot_stream_generator(request, orchestrator, system_prompt),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
            logger.info("=== Returning ToT StreamingResponse ===")
            return response
        except Exception as e:
            logger.error(f"=== FAILED to create/use ToT Orchestrator: {e} ===")
            import traceback
            logger.error(f"=== Traceback: {traceback.format_exc()} ===")
            logger.info("=== Falling back to standard agent ===")
            # Fall through to standard agent below

    # Standard agent path (either should_use_tot=False or ToT failed)
    logger.info("=== Using standard Agent Manager ===")
    return StreamingResponse(
        chat_stream_generator(request, agent, system_prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
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
    except:
        agent_initialized = False

    # Count skills
    try:
        bootstrap = bootstrap_skills()
        bootstrap.scan_skills()
        skills_count = bootstrap.get_skill_count()
    except:
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

    except Exception as e:
        logger.error(f"Background memory extraction failed for {session_id}: {e}", exc_info=True)

