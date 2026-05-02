"""
Dream system configuration.

Controls executor mode, judge mode, distiller parameters, promotion thresholds.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class DreamConfig:
    """Configuration for the Dream offline batch self-replay system."""

    # --- Executor phase ---
    executor_mode: Literal["simulated", "replay"] = "simulated"
    executor_network: bool = False  # Executor must not access network
    executor_max_steps: int = 8
    executor_budget_tokens: int = 2000  # limit inference cost

    # --- Distiller phase (requires LLM) ---
    distiller_network: bool = True  # allow network for LLM calls
    distiller_model: str = "gpt-4"
    distiller_batch_mode: bool = True  # batch mode to reduce cost
    distiller_max_confidence: float = 0.8  # offline distill confidence ceiling

    # --- Judge phase ---
    judge_mode: Literal["llm", "rule", "hybrid"] = "hybrid"

    # --- Consolidator phase ---
    consolidator_confidence_range: tuple = (0.65, 0.85)  # post-merge confidence range

    # --- Promotion phase ---
    promotion_confidence_boost: float = 0.2  # confidence increment on promotion
    promotion_max_confidence: float = 0.95  # post-promotion confidence ceiling
    regression_min_tests: int = 3  # minimum regression test count
    regression_min_pass: int = 3  # minimum pass count

    # --- Sampling ---
    max_samples: int = 3  # trajectories per batch
    mutations_per_traj: int = 5  # mutations per trajectory

    # --- Scoring ---
    min_accept_score: float = 75.0  # minimum judge score to accept

    # --- Storage ---
    trajectory_db_path: str = "data/dream/trajectory_store.db"
    traces_dir: str = "logs/traces/"
