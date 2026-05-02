"""
Dream Module — Offline batch self-replay system.

Components:
- TrajectoryStore: SQLite-backed trajectory indexing and sampling
- DreamSampler: Weighted trajectory sampling
- Mutator: 8 mutation strategies for trajectory variation
- Executor: Simulated (Phase 1) and Replay (Phase 2) execution
- Judge: StrongJudge 6-dimension evaluation (hybrid mode)
- Distiller: LLM-based skill distillation
- SkillDedup: Embedding-based skill deduplication and merge
- RegressionTest: Skill regression testing before promotion
- MemoryWriter: Long-term memory skill registration
"""

from app.core.dream.config import DreamConfig
from app.core.dream.graph import build_dream_subgraph, run_dream
from app.core.dream.models import (
    DreamBatch,
    DreamState,
    DreamTrajectory,
    JudgeScore,
    MutationSpec,
    SkillCard,
)

__all__ = [
    "DreamConfig",
    "DreamState",
    "DreamTrajectory",
    "MutationSpec",
    "DreamBatch",
    "JudgeScore",
    "SkillCard",
    "build_dream_subgraph",
    "run_dream",
]
