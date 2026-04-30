"""
DreamSampler — Weighted trajectory sampling node.

Filters and re-samples trajectories from TrajectoryStore output,
giving higher weight to failures for Dream exploration.
"""

import logging
import random
from typing import List

from app.core.dream.models import DreamBatch, DreamState, DreamTrajectory

logger = logging.getLogger(__name__)


def _compute_weight(traj: DreamTrajectory) -> float:
    """Compute sampling weight for a trajectory."""
    w = 1.0
    if not traj.success:
        w *= 2.0
    # Trajectories with failures are more instructive
    if traj.failure_type and traj.failure_type != "Unknown":
        w *= 1.5
    # Low-cost trajectories might be incomplete
    if traj.cost_tokens and 0 < traj.cost_tokens < 500:
        w *= 1.3
    return w


def _weighted_resample(
    trajectories: List[DreamTrajectory],
    limit: int,
) -> List[DreamTrajectory]:
    """Resample trajectories with failure-weighted probabilities."""
    if not trajectories:
        return []

    weights = [_compute_weight(t) for t in trajectories]
    n = min(limit, len(trajectories))

    # Weighted sampling without replacement
    indices = list(range(len(trajectories)))
    selected: List[DreamTrajectory] = []
    remaining_weights = list(weights)

    for _ in range(n):
        if not indices:
            break
        total = sum(remaining_weights)
        if total <= 0:
            pick = random.choice(range(len(indices)))
        else:
            r = random.uniform(0, total)
            cumulative = 0.0
            pick = 0
            for i, w in enumerate(remaining_weights):
                cumulative += w
                if r <= cumulative:
                    pick = i
                    break
        selected.append(trajectories[indices[pick]])
        indices.pop(pick)
        remaining_weights.pop(pick)

    return selected


def _classify_sample_reason(traj: DreamTrajectory) -> str:
    if not traj.success:
        return "failure_replay"
    if traj.failure_type:
        return "failure_analysis"
    if traj.cost_tokens and traj.cost_tokens < 500:
        return "low_cost_review"
    return "success_diversity"


def dream_sampler_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: re-sample trajectories with failure emphasis."""
    trajectories = state.get("sampled_trajectories", [])
    max_samples = state.get("max_samples", 3)

    if not trajectories:
        logger.warning("DreamSampler: no trajectories to sample")
        state["dream_batches"] = []
        return state

    sampled = _weighted_resample(trajectories, max_samples)

    # Build DreamBatch for each sampled trajectory
    batches = []
    for traj in sampled:
        reason = _classify_sample_reason(traj)
        batches.append(DreamBatch(
            base_traj_id=traj.traj_id,
            sampled_reason=reason,
        ))

    logger.info(
        f"DreamSampler: {len(batches)} batches from {len(trajectories)} trajectories"
    )

    state["sampled_trajectories"] = sampled
    state["dream_batches"] = batches
    return state
