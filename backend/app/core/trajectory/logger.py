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

from app.core.trajectory.models import (
    StepRecord,
    TrajectorySummary,
    TokenBreakdown,
    RoundMetrics,
    SkillExecutionRecord,
)
from app.logging_config import get_agent_logger


class AgentExecutionLogger:
    """
    Context manager for logging agent execution details with trajectory recording.

    Usage:
        with AgentExecutionLogger("task_name") as logger:
            logger.log_input(messages, system_prompt)
            logger.set_user_question("What is X?")
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

        # --- Enhanced metrics ---
        self.user_question: str = ""
        self._accumulated_tokens: TokenBreakdown = TokenBreakdown()
        self._rounds: list[RoundMetrics] = []
        self._skills: list[SkillExecutionRecord] = []
        self._current_round: int = 0
        self._total_llm_duration: float = 0.0
        self._total_tool_duration: float = 0.0

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

    # --- User question ---

    def set_user_question(self, question: str):
        """Record the user's original question."""
        self.user_question = question
        self.logger.info(f"USER QUESTION: {question[:200]}")

    # --- Round tracking ---

    def start_round(self):
        """Start a new LLM round."""
        self._current_round += 1

    def log_round_metrics(self, llm_duration: float, tool_duration: float = 0.0,
                          tool_count: int = 0, prompt_tokens: int = 0,
                          completion_tokens: int = 0, total_tokens: int = 0):
        """Log metrics for a completed LLM round."""
        self._total_llm_duration += llm_duration
        self._total_tool_duration += tool_duration
        self._rounds.append(RoundMetrics(
            round_number=self._current_round,
            llm_duration=llm_duration,
            tool_count=tool_count,
            tool_duration=tool_duration,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ))
        self.logger.info(
            f"ROUND {self._current_round}: "
            f"llm={llm_duration:.2f}s, tools={tool_count}, "
            f"tokens={total_tokens} (prompt={prompt_tokens}, completion={completion_tokens})"
        )

    # --- Token tracking ---

    def log_token_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0,
                        total_tokens: int = 0):
        """Accrue token usage from an LLM response."""
        self._accumulated_tokens.total_prompt += prompt_tokens
        self._accumulated_tokens.total_completion += completion_tokens
        self._accumulated_tokens.total += total_tokens

    def log_token_breakdown(self, breakdown: TokenBreakdown):
        """Accrue a full token breakdown."""
        self._accumulated_tokens = self._accumulated_tokens + breakdown

    # --- Skill tracking ---

    def log_skill_execution(self, skill_name: str, matched: bool, executed: bool,
                            success: bool = False, duration: float = 0.0,
                            error: str = None):
        """Record a skill interception or execution."""
        record = SkillExecutionRecord(
            skill_name=skill_name,
            matched=matched,
            executed=executed,
            success=success,
            duration=duration,
            error=error,
        )
        self._skills.append(record)
        self.logger.info(
            f"SKILL: {skill_name} matched={matched} executed={executed} "
            f"success={success} duration={duration:.2f}s"
        )

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

    def log_tool_call(self, tool_name: str, tool_args: dict, round_number: int = 0):
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
            round_number=round_number or self._current_round,
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
                round_number=self._current_round,
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
            round_number=self._current_round,
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
        summary = TrajectorySummary(
            user_question=self.user_question,
            token_breakdown=self._accumulated_tokens,
        )
        actions_seen: set[str] = set()

        for step in self.steps:
            if step.success:
                summary.successful_steps += 1
            else:
                summary.failed_steps += 1
            summary.tool_duration += step.duration
            if step.action and step.action != "unknown":
                actions_seen.add(step.action)

        summary.actions_used = list(actions_seen)
        summary.total_rounds = self._current_round
        summary.llm_duration = self._total_llm_duration
        summary.rounds = self._rounds
        summary.skills = [
            {
                "skill_name": s.skill_name,
                "matched": s.matched,
                "executed": s.executed,
                "success": s.success,
                "duration": s.duration,
                "error": s.error,
            }
            for s in self._skills
        ]

        total_duration = 0.0
        if self.start_time and self.end_time:
            total_duration = (self.end_time - self.start_time).total_seconds()
        elif self.start_time:
            total_duration = (datetime.now() - self.start_time).total_seconds()
        summary.total_duration = total_duration

        return {
            "task_name": self.task_name,
            "session_id": self.session_id or "",
            "request_id": self.request_id,
            "user_question": self.user_question,
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
                    "round_number": s.round_number,
                }
                for s in self.steps
            ],
            "summary": {
                "user_question": summary.user_question,
                "total_duration": summary.total_duration,
                "llm_duration": summary.llm_duration,
                "tool_duration": summary.tool_duration,
                "total_rounds": summary.total_rounds,
                "successful_steps": summary.successful_steps,
                "failed_steps": summary.failed_steps,
                "actions_used": summary.actions_used,
                "token_breakdown": summary.token_breakdown.to_dict() if summary.token_breakdown else None,
                "rounds": [
                    {
                        "round_number": r.round_number,
                        "llm_duration": r.llm_duration,
                        "tool_count": r.tool_count,
                        "tool_duration": r.tool_duration,
                        "prompt_tokens": r.prompt_tokens,
                        "completion_tokens": r.completion_tokens,
                        "total_tokens": r.total_tokens,
                    }
                    for r in summary.rounds
                ],
                "skills": summary.skills,
            },
        }

    def save_trajectory(self) -> str | None:
        """Save trajectory data to file."""
        from app.core.trajectory.writer import save_trajectory
        data = self.get_trajectory()
        return save_trajectory(data, self.task_name, self.session_id or "")
