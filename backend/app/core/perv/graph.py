"""
PEVR Graph - LangGraph StateGraph assembly.

Wires the planner -> executor -> [summarizer?] -> verifier -> replanner/finalize -> END flow.

Graph structure (with PERV Router risk-based routing):

    START
      |
      v
    planner
      |
      v
    executor
      |
      +--[low risk]--> finalize --> END
      +--[medium risk]--> summarizer --> verifier --> [pass] finalize --> END
      |                                             |
      |                                    [fail, retries] replanner --> executor
      +--[high risk]--> verifier --> [pass] finalize --> END
                                       |
                            [fail, max retries] finalize --> END

Nodes do NOT use StreamWriter (unavailable in langgraph 0.0.20).
They accept ``state: dict`` and return dict updates.  SSE event tracking
is handled through the ``reasoning_trace`` field in PlannerState.
"""

import logging
import sys
import io
import threading

from langgraph.graph import StateGraph, END

from app.core.perv.state import PlannerState
from app.core.perv.nodes import (
    planner_node,
    executor_node,
    verifier_node,
    replanner_node,
    finalizer_node,
    summarizer_node,
    skill_policy_node,
)

logger = logging.getLogger(__name__)
_stderr_lock = threading.Lock()


def _should_verify(state: dict) -> str:
    """Conditional edge: decide the next node after executor.

    Based on route_decision risk level:
    - high risk -> verifier（完整验证）
    - medium risk -> summarizer -> verifier（压缩后验证）
    - low risk -> finalize（跳过验证）
    - max retries reached -> finalize（强制结束）

    Args:
        state: Current PEVR state dictionary.

    Returns:
        ``"verify"``, ``"summarize"``, or ``"finalize"``.
    """
    # 最大重试次数已到 -> 强制结束
    if state.get("retry_count", 0) >= state.get("max_retries", 3):
        logger.warning("Max retries reached after executor, forcing finalize")
        return "finalize"

    route_decision = state.get("route_decision")
    risk = route_decision.get("risk", "medium") if route_decision else "medium"

    if risk == "high":
        return "verify"
    elif risk == "medium":
        return "summarize"
    else:  # low risk
        return "finalize"


def should_continue(state: dict) -> str:
    """Conditional edge: decide the next node after verification.

    Returns ``"finalize"`` when:
      - The verifier report indicates the task passed (either ``passed=True``
        or ``verdict="pass"``), **or**
      - The retry budget has been exhausted.

    Otherwise returns ``"replan"`` to trigger another loop iteration.

    Args:
        state: Current PEVR state dictionary.

    Returns:
        ``"finalize"`` or ``"replan"``.
    """
    report = state.get("verifier_report") or {}

    # Support both old format (passed: bool) and new format (verdict: str)
    passed = report.get("passed", False)
    verdict = report.get("verdict", "")

    if passed or verdict == "pass":
        return "finalize"
    if state.get("retry_count", 0) >= state.get("max_retries", 3):
        logger.warning(
            "Max retries (%d) reached without passing verification; finalizing.",
            state.get("max_retries", 3),
        )
        return "finalize"
    return "replan"


def build_planner_graph():
    """Build and compile the PEVR StateGraph.

    Uses ``set_entry_point`` and ``END`` (not ``START``) for compatibility
    with ``langgraph>=0.0.20``.

    Includes Summarizer node for medium-risk tasks and conditional
    executor -> verifier routing based on risk level.

    Returns:
        A compiled LangGraph ready for ``ainvoke`` / ``astream``.
    """
    graph = StateGraph(PlannerState)

    # --- Nodes ---
    graph.add_node("planner", planner_node)
    graph.add_node("skill_policy", skill_policy_node)
    graph.add_node("executor", executor_node)
    graph.add_node("summarizer", summarizer_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("replanner", replanner_node)
    graph.add_node("finalize", finalizer_node)

    # --- Entry point ---
    graph.set_entry_point("planner")

    # --- Linear edges ---
    # planner → skill_policy → executor (skill references are compiled)
    graph.add_edge("planner", "skill_policy")
    graph.add_edge("skill_policy", "executor")

    # --- Executor 后根据风险等级分流 ---
    graph.add_conditional_edges(
        "executor",
        _should_verify,
        {
            "summarize": "summarizer",   # 中风险：先压缩
            "verify": "verifier",        # 高风险：直接验证
            "finalize": "finalize",      # 低风险：跳过验证
        },
    )

    # --- Summarizer -> Verifier ---
    graph.add_edge("summarizer", "verifier")

    # --- Conditional branching after verification ---
    graph.add_conditional_edges(
        "verifier",
        should_continue,
        {
            "replan": "replanner",
            "finalize": "finalize",
        },
    )

    # --- Loop-back edge (replanner → skill_policy, so new plans are also compiled) ---
    graph.add_edge("replanner", "skill_policy")

    # --- Terminal edge ---
    graph.add_edge("finalize", END)

    # langgraph graph.compile() may internally write to stderr (e.g. mermaid
    # visualization), which fails with OSError on Windows uvicorn subprocess.
    # Temporarily redirect stderr to avoid the crash.
    with _stderr_lock:
        _prev_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            compiled = graph.compile()
        finally:
            sys.stderr = _prev_stderr
    logger.info("PEVR graph compiled successfully (7 nodes, risk-based routing, skill_policy)")
    return compiled
