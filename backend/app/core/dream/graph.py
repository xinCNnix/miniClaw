"""
Dream Subgraph — 9-node LangGraph for offline batch self-replay.

Pipeline: TrajectoryStore → Sampler → Mutator → Executor → Judge
          → Distiller → SkillDedup → RegressionTest → MemoryWriter → END
"""

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from app.core.dream.models import DreamState

logger = logging.getLogger(__name__)


def build_dream_subgraph() -> StateGraph:
    """Build and compile the Dream Subgraph with all 9 nodes."""
    # Lazy imports to avoid circular dependencies
    from app.core.dream.nodes.trajectory_store import trajectory_store_node
    from app.core.dream.nodes.sampler import dream_sampler_node
    from app.core.dream.nodes.mutator import mutator_node
    from app.core.dream.nodes.executor import executor_node
    from app.core.dream.nodes.judge import judge_node
    from app.core.dream.nodes.distiller import distiller_node
    from app.core.dream.nodes.skill_dedup import skill_dedup_node
    from app.core.dream.nodes.regression import regression_test_node
    from app.core.dream.nodes.memory_writer import memory_writer_node

    g = StateGraph(DreamState)

    # Register all 9 nodes
    g.add_node("trajectory_store", trajectory_store_node)
    g.add_node("sampler", dream_sampler_node)
    g.add_node("mutator", mutator_node)
    g.add_node("executor", executor_node)
    g.add_node("judge", judge_node)
    g.add_node("distiller", distiller_node)
    g.add_node("skill_dedup", skill_dedup_node)
    g.add_node("regression_test", regression_test_node)
    g.add_node("memory_writer", memory_writer_node)

    # Wire the pipeline
    g.set_entry_point("trajectory_store")
    g.add_edge("trajectory_store", "sampler")
    g.add_edge("sampler", "mutator")
    g.add_edge("mutator", "executor")
    g.add_edge("executor", "judge")
    g.add_edge("judge", "distiller")
    g.add_edge("distiller", "skill_dedup")
    g.add_edge("skill_dedup", "regression_test")
    g.add_edge("regression_test", "memory_writer")
    g.add_edge("memory_writer", END)

    compiled = g.compile()
    logger.info("Dream Subgraph compiled with 9 nodes")
    return compiled


async def run_dream(
    mode: str = "nightly",
    max_samples: int = 3,
    mutations_per_traj: int = 5,
    max_exec_steps: int = 8,
    min_accept_score: float = 75.0,
    executor_mode: str = "simulated",
) -> DreamState:
    """Run a complete Dream session.

    Args:
        mode: Dream mode (nightly, manual, triggered).
        max_samples: Number of trajectories to sample.
        mutations_per_traj: Mutations per trajectory.
        max_exec_steps: Max execution steps per mutation.
        min_accept_score: Minimum judge score to accept.
        executor_mode: simulated or replay.

    Returns:
        Final DreamState with all results.
    """
    import uuid

    graph = build_dream_subgraph()

    initial_state: DreamState = {
        "dream_request_id": f"dream_{uuid.uuid4().hex[:8]}",
        "dream_mode": mode,
        "sampled_trajectories": [],
        "dream_batches": [],
        "dream_trajectories": [],
        "judge_scores": {},
        "distilled_skills": [],
        "deduplicated_skills": [],
        "regression_report": {},
        "written_skill_ids": [],
        "write_errors": [],
        "max_samples": max_samples,
        "mutations_per_traj": mutations_per_traj,
        "max_exec_steps": max_exec_steps,
        "min_accept_score": min_accept_score,
        "executor_mode": executor_mode,
    }

    result = await graph.ainvoke(initial_state)

    # Log summary
    n_written = len(result.get("written_skill_ids", []))
    n_errors = len(result.get("write_errors", []))
    n_sampled = len(result.get("sampled_trajectories", []))
    n_mutations = sum(
        len(b.mutation_specs)
        for b in result.get("dream_batches", [])
        if hasattr(b, "mutation_specs")
    )
    n_skills = len(result.get("distilled_skills", []))
    n_stable = sum(
        1 for r in result.get("regression_report", {}).values() if r.get("passed")
    )

    logger.info(
        f"Dream session complete: "
        f"{n_sampled} trajectories → {n_mutations} mutations → "
        f"{n_skills} skills → {n_stable} stable → {n_written} written "
        f"({n_errors} errors)"
    )

    return result
