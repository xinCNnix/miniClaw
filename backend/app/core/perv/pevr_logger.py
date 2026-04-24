"""
PEVR Execution Logger — backward compat re-export from execution_trace.

PEVRLogger has been migrated to app.core.execution_trace.perv_trace.PEVRTrace.
This module re-exports for backward compatibility.

Canonical locations:
    - PEVRTrace (was PEVRLogger): app.core.execution_trace.perv_trace
    - extract_token_usage: app.core.execution_trace.token_utils
    - _ts: app.core.execution_trace.token_utils
    - Data models: app.core.execution_trace.models
"""

# Re-export PEVRTrace as PEVRLogger
from app.core.execution_trace.perv_trace import PEVRTrace as PEVRLogger  # noqa: F401
from app.core.execution_trace.perv_trace import get_pevr_logger  # noqa: F401

# Re-export utilities
from app.core.execution_trace.token_utils import extract_token_usage, _ts  # noqa: F401

# Re-export data models
from app.core.execution_trace.models import (  # noqa: F401
    TokenUsage,
    ToolCallRecord,
    PlanStepRecord,
    SkillPolicyRecord,
    LoopRecord,
)

# Module-level logger name (used by logging_config.py)
PEVR_LOGGER_NAME = "app.core.perv"

__all__ = [
    "PEVRLogger",
    "get_pevr_logger",
    "extract_token_usage",
    "_ts",
    "TokenUsage",
    "ToolCallRecord",
    "PlanStepRecord",
    "SkillPolicyRecord",
    "LoopRecord",
]
