"""
Enhanced Error Handler for Agent Execution

This module provides centralized error handling with:
- Consecutive error detection
- Automatic termination on fatal errors
- User-friendly error messages
- Error recovery suggestions
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Error type enumeration"""
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    LLM_API_FAILED = "llm_api_failed"
    VALIDATION_ERROR = "validation_error"
    CONSECUTIVE_ERRORS = "consecutive_errors"
    MAX_TOTAL_ERRORS = "max_total_errors"
    MAX_ROUNDS_EXCEEDED = "max_rounds_exceeded"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class FatalError:
    """
    Fatal error data structure

    Attributes:
        message: User-friendly error message
        details: Detailed error information
        error_type: Error type (from ErrorType enum)
        suggestion: Suggested solution for the user
        can_retry: Whether the user can retry the operation
    """
    message: str
    details: str
    error_type: str
    suggestion: str
    can_retry: bool = True

    def to_sse_dict(self) -> dict:
        """
        Convert to SSE event format

        Returns:
            Dictionary compatible with SSE format
        """
        return {
            "type": "fatal_error",
            "data": {
                "message": self.message,
                "details": self.details,
                "error_type": self.error_type,
                "suggestion": self.suggestion,
                "can_retry": self.can_retry
            }
        }


class ErrorHandler:
    """
    Centralized error handler for agent execution

    Features:
    - Track consecutive and total errors
    - Detect fatal error conditions
    - Generate user-friendly error messages
    - Provide actionable suggestions
    """

    def __init__(self, max_consecutive_errors: int = 3, max_total_errors: int = 10):
        """
        Initialize error handler

        Args:
            max_consecutive_errors: Maximum consecutive errors before termination
            max_total_errors: Maximum total errors before termination
        """
        self.max_consecutive_errors = max_consecutive_errors
        self.max_total_errors = max_total_errors

        # Error tracking
        self.consecutive_errors = 0
        self.total_errors = 0
        self.error_history = []  # Keep last 10 errors

    async def handle_tool_error(
        self,
        tool_name: str,
        error: Exception,
        tool_args: dict
    ) -> dict:
        """
        Handle tool execution error

        Args:
            tool_name: Name of the tool that failed
            error: Exception that occurred
            tool_args: Arguments passed to the tool

        Returns:
            Error result dictionary
        """
        self.total_errors += 1
        self.consecutive_errors += 1

        # Record error in history
        error_record = {
            "tool_name": tool_name,
            "error": str(error),
            "error_type": type(error).__name__,
            "args": tool_args,
            "timestamp": __import__("time").time()
        }
        self.error_history.append(error_record)

        # Keep only last 10 errors
        if len(self.error_history) > 10:
            self.error_history.pop(0)

        # Log error with context
        logger.error(f"Tool {tool_name} failed: {error}")
        logger.debug(f"Tool args: {tool_args}")
        logger.debug(f"Consecutive errors: {self.consecutive_errors}/{self.max_consecutive_errors}")
        logger.debug(f"Total errors: {self.total_errors}/{self.max_total_errors}")

        # Return error result
        return {
            "error": True,
            "message": f"工具 {tool_name} 执行失败: {str(error)}",
            "tool_name": tool_name,
            "error_type": ErrorType.TOOL_EXECUTION_FAILED.value,
            "consecutive_errors": self.consecutive_errors,
            "total_errors": self.total_errors
        }

    async def handle_validation_error(
        self,
        tool_name: str,
        validation_error: Exception
    ) -> dict:
        """
        Handle Pydantic validation error

        Args:
            tool_name: Name of the tool with validation error
            validation_error: Validation exception

        Returns:
            Error result dictionary
        """
        self.total_errors += 1
        self.consecutive_errors += 1

        error_msg = str(validation_error)

        # Extract field names from validation error
        missing_fields = []
        if "Field required" in error_msg:
            import re
            fields = re.findall(r'(\w+)\s*\n\s*Field required', error_msg)
            missing_fields = fields

        logger.error(f"Validation error for {tool_name}: {error_msg}")
        logger.debug(f"Missing fields: {missing_fields}")

        return {
            "error": True,
            "message": f"工具 {tool_name} 参数验证失败",
            "details": f"缺少必填字段: {', '.join(missing_fields) if missing_fields else error_msg}",
            "tool_name": tool_name,
            "error_type": ErrorType.VALIDATION_ERROR.value,
            "missing_fields": missing_fields,
            "consecutive_errors": self.consecutive_errors,
            "total_errors": self.total_errors
        }

    async def check_fatal_error(self) -> Optional[FatalError]:
        """
        Check if fatal error threshold has been reached

        Returns:
            FatalError object if threshold reached, None otherwise
        """
        # Check consecutive error threshold
        if self.consecutive_errors >= self.max_consecutive_errors:
            # Get the most recent error for details
            last_error = self.error_history[-1] if self.error_history else None
            details = f"累计错误: {self.total_errors}"
            if last_error:
                details += f"\n最新错误: {last_error['tool_name']} - {last_error['error']}"

            return FatalError(
                message=f"连续 {self.consecutive_errors} 个工具执行失败",
                details=details,
                error_type=ErrorType.CONSECUTIVE_ERRORS.value,
                suggestion="请检查工具参数是否正确，或简化任务后重试。如果问题持续，请联系管理员。",
                can_retry=True
            )

        # Check total error threshold
        if self.total_errors >= self.max_total_errors:
            last_error = self.error_history[-1] if self.error_history else None
            details = f"连续错误: {self.consecutive_errors}"
            if last_error:
                details += f"\n最新错误: {last_error['tool_name']} - {last_error['error']}"

            return FatalError(
                message=f"累计 {self.total_errors} 个错误，超过阈值",
                details=details,
                error_type=ErrorType.MAX_TOTAL_ERRORS.value,
                suggestion="任务过于复杂或存在系统性问题。建议：\n1. 简化任务描述\n2. 检查知识库配置\n3. 切换到简单思维模式",
                can_retry=True
            )

        return None

    def reset_consecutive_errors(self):
        """
        Reset consecutive error counter after successful execution

        This should be called when a tool executes successfully
        """
        if self.consecutive_errors > 0:
            logger.debug(f"Resetting consecutive errors: {self.consecutive_errors} -> 0")
        self.consecutive_errors = 0

    def get_error_summary(self) -> dict:
        """
        Get summary of errors

        Returns:
            Dictionary with error statistics
        """
        # Count errors by tool
        tool_error_counts = {}
        for error_record in self.error_history:
            tool_name = error_record["tool_name"]
            tool_error_counts[tool_name] = tool_error_counts.get(tool_name, 0) + 1

        return {
            "consecutive_errors": self.consecutive_errors,
            "total_errors": self.total_errors,
            "tool_error_counts": tool_error_counts,
            "recent_errors": [
                {
                    "tool": e["tool_name"],
                    "error": e["error"],
                    "type": e["error_type"]
                }
                for e in self.error_history[-5:]  # Last 5 errors
            ]
        }

    def should_terminate(self) -> bool:
        """
        Check if execution should be terminated due to errors

        Returns:
            True if termination threshold reached
        """
        return (
            self.consecutive_errors >= self.max_consecutive_errors or
            self.total_errors >= self.max_total_errors
        )
