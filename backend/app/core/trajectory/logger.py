"""
Agent Execution Logger

Context manager for logging agent execution with dual-mode trajectory recording:
- Manual mode: log_tool_call() + log_tool_result() from chat.py event stream
- Callback mode: log_step() + log_step_result() from LangChain TrajectoryCallbackHandler

Both modes write to the same self.steps list with deduplication.
"""

import logging
from datetime import datetime
from typing import Optional

from app.core.trajectory.models import StepRecord, TrajectorySummary
from app.logging_config import get_agent_logger


class AgentExecutionLogger:
    """
    Context manager for logging agent execution details with trajectory recording.

    Usage:
        with AgentExecutionLogger("task_name") as logger:
            logger.log_input(messages, system_prompt)
            # ... execute agent ...
            logger.log_final_output(response)
        # __exit__ auto-saves trajectory if configured
    """

    def __init__(self, task_name: str):
        self.task_name = task_name
        self.logger = get_agent_logger()

        # Trajectory data storage
        self.steps: list[StepRecord] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.request_id: Optional[str] = None
        self.session_id: Optional[str] = None
        self._enable_trajectory: bool = True

        # Deduplication tracking: step_numbers that have been recorded via callback
        self._callback_step_numbers: set[int] = set()
        # Manual mode step counter
        self._manual_step_counter: int = 0
        # Track pending manual step for log_tool_call -> log_tool_result pairing
        self._pending_manual_step: Optional[StepRecord] = None

        # Read config
        try:
            from app.config import get_settings
            settings = get_settings()
            self._enable_trajectory = getattr(settings, "enable_agent_trajectory", True)
            self._save_to_file = getattr(settings, "save_trajectory_to_file", True)
        except Exception:
            self._save_to_file = True

        # Request tracking context
        try:
            from app.core.tracking_context import get_request_id, get_session_id
            self.request_id = get_request_id()
            self.session_id = get_session_id()
        except Exception:
            pass

    # --- Trajectory control ---

    @property
    def enable_trajectory(self) -> bool:
        """Whether trajectory recording is enabled."""
        return self._enable_trajectory

    @enable_trajectory.setter
    def enable_trajectory(self, value: bool) -> None:
        self._enable_trajectory = value

    # --- Context manager ---

    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info("=" * 80)
        self.logger.info(f"AGENT EXECUTION START: {self.task_name}")
        self.logger.info("=" * 80)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = datetime.now()
        if exc_type is not None:
            self.logger.error(f"AGENT EXECUTION FAILED: {self.task_name}")
            self.logger.error(f"Error: {exc_val}", exc_info=True)
        else:
            self.logger.info("=" * 80)
            self.logger.info(f"AGENT EXECUTION COMPLETE: {self.task_name}")
            self.logger.info("=" * 80)
        self.logger.info("")

        # Auto-save trajectory
        if self._enable_trajectory and self._save_to_file:
            try:
                self.save_trajectory()
            except Exception as e:
                self.logger.error(f"Failed to auto-save trajectory: {e}")

    # --- Manual mode methods (called from chat.py event stream) ---

    def log_input(self, messages: list, system_prompt: str):
        """Log agent input."""
        self.logger.debug(f"Input messages count: {len(messages)}")
        self.logger.debug(f"System prompt length: {len(system_prompt)} chars")
        self.logger.debug(f"System prompt preview: {system_prompt[:500]}...")

        for i, msg in enumerate(messages[-3:]):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            self.logger.debug(f"Message {i+1} [{role}]: {content[:200]}...")

    def log_tool_call(self, tool_name: str, tool_args: dict):
        """Log tool invocation. Creates a pending StepRecord."""
        self.logger.info(f"TOOL CALL: {tool_name}")
        self.logger.debug(f"Arguments: {tool_args}")

        if not self._enable_trajectory:
            return

        self._manual_step_counter += 1
        self._pending_manual_step = StepRecord(
            step_number=self._manual_step_counter,
            thought="",
            action=tool_name,
            input_data=tool_args if isinstance(tool_args, dict) else {"input": str(tool_args)},
            timestamp=datetime.now().isoformat(),
        )

    def log_tool_result(self, tool_name: str, result: str, success: bool, duration: float = None):
        """Log tool result. Completes the pending StepRecord."""
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"TOOL RESULT: {tool_name} - {status}")
        if duration:
            self.logger.debug(f"Duration: {duration:.2f}s")

        result_preview = result[:500] if result else ""
        self.logger.debug(f"Result preview: {result_preview}...")
        result_size = len(result) if result else 0
        self.logger.debug(f"Result size: {result_size} chars")

        if not self._enable_trajectory:
            return

        # Complete the pending step or create standalone
        if self._pending_manual_step and self._pending_manual_step.action == tool_name:
            step = self._pending_manual_step
            step.result = result
            step.success = success
            step.duration = duration or 0.0
            if not success:
                step.error = result
            self._pending_manual_step = None
        else:
            self._manual_step_counter += 1
            step = StepRecord(
                step_number=self._manual_step_counter,
                thought="",
                action=tool_name,
                input_data={},
                result=result,
                success=success,
                duration=duration or 0.0,
                timestamp=datetime.now().isoformat(),
                error=result if not success else None,
            )

        # Avoid duplicate with callback mode
        if step.step_number not in self._callback_step_numbers:
            self.steps.append(step)

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

    # --- Callback mode methods (called from TrajectoryCallbackHandler) ---

    def log_step(self, thought: str, action: str, input_data: dict) -> int:
        """
        Record a step via callback mode.

        Returns the step number assigned.
        """
        if not self._enable_trajectory:
            return -1

        step_number = len(self.steps) + 1
        step = StepRecord(
            step_number=step_number,
            thought=thought,
            action=action,
            input_data=input_data if isinstance(input_data, dict) else {"input": str(input_data)},
            timestamp=datetime.now().isoformat(),
        )
        self.steps.append(step)
        self._callback_step_numbers.add(step_number)
        return step_number

    def log_step_result(
        self,
        step_number: int,
        result: str,
        success: bool = True,
        duration: float = 0.0,
    ) -> None:
        """Update an existing step with result data via callback mode."""
        if not self._enable_trajectory:
            return

        # Find the step by step_number
        for step in reversed(self.steps):
            if step.step_number == step_number:
                step.result = result
                step.success = success
                step.duration = duration
                if not success:
                    step.error = result
                return

    # --- Trajectory data retrieval ---

    def get_trajectory(self) -> dict:
        """Get trajectory data as a serializable dict."""
        summary = TrajectorySummary()
        actions_seen: set[str] = set()

        for step in self.steps:
            if step.success:
                summary.successful_steps += 1
            else:
                summary.failed_steps += 1
            summary.total_duration += step.duration
            if step.action and step.action != "unknown":
                actions_seen.add(step.action)

        summary.actions_used = list(actions_seen)

        total_duration = 0.0
        if self.start_time and self.end_time:
            total_duration = (self.end_time - self.start_time).total_seconds()
        elif self.start_time:
            total_duration = (datetime.now() - self.start_time).total_seconds()

        return {
            "task_name": self.task_name,
            "session_id": self.session_id or "",
            "request_id": self.request_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration": total_duration,
            "total_steps": len(self.steps),
            "steps": [
                {
                    "step_number": s.step_number,
                    "thought": s.thought,
                    "action": s.action,
                    "input_data": s.input_data,
                    "result": s.result,
                    "success": s.success,
                    "duration": s.duration,
                    "timestamp": s.timestamp,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "summary": {
                "successful_steps": summary.successful_steps,
                "failed_steps": summary.failed_steps,
                "total_duration": summary.total_duration,
                "actions_used": summary.actions_used,
            },
        }

    def save_trajectory(self) -> str | None:
        """Save trajectory data to file."""
        from app.core.trajectory.writer import save_trajectory
        data = self.get_trajectory()
        return save_trajectory(data, self.task_name, self.session_id or "")
