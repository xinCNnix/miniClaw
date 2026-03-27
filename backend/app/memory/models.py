"""Pydantic models for pattern memory component."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Pattern(BaseModel):
    """Single pattern data structure.

    Attributes:
        id: Unique pattern identifier
        description: Pattern description (one sentence)
        situation: Situation that triggers the pattern
        outcome: Execution result
        fix_action: Action taken to fix the issue
        created_at: Timestamp when pattern was created
    """

    id: str = Field(description="Pattern unique identifier")
    description: str = Field(description="Pattern description (one sentence)")
    situation: str = Field(description="Trigger situation for the pattern")
    outcome: str = Field(description="Execution result")
    fix_action: str = Field(description="Fix action taken")
    created_at: datetime = Field(default_factory=datetime.now)


class PatternExtractionResult(BaseModel):
    """Pattern extraction result.

    Attributes:
        pattern: Extracted pattern description
        confidence: Confidence score (0.0 to 1.0)
        source_data: Source data used for extraction
    """

    pattern: str = Field(description="Extracted pattern description")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score")
    source_data: dict[str, Any] = Field(
        default_factory=dict, description="Source data for extraction"
    )


# Re-export advanced models for convenience
from app.memory.auto_learning.advanced.models import (  # noqa: E402
    Trajectory,
    TrainingMetrics,
    RLExperience,
)

__all__ = [
    "Pattern",
    "PatternExtractionResult",
    "Trajectory",
    "TrainingMetrics",
    "RLExperience",
]
