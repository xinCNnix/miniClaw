"""
Trajectory File Writer — backward compat re-export from execution_trace.

The canonical writer is now app.core.execution_trace.writer.
"""

from app.core.execution_trace.writer import save_trace as save_trajectory  # noqa: F401

__all__ = ["save_trajectory"]
