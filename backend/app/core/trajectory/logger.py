"""
Agent Execution Logger — backward compat re-export from execution_trace.

AgentExecutionLogger has been migrated to app.core.execution_trace.normal_trace.NormalTrace.
This module re-exports NormalTrace as AgentExecutionLogger for backward compatibility.
"""

from app.core.execution_trace.normal_trace import NormalTrace as AgentExecutionLogger  # noqa: F401

__all__ = ["AgentExecutionLogger"]
