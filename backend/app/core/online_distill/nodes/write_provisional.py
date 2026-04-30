"""WriteProvisional node — writes provisional skill to isolation zone + registry."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from app.core.dream.models import SkillCard
from app.core.online_distill.config import get_distill_config
from app.core.online_distill.models import DistillState

logger = logging.getLogger(__name__)


def _ensure_provisional(skill: SkillCard) -> SkillCard:
    """Force provisional status — prevent any path from writing non-provisional."""
    if skill.status != "provisional":
        object.__setattr__(skill, "status", "provisional")
    return skill


def _build_skill_md(skill: SkillCard) -> str:
    """Render SkillCard as SKILL.md format with odistill_meta frontmatter."""
    import yaml

    meta: Dict[str, Any] = {
        "name": skill.skill_name,
        "description": skill.problem_pattern,
        "dependencies": {},
        "odistill_meta": {
            "source": "online_distill",
            "confidence": skill.confidence,
            "status": skill.status,
            "provenance": {
                "traj_ids": skill.source_traj_ids,
                "created_at": datetime.now().isoformat(),
            },
            "regression_tests": skill.regression_tests,
        },
    }
    frontmatter = yaml.dump(meta, allow_unicode=True, default_flow_style=False)
    steps_md = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(skill.steps))
    anti_md = "\n".join(f"- {a}" for a in skill.anti_patterns) if skill.anti_patterns else "None"
    verify_md = "\n".join(f"- {v}" for v in skill.verification)

    return (
        f"---\n{frontmatter}---\n\n"
        f"# {skill.skill_name}\n\n"
        f"## Description\n{skill.problem_pattern}\n\n"
        f"## Trigger\n{skill.trigger}\n\n"
        f"## Steps\n{steps_md}\n\n"
        f"## Verification\n{verify_md}\n\n"
        f"## Anti-patterns\n{anti_md}\n\n"
        f"## Constraints\n- confidence: {skill.confidence}\n"
        f"- status: {skill.status}\n"
    )


def _register_provisional_skill(skill: SkillCard) -> None:
    """Register provisional skill in skills_registry.json (atomic write + file lock)."""
    registry_path = Path("data/skills/skills_registry.json")
    lock_path = registry_path.with_suffix(".lock")

    try:
        from filelock import FileLock

        lock = FileLock(str(lock_path), timeout=5.0)
    except ImportError:
        # Fallback: no file lock (filelock not installed)
        from contextlib import nullcontext as _no_lock_ctx

        lock = _no_lock_ctx()

    with lock:
        registry: Dict[str, Any] = {}
        if registry_path.exists():
            try:
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                registry = {}

        registry[skill.skill_name] = {
            "skill_id": skill.skill_id,
            "status": "provisional",
            "source": "online_distill",
            "confidence": skill.confidence,
            "registered_at": datetime.now().isoformat(),
        }

        tmp_path = registry_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(str(tmp_path), str(registry_path))


async def _write_to_memory_procedural(skill: SkillCard) -> None:
    """Write provisional skill to memory procedural layer."""
    try:
        from app.memory.engine.nodes.write import write_memory_stores

        # write_memory_stores is a LangGraph node expecting MemoryState;
        # we call it with a minimal compatible state dict
        state = {
            "layer": "procedural",
            "key": f"provisional_skill:{skill.skill_id}",
            "value": {
                "skill_name": skill.skill_name,
                "trigger": skill.trigger,
                "steps": skill.steps,
                "confidence": skill.confidence,
                "status": "provisional",
            },
        }
        await write_memory_stores(state)
    except Exception as e:
        logger.debug("[OnlineDistill] Memory procedural write skipped: %s", e)


async def write_provisional_node(state: DistillState) -> DistillState:
    """Write provisional skill to isolation zone + register in skills_registry.json."""
    skill = state.get("distilled_skill")

    if skill is None:
        state["written_skill_id"] = None
        state["write_error"] = None
        return state

    distill_config = get_distill_config()

    # Safety: always enforce provisional status
    skill = _ensure_provisional(skill)

    try:
        # 1. Write SKILL.md file
        skill_dir = Path(distill_config.provisional_dir) / skill.skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = _build_skill_md(skill)
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

        # 2. Update skills_registry.json
        _register_provisional_skill(skill)

        # 3. Write to memory procedural layer (best-effort)
        await _write_to_memory_procedural(skill)

        state["written_skill_id"] = skill.skill_id
        state["write_error"] = None
    except Exception as e:
        logger.warning("[OnlineDistill] WriteProvisional failed: %s", e)
        state["written_skill_id"] = None
        state["write_error"] = str(e)

    return state
