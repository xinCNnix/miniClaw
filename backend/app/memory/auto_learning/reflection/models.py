"""Data models for reflection-driven learning system."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReflectionResult(BaseModel):
    """Result from reflection engine analysis.

    The reflection engine analyzes agent execution results
    to identify problems and suggest improvements.

    Key Design:
    1. Clearly distinguish LLM micro-level and Agent macro-level evaluations
    2. Include all required fields for strategy learning
    3. Bind quality score for reward calculation

    Attributes:
        completed: Whether the task was completed successfully
        problems: List of identified problems
        suggestions: List of improvement suggestions
        confidence: Confidence score (0.0 to 1.0)
        reasoning: Optional detailed reasoning from LLM
        timestamp: When the reflection was generated

        # New fields for structured output (Phase 3.1)
        task: Task description
        failure_type: Type of failure (tool_error, planning_error, etc.)
        root_cause: Root cause analysis
        reusable_pattern: Reusable strategy (optional)
        quality_score: Quality score (0.0 to 10.0)

        # Layer markers
        should_persist: Whether to persist to memory
        evaluation_type: Type of evaluation (macro_task vs micro_llm)
    """

    # ============================================================
    # Base fields
    # ============================================================

    completed: bool = Field(description="Whether the task was completed successfully")
    problems: list[str] = Field(
        default_factory=list, description="Identified problems in execution"
    )
    suggestions: list[str] = Field(
        default_factory=list, description="Improvement suggestions"
    )
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Confidence score"
    )
    reasoning: str | None = Field(
        default=None, description="Detailed reasoning from LLM"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Timestamp of reflection"
    )

    # ============================================================
    # New fields for structured output (Phase 3.1)
    # ============================================================

    task: str = Field(default="", description="Task description")
    failure_type: Literal[
        "tool_error",      # Tool call failure
        "planning_error",  # Planning error
        "information_gap", # Insufficient information
        "quality_low",     # Poor quality
        "unknown",         # Unknown cause
        "none",            # No failure
    ] = Field(default="none", description="Type of failure")

    root_cause: str = Field(default="", description="Root cause analysis")
    reusable_pattern: str | None = Field(
        default=None, description="Reusable strategy (optional)"
    )
    quality_score: float = Field(
        default=5.0, ge=0.0, le=10.0, description="Quality score (0-10)"
    )

    # ============================================================
    # Layer markers
    # ============================================================

    should_persist: bool = Field(
        default=False, description="Whether to persist to memory"
    )
    evaluation_type: str = Field(
        default="macro_task", description="Type of evaluation"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging.

        Returns:
            Dictionary representation of reflection result
        """
        return {
            "completed": self.completed,
            "problems": self.problems,
            "suggestions": self.suggestions,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat(),
            # New fields
            "task": self.task,
            "failure_type": self.failure_type,
            "root_cause": self.root_cause,
            "reusable_pattern": self.reusable_pattern,
            "quality_score": self.quality_score,
            "should_persist": self.should_persist,
            "evaluation_type": self.evaluation_type,
        }


class ToolMetrics(BaseModel):
    """Metrics from tool execution.

    Attributes:
        total_calls: Total number of tool calls
        successful_calls: Number of successful tool calls
        failed_calls: Number of failed tool calls
        total_duration: Total duration of all tool calls in seconds
        error_rate: Error rate (failed_calls / total_calls)
        tool_names: List of tool names used (for diversity calculation)
    """

    total_calls: int = Field(default=0, description="Total number of tool calls")
    successful_calls: int = Field(default=0, description="Number of successful calls")
    failed_calls: int = Field(default=0, description="Number of failed calls")
    total_duration: float = Field(
        default=0.0, description="Total duration in seconds"
    )
    error_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Error rate"
    )
    tool_names: list[str] = Field(
        default_factory=list, description="List of tool names used"
    )

    @classmethod
    def from_tool_calls(cls, tool_calls: list[dict]) -> "ToolMetrics":
        """Create metrics from tool call records.

        Args:
            tool_calls: List of tool call records

        Returns:
            ToolMetrics instance
        """
        total = len(tool_calls)
        successful = sum(1 for tc in tool_calls if tc.get("success", False))
        failed = total - successful
        duration = sum(tc.get("duration", 0.0) for tc in tool_calls)
        tool_names = [tc.get("name", "unknown") for tc in tool_calls]

        return cls(
            total_calls=total,
            successful_calls=successful,
            failed_calls=failed,
            total_duration=duration,
            error_rate=failed / total if total > 0 else 0.0,
            tool_names=tool_names,
        )


class RewardResult(BaseModel):
    """Result from reward model computation.

    The reward model computes a scalar reward for RL training
    based on semantic evaluation and manual shaping.

    Attributes:
        total_reward: Total reward (-1.0 to 1.0)
        semantic_reward: LLM-based semantic reward
        shaping_reward: Manual shaping reward
        breakdown: Detailed breakdown of reward components (can include strings)
        timestamp: When the reward was computed
    """

    total_reward: float = Field(
        ge=-1.0, le=1.0, description="Total reward"
    )
    semantic_reward: float = Field(
        ge=-1.0, le=1.0, description="LLM semantic reward"
    )
    shaping_reward: float = Field(
        ge=-1.0, le=1.0, description="Manual shaping reward"
    )
    breakdown: dict[str, Any] = Field(
        default_factory=dict, description="Detailed breakdown"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Timestamp of computation"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging.

        Returns:
            Dictionary representation of reward result
        """
        return {
            "total_reward": self.total_reward,
            "semantic_reward": self.semantic_reward,
            "shaping_reward": self.shaping_reward,
            "breakdown": self.breakdown,
            "timestamp": self.timestamp.isoformat(),
        }


class LearningResult(BaseModel):
    """Result from PatternLearner learning cycle.

    Attributes:
        session_id: Session identifier
        reflection: Reflection result
        reward: Reward result
        pattern_extracted: Whether a pattern was extracted
        pattern_id: ID of extracted pattern (if any)
        training_triggered: Whether training was triggered
        timestamp: When learning was completed
    """

    session_id: str = Field(description="Session identifier")
    reflection: ReflectionResult = Field(description="Reflection analysis result")
    reward: RewardResult = Field(description="Reward computation result")
    pattern_extracted: bool = Field(default=False, description="Pattern extracted")
    pattern_id: str | None = Field(default=None, description="Extracted pattern ID")
    training_triggered: bool = Field(default=False, description="Training triggered")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Timestamp of learning"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging.

        Returns:
            Dictionary representation of learning result
        """
        return {
            "session_id": self.session_id,
            "reflection": self.reflection.to_dict(),
            "reward": self.reward.to_dict(),
            "pattern_extracted": self.pattern_extracted,
            "pattern_id": self.pattern_id,
            "training_triggered": self.training_triggered,
            "timestamp": self.timestamp.isoformat(),
        }


__all__ = [
    "ReflectionResult",
    "ToolMetrics",
    "RewardResult",
    "LearningResult",
]
