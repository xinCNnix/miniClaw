"""Online Distill configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class DistillConfig:
    """Online Distill configuration."""

    # Master switch
    enabled: bool = True

    # Verify stage
    min_quality_score: float = 6.0
    require_evidence: bool = True

    # Distill stage
    distill_model: str = ""  # 留空则自动使用当前主模型
    max_confidence: float = 0.6
    min_regression_tests: int = 3
    require_success_for_distill: bool = True

    # Allow distilling "high-value failures"
    allow_failure_distill: bool = True
    failure_distill_tags: List[str] = field(
        default_factory=lambda: ["recoverable", "partial_success", "LogicBug"]
    )

    # WriteProvisional stage
    provisional_dir: str = "data/skills/provisional"
    max_provisional_skills: int = 100
    auto_cleanup_days: int = 30

    # Async execution
    timeout_seconds: float = 30.0


_distill_config: DistillConfig | None = None


def get_distill_config() -> DistillConfig:
    """Return cached DistillConfig, reading env overrides on first call."""
    global _distill_config
    if _distill_config is not None:
        return _distill_config

    cfg = DistillConfig()

    # Environment variable overrides
    if os.getenv("ONLINE_DISTILL_ENABLED", "").lower() in ("0", "false", "no"):
        cfg.enabled = False
    if val := os.getenv("ONLINE_DISTILL_MODEL"):
        cfg.distill_model = val
    if not cfg.distill_model:
        try:
            from app.core.model_roles import get_role_llm_config
            main_config = get_role_llm_config("main")
            cfg.distill_model = main_config.model
        except Exception:
            cfg.distill_model = "deepseek-chat"  # 最终兜底
    if val := os.getenv("ONLINE_DISTILL_TIMEOUT"):
        try:
            cfg.timeout_seconds = float(val)
        except ValueError:
            pass
    if val := os.getenv("ONLINE_DISTILL_MIN_SCORE"):
        try:
            cfg.min_quality_score = float(val)
        except ValueError:
            pass

    _distill_config = cfg
    return _distill_config
