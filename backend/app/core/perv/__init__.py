"""
PEVR (Planner-Executor-Verifier-Replanner) module.

Provides a closed-loop execution system that plans, executes, verifies,
and replans until the task is fully answered.
"""

from .orchestrator import PlannerOrchestrator, get_orchestrator
from .state import PlannerState, PlanStep, Observation, VerifierReport, PlanUpdate, RouteDecision
from .pevr_logger import extract_token_usage
from .router import route, hard_rule_router
from .scheduler import ExecutionLayer, build_execution_layers, get_max_parallelism, adjust_parallelism

__all__ = [
    "PlannerOrchestrator",
    "get_orchestrator",
    "PlannerState",
    "PlanStep",
    "Observation",
    "VerifierReport",
    "PlanUpdate",
    "RouteDecision",
    "extract_token_usage",
    "route",
    "hard_rule_router",
    "get_orchestrator",
    "ExecutionLayer",
    "build_execution_layers",
    "get_max_parallelism",
    "adjust_parallelism",
]
