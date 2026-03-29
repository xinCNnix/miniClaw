"""
Structured Logging Formatter Module

This module provides structured logging formatters that support both
traditional text format and JSON format for better log analysis and querying.
"""

import json
import logging
import time
from typing import Any, Dict, Optional
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """
    Base class for structured formatters with automatic context injection.

    Features:
    - ISO 8601 timestamp
    - Automatic context injection (request_id, session_id, user_id)
    - Custom field support
    - Compatible with existing text format
    """

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        style: str = '%',
        validate: bool = True,
        context_fields: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize structured formatter.

        Args:
            fmt: Format string (for text fallback)
            datefmt: Date format string
            style: Format style (% { $)
            validate: Validate format string
            context_fields: Default context fields to include
        """
        super().__init__(fmt, datefmt, style, validate)
        self.context_fields = context_fields or {}
        self.default_context = {}

    def add_context_field(self, key: str, value: Any) -> None:
        """
        Add a default context field.

        Args:
            key: Field name
            value: Field value
        """
        self.context_fields[key] = value

    def set_default_context(self, context: Dict[str, Any]) -> None:
        """
        Set default context for all log records.

        Args:
            context: Context dictionary
        """
        self.default_context = context.copy()

    def get_timestamp(self, record: logging.LogRecord) -> str:
        """
        Get ISO 8601 timestamp from log record.

        Args:
            record: Log record

        Returns:
            ISO 8601 formatted timestamp
        """
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return timestamp.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def get_context(self, record: logging.LogRecord) -> Dict[str, Any]:
        """
        Extract context from log record.

        Args:
            record: Log record

        Returns:
            Context dictionary
        """
        context = self.default_context.copy()
        context.update(self.context_fields)

        # Extract tracking context
        if hasattr(record, 'request_id') and record.request_id:
            context['request_id'] = record.request_id
        if hasattr(record, 'session_id') and record.session_id:
            context['session_id'] = record.session_id
        if hasattr(record, 'user_id') and record.user_id:
            context['user_id'] = record.user_id

        # Extract any additional custom fields
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                'relativeCreated', 'thread', 'threadName', 'processName',
                'process', 'getMessage', 'exc_info', 'exc_text', 'stack_info',
                'request_id', 'session_id', 'user_id', 'message'
            }:
                # Only include serializable values
                try:
                    json.dumps(value)
                    context[key] = value
                except (TypeError, ValueError):
                    # Skip non-serializable values
                    pass

        return context

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record (base implementation uses text format).

        Args:
            record: Log record

        Returns:
            Formatted log string
        """
        # Default to text format
        return super().format(record)


class JSONFormatter(StructuredFormatter):
    """
    JSON formatter for structured logging.

    Output format:
    {
      "timestamp": "2026-03-21T10:30:45.123Z",
      "level": "ERROR",
      "logger": "app.tools.terminal",
      "message": "Command execution failed",
      "context": {
        "request_id": "abc12345",
        "session_id": "sess_678",
        "user_id": "user_001"
      },
      "error": {
        "type": "ValueError",
        "message": "Command contains blocked pattern",
        "traceback": "..."
      },
      "performance": {
        "duration_ms": 1234
      }
    }
    """

    def __init__(
        self,
        context_fields: Optional[Dict[str, Any]] = None,
        indent: Optional[bool] = None,
        ensure_ascii: bool = False
    ):
        """
        Initialize JSON formatter.

        Args:
            context_fields: Default context fields
            indent: JSON indentation (None for compact, True for pretty)
            ensure_ascii: Ensure ASCII encoding (False for UTF-8)
        """
        super().__init__(context_fields=context_fields)
        self.indent = 2 if indent else None
        self.ensure_ascii = ensure_ascii

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record

        Returns:
            JSON formatted log string
        """
        log_entry = {
            "timestamp": self.get_timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context
        context = self.get_context(record)
        if context:
            log_entry["context"] = context

        # Add error information
        if record.exc_info:
            log_entry["error"] = self._format_error(record)

        # Add performance data if available
        if hasattr(record, 'duration_ms'):
            log_entry["performance"] = {
                "duration_ms": record.duration_ms
            }
        if hasattr(record, 'memory_mb'):
            if "performance" not in log_entry:
                log_entry["performance"] = {}
            log_entry["performance"]["memory_mb"] = record.memory_mb

        # Add location info
        log_entry["location"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
            "module": record.module
        }

        # Add thread/process info for DEBUG level
        if record.levelno <= logging.DEBUG:
            log_entry["process"] = {
                "id": record.process,
                "name": record.processName
            }
            log_entry["thread"] = {
                "id": record.thread,
                "name": record.threadName
            }

        # Serialize to JSON
        try:
            return json.dumps(
                log_entry,
                indent=self.indent,
                ensure_ascii=self.ensure_ascii,
                default=self._json_serializer
            )
        except Exception as e:
            # Fallback to simple format if JSON serialization fails
            return json.dumps({
                "timestamp": log_entry["timestamp"],
                "level": log_entry["level"],
                "logger": log_entry["logger"],
                "message": log_entry["message"],
                "error": f"JSON serialization failed: {e}"
            })

    def _format_error(self, record: logging.LogRecord) -> Dict[str, Any]:
        """
        Format exception information from log record.

        Args:
            record: Log record

        Returns:
            Error information dictionary
        """
        error_info = {}

        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            error_info["type"] = exc_type.__name__ if exc_type else "Unknown"
            error_info["message"] = str(exc_value) if exc_value else ""

            # Format traceback
            if record.exc_text:
                error_info["traceback"] = record.exc_text
            else:
                import traceback
                error_info["traceback"] = "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                )

        return error_info

    def _json_serializer(self, obj: Any) -> Any:
        """
        Custom JSON serializer for non-serializable objects.

        Args:
            obj: Object to serialize

        Returns:
            Serializable representation
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return str(obj)


class TextStructuredFormatter(StructuredFormatter):
    """
    Text formatter with structured context injection.

    Output format:
    2026-03-21T10:30:45.123Z [ERROR] [RID:abc12345] app.tools.terminal - Command execution failed
    """

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        style: str = '%',
        include_timestamp: bool = True,
        include_context: bool = True
    ):
        """
        Initialize text structured formatter.

        Args:
            fmt: Custom format string (overrides auto-format)
            datefmt: Date format string
            style: Format style
            include_timestamp: Include ISO timestamp
            include_context: Include context in format
        """
        # Build default format
        if fmt is None:
            fmt_parts = []
            if include_timestamp:
                fmt_parts.append('%(asctime)s')
            fmt_parts.append('[%(levelname)s]')
            if include_context:
                fmt_parts.append('[RID:%(request_id)s]')
            fmt_parts.append('%(name)s - %(message)s')
            fmt = ' '.join(fmt_parts)

        # Use ISO format for timestamp
        if datefmt is None:
            datefmt = '%Y-%m-%dT%H:%M:%S'

        super().__init__(fmt, datefmt, style, validate=True)
        self.include_timestamp = include_timestamp
        self.include_context = include_context

        # Override formatTime to use ISO format
        if include_timestamp:
            self.formatTime = self._format_time_iso

    def _format_time_iso(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        """
        Format time as ISO 8601.

        Args:
            record: Log record
            datefmt: Date format (ignored, always ISO)

        Returns:
            ISO 8601 formatted timestamp
        """
        return self.get_timestamp(record)

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as structured text.

        Args:
            record: Log record

        Returns:
            Formatted log string
        """
        # Ensure request_id is in record for formatting
        if self.include_context and not hasattr(record, 'request_id'):
            record.request_id = getattr(record, 'request_id', 'N/A')

        formatted = super().format(record)

        # Append exception info if present
        if record.exc_info:
            formatted += '\n' + self.formatException(record.exc_info)

        # Append stack trace if present
        if record.stack_info:
            formatted += '\n' + self.formatStack(record.stack_info)

        return formatted


class SanitizingFormatterWrapper:
    """
    Wrapper that adds sanitization to any formatter.

    Usage:
        base_formatter = JSONFormatter()
        formatter = SanitizingFormatterWrapper(base_formatter, sanitizer)
    """

    def __init__(self, base_formatter: logging.Formatter, sanitizer):
        """
        Initialize sanitizing wrapper.

        Args:
            base_formatter: Base formatter to wrap
            sanitizer: LogSanitizer instance
        """
        self.base_formatter = base_formatter
        self.sanitizer = sanitizer

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with sanitization.

        Args:
            record: Log record

        Returns:
            Formatted and sanitized log string
        """
        # Sanitize record before formatting
        if self.sanitizer and self.sanitizer.enabled:
            record = self.sanitizer.sanitize_log_record(record)

        # Format with base formatter
        return self.base_formatter.format(record)

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to base formatter."""
        return getattr(self.base_formatter, name)
