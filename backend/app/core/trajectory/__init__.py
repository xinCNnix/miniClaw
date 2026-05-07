"""
Trajectory Recording Module — backward compat re-export from execution_trace.

All trajectory classes have been migrated to app.core.execution_trace.
This module re-exports them for backward compatibility.
"""

__all__ = [
    "AgentExecutionLogger",
    "StepRecord",
    "TrajectorySummary",
]


def __getattr__(name: str):
    """Lazy imports to avoid circular dependency with execution_trace."""
    if name == "AgentExecutionLogger":
        from app.core.execution_trace.normal_trace import NormalTrace
        return NormalTrace
    if name in ("StepRecord", "TrajectorySummary"):
        from app.core.execution_trace import models
        return getattr(models, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
