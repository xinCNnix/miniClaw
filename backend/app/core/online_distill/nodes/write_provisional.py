"""WriteProvisional node — writes provisional skill to isolation zone + registry."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

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

        # 兼容现有 skills_registry.json 的 {"skills": {...}} 结构
        skills_map = registry.setdefault("skills", {})

        skills_map[skill.skill_name] = {
            "skill_id": skill.skill_id,
            "status": "provisional",
            "source": "online_distill",
            "confidence": skill.confidence,
            "registered_at": datetime.now().isoformat(),
        }

        registry["last_updated"] = datetime.now().isoformat()

        tmp_path = registry_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(str(tmp_path), str(registry_path))


async def _write_to_memory_procedural(skill: SkillCard) -> None:
    """Write provisional skill to memory procedural layer.

    write_memory_stores 期望 MemoryState 格式，核心字段为 state["scored"] 列表。
    每个 item 包含 layer/text/evidence/importance/confidence/ttl_days 等。
    """
    try:
        from app.memory.engine.nodes.write import write_memory_stores

        state = {
            "scored": [
                {
                    "layer": "procedural",
                    "text": f"{skill.skill_name}: {skill.problem_pattern}",
                    "evidence": [],
                    "importance": skill.confidence,
                    "confidence": skill.confidence,
                    "ttl_days": 30,
                    "trigger_conditions": [skill.trigger],
                    "steps": skill.steps,
                },
            ],
            "logs": [],
        }
        await write_memory_stores(state)
    except Exception as e:
        logger.debug("[OnlineDistill] Memory procedural write skipped: %s", e)


def cleanup_expired_provisional_skills() -> int:
    """清理过期的 provisional skill（超过 auto_cleanup_days 且未被晋升）。

    Returns:
        清理的 skill 数量
    """
    config = get_distill_config()
    provisional_dir = Path(config.provisional_dir)
    if not provisional_dir.exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=config.auto_cleanup_days)
    cleaned = 0

    # 扫描 provisional 目录下的 skill 子目录
    for skill_dir in sorted(provisional_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            continue

        # 解析 frontmatter 中的 created_at
        created_at = _parse_skill_created_at(skill_md_path)
        if created_at is not None and created_at < cutoff:
            try:
                shutil.rmtree(skill_dir)
                cleaned += 1
                logger.info(
                    "[OnlineDistill] Cleaned expired provisional skill: %s",
                    skill_dir.name,
                )
            except OSError as e:
                logger.warning(
                    "[OnlineDistill] Failed to clean %s: %s", skill_dir.name, e
                )

    # 同步清理 registry 中的过期条目
    if cleaned > 0:
        _cleanup_registry(provisional_dir)

    # 数量上限检查
    _enforce_max_provisional(provisional_dir, config.max_provisional_skills)

    return cleaned


def _parse_skill_created_at(skill_md_path: Path) -> datetime | None:
    """从 SKILL.md 的 YAML frontmatter 中解析 created_at 时间戳。"""
    try:
        import yaml

        text = skill_md_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return None
        end = text.index("---", 3)
        frontmatter = yaml.safe_load(text[3:end])
        meta = frontmatter.get("odistill_meta", {})
        provenance = meta.get("provenance", {})
        ts_str = provenance.get("created_at", "")
        if ts_str:
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except Exception:
        pass
    return None


def _cleanup_registry(provisional_dir: Path) -> None:
    """从 skills_registry.json 中移除文件系统已不存在的 provisional skill 条目。"""
    registry_path = Path("data/skills/skills_registry.json")
    if not registry_path.exists():
        return

    lock_path = registry_path.with_suffix(".lock")
    try:
        from filelock import FileLock

        lock = FileLock(str(lock_path), timeout=5.0)
    except ImportError:
        from contextlib import nullcontext as _no_lock_ctx

        lock = _no_lock_ctx()

    with lock:
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        skills_map = registry.get("skills", {})
        existing_dirs = {d.name for d in provisional_dir.iterdir() if d.is_dir()} if provisional_dir.exists() else set()

        to_remove = [
            name
            for name, info in skills_map.items()
            if info.get("source") == "online_distill"
            and info.get("status") == "provisional"
            and name not in existing_dirs
        ]
        for name in to_remove:
            del skills_map[name]

        if to_remove:
            registry["last_updated"] = datetime.now().isoformat()
            tmp_path = registry_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(str(tmp_path), str(registry_path))


def _enforce_max_provisional(provisional_dir: Path, max_skills: int) -> None:
    """当 provisional skill 数量超过上限时，按创建时间排序删除最旧的。"""
    if not provisional_dir.exists():
        return

    dirs = sorted(
        [d for d in provisional_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()],
        key=lambda d: _parse_skill_created_at(d / "SKILL.md") or datetime.min.replace(tzinfo=timezone.utc),
    )

    while len(dirs) > max_skills:
        oldest = dirs.pop(0)
        try:
            shutil.rmtree(oldest)
            logger.info("[OnlineDistill] Evicted oldest provisional skill: %s", oldest.name)
        except OSError:
            break

    if len(dirs) < len([d for d in provisional_dir.iterdir() if d.is_dir()]):
        _cleanup_registry(provisional_dir)


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

        # 4. 清理过期 provisional skill
        try:
            cleanup_expired_provisional_skills()
        except Exception as e:
            logger.debug("[OnlineDistill] Cleanup check skipped: %s", e)

        state["written_skill_id"] = skill.skill_id
        state["write_error"] = None
    except Exception as e:
        logger.warning("[OnlineDistill] WriteProvisional failed: %s", e)
        state["written_skill_id"] = None
        state["write_error"] = str(e)

    return state
