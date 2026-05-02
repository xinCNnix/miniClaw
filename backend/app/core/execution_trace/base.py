"""
Base Execution Trace Abstract Base Class

Defines the common interface shared by all three execution modes
(Normal, PERV, ToT).
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.core.execution_trace.models import (
    ToolCallRecord,
    SkillExecutionRecord,
    RoundMetrics,
)

logger = logging.getLogger(__name__)


class BaseExecutionTrace(ABC):
    """Abstract base class for execution trace loggers.

    Provides common lifecycle management (context manager) and shared
    recording methods.  Subclasses implement get_summary() and add
    mode-specific methods.
    """

    def __init__(self):
        self.user_question: str = ""
        self.start_time: float = 0.0
        self.end_time: Optional[float] = None

        # Shared counters
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tool_calls: int = 0

        # Shared record lists
        self.tools: list[ToolCallRecord] = []
        self.skills: list[SkillExecutionRecord] = []
        self.rounds: list[RoundMetrics] = []

    # --- Context manager ---

    def __enter__(self) -> "BaseExecutionTrace":
        self.start_time = datetime.now().timestamp()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = datetime.now().timestamp()

    # --- Abstract ---

    @abstractmethod
    def get_summary(self) -> dict:
        """Return a JSON-serializable execution summary."""

    # --- Common record methods ---

    def set_user_question(self, question: str):
        """Record the user's original question."""
        self.user_question = question

    def record_token_usage(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        """Accrue token usage from an LLM response."""
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

    def record_tool(self, name: str, args: str = "", result: str = "",
                    success: bool = True, duration: float = 0.0,
                    round_number: int = 0):
        """Record a tool call."""
        self.tools.append(ToolCallRecord(
            tool_name=name,
            args_summary=args,
            success=success,
            duration_ms=duration * 1000,
            output_preview=result[:200] if result else "",
        ))
        self.total_tool_calls += 1

    def record_skill(self, name: str, matched: bool, executed: bool,
                     success: bool = False, duration: float = 0.0,
                     error: Optional[str] = None):
        """Record a skill interception or execution."""
        self.skills.append(SkillExecutionRecord(
            skill_name=name,
            matched=matched,
            executed=executed,
            success=success,
            duration=duration,
            error=error,
        ))

    def record_round(self, round_number: int, llm_duration: float,
                     tool_count: int, tool_duration: float,
                     tokens: dict):
        """Record metrics for a completed LLM round."""
        self.rounds.append(RoundMetrics(
            round_number=round_number,
            llm_duration=llm_duration,
            tool_count=tool_count,
            tool_duration=tool_duration,
            prompt_tokens=tokens.get("prompt_tokens", 0),
            completion_tokens=tokens.get("completion_tokens", 0),
            total_tokens=tokens.get("total_tokens", 0),
        ))
