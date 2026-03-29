"""
Enhanced debug logger for streaming operations.

This module provides structured logging for streaming operations with:
- Detailed chunk structure logging
- Performance metrics
- Error context tracking
- Visual separators for easy reading
"""

import logging
import time
import asyncio
from typing import Any, Dict, Optional
from contextlib import asynccontextmanager


class StreamingDebugLogger:
    """
    Enhanced logger for streaming operations with structured output.

    Features:
    - Performance timing
    - Chunk structure analysis
    - Tool call tracking
    - Visual separators
    """

    def __init__(self, logger_name: str = "streaming_debug"):
        """Initialize the debug logger."""
        self.logger = logging.getLogger(logger_name)
        self.round_timings: Dict[int, Dict[str, float]] = {}

    def log_separator(self, title: str = "", level: int = logging.INFO):
        """Log a visual separator."""
        if title:
            separator = f"{'='*20} {title} {'='*20}"
        else:
            separator = f"{'='*60}"
        self.logger.log(level, separator)

    def log_chunk_structure(
        self,
        round_num: int,
        chunk_num: int,
        chunk: Any,
        elapsed: float
    ):
        """Log detailed chunk structure information."""
        self.logger.info(f"[Round {round_num}] [*] Chunk #{chunk_num} ({elapsed:.2f}s)")
        self.logger.info(f"[Round {round_num}]    Type: {type(chunk).__name__}")

        # Log attributes
        attrs = [attr for attr in dir(chunk) if not attr.startswith('_')]
        self.logger.info(f"[Round {round_num}]    Attributes: {attrs}")

        # Log content
        if hasattr(chunk, 'content'):
            content = chunk.content
            content_preview = str(content)[:100] if content else "None"
            content_len = len(str(content)) if content else 0
            self.logger.info(f"[Round {round_num}]    Content: {content_len} chars, preview: '{content_preview}'")

        # Log tool_calls
        if hasattr(chunk, 'tool_calls'):
            tool_calls = chunk.tool_calls
            if tool_calls:
                self.logger.info(f"[Round {round_num}]    [OK] tool_calls: {len(tool_calls)} items")
                for i, tc in enumerate(tool_calls):
                    if isinstance(tc, dict):
                        self.logger.info(f"[Round {round_num}]       [{i}] name={tc.get('name')}, args={tc.get('args')}")
                    else:
                        self.logger.info(f"[Round {round_num}]       [{i}] type={type(tc)}")
            else:
                self.logger.info(f"[Round {round_num}]    tool_calls: empty")

        # Log tool_call_chunks
        if hasattr(chunk, 'tool_call_chunks'):
            tcc = chunk.tool_call_chunks
            if tcc:
                self.logger.info(f"[Round {round_num}]    [TOOL] tool_call_chunks: {len(tcc)} items")
            else:
                self.logger.info(f"[Round {round_num}]    tool_call_chunks: empty")

    def log_streaming_summary(
        self,
        round_num: int,
        chunk_count: int,
        text_delta_count: int,
        tool_call_chunks_count: int,
        streaming_time: float,
        tool_calls_found: bool,
        llm_response_is_none: bool
    ):
        """Log streaming completion summary."""
        self.log_separator(f"Round {round_num} Streaming Complete", logging.INFO)
        self.logger.info(f"[Round {round_num}] [*] Streaming Summary:")
        self.logger.info(f"[Round {round_num}]    Total chunks: {chunk_count}")
        self.logger.info(f"[Round {round_num}]    Text deltas: {text_delta_count}")
        self.logger.info(f"[Round {round_num}]    Tool call chunks: {tool_call_chunks_count}")
        self.logger.info(f"[Round {round_num}]    Streaming time: {streaming_time:.2f}s")
        self.logger.info(f"[Round {round_num}]    Tool calls found: {tool_calls_found}")
        self.logger.info(f"[Round {round_num}]    llm_response is None: {llm_response_is_none}")

        if llm_response_is_none:
            self.logger.warning(f"[Round {round_num}] [!] WARNING: llm_response is None!")
            self.logger.warning(f"[Round {round_num}]    This indicates:")
            self.logger.warning(f"[Round {round_num}]    - LLM returned empty response, OR")
            self.logger.warning(f"[Round {round_num}]    - No chunk had tool_calls attribute, OR")
            self.logger.warning(f"[Round {round_num}]    - All chunks had empty tool_calls")

    def log_tool_call_validation(
        self,
        round_num: int,
        tool_calls_count: int,
        validated_count: int,
        skipped_details: Optional[list] = None
    ):
        """Log tool call validation results."""
        self.logger.info(f"[Round {round_num}] [*] Tool Call Validation:")
        self.logger.info(f"[Round {round_num}]    Input: {tool_calls_count} tool calls")
        self.logger.info(f"[Round {round_num}]    Validated: {validated_count} tool calls")

        if validated_count < tool_calls_count:
            self.logger.warning(f"[Round {round_num}]    [!] Skipped: {tool_calls_count - validated_count} tool calls")
            if skipped_details:
                for detail in skipped_details:
                    self.logger.warning(f"[Round {round_num}]       - {detail}")

    def log_round_summary(
        self,
        round_num: int,
        duration: float,
        tool_calls_executed: int,
        success: bool = True
    ):
        """Log round completion summary."""
        status = "[OK] SUCCESS" if success else "[FAIL] FAILED"
        self.log_separator(f"Round {round_num} Complete", logging.INFO)
        self.logger.info(f"[Round {round_num}] {status}")
        self.logger.info(f"[Round {round_num}]    Duration: {duration:.2f}s")
        self.logger.info(f"[Round {round_num}]    Tool calls executed: {tool_calls_executed}")

        # Store timing
        self.round_timings[round_num] = {
            "duration": duration,
            "tool_calls": tool_calls_executed
        }

    def log_error_context(
        self,
        round_num: int,
        error: Exception,
        context: Dict[str, Any]
    ):
        """Log error with full context."""
        self.log_separator(f"ERROR in Round {round_num}", logging.ERROR)
        self.logger.error(f"[Round {round_num}] [ERROR] Error: {type(error).__name__}")
        self.logger.error(f"[Round {round_num}]    Message: {str(error)}")
        self.logger.error(f"[Round {round_num}]    Context:")
        for key, value in context.items():
            self.logger.error(f"[Round {round_num}]       {key}: {value}")

    @asynccontextmanager
    async def timed_operation(self, operation_name: str, round_num: int):
        """Context manager for timing operations."""
        start_time = asyncio.get_event_loop().time()
        self.logger.info(f"[Round {round_num}] [TIME] Starting: {operation_name}")
        try:
            yield
        finally:
            duration = asyncio.get_event_loop().time() - start_time
            self.logger.info(f"[Round {round_num}] [OK] Completed: {operation_name} ({duration:.2f}s)")


# Global instance
_streaming_logger = StreamingDebugLogger()


def get_streaming_logger() -> StreamingDebugLogger:
    """Get the global streaming debug logger."""
    return _streaming_logger
