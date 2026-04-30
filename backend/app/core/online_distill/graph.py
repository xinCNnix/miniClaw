"""OnlineDistillGraph — LangGraph state machine for online skill distillation."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.core.online_distill.models import DistillState
from app.core.online_distill.nodes.build_traj import build_traj_node
from app.core.online_distill.nodes.distill import distill_node
from app.core.online_distill.nodes.verify import verify_node
from app.core.online_distill.nodes.write_provisional import write_provisional_node
from app.core.online_distill.nodes.write_traj import write_traj_node


def build_distill_graph():
    """Build and compile the OnlineDistillGraph."""
    g = StateGraph(DistillState)

    g.add_node("verify", verify_node)
    g.add_node("build_traj", build_traj_node)
    g.add_node("write_traj", write_traj_node)
    g.add_node("distill", distill_node)
    g.add_node("write_provisional", write_provisional_node)

    g.set_entry_point("verify")

    g.add_edge("verify", "build_traj")
    g.add_edge("build_traj", "write_traj")
    g.add_edge("write_traj", "distill")
    g.add_edge("distill", "write_provisional")
    g.add_edge("write_provisional", END)

    return g.compile()
