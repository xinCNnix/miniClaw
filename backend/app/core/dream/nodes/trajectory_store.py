"""
TrajectoryStore — SQLite-backed trajectory indexing and sampling.

Contains both the TrajectoryStore class and the LangGraph node function
for the Dream Subgraph.
"""

import json
import logging
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.dream.config import DreamConfig
from app.core.dream.models import DreamState, DreamTrajectory

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trajectories (
    traj_id       TEXT PRIMARY KEY,
    source        TEXT NOT NULL DEFAULT 'online',
    mode          TEXT NOT NULL DEFAULT '',
    task          TEXT NOT NULL DEFAULT '',
    success       INTEGER NOT NULL DEFAULT 0,
    failure_type  TEXT,
    failure_summary TEXT,
    tags_json     TEXT NOT NULL DEFAULT '[]',
    cost_tokens   INTEGER,
    cost_time_ms  REAL,
    created_at    TEXT,
    file_path     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_traj_success ON trajectories(success);
CREATE INDEX IF NOT EXISTS idx_traj_failure_type ON trajectories(failure_type);
CREATE INDEX IF NOT EXISTS idx_traj_created_at ON trajectories(created_at);
CREATE INDEX IF NOT EXISTS idx_traj_mode ON trajectories(mode);
"""


class TrajectoryStore:
    """SQLite-backed trajectory store for Dream pipeline.

    Reads JSON files from logs/traces/, indexes into SQLite,
    supports filtered queries and weighted sampling.
    """

    def __init__(self, config: Optional[DreamConfig] = None):
        cfg = config or DreamConfig()
        self.db_path = cfg.trajectory_db_path
        self.traces_dir = cfg.traces_dir
        self._init_db()

    # ------------------------------------------------------------------
    # DB lifecycle
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    # ------------------------------------------------------------------
    # Programmatic single-row insert (used by Online Distill)
    # ------------------------------------------------------------------

    def add(
        self,
        traj_id: str,
        source: str = "online",
        mode: str = "",
        task: str = "",
        success: bool = False,
        failure_type: Optional[str] = None,
        failure_summary: Optional[str] = None,
        tags_json: str = "[]",
        cost_tokens: Optional[int] = None,
        cost_time_ms: Optional[float] = None,
        created_at: Optional[str] = None,
        file_path: str = "",
    ) -> str:
        """Insert a single trajectory row. Returns traj_id."""
        with self._conn() as con:
            con.execute(
                """INSERT OR REPLACE INTO trajectories
                   (traj_id, source, mode, task, success, failure_type,
                    failure_summary, tags_json, cost_tokens, cost_time_ms,
                    created_at, file_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    traj_id,
                    source,
                    mode,
                    task[:500],
                    int(success),
                    failure_type,
                    failure_summary,
                    tags_json,
                    cost_tokens,
                    cost_time_ms,
                    created_at or datetime.now().isoformat(),
                    file_path,
                ),
            )
        return traj_id

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_from_logs(self, traces_dir: Optional[str] = None) -> int:
        """Scan JSON trace files and build SQLite index. Returns count indexed."""
        base = Path(traces_dir or self.traces_dir)
        if not base.exists():
            logger.warning(f"Traces directory not found: {base}")
            return 0

        count = 0
        for mode_dir in base.iterdir():
            if not mode_dir.is_dir():
                continue
            mode = mode_dir.name
            for fp in mode_dir.glob("*.json"):
                if self._index_file(fp, mode):
                    count += 1

        logger.info(f"Indexed {count} trajectory files from {base}")
        return count

    def _index_file(self, fp: Path, mode: str) -> bool:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Skipping {fp}: {e}")
            return False

        traj_id = fp.stem
        task = data.get("user_question", "") or data.get("task", "")
        success = self._infer_success(data)

        failure_type = None
        failure_summary = None
        if not success:
            failure_type, failure_summary = self._extract_failure(data)

        token_breakdown = data.get("token_breakdown") or {}
        cost_tokens = token_breakdown.get("total", 0)
        duration = data.get("total_duration", 0.0)
        cost_time_ms = duration * 1000 if duration else None

        tags = [
            s.get("skill_name", "")
            for s in data.get("skills", [])
            if s.get("skill_name")
        ]

        created_at = self._extract_timestamp(fp, data)

        with self._conn() as con:
            con.execute(
                """INSERT OR REPLACE INTO trajectories
                   (traj_id, source, mode, task, success, failure_type,
                    failure_summary, tags_json, cost_tokens, cost_time_ms,
                    created_at, file_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    traj_id,
                    "online",
                    mode,
                    task[:500],
                    int(success),
                    failure_type,
                    failure_summary,
                    json.dumps(tags, ensure_ascii=False),
                    cost_tokens or None,
                    cost_time_ms,
                    created_at,
                    str(fp),
                ),
            )
        return True

    @staticmethod
    def _infer_success(data: dict) -> bool:
        if "success" in data:
            return bool(data["success"])
        steps = data.get("steps", [])
        if steps:
            return all(s.get("success", True) for s in steps)
        loops = data.get("loops", [])
        if loops:
            return loops[-1].get("verification_passed", False)
        return True

    @staticmethod
    def _extract_failure(data: dict) -> tuple:
        errors: list[str] = []
        for step in data.get("steps", []):
            if step.get("error"):
                errors.append(step["error"])
        for loop in data.get("loops", []):
            if loop.get("execution_error"):
                errors.append(loop["execution_error"])

        summary = "; ".join(errors[:3]) if errors else "Unknown failure"
        sl = summary.lower()
        for ft in (
            "ImportError", "DependencyMissing", "SyntaxError",
            "RuntimeError", "Timeout", "PermissionDenied",
            "NetworkBlocked", "ToolError", "TestFailure",
        ):
            if ft.lower() in sl or ft.lower().replace("error", "") in sl:
                return ft, summary
        if "logic" in sl or "bug" in sl:
            return "LogicBug", summary
        return "Unknown", summary

    @staticmethod
    def _extract_timestamp(fp: Path, data: dict) -> str:
        if data.get("created_at"):
            return str(data["created_at"])
        if data.get("timestamp"):
            return str(data["timestamp"])
        parts = fp.stem.split("_")
        for i in range(len(parts) - 1):
            try:
                return datetime.strptime(
                    f"{parts[i]}_{parts[i + 1]}", "%Y%m%d_%H%M%S"
                ).isoformat()
            except (ValueError, IndexError):
                continue
        return datetime.fromtimestamp(fp.stat().st_mtime).isoformat()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        limit: int = 10,
        filter_success: Optional[bool] = None,
        failure_types: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        since: Optional[str] = None,
        mode: Optional[str] = None,
        order_by: str = "created_at DESC",
    ) -> List[DreamTrajectory]:
        clauses: list[str] = []
        params: list[Any] = []

        if filter_success is not None:
            clauses.append("success = ?")
            params.append(int(filter_success))
        if failure_types:
            placeholders = ",".join("?" * len(failure_types))
            clauses.append(f"failure_type IN ({placeholders})")
            params.extend(failure_types)
        if tags:
            tag_clauses = ["tags_json LIKE ?" for _ in tags]
            clauses.append(f"({' OR '.join(tag_clauses)})")
            params.extend([f'%"{t}"%' for t in tags])
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        if mode:
            clauses.append("mode = ?")
            params.append(mode)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM trajectories{where} ORDER BY {order_by} LIMIT ?"
        params.append(limit)

        with self._conn() as con:
            rows = con.execute(sql, params).fetchall()
            return [self._row_to_trajectory(r) for r in rows]

    # ------------------------------------------------------------------
    # Weighted sampling
    # ------------------------------------------------------------------

    def weighted_sample(
        self,
        limit: int = 5,
        failure_weight: float = 2.0,
        low_score_weight: float = 1.5,
    ) -> List[DreamTrajectory]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM trajectories ORDER BY created_at DESC"
            ).fetchall()

        if not rows:
            return []

        weights: list[float] = []
        for r in rows:
            w = 1.0
            if not r["success"]:
                w *= failure_weight
            cost = r["cost_tokens"] or 0
            if 0 < cost < 500:
                w *= low_score_weight
            weights.append(w)

        n = min(limit, len(rows))
        sampled = _weighted_sample_without_replacement(weights, n)
        return [self._row_to_trajectory(rows[i]) for i in sampled]

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _row_to_trajectory(self, row: sqlite3.Row) -> DreamTrajectory:
        file_path = row["file_path"]
        steps = []
        final_answer = None
        constraints: list[str] = []

        if file_path and Path(file_path).exists():
            try:
                data = json.loads(Path(file_path).read_text(encoding="utf-8"))
                steps = _extract_steps(data)
                final_answer = data.get("final_answer")
                constraints = data.get("constraints", [])
            except (json.JSONDecodeError, OSError):
                pass

        return DreamTrajectory(
            traj_id=row["traj_id"],
            source=row["source"],
            task=row["task"],
            constraints=constraints,
            steps=steps,
            final_answer=final_answer,
            success=bool(row["success"]),
            failure_type=row["failure_type"],
            failure_summary=row["failure_summary"],
            cost_tokens=row["cost_tokens"],
            cost_time_ms=row["cost_time_ms"],
            tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        with self._conn() as con:
            total = con.execute("SELECT COUNT(*) FROM trajectories").fetchone()[0]
            successes = con.execute(
                "SELECT COUNT(*) FROM trajectories WHERE success = 1"
            ).fetchone()[0]
            modes = {
                r["mode"]: r["cnt"]
                for r in con.execute(
                    "SELECT mode, COUNT(*) as cnt FROM trajectories GROUP BY mode"
                ).fetchall()
            }
            failure_types = {
                r["failure_type"]: r["cnt"]
                for r in con.execute(
                    "SELECT failure_type, COUNT(*) as cnt FROM trajectories "
                    "WHERE success = 0 GROUP BY failure_type"
                ).fetchall()
                if r["failure_type"]
            }

        return {
            "total": total,
            "successes": successes,
            "failures": total - successes,
            "modes": modes,
            "failure_types": failure_types,
        }


# ======================================================================
# Helper functions (module-level for testability)
# ======================================================================

def _weighted_sample_without_replacement(
    weights: list[float], n: int
) -> list[int]:
    indices = list(range(len(weights)))
    selected: list[int] = []
    remaining = list(weights)

    for _ in range(n):
        if not indices:
            break
        total = sum(remaining)
        if total <= 0:
            pick = random.choice(range(len(indices)))
        else:
            r = random.uniform(0, total)
            cumulative = 0.0
            pick = 0
            for i, w in enumerate(remaining):
                cumulative += w
                if r <= cumulative:
                    pick = i
                    break
        selected.append(indices[pick])
        indices.pop(pick)
        remaining.pop(pick)

    return selected


def _extract_steps(data: dict) -> list:
    from app.core.execution_trace.models import StepRecord

    steps = []
    for i, s in enumerate(data.get("steps", [])):
        steps.append(StepRecord(
            step_number=i + 1,
            thought=s.get("thought", ""),
            action=s.get("action", ""),
            input_data=s.get("input_data", {}),
            result=s.get("result"),
            success=s.get("success", True),
            duration=s.get("duration", 0.0),
            timestamp=s.get("timestamp", ""),
            error=s.get("error"),
        ))
    return steps


# ======================================================================
# LangGraph Node
# ======================================================================

_store_instance: TrajectoryStore | None = None


def trajectory_store_node(state: DreamState) -> DreamState:
    """Dream Subgraph node: index traces and weighted-sample trajectories."""
    global _store_instance

    config = DreamConfig()
    if _store_instance is None:
        _store_instance = TrajectoryStore(config)

    _store_instance.index_from_logs(config.traces_dir)

    max_samples = state.get("max_samples", config.max_samples)
    trajectories = _store_instance.weighted_sample(limit=max_samples)

    logger.info(
        f"TrajectoryStore: sampled {len(trajectories)} trajectories "
        f"(stats: {_store_instance.get_stats()})"
    )

    state["sampled_trajectories"] = trajectories
    return state
