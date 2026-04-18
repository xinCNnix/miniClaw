"""Error context logger that captures additional context around exceptions."""

import logging
import traceback
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ErrorContextLogger:
    """Logger that captures structured error context for better debugging."""

    def __init__(self, logger_name: str = __name__):
        self._logger = logging.getLogger(logger_name)

    def log_exception(
        self,
        message: str,
        exception: Exception,
        context: Optional[dict[str, Any]] = None,
        level: int = logging.ERROR,
    ) -> dict:
        """Log an exception with structured context.

        Returns a structured error dict for further processing.
        """
        error_info = {
            "error_type": type(exception).__name__,
            "error_message": str(exception),
            "traceback": traceback.format_exc(),
            "context": context or {},
        }

        log_message = (
            f"{message} | type={error_info['error_type']} "
            f"msg={error_info['error_message']}"
        )
        if context:
            # Summarize context keys for log readability
            ctx_keys = ", ".join(context.keys())
            log_message += f" context=[{ctx_keys}]"

        self._logger.log(level, log_message, exc_info=True)

        return error_info

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._logger.critical(msg, *args, **kwargs)


def get_error_context_logger(name: str) -> ErrorContextLogger:
    """Factory function for ErrorContextLogger."""
    return ErrorContextLogger(name)
