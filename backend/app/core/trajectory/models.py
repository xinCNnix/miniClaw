"""
Trajectory Data Models

Data structures for recording agent execution trajectory steps and summaries.
"""

from dataclasses import dataclass, field
from typing import Optional


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


@dataclass
class TrajectorySummary:
    """Trajectory execution summary."""

    successful_steps: int = 0
    failed_steps: int = 0
    total_duration: float = 0.0
    actions_used: list[str] = field(default_factory=list)
