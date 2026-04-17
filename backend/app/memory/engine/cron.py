"""MemoryJanitor — periodic decay and cleanup tasks.

红线4: Prevents database from growing without bound.

Cleanup tasks:
1. Delete TTL-expired event_log records
2. Decay episodic chunk scores by time factor
3. Prune low importance + low access_count memories
4. Trigger Wiki page consolidation
5. Physically delete KG is_active=0 rows older than 30 days
6. Delete ChromaDB vectors below score threshold
7. Archive and delete session files older than session_retention_days
"""

import asyncio
import hashlib
import json
import logging
import math
import time
from pathlib import Path
from uuid import uuid4

from app.config import get_settings

logger = logging.getLogger(__name__)


class MemoryJanitor:
    """Periodic memory decay and cleanup engine."""

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    def decay_factor(self, days_old: int) -> float:
        """Time decay factor: exp(-0.01 * days_old).

        - 7 days:  ~0.93
        - 30 days: ~0.74
        - 90 days: ~0.41
        - 180 days:~0.17
        """
        settings = get_settings()
        factor = getattr(settings, "memory_decay_factor", 0.01)
        return math.exp(-factor * days_old)

    async def run_decay_cycle(self) -> None:
        """Execute one full cleanup cycle."""
        settings = get_settings()
        logger.info("[MemoryJanitor] Starting decay cycle")

        try:
            # 1. Delete TTL-expired event_log records
            await self._cleanup_expired_events(settings)

            # 2. Decay episodic chunk scores
            await self._decay_vector_scores(settings)

            # 3. Prune low importance memories
            await self._prune_low_importance(settings)

            # 4. Wiki consolidation
            await self._consolidate_wiki(settings)

            # 5. KG garbage collection
            await self._gc_kg_deactivated(settings)

            # 6. ChromaDB low-score vector cleanup
            await self._cleanup_low_score_vectors(settings)

            # 7. Session file cleanup
            await self._cleanup_expired_sessions(settings)

            logger.info("[MemoryJanitor] Decay cycle completed")
        except Exception as e:
            logger.error(f"[MemoryJanitor] Decay cycle failed: {e}", exc_info=True)

    async def run_periodically(self, interval_seconds: float) -> None:
        """Run decay cycles at regular intervals."""
        self._running = True
        logger.info(f"[MemoryJanitor] Starting periodic cleanup (interval={interval_seconds}s)")

        while self._running:
            try:
                await self.run_decay_cycle()
            except Exception as e:
                logger.error(f"[MemoryJanitor] Cycle error: {e}")

            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        """Stop the periodic cleanup."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[MemoryJanitor] Stopped")

    # --- Step 1: Expired EventLog ---

    async def _cleanup_expired_events(self, settings) -> None:
        """Delete event_log records whose TTL has expired."""
        ttl_days = getattr(settings, "memory_ttl_default_days", 90)
        cutoff = time.time() - (ttl_days * 86400)

        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(
                    text("DELETE FROM event_log WHERE ts < :cutoff"),
                    {"cutoff": cutoff},
                )
                session.commit()
                if result.rowcount > 0:
                    logger.info(f"[Janitor] Deleted {result.rowcount} expired event_log records")
        except Exception as e:
            logger.warning(f"[Janitor] EventLog cleanup failed: {e}")

    # --- Step 2: Decay vector scores ---

    async def _decay_vector_scores(self, settings) -> None:
        """Apply time decay to ChromaDB vector scores via metadata."""
        try:
            from app.core.rag_engine import get_chroma_client

            client = get_chroma_client()

            # Decay conversation chunks
            try:
                collection = client.get_collection("conversations")
                # Get all docs with timestamps
                results = collection.get(include=["metadatas"])
                if results and results["metadatas"]:
                    for i, meta in enumerate(results["metadatas"]):
                        ts = meta.get("ts", meta.get("timestamp", 0))
                        if ts:
                            days_old = max(0, (time.time() - float(ts)) / 86400)
                            decayed_score = self.decay_factor(int(days_old))
                            meta["decay_score"] = decayed_score

                    # Update metadata
                    collection.update(
                        ids=results["ids"],
                        metadatas=results["metadatas"],
                    )
            except Exception:
                pass  # Collection may not exist

        except Exception as e:
            logger.warning(f"[Janitor] Vector score decay failed: {e}")

    # --- Step 3: Prune low importance ---

    async def _prune_low_importance(self, settings) -> None:
        """Delete memories with very low importance score."""
        prune_threshold = getattr(settings, "memory_prune_threshold", 0.1)

        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(
                    text("DELETE FROM memories WHERE importance_score < :threshold"),
                    {"threshold": prune_threshold},
                )
                session.commit()
                if result.rowcount > 0:
                    logger.info(f"[Janitor] Pruned {result.rowcount} low-importance memories")
        except Exception as e:
            logger.warning(f"[Janitor] Memory pruning failed: {e}")

    # --- Step 4: Wiki consolidation ---

    async def _consolidate_wiki(self, settings) -> None:
        """Trigger Wiki page consolidation for oversized pages."""
        if not getattr(settings, "enable_wiki", False):
            return

        try:
            from app.memory.wiki.store import get_wiki_store

            wiki_store = get_wiki_store()
            stats = await wiki_store.get_stats()
            pages = await wiki_store.list_pages()

            for page_meta in pages[:20]:  # Check top 20 pages
                page_id = page_meta.get("page_id") if isinstance(page_meta, dict) else page_meta
                if page_id:
                    try:
                        await wiki_store.consolidate_page(page_id)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[Janitor] Wiki consolidation failed: {e}")

    # --- Step 5: KG garbage collection ---

    async def _gc_kg_deactivated(self, settings) -> None:
        """Physically delete KG relations that have been soft-deleted for > 30 days."""
        if not getattr(settings, "enable_kg", False):
            return

        cutoff = time.time() - (30 * 86400)

        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                # KG relations use raw SQL tables managed by sqlite_store
                result = session.execute(
                    text(
                        "DELETE FROM kg_relations WHERE is_active = 0 AND updated_at < :cutoff"
                    ),
                    {"cutoff": cutoff},
                )
                session.commit()
                if result.rowcount > 0:
                    logger.info(f"[Janitor] GC'd {result.rowcount} deactivated KG relations")
        except Exception as e:
            logger.warning(f"[Janitor] KG GC failed: {e}")

    # --- Step 6: Low-score vector cleanup ---

    async def _cleanup_low_score_vectors(self, settings) -> None:
        """Remove ChromaDB vectors with decayed scores below threshold."""
        prune_threshold = getattr(settings, "memory_prune_threshold", 0.1)

        try:
            from app.core.rag_engine import get_chroma_client

            client = get_chroma_client()

            for coll_name in ["conversations", "case_records"]:
                try:
                    collection = client.get_collection(coll_name)
                    results = collection.get(
                        where={"decay_score": {"$lt": prune_threshold}},
                        include=["metadatas"],
                    )
                    if results and results["ids"]:
                        collection.delete(ids=results["ids"])
                        logger.info(
                            f"[Janitor] Removed {len(results['ids'])} low-score vectors from {coll_name}"
                        )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[Janitor] Vector cleanup failed: {e}")

    # --- Step 7: Session file cleanup ---

    async def _cleanup_expired_sessions(self, settings) -> None:
        """Archive and delete session files older than session_retention_days.

        Core rule: session files are only deleted AFTER all their events
        have been deduplicated and written to the event_log table.
        """
        retention_days = getattr(settings, "session_retention_days", 30)
        cutoff = time.time() - (retention_days * 86400)
        sessions_dir = Path("data/sessions")

        if not sessions_dir.exists():
            return

        for session_file in sessions_dir.glob("*.json"):
            try:
                mtime = session_file.stat().st_mtime
                if mtime > cutoff:
                    continue  # Not expired yet

                session_id = session_file.stem

                # Check if already archived
                is_archived = await self._is_session_archived(session_id)

                if not is_archived:
                    # Try to archive first
                    archived = await self._archive_session(session_id, session_file)
                    if not archived:
                        logger.warning(f"[Janitor] Session {session_id} archive failed, skipping deletion")
                        continue

                # Safe to delete
                session_file.unlink()
                logger.info(f"[Janitor] Deleted archived session: {session_id}")

            except Exception as e:
                logger.warning(f"[Janitor] Session cleanup error for {session_file.name}: {e}")

    async def _is_session_archived(self, session_id: str) -> bool:
        """Check if a session's events have been archived to event_log."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(
                    text(
                        "SELECT 1 FROM event_log "
                        "WHERE session_id = :sid AND event_type = 'session_archived' "
                        "LIMIT 1"
                    ),
                    {"sid": session_id},
                )
                return result.scalar() is not None
        except Exception:
            return False

    async def _archive_session(self, session_id: str, session_file: Path) -> bool:
        """Archive a session's events to event_log, then mark as archived.

        Returns:
            True if archival was successful (session can be safely deleted).
        """
        try:
            import hashlib

            # Load session data
            content = session_file.read_text(encoding="utf-8")
            session_data = json.loads(content)
            messages = session_data.get("messages", [])

            if not messages:
                # Empty session, just mark as archived
                await self._write_archive_marker(session_id)
                return True

            events = []
            for msg in messages:
                payload = {
                    "role": msg.get("role", "unknown"),
                    "content": msg.get("content", "")[:500],  # Truncate to prevent bloat
                }
                content_hash = hashlib.sha256(
                    json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()

                # Check dedup
                from app.core.database import get_db_session
                from sqlalchemy import text

                with get_db_session() as session:
                    exists = session.execute(
                        text("SELECT 1 FROM event_log WHERE hash = :hash LIMIT 1"),
                        {"hash": content_hash},
                    )
                    if exists.scalar() is not None:
                        continue  # Already archived

                events.append({
                    "event_id": f"evt_{uuid4().hex[:12]}",
                    "session_id": session_id,
                    "event_type": msg.get("role", "unknown"),
                    "source_type": "conversation",
                    "payload": payload,
                    "hash": content_hash,
                    "ts": msg.get("timestamp", time.time()),
                    "meta": {"archived_from": str(session_file)},
                })

            # Batch insert events
            if events:
                await self._batch_insert_events(events)

            # Write archive marker
            await self._write_archive_marker(session_id)
            return True

        except Exception as e:
            logger.error(f"[Janitor] Archive failed for session {session_id}: {e}")
            return False

    async def _batch_insert_events(self, events: list[dict]) -> None:
        """Batch insert events into event_log."""
        from app.core.database import get_db_session
        from sqlalchemy import text

        with get_db_session() as session:
            for evt in events:
                payload_str = json.dumps(evt["payload"], sort_keys=True, ensure_ascii=False)
                session.execute(
                    text(
                        "INSERT OR IGNORE INTO event_log "
                        "(event_id, ts, session_id, user_id, event_type, source_type, "
                        " payload_json, hash, source_ref, meta_json) "
                        "VALUES (:event_id, :ts, :session_id, :user_id, :event_type, :source_type, "
                        " :payload_json, :hash, :source_ref, :meta_json)"
                    ),
                    {
                        "event_id": evt["event_id"],
                        "ts": evt["ts"],
                        "session_id": evt["session_id"],
                        "user_id": "",
                        "event_type": evt["event_type"],
                        "source_type": evt.get("source_type", "conversation"),
                        "payload_json": payload_str,
                        "hash": evt["hash"],
                        "source_ref": "",
                        "meta_json": json.dumps(evt.get("meta", {}), ensure_ascii=False),
                    },
                )
            session.commit()

    async def _write_archive_marker(self, session_id: str) -> None:
        """Write a session_archived marker event."""
        from app.core.database import get_db_session
        from sqlalchemy import text

        marker_payload = {"status": "archived", "original_session_id": session_id}
        content_hash = hashlib.sha256(
            json.dumps(marker_payload, sort_keys=True).encode()
        ).hexdigest()

        with get_db_session() as session:
            session.execute(
                text(
                    "INSERT OR IGNORE INTO event_log "
                    "(event_id, ts, session_id, user_id, event_type, source_type, "
                    " payload_json, hash, source_ref, meta_json) "
                    "VALUES (:event_id, :ts, :session_id, :user_id, :event_type, :source_type, "
                    " :payload_json, :hash, :source_ref, :meta_json)"
                ),
                {
                    "event_id": f"evt_archive_{session_id}",
                    "ts": time.time(),
                    "session_id": session_id,
                    "user_id": "",
                    "event_type": "session_archived",
                    "source_type": "system",
                    "payload_json": json.dumps(marker_payload),
                    "hash": content_hash,
                    "source_ref": "",
                    "meta_json": "{}",
                },
            )
            session.commit()


# Singleton
_janitor: MemoryJanitor | None = None


def get_memory_janitor() -> MemoryJanitor:
    global _janitor
    if _janitor is None:
        _janitor = MemoryJanitor()
    return _janitor
