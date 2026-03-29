"""
Error Context Logger Module

This module provides enhanced error logging with full context capture,
including call stacks, local variables, and error aggregation.
"""

import logging
import traceback
import hashlib
import time
from typing import Any, Dict, Optional, List, Callable
from datetime import datetime, timezone
from collections import defaultdict


class ErrorContextLogger:
    """
    Enhanced error logger with full context capture.

    Features:
    - Automatic call stack capture
    - Optional local variable capture
    - Error signature generation for aggregation
    - Request/session correlation
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        capture_locals: bool = False,
        max_local_vars: int = 10,
        max_stack_depth: int = 10
    ):
        """
        Initialize error context logger.

        Args:
            logger: Base logger to use
            capture_locals: Capture local variables (use with caution)
            max_local_vars: Maximum local variables to capture
            max_stack_depth: Maximum stack depth to capture
        """
        self.logger = logger or logging.getLogger(__name__)
        self.capture_locals = capture_locals
        self.max_local_vars = max_local_vars
        self.max_stack_depth = max_stack_depth

    def log_exception(
        self,
        exc: Exception,
        level: int = logging.ERROR,
        **context
    ) -> None:
        """
        Log exception with full context.

        Args:
            exc: Exception to log
            level: Log level (default: ERROR)
            **context: Additional context information
        """
        # Get error signature
        signature = self.get_error_signature(exc)

        # Build error context
        error_context = {
            "signature": signature,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context.copy()
        }

        # Capture stack info
        stack_info = self._capture_stack_info()
        if stack_info:
            error_context["stack"] = stack_info

        # Capture locals if enabled
        if self.capture_locals:
            locals_info = self._capture_locals()
            if locals_info:
                error_context["locals"] = locals_info

        # Log with structured data
        self.logger.log(
            level,
            f"Exception caught: {type(exc).__name__}: {exc}",
            extra={"error_context": error_context}
        )

    def log_error(
        self,
        message: str,
        level: int = logging.ERROR,
        **context
    ) -> None:
        """
        Log error message with context.

        Args:
            message: Error message
            level: Log level (default: ERROR)
            **context: Additional context information
        """
        error_context = {
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context.copy()
        }

        # Capture caller info
        caller_info = self._get_caller_info()
        if caller_info:
            error_context["caller"] = caller_info

        self.logger.log(
            level,
            message,
            extra={"error_context": error_context}
        )

    def get_error_signature(self, exc: Exception) -> str:
        """
        Generate unique signature for error type and message.

        Args:
            exc: Exception

        Returns:
            Error signature (hash)
        """
        # Create signature from error type and message
        signature_str = f"{type(exc).__name__}:{str(exc)}"
        return hashlib.md5(signature_str.encode()).hexdigest()[:12]

    def capture_locals(
        self,
        frame,
        max_depth: int = 5
    ) -> Dict[str, Any]:
        """
        Capture local variables from frame.

        Args:
            frame: Stack frame
            max_depth: Maximum depth to traverse

        Returns:
            Dictionary of captured locals
        """
        locals_dict = {}

        try:
            # Get local variables
            local_vars = frame.f_locals

            # Limit number of variables
            for i, (key, value) in enumerate(local_vars.items()):
                if i >= self.max_local_vars:
                    break

                # Try to serialize value
                try:
                    # Convert to string representation
                    str_value = str(value)

                    # Truncate long values
                    if len(str_value) > 500:
                        str_value = str_value[:500] + "..."

                    # Try to get type info
                    type_name = type(value).__name__

                    locals_dict[key] = {
                        "type": type_name,
                        "value": str_value,
                        "size": len(str_value) if isinstance(value, (str, list, dict)) else None
                    }

                    # For lists/dicts, include length
                    if isinstance(value, (list, dict)):
                        locals_dict[key]["length"] = len(value)

                except Exception:
                    # Skip values that can't be converted
                    locals_dict[key] = {
                        "type": "unknown",
                        "value": "<unrepresentable>"
                    }

        except Exception as e:
            locals_dict["_error"] = f"Failed to capture locals: {e}"

        return locals_dict

    def _capture_stack_info(self) -> List[Dict[str, Any]]:
        """
        Capture current stack trace.

        Returns:
            List of stack frame information
        """
        stack_info = []

        try:
            stack = traceback.extract_stack()

            # Limit depth
            for frame in stack[-self.max_stack_depth:]:
                stack_info.append({
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                    "code": frame.line
                })

        except Exception as e:
            stack_info.append({"error": f"Failed to capture stack: {e}"})

        return stack_info

    def _capture_locals(self) -> Optional[Dict[str, Any]]:
        """
        Capture local variables from current frame.

        Returns:
            Dictionary of local variables or None
        """
        try:
            import inspect
            frame = inspect.currentframe()

            if frame and frame.f_back:
                return self.capture_locals(frame.f_back)

            return None

        except Exception:
            return None

    def _get_caller_info(self) -> Optional[Dict[str, str]]:
        """
        Get information about the calling function.

        Returns:
            Caller information dictionary or None
        """
        try:
            import inspect
            frame = inspect.currentframe()

            if frame and frame.f_back:
                caller_frame = frame.f_back
                return {
                    "file": caller_frame.f_code.co_filename,
                    "line": caller_frame.f_lineno,
                    "function": caller_frame.f_code.co_name
                }

            return None

        except Exception:
            return None


class ErrorAggregator:
    """
    Aggregates errors for analysis and alerting.

    Features:
    - Error frequency tracking
    - Error type grouping
    - Alert threshold checking
    - Time-window based aggregation
    """

    def __init__(
        self,
        alert_threshold: int = 10,
        time_window: int = 60
    ):
        """
        Initialize error aggregator.

        Args:
            alert_threshold: Threshold for triggering alerts
            time_window: Time window in seconds for aggregation
        """
        self.alert_threshold = alert_threshold
        self.time_window = time_window

        # Error tracking
        self.errors_by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.errors_by_signature: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.total_errors = 0

        # Timestamp tracking
        self.start_time = time.time()

    def add_error(
        self,
        error_type: str,
        signature: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add an error to the aggregation.

        Args:
            error_type: Error type name
            signature: Error signature (from ErrorContextLogger)
            message: Error message
            context: Additional context
        """
        error_record = {
            "timestamp": time.time(),
            "type": error_type,
            "signature": signature,
            "message": message,
            "context": context or {}
        }

        # Track by type
        self.errors_by_type[error_type].append(error_record)

        # Track by signature
        self.errors_by_signature[signature].append(error_record)

        # Increment total
        self.total_errors += 1

        # Clean old errors outside time window
        self._cleanup_old_errors()

    def should_alert(self, error_type: Optional[str] = None) -> bool:
        """
        Check if error count exceeds threshold.

        Args:
            error_type: Specific error type to check (None = all errors)

        Returns:
            True if should alert
        """
        if error_type:
            return len(self.errors_by_type[error_type]) >= self.alert_threshold
        else:
            return self.total_errors >= self.alert_threshold

    def get_error_stats(self, error_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get error statistics.

        Args:
            error_type: Specific error type (None = all errors)

        Returns:
            Statistics dictionary
        """
        if error_type:
            errors = self.errors_by_type[error_type]
            return {
                "type": error_type,
                "count": len(errors),
                "unique_signatures": len(set(e["signature"] for e in errors)),
                "latest_error": errors[-1] if errors else None
            }
        else:
            # Aggregate all types
            return {
                "total_errors": self.total_errors,
                "unique_types": len(self.errors_by_type),
                "unique_signatures": len(self.errors_by_signature),
                "errors_by_type": {
                    error_type: len(errors)
                    for error_type, errors in self.errors_by_type.items()
                },
                "uptime_seconds": time.time() - self.start_time
            }

    def aggregate_errors(self, time_window: Optional[int] = None) -> Dict[str, Any]:
        """
        Aggregate errors within time window.

        Args:
            time_window: Time window in seconds (None = use default)

        Returns:
            Aggregated error data
        """
        window = time_window or self.time_window
        cutoff_time = time.time() - window

        # Filter errors within time window
        recent_errors = {
            error_type: [
                e for e in errors
                if e["timestamp"] >= cutoff_time
            ]
            for error_type, errors in self.errors_by_type.items()
        }

        # Calculate statistics
        aggregated = {
            "time_window": window,
            "total_errors": sum(len(errors) for errors in recent_errors.values()),
            "errors_by_type": {
                error_type: len(errors)
                for error_type, errors in recent_errors.items()
            },
            "error_rate_per_minute": {},
            "top_errors": []
        }

        # Calculate error rates
        for error_type, errors in recent_errors.items():
            if len(errors) > 0:
                rate = (len(errors) / window) * 60
                aggregated["error_rate_per_minute"][error_type] = round(rate, 2)

        # Top errors by frequency
        sorted_errors = sorted(
            recent_errors.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        aggregated["top_errors"] = [
            {"type": error_type, "count": len(errors)}
            for error_type, errors in sorted_errors[:10]
        ]

        return aggregated

    def _cleanup_old_errors(self) -> None:
        """Remove errors outside the time window."""
        cutoff_time = time.time() - self.time_window

        # Clean by type
        for error_type in list(self.errors_by_type.keys()):
            self.errors_by_type[error_type] = [
                e for e in self.errors_by_type[error_type]
                if e["timestamp"] >= cutoff_time
            ]

            # Remove empty entries
            if not self.errors_by_type[error_type]:
                del self.errors_by_type[error_type]

        # Clean by signature
        for signature in list(self.errors_by_signature.keys()):
            self.errors_by_signature[signature] = [
                e for e in self.errors_by_signature[signature]
                if e["timestamp"] >= cutoff_time
            ]

            if not self.errors_by_signature[signature]:
                del self.errors_by_signature[signature]

    def reset(self) -> None:
        """Reset all error tracking."""
        self.errors_by_type.clear()
        self.errors_by_signature.clear()
        self.total_errors = 0
        self.start_time = time.time()


class AlertRule:
    """
    Alert rule definition.

    Args:
        name: Rule name
        condition: Function that evaluates if rule should trigger
        threshold: Threshold value
        window: Time window in seconds
        channels: List of channel names to send alerts to
    """

    def __init__(
        self,
        name: str,
        condition: Optional[Callable[[logging.LogRecord], bool]] = None,
        threshold: int = 10,
        window: int = 60,
        channels: Optional[List[str]] = None
    ):
        self.name = name
        self.condition = condition or (lambda record: record.levelno >= logging.ERROR)
        self.threshold = threshold
        self.window = window
        self.channels = channels or ["console"]


# Global error aggregator instance
_global_error_aggregator: Optional[ErrorAggregator] = None


def get_error_aggregator() -> ErrorAggregator:
    """
    Get the global error aggregator instance.

    Returns:
        ErrorAggregator instance
    """
    global _global_error_aggregator
    if _global_error_aggregator is None:
        _global_error_aggregator = ErrorAggregator()
    return _global_error_aggregator
