"""
Logging Configuration Module

This module sets up detailed logging for the backend application.
Logs are written to both console and rotating log files.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from app.config import get_settings


class SafeConsoleHandler(logging.StreamHandler):
    """
    Console handler that safely handles Unicode characters on Windows.

    Windows console uses GBK encoding by default, which cannot handle
    certain Unicode characters (e.g., zero-width characters like \\u200c).
    This handler replaces unencodable characters instead of crashing.
    """

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream

            # Safely encode and write message
            # Use 'replace' to substitute unencodable chars with '?'
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                # Fallback: encode with 'replace' error handler
                safe_msg = msg.encode(stream.encoding or 'utf-8', errors='replace').decode(stream.encoding or 'utf-8')
                stream.write(safe_msg + self.terminator)

            self.flush()
        except Exception:
            self.handleError(record)


def setup_logging(
    log_level: str = None,
    log_dir: str = None,
    log_to_file: bool = True,
    log_to_console: bool = True,
):
    """
    Set up application logging with file and console handlers.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        log_to_file: Enable file logging
        log_to_console: Enable console logging
    """
    settings = get_settings()

    # Use settings if not provided
    if log_level is None:
        log_level = settings.log_level
    if log_dir is None:
        log_dir = settings.log_dir

    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        fmt=settings.log_format,
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (with Unicode-safe handling for Windows)
    if log_to_console:
        console_handler = SafeConsoleHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler (rotating)
    if log_to_file:
        file_handler = RotatingFileHandler(
            filename=log_path / "backend.log",
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Separate file for agent execution (always DEBUG level)
    agent_handler = RotatingFileHandler(
        filename=log_path / "agent.log",
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    agent_handler.setLevel(logging.DEBUG)
    agent_handler.setFormatter(formatter)

    # Create agent-specific logger
    agent_logger = logging.getLogger("agent")
    agent_logger.setLevel(logging.DEBUG)
    agent_logger.addHandler(agent_handler)
    # Also add to root if needed
    if log_to_console:
        agent_logger.addHandler(console_handler)

    # Configure specific loggers
    _configure_specific_loggers()

    logging.info("Logging system initialized")
    logging.info(f"Log level: {log_level}")
    logging.info(f"Log directory: {log_path.absolute()}")
    if settings.debug_agent:
        logging.info("DEBUG AGENT mode is ENABLED - detailed agent execution will be logged")


def _configure_specific_loggers():
    """Configure logging levels for specific modules."""
    settings = get_settings()

    # Set detailed logging for agent-related modules
    agent_modules = [
        "app.api.chat",
        "app.core.agent",
        "app.tools",
    ]

    if settings.debug_agent:
        for module in agent_modules:
            logging.getLogger(module).setLevel(logging.DEBUG)


def get_agent_logger(name: str = "agent") -> logging.Logger:
    """
    Get a logger for agent execution tracking.

    Args:
        name: Logger name (default: "agent")

    Returns:
        Logger instance that outputs to agent.log and console
    """
    logger = logging.getLogger(name)

    # Ensure the logger has the same handlers as the "agent" logger
    # This is important for child loggers like "agent.executor"
    agent_root = logging.getLogger("agent")
    if not logger.handlers:
        for handler in agent_root.handlers:
            logger.addHandler(handler)
    logger.setLevel(agent_root.level)

    return logger


class AgentExecutionLogger:
    """
    Context manager for logging agent execution details.

    Usage:
        with AgentExecutionLogger("task_name") as logger:
            logger.log_input(user_message)
            # ... execute ...
            logger.log_output(response)
    """

    def __init__(self, task_name: str):
        """
        Initialize agent execution logger.

        Args:
            task_name: Name of the task being executed
        """
        self.task_name = task_name
        self.logger = get_agent_logger()

    def __enter__(self):
        """Start execution logging."""
        self.logger.info("=" * 80)
        self.logger.info(f"AGENT EXECUTION START: {self.task_name}")
        self.logger.info("=" * 80)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End execution logging."""
        if exc_type is not None:
            self.logger.error(f"AGENT EXECUTION FAILED: {self.task_name}")
            self.logger.error(f"Error: {exc_val}", exc_info=True)
        else:
            self.logger.info("=" * 80)
            self.logger.info(f"AGENT EXECUTION COMPLETE: {self.task_name}")
            self.logger.info("=" * 80)
        self.logger.info("")  # Empty line for readability

    def log_input(self, messages: list, system_prompt: str):
        """Log agent input."""
        self.logger.debug(f"Input messages count: {len(messages)}")
        self.logger.debug(f"System prompt length: {len(system_prompt)} chars")
        self.logger.debug(f"System prompt preview: {system_prompt[:500]}...")

        for i, msg in enumerate(messages[-3:]):  # Last 3 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            self.logger.debug(f"Message {i+1} [{role}]: {content[:200]}...")

    def log_tool_call(self, tool_name: str, tool_args: dict):
        """Log tool invocation."""
        self.logger.info(f"TOOL CALL: {tool_name}")
        self.logger.debug(f"Arguments: {tool_args}")

    def log_tool_result(self, tool_name: str, result: str, success: bool, duration: float = None):
        """Log tool result."""
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"TOOL RESULT: {tool_name} - {status}")
        if duration:
            self.logger.debug(f"Duration: {duration:.2f}s")

        # Log result preview
        result_preview = result[:500] if result else ""
        self.logger.debug(f"Result preview: {result_preview}...")

        # Log result size
        result_size = len(result) if result else 0
        self.logger.debug(f"Result size: {result_size} chars")

    def log_llm_response(self, response_content: str, tool_calls: list = None):
        """Log LLM response."""
        self.logger.info(f"LLM RESPONSE: {len(response_content)} chars")
        self.logger.debug(f"Content preview: {response_content[:300]}...")

        if tool_calls:
            self.logger.info(f"Tool calls requested: {len(tool_calls)}")
            for tc in tool_calls:
                tc_name = tc.get("name", "unknown")
                tc_args = tc.get("args", {})
                self.logger.debug(f"  - {tc_name}: {str(tc_args)[:200]}...")

    def log_final_output(self, output: str):
        """Log final agent output."""
        self.logger.info(f"FINAL OUTPUT: {len(output)} chars")
        self.logger.debug(f"Output content: {output}")
