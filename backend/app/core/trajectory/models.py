"""
Trajectory Data Models

Data structures for recording agent execution trajectory steps and summaries.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenBreakdown:
    """Per-component token usage breakdown."""

    system_prompt: int = 0
    conversation_history: int = 0
    user_input: int = 0
    tool_results: int = 0
    tca_injection: int = 0
    meta_policy_injection: int = 0
    total_prompt: int = 0
    total_completion: int = 0
    total: int = 0

    def to_dict(self) -> dict:
        return {
            "system_prompt": self.system_prompt,
            "conversation_history": self.conversation_history,
            "user_input": self.user_input,
            "tool_results": self.tool_results,
            "tca_injection": self.tca_injection,
            "meta_policy_injection": self.meta_policy_injection,
            "total_prompt": self.total_prompt,
            "total_completion": self.total_completion,
            "total": self.total,
        }

    def __add__(self, other: "TokenBreakdown") -> "TokenBreakdown":
        return TokenBreakdown(
            system_prompt=self.system_prompt + other.system_prompt,
            conversation_history=self.conversation_history + other.conversation_history,
            user_input=self.user_input + other.user_input,
            tool_results=self.tool_results + other.tool_results,
            tca_injection=self.tca_injection + other.tca_injection,
            meta_policy_injection=self.meta_policy_injection + other.meta_policy_injection,
            total_prompt=self.total_prompt + other.total_prompt,
            total_completion=self.total_completion + other.total_completion,
            total=self.total + other.total,
        )


@dataclass
class RoundMetrics:
    """Metrics for a single LLM round."""

    round_number: int = 0
    llm_duration: float = 0.0
    tool_count: int = 0
    tool_duration: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class StepRecord:
    """Single step execution record in agent trajectory."""

    step_number: int
    thought: str  # LLM thinking content
    action: str  # Tool name
    input_data: dict  # Tool input parameters
    result: Optional[str] = None  # Tool execution result
    success: bool = True
    duration: float = 0.0  # Execution time (seconds)
    timestamp: str = ""  # ISO format timestamp
    error: Optional[str] = None  # Error message if failed
    round_number: int = 0  # Which round this step belongs to


@dataclass
class SkillExecutionRecord:
    """Record of a skill interception during execution."""

    skill_name: str
    matched: bool = False
    executed: bool = False
    success: bool = False
    duration: float = 0.0
    error: Optional[str] = None


@dataclass
class TrajectorySummary:
    """Trajectory execution summary."""

    user_question: str = ""
    total_duration: float = 0.0
    llm_duration: float = 0.0
    tool_duration: float = 0.0
    total_rounds: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    actions_used: list[str] = field(default_factory=list)
    token_breakdown: Optional[TokenBreakdown] = None
    rounds: list[RoundMetrics] = field(default_factory=list)
    skills: list[dict] = field(default_factory=list)
