"""
Agent Stream Coordinator

协调 LLM 流式响应和工具调用组装。

Author: Task 3.1 Implementation
Created: 2026-03-22
"""

import logging
from collections.abc import AsyncIterator

from langchain_core.language_models import BaseChatModel

from app.core.exceptions import LLMError

from .tool_assembler import ToolCallAssembler

logger = logging.getLogger(__name__)


class AgentStreamCoordinator:
    """
    协调 LLM 流式响应。

    职责：
    - 封装 LLM.astream() 调用
    - 实时转发内容增量
    - 转发工具调用增量到 assembler
    - 提供流式生命周期事件
    """

    def __init__(
        self,
        llm: BaseChatModel,
        assembler: ToolCallAssembler,
        callbacks: list = None,
    ) -> None:
        """
        初始化协调器。

        Args:
            llm: LLM 实例
            assembler: ToolCallAssembler 实例
            callbacks: Optional list of callback handlers
        """
        self.llm = llm
        self.assembler = assembler
        self.callbacks = callbacks
        logger.info("[COORDINATOR] Initialized with LLM and assembler")

    async def stream_response(
        self,
        messages: list[dict],
        callbacks: list = None,
    ) -> AsyncIterator[dict]:
        """
        流式处理 LLM 响应。

        Args:
            messages: 对话消息列表
            callbacks: Optional list of callback handlers (overrides instance callbacks)

        Yields:
            事件字典，包含：
            - llm_stream_start: 流开始
            - content_delta: 内容增量
            - tool_call_delta: 工具调用增量
            - llm_stream_end: 流结束
            - stream_error: 流错误

        Raises:
            LLMError: 如果 LLM 流式响应失败
        """
        logger.info(f"[COORDINATOR] Starting LLM stream with {len(messages)} messages")
        yield {"type": "llm_stream_start"}

        chunk_count = 0
        total_content_chars = 0
        tool_call_count = 0

        # Prepare config with callbacks
        config = {}
        callbacks_to_use = callbacks or self.callbacks
        if callbacks_to_use:
            config["callbacks"] = callbacks_to_use

        try:
            # 调用 LLM 的流式接口
            async for chunk in self.llm.astream(
                messages,
                config=config if config else None
            ):
                chunk_count += 1

                # 转发给 assembler 进行工具调用组装
                try:
                    self.assembler.add_chunk(chunk)
                except Exception as e:
                    logger.error(f"[COORDINATOR] Assembler error processing chunk: {e}", exc_info=True)
                    # 继续处理，不中断流

                # 转发内容增量
                if hasattr(chunk, 'content') and chunk.content:
                    content_str = str(chunk.content)
                    total_content_chars += len(content_str)
                    yield {
                        "type": "content_delta",
                        "content": content_str
                    }
                    logger.debug(f"[COORDINATOR] Content delta: {len(content_str)} chars")

                # 转发工具调用增量
                if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        tool_call_count += 1
                        yield {
                            "type": "tool_call_delta",
                            "name": tc.get("name"),
                            "args": tc.get("args"),
                            "index": tc.get("index"),
                            "id": tc.get("id")
                        }
                        logger.debug(f"[COORDINATOR] Tool call delta: {tc.get('name')}")

            logger.info(
                f"[COORDINATOR] Stream completed: {chunk_count} chunks, "
                f"{total_content_chars} content chars, {tool_call_count} tool calls"
            )
            yield {"type": "llm_stream_end"}

        except LLMError:
            # Re-raise LLM errors as-is
            raise
        except Exception as e:
            logger.error(f"[COORDINATOR] Stream error: {e}", exc_info=True)
            yield {
                "type": "stream_error",
                "error": str(e),
                "error_type": type(e).__name__
            }
            # Also raise as LLMError for consistent error handling
            raise LLMError(
                message=f"LLM streaming failed: {e}",
                original_error=e
            ) from e

    def reset(self) -> None:
        """
        重置协调器状态。

        注意：这会重置关联的 assembler。
        """
        self.assembler.reset()
        logger.debug("[COORDINATOR] Reset state")
