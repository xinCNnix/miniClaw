"""
GraphCheckpoint — TaskGraph SQLite 持久化。

保存时机:
- 每个 task mark_done 后
- 每个 task mark_failed 后
- MicroToT/BeamSearch replan 后
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.tot.taskgraph.models import TaskGraph

logger = logging.getLogger(__name__)


class GraphCheckpoint:
    """TaskGraph 持久化管理"""

    def __init__(self, db_path: str = "data/taskgraph/checkpoints.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    graph_json TEXT NOT NULL,
                    artifacts_summary TEXT,
                    progress_json TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_session ON checkpoints(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cp_run ON checkpoints(run_id)")

    def save(
        self,
        session_id: str,
        run_id: str,
        graph: TaskGraph,
        artifacts_summary: Any,
    ) -> str:
        """保存 checkpoint，返回 checkpoint_id"""
        progress = graph.progress_summary()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO checkpoints (session_id, run_id, graph_json, artifacts_summary, progress_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    run_id,
                    graph.model_dump_json(),
                    json.dumps(artifacts_summary) if isinstance(artifacts_summary, dict) else str(artifacts_summary),
                    json.dumps(progress),
                    time.time(),
                ),
            )
            conn.commit()
            return str(cursor.lastrowid)

    def load(self, session_id: str) -> Optional[Tuple[TaskGraph, Dict]]:
        """加载最新的 checkpoint"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT graph_json, progress_json FROM checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        graph_json, progress_json = row
        graph = TaskGraph.model_validate_json(graph_json)
        progress = json.loads(progress_json) if progress_json else {}
        return graph, progress

    def list_checkpoints(self, session_id: str) -> List[Dict]:
        """列出 session 的所有 checkpoint"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, run_id, progress_json, created_at FROM checkpoints WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()

        return [
            {
                "id": r[0],
                "run_id": r[1],
                "progress": json.loads(r[2]) if r[2] else {},
                "created_at": r[3],
            }
            for r in rows
        ]
