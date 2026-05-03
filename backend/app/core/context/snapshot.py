"""Snapshot persistence for context window checkpoint/restore."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentSnapshot:
    """Captures agent execution state for checkpoint/restore."""

    snapshot_id: str
    session_id: str
    created_at: str
    active_task: str | None
    pending_tasks: list[str]
    world_state: dict[str, Any]
    memory_refs: dict[str, Any]
    conversation_summary: str
    parent_snapshot_id: str | None = None
    total_rounds: int = 0


class SnapshotManager:
    """JSON file storage for AgentSnapshot objects."""

    def __init__(self, base_dir: str = "data/snapshots"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: AgentSnapshot) -> str:
        path = self.base_dir / f"{snapshot.snapshot_id}.json"
        path.write_text(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Saved snapshot {snapshot.snapshot_id} for session {snapshot.session_id}")
        return snapshot.snapshot_id

    def load(self, snapshot_id: str) -> AgentSnapshot:
        path = self.base_dir / f"{snapshot_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.debug(f"Loaded snapshot {snapshot_id} (session={data.get('session_id', '?')})")
        return AgentSnapshot(**data)

    def list_snapshots(self, session_id: str) -> list[AgentSnapshot]:
        snapshots = []
        for path in self.base_dir.glob("*.json"):
            try:
                snap = AgentSnapshot(**json.loads(path.read_text(encoding="utf-8")))
                if snap.session_id == session_id:
                    snapshots.append(snap)
            except Exception:
                continue
        snapshots.sort(key=lambda s: s.created_at)
        return snapshots

    def cleanup(self, session_id: str, keep_last: int = 3) -> int:
        snapshots = self.list_snapshots(session_id)
        if len(snapshots) <= keep_last:
            return 0
        to_remove = snapshots[:-keep_last]
        for snap in to_remove:
            (self.base_dir / f"{snap.snapshot_id}.json").unlink(missing_ok=True)
        logger.info(f"Cleaned up {len(to_remove)} snapshots for session {session_id}")
        return len(to_remove)
