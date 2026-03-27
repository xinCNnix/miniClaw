"""
Logging Configuration Module

This module sets up detailed logging for the backend application.
Logs are written to both console and rotating log files.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional
from app.config import get_settings


class LevelFilter(logging.Filter):
    """
    日志级别过滤器，只允许特定级别的日志通过

    Args:
        low: 最低级别（包含）
        high: 最高级别（包含）
    """

    def __init__(self, low: int, high: int):
        super().__init__()
        self.low = low
        self.high = high

    def filter(self, record: logging.LogRecord) -> bool:
        """
        过滤日志记录

        Args:
            record: 日志记录

        Returns:
            True 如果日志级别在范围内，否则 False
        """
        return self.low <= record.levelno <= self.high


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


class RequestTrackingFormatter(logging.Formatter):
    """
    自定义日志格式化器，支持请求追踪 ID

    如果日志记录中包含 request_id，使用带追踪的格式；
    否则使用普通格式。
    """

    def __init__(self, fmt_default=None, fmt_with_tracking=None, datefmt=None, style='%'):
        """
        初始化请求追踪格式化器

        Args:
            fmt_default: 普通日志格式
            fmt_with_tracking: 带请求追踪的日志格式
            datefmt: 日期格式
            style: 格式化风格（默认为 %）
        """
        super().__init__(fmt_default, datefmt, style)
        self.fmt_default = fmt_default
        self.fmt_with_tracking = fmt_with_tracking

    def format(self, record):
        """
        格式化日志记录

        Args:
            record: 日志记录

        Returns:
            格式化后的日志字符串
        """
        # 检查是否有 request_id
        if hasattr(record, 'request_id') and record.request_id:
            # 使用带追踪的格式
            original_fmt = self._fmt
            self._fmt = self.fmt_with_tracking or self.fmt_default or self._fmt
            # 更新 style 以使用新格式
            self._style = logging.PercentStyle(self._fmt)
            # 确保 request_id 在记录中可用
            if 'request_id' not in record.__dict__:
                record.__dict__['request_id'] = record.request_id
            # 格式化并恢复原始格式
            try:
                return super().format(record)
            finally:
                self._fmt = original_fmt
                self._style = logging.PercentStyle(self._fmt)
        else:
            # 使用普通格式
            return super().format(record)


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

    # Create formatters (with and without request tracking)
    formatter = RequestTrackingFormatter(
        fmt_default=settings.log_format,
        fmt_with_tracking=getattr(settings, 'log_format_with_tracking', settings.log_format),
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (with Unicode-safe handling for Windows)
    if log_to_console:
        console_handler = SafeConsoleHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler (rotating) - Main backend log (all levels)
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

        # DEBUG-only log file (only DEBUG level messages)
        debug_handler = RotatingFileHandler(
            filename=log_path / "debug.log",
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.addFilter(LevelFilter(logging.DEBUG, logging.DEBUG))  # Only DEBUG
        debug_handler.setFormatter(formatter)
        root_logger.addHandler(debug_handler)

        # ERROR-only log file (ERROR and CRITICAL)
        error_handler = RotatingFileHandler(
            filename=log_path / "error.log",
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)  # ERROR and CRITICAL
        error_handler.addFilter(LevelFilter(logging.ERROR, logging.CRITICAL))  # Only ERROR and CRITICAL
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)

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
    if log_to_file:
        logging.info("Log files:")
        logging.info(f"  - backend.log: All logs (level {log_level}+)")
        logging.info(f"  - debug.log: DEBUG level only")
        logging.info(f"  - error.log: ERROR and CRITICAL level only")
        logging.info(f"  - agent.log: Agent execution logs (DEBUG level)")
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
        "app.core.tot",           # ToT framework
        "app.core.tot.nodes",     # ToT nodes
        "app.core.smart_stopping", # Smart stopping mechanism
    ]

    if settings.debug_agent:
        # 🔧 修复：确保所有 handlers 也允许 DEBUG 级别
        root_logger = logging.getLogger()

        # 降低所有 handlers 的级别到 DEBUG
        for handler in root_logger.handlers:
            if handler.level > logging.DEBUG:
                handler.setLevel(logging.DEBUG)

        # 设置模块级别为 DEBUG
        for module in agent_modules:
            module_logger = logging.getLogger(module)
            module_logger.setLevel(logging.DEBUG)

            # 确保模块的 handlers 也是 DEBUG 级别
            for handler in module_logger.handlers:
                if handler.level > logging.DEBUG:
                    handler.setLevel(logging.DEBUG)


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
    Context manager for logging agent execution details with full trajectory tracking.

    Enhanced to support:
    - Complete execution trajectory (thought, action, input, result)
    - JSON format for analysis
    - Trajectory visualization
    - Request/session correlation

    Usage:
        with AgentExecutionLogger("task_name") as logger:
            logger.log_input(user_message)
            logger.log_step("thought", "action", {"input": "data"})
            logger.log_step_result(0, "result", True, 1.2)
            logger.log_output(response)
            trajectory = logger.get_trajectory_json()
    """

    def __init__(
        self,
        task_name: str,
        enable_trajectory: bool = True,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        """
        Initialize agent execution logger.

        Args:
            task_name: Name of the task being executed
            enable_trajectory: Enable detailed trajectory tracking
            session_id: Optional session ID for correlation
            request_id: Optional request ID for correlation
        """
        self.task_name = task_name
        self.enable_trajectory = enable_trajectory
        self.session_id = session_id
        self.request_id = request_id
        self.logger = get_agent_logger()
        self.execution_history: list[dict] = []
        self.trajectory: list[dict] = []  # Enhanced trajectory tracking
        self.step_counter = 0
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        """Start execution logging."""
        import time
        self.start_time = time.time()
        self.logger.info("=" * 80)
        self.logger.info(f"AGENT EXECUTION START: {self.task_name}")
        if self.request_id:
            self.logger.info(f"Request ID: {self.request_id}")
        if self.session_id:
            self.logger.info(f"Session ID: {self.session_id}")
        self.logger.info("=" * 80)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End execution logging."""
        import time
        self.end_time = time.time()

        if exc_type is not None:
            self.logger.error(f"AGENT EXECUTION FAILED: {self.task_name}")
            self.logger.error(f"Error: {exc_val}", exc_info=True)
            # Mark trajectory as failed
            if self.enable_trajectory and self.trajectory:
                self.trajectory[-1]["success"] = False
                self.trajectory[-1]["error"] = str(exc_val)
        else:
            duration = self.end_time - self.start_time
            self.logger.info("=" * 80)
            self.logger.info(f"AGENT EXECUTION COMPLETE: {self.task_name}")
            self.logger.info(f"Total Duration: {duration:.2f}s")
            self.logger.info(f"Total Steps: {self.step_counter}")
            self.logger.info("=" * 80)

            # Log trajectory summary
            if self.enable_trajectory:
                summary = self._get_trajectory_summary()
                self.logger.info(f"Successful Steps: {summary['successful_steps']}")
                self.logger.info(f"Failed Steps: {summary['failed_steps']}")
                if summary.get('actions_used'):
                    self.logger.info(f"Actions Used: {', '.join(summary['actions_used'])}")

        self.logger.info("")  # Empty line for readability

    def log_input(self, messages: list, system_prompt: str):
        """Log agent input."""
        self.logger.debug(f"Input messages count: {len(messages)}")
        self.logger.debug(f"System prompt length: {len(system_prompt)} chars")
        self.logger.debug(f"System prompt preview: {system_prompt[:500]}...")

        # ✅ 完整记录所有消息（修复截断问题）
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            self.logger.info(f"Message {i+1} [{role}] ({len(content)} chars):")
            # ✅ 完整记录，不再截断
            self.logger.info(f"  {content}")

    def log_tool_call(self, tool_name: str, tool_args: dict):
        """Log tool invocation."""
        import time
        self.logger.info(f"TOOL CALL: {tool_name}")
        self.logger.debug(f"Arguments: {tool_args}")

        # Record in execution history
        self.execution_history.append({
            "type": "tool_call",
            "tool_name": tool_name,
            "input": tool_args,
            "timestamp": time.time(),
        })

    def log_tool_result(self, tool_name: str, result: str, success: bool, duration: float = None):
        """Log tool result."""
        import time
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

        # Update execution history with result
        for record in reversed(self.execution_history):
            if record.get("type") == "tool_call" and record.get("tool_name") == tool_name:
                record["success"] = success
                record["duration"] = duration or 0.0
                record["output"] = result
                record["error"] = None if success else result
                break

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
        # ✅ 完整记录最终输出，不再只在 debug 级别
        self.logger.info(f"Content: {output}")

    def get_tool_calls(self) -> list[dict]:
        """
        Get tool call records from execution history.

        Returns:
            List of tool call dictionaries, each containing:
                - tool_name: str
                - success: bool
                - duration: float
                - input: dict
                - output: str
                - error: str or None
        """
        tool_calls = []
        for record in self.execution_history:
            if record.get("type") == "tool_call":
                tool_calls.append({
                    "tool_name": record.get("tool_name", "unknown"),
                    "success": record.get("success", True),
                    "duration": record.get("duration", 0.0),
                    "input": record.get("input", {}),
                    "output": record.get("output", ""),
                    "error": record.get("error", None),
                })
        return tool_calls

    def get_execution_time(self) -> float:
        """
        Get total execution time.

        Returns:
            Total execution time in seconds, or 0.0 if not available
        """
        if not self.execution_history or self.start_time is None:
            return 0.0

        import time
        end_time = self.execution_history[-1].get("timestamp", time.time())
        return end_time - self.start_time

    def log_step(
        self,
        thought: str,
        action: str,
        input_data: dict
    ) -> None:
        """
        Log a single execution step with thought, action, and input.

        Args:
            thought: Agent's thought process
            action: Action taken by the agent
            input_data: Input data for the action
        """
        import time

        if not self.enable_trajectory:
            return

        step = {
            "step_number": self.step_counter,
            "thought": thought,
            "action": action,
            "input": input_data,
            "timestamp": time.time()
        }

        self.trajectory.append(step)

        # ✅ 递增步骤计数器（修复）
        self.step_counter += 1

        # Log to file
        self.logger.info(f"STEP {self.step_counter - 1}: {action}")
        self.logger.debug(f"  Thought: {thought[:200]}...")
        self.logger.debug(f"  Input: {str(input_data)[:200]}...")

    def log_step_result(
        self,
        step_number: int,
        result: str,
        success: bool,
        duration: float
    ) -> None:
        """
        Log the result of a step.

        Args:
            step_number: Step number (0-indexed)
            result: Result of the action
            success: Whether the action succeeded
            duration: Duration of the action in seconds
        """
        if not self.enable_trajectory:
            return

        if step_number < len(self.trajectory):
            self.trajectory[step_number]["result"] = result
            self.trajectory[step_number]["success"] = success
            self.trajectory[step_number]["duration"] = duration

            # Log to file
            status = "SUCCESS" if success else "FAILED"
            self.logger.info(f"STEP {step_number} RESULT: {status} ({duration:.2f}s)")
            self.logger.debug(f"  Result: {result[:300]}...")

    def get_trajectory(self) -> list[dict]:
        """
        Get the complete execution trajectory.

        Returns:
            List of trajectory steps
        """
        return self.trajectory.copy()

    def get_trajectory_json(self) -> str:
        """
        Get the complete execution trajectory as JSON.

        Returns:
            JSON string of trajectory
        """
        import json
        import time

        trajectory_data = {
            "task_name": self.task_name,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "start_time": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(self.start_time)
            ) if self.start_time else None,
            "end_time": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(self.end_time)
            ) if self.end_time else None,
            "total_duration": (self.end_time - self.start_time) if self.end_time and self.start_time else 0,
            "total_steps": len(self.trajectory),
            "steps": self.trajectory,
            "summary": self._get_trajectory_summary()
        }

        return json.dumps(trajectory_data, indent=2, ensure_ascii=False)

    def save_trajectory(self, filepath: str) -> None:
        """
        Save execution trajectory to file.

        Args:
            filepath: Path to save trajectory JSON
        """
        import json
        from pathlib import Path

        # Ensure directory exists
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.get_trajectory_json())

        self.logger.info(f"Trajectory saved to: {filepath}")

    def _get_trajectory_summary(self) -> dict:
        """
        Get trajectory summary statistics.

        Returns:
            Summary dictionary
        """
        if not self.trajectory:
            return {
                "successful_steps": 0,
                "failed_steps": 0,
                "total_duration": 0,
                "actions_used": []
            }

        successful = sum(1 for step in self.trajectory if step.get("success", True))
        failed = len(self.trajectory) - successful
        actions = list(set(step.get("action", "unknown") for step in self.trajectory))
        total_duration = sum(step.get("duration", 0) for step in self.trajectory)

        return {
            "successful_steps": successful,
            "failed_steps": failed,
            "total_duration": total_duration,
            "actions_used": actions
        }

    def get_step_statistics(self) -> dict:
        """
        Get statistics about execution steps.

        Returns:
            Statistics dictionary
        """
        if not self.trajectory:
            return {}

        stats = {
            "total_steps": len(self.trajectory),
            "successful_steps": 0,
            "failed_steps": 0,
            "average_step_duration": 0,
            "max_step_duration": 0,
            "min_step_duration": float('inf'),
            "actions_count": {}
        }

        durations = []
        for step in self.trajectory:
            if step.get("success", True):
                stats["successful_steps"] += 1
            else:
                stats["failed_steps"] += 1

            duration = step.get("duration", 0)
            durations.append(duration)
            stats["max_step_duration"] = max(stats["max_step_duration"], duration)
            stats["min_step_duration"] = min(stats["min_step_duration"], duration)

            # Count actions
            action = step.get("action", "unknown")
            stats["actions_count"][action] = stats["actions_count"].get(action, 0) + 1

        if durations:
            stats["average_step_duration"] = sum(durations) / len(durations)
            if stats["min_step_duration"] == float('inf'):
                stats["min_step_duration"] = 0

        return stats

