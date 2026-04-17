"""Procedural Memory — reusable step-by-step procedures.

Auto-extracted from successful task completions. Provides "how-to"
knowledge for the retrieval pipeline.

Storage: SQLite (procedures table).
"""

import json
import logging
import time
from typing import Optional
from uuid import uuid4

from app.config import get_settings

logger = logging.getLogger(__name__)


class ProcedureStore:
    """Store and retrieve procedural memories."""

    async def add_procedure(self, proc: dict) -> str:
        """Add a new procedure.

        Args:
            proc: dict with keys: name, description, trigger_conditions,
                  steps (list of str), success_rate

        Returns:
            proc_id
        """
        proc_id = f"proc_{uuid4().hex[:12]}"

        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                # Check for duplicate by name
                existing = session.execute(
                    text("SELECT proc_id, success_rate FROM procedures WHERE name = :name"),
                    {"name": proc.get("name", "")},
                )
                row = existing.fetchone()

                if row:
                    # Update existing procedure if new success_rate is higher
                    existing_id, existing_rate = row
                    new_rate = proc.get("success_rate", 0)
                    if new_rate > existing_rate:
                        session.execute(
                            text(
                                "UPDATE procedures SET steps_json = :steps, "
                                "success_rate = :rate, last_used = :ts "
                                "WHERE proc_id = :pid"
                            ),
                            {
                                "steps": json.dumps(proc.get("steps", []), ensure_ascii=False),
                                "rate": new_rate,
                                "ts": time.time(),
                                "pid": existing_id,
                            },
                        )
                        session.commit()
                        logger.info(f"Updated procedure: {proc.get('name', '')}")
                    return existing_id

                # New procedure
                session.execute(
                    text(
                        "INSERT INTO procedures "
                        "(proc_id, name, description, trigger_conditions, steps_json, success_rate, last_used) "
                        "VALUES (:proc_id, :name, :description, :trigger_conditions, :steps_json, :success_rate, :last_used)"
                    ),
                    {
                        "proc_id": proc_id,
                        "name": proc.get("name", ""),
                        "description": proc.get("description", ""),
                        "trigger_conditions": json.dumps(
                            proc.get("trigger_conditions", []), ensure_ascii=False
                        ),
                        "steps_json": json.dumps(proc.get("steps", []), ensure_ascii=False),
                        "success_rate": proc.get("success_rate", 0),
                        "last_used": time.time(),
                    },
                )
                session.commit()
                return proc_id

        except Exception as e:
            logger.error(f"Failed to add procedure: {e}", exc_info=True)
            return ""

    async def search_procedures(self, query: str, top_k: int = 5) -> list[dict]:
        """Search procedures by name or description."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(
                    text(
                        "SELECT proc_id, name, description, steps_json, trigger_conditions, success_rate "
                        "FROM procedures "
                        "WHERE name LIKE :q OR description LIKE :q "
                        "ORDER BY success_rate DESC LIMIT :limit"
                    ),
                    {"q": f"%{query}%", "limit": top_k},
                )
                rows = result.fetchall()
                return [
                    {
                        "proc_id": r[0],
                        "name": r[1],
                        "description": r[2],
                        "steps": json.loads(r[3] or "[]"),
                        "trigger_conditions": json.loads(r[4] or "[]"),
                        "success_rate": r[5],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Procedure search failed: {e}")
            return []

    async def get_all_procedures(self) -> list[dict]:
        """Get all procedures."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(
                    text(
                        "SELECT proc_id, name, description, steps_json, trigger_conditions, success_rate, last_used "
                        "FROM procedures ORDER BY success_rate DESC"
                    )
                )
                rows = result.fetchall()
                return [
                    {
                        "proc_id": r[0],
                        "name": r[1],
                        "description": r[2],
                        "steps": json.loads(r[3] or "[]"),
                        "trigger_conditions": json.loads(r[4] or "[]"),
                        "success_rate": r[5],
                        "last_used": r[6],
                    }
                    for r in rows
                ]
        except Exception:
            return []

    async def update_last_used(self, proc_id: str) -> None:
        """Mark a procedure as recently used."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                session.execute(
                    text("UPDATE procedures SET last_used = :ts WHERE proc_id = :pid"),
                    {"ts": time.time(), "pid": proc_id},
                )
                session.commit()
        except Exception:
            pass

    async def get_stats(self) -> dict:
        """Get procedure memory statistics."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(text("SELECT COUNT(*), AVG(success_rate) FROM procedures"))
                row = result.fetchone()
                return {
                    "total": row[0] if row else 0,
                    "avg_success_rate": round(row[1], 2) if row and row[1] else 0,
                }
        except Exception:
            return {"total": 0, "avg_success_rate": 0}


# Singleton
_store: ProcedureStore | None = None


def get_procedure_store() -> ProcedureStore:
    global _store
    if _store is None:
        _store = ProcedureStore()
    return _store
