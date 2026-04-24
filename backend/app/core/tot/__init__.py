"""
Tree of Thoughts (ToT) Reasoning Module

This module implements Tree of Thoughts reasoning using LangGraph,
enabling complex multi-step problem solving and deep research.
"""

__all__ = [
    "ToTState",
    "Thought",
    "build_tot_graph",
    "TaskComplexityClassifier",
    "ToTOrchestrator",
]


def __getattr__(name: str):
    """Lazy imports to avoid circular dependencies at module load time."""
    if name in ("ToTState", "Thought"):
        from app.core.tot.state import ToTState, Thought
        return ToTState if name == "ToTState" else Thought
    if name == "build_tot_graph":
        from app.core.tot.graph_builder import build_tot_graph
        return build_tot_graph
    if name in ("TaskComplexityClassifier", "ToTOrchestrator"):
        from app.core.tot.router import TaskComplexityClassifier, ToTOrchestrator
        return TaskComplexityClassifier if name == "TaskComplexityClassifier" else ToTOrchestrator

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
