"""
ToT Execution Logger — backward compat re-export from execution_trace.

ToTExecutionLogger has been migrated to app.core.execution_trace.tot_trace.ToTTrace.
This module re-exports for backward compatibility.

Canonical locations:
    - ToTTrace (was ToTExecutionLogger): app.core.execution_trace.tot_trace
    - Data models: app.core.execution_trace.models
"""

# Re-export ToTTrace as ToTExecutionLogger
from app.core.execution_trace.tot_trace import ToTTrace as ToTExecutionLogger  # noqa: F401

# Re-export data models
from app.core.execution_trace.models import (  # noqa: F401
    ToolCallRecord,
    ThoughtScore,
    PromptCompositionRecord,
    EvidenceExtractionRecord,
    CoverageUpdateRecord,
    ContradictionRecord,
    CitationChaseRecord,
    IterationRecord,
)

__all__ = [
    "ToTExecutionLogger",
    "ToolCallRecord",
    "ThoughtScore",
    "PromptCompositionRecord",
    "EvidenceExtractionRecord",
    "CoverageUpdateRecord",
    "ContradictionRecord",
    "CitationChaseRecord",
    "IterationRecord",
]
