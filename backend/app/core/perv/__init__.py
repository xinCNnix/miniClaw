"""
PEVR (Planner-Executor-Verifier-Replanner) module.

Provides a closed-loop execution system that plans, executes, verifies,
and replans until the task is fully answered.
"""

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
    "skill_policy_node",
]


def __getattr__(name: str):
    """Lazy imports to avoid circular dependencies at module load time."""
    _ORCHESTRATOR = {"PlannerOrchestrator", "get_orchestrator"}
    _STATE = {"PlannerState", "PlanStep", "Observation", "VerifierReport", "PlanUpdate", "RouteDecision"}
    _ROUTER = {"route", "hard_rule_router"}
    _SCHEDULER = {"ExecutionLayer", "build_execution_layers", "get_max_parallelism", "adjust_parallelism"}

    if name in _ORCHESTRATOR:
        from .orchestrator import PlannerOrchestrator, get_orchestrator
        return PlannerOrchestrator if name == "PlannerOrchestrator" else get_orchestrator
    if name in _STATE:
        from .state import PlannerState, PlanStep, Observation, VerifierReport, PlanUpdate, RouteDecision
        return locals()[name]
    if name == "extract_token_usage":
        from app.core.execution_trace.token_utils import extract_token_usage
        return extract_token_usage
    if name in _ROUTER:
        from .router import route, hard_rule_router
        return route if name == "route" else hard_rule_router
    if name in _SCHEDULER:
        from .scheduler import ExecutionLayer, build_execution_layers, get_max_parallelism, adjust_parallelism
        return {
            "ExecutionLayer": ExecutionLayer,
            "build_execution_layers": build_execution_layers,
            "get_max_parallelism": get_max_parallelism,
            "adjust_parallelism": adjust_parallelism,
        }[name]
    if name == "skill_policy_node":
        from .nodes.skill_policy import skill_policy_node
        return skill_policy_node

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
