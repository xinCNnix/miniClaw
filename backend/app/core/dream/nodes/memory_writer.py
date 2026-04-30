"""
MemoryWriter — Long-term memory skill registration.

Writes skills that passed regression testing to the skill registry.
Only stable skills are persisted to long-term memory.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from app.core.dream.models import DreamState, SkillCard

logger = logging.getLogger(__name__)

# Default skill registry path
_DEFAULT_REGISTRY = "data/skills/skills_registry.json"


def _ensure_registry(registry_path: str) -> Dict[str, Any]:
    """Load or create skill registry."""
    path = Path(registry_path)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Corrupted registry, creating new: {e}")
    return {"skills": {}, "version": "1.0", "updated_at": ""}


def _skill_to_registry_entry(skill: SkillCard) -> Dict[str, Any]:
    """Convert SkillCard to registry entry format compatible with skill_policy."""
    return {
        "skill_id": skill.skill_id,
        "skill_name": skill.skill_name,
        "skill_type": "instruction",
        "trigger": skill.trigger,
        "problem_pattern": skill.problem_pattern,
        "steps": skill.steps,
        "verification": skill.verification,
        "anti_patterns": skill.anti_patterns,
        "examples": skill.examples,
        "tags": skill.tags,
        "confidence": skill.confidence,
        "status": skill.status,
        "supporting_cases": skill.supporting_cases,
        "source_traj_ids": skill.source_traj_ids,
        "regression_tests": skill.regression_tests,
        "source": "dream",
    }


def _write_skill_file(skill: SkillCard, skills_dir: str) -> str:
    """Write a SKILL.md file for the skill in the skills directory."""
    skill_dir = Path(skills_dir) / skill.skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_md = skill_dir / "SKILL.md"
    content = f"""---
name: {skill.skill_name}
description: {skill.problem_pattern[:100]}
confidence: {skill.confidence}
status: {skill.status}
tags: {json.dumps(skill.tags)}
source: dream
---

# {skill.skill_name}

## Trigger
{skill.trigger}

## Steps
"""
    for i, step in enumerate(skill.steps, 1):
        content += f"{i}. {step}\n"

    content += f"""
## Verification
"""
    for v in skill.verification:
        content += f"- {v}\n"

    if skill.anti_patterns:
        content += "\n## Anti-patterns\n"
        for ap in skill.anti_patterns:
            content += f"- {ap}\n"

    if skill.examples:
        content += "\n## Examples\n"
        for ex in skill.examples:
            content += f"- {ex}\n"

    skill_md.write_text(content, encoding="utf-8")
    return str(skill_md)


def memory_writer_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: write passed skills to long-term memory."""
    skills = state.get("deduplicated_skills", [])
    regression_report = state.get("regression_report", {})

    written_ids: List[str] = []
    write_errors: List[str] = []

    # Determine registry path
    try:
        from app.config import get_settings
        settings = get_settings()
        registry_path = getattr(settings, "skills_registry_path", _DEFAULT_REGISTRY)
        skills_dir = getattr(settings, "skills_dir", "data/skills")
    except Exception:
        registry_path = _DEFAULT_REGISTRY
        skills_dir = "data/skills"

    # Load existing registry
    registry = _ensure_registry(registry_path)

    for skill in skills:
        # Only write skills that passed regression (stable status)
        report = regression_report.get(skill.skill_id, {})
        if not report.get("passed", False):
            continue

        try:
            # Write SKILL.md file
            skill_path = _write_skill_file(skill, skills_dir)

            # Update registry
            entry = _skill_to_registry_entry(skill)
            registry["skills"][skill.skill_id] = entry

            written_ids.append(skill.skill_id)
            logger.info(f"MemoryWriter: wrote skill {skill.skill_name} ({skill.skill_id})")

        except Exception as e:
            error_msg = f"Failed to write {skill.skill_id}: {e}"
            write_errors.append(error_msg)
            logger.error(f"MemoryWriter: {error_msg}")

    # Save updated registry
    if written_ids:
        try:
            from datetime import datetime
            registry["updated_at"] = datetime.now().isoformat()
            path = Path(registry_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            write_errors.append(f"Failed to save registry: {e}")
            logger.error(f"MemoryWriter: {e}")

    logger.info(
        f"MemoryWriter: {len(written_ids)} skills written, "
        f"{len(write_errors)} errors"
    )

    state["written_skill_ids"] = written_ids
    state["write_errors"] = write_errors
    return state
