"""Case Memory — stores and retrieves completed task trajectories.

Cases are extracted from execution logs (PEVR, ToT, normal agent) at
task completion. They enable "similar task" reuse.

Storage: SQLite (case_records table) + ChromaDB vector index for semantic search.
"""

import json
import logging
import time
from typing import Optional
from uuid import uuid4

from app.config import get_settings

logger = logging.getLogger(__name__)


class CaseMemoryStore:
    """Store and retrieve case records."""

    async def add_case(self, case: dict) -> str:
        """Add a new case record.

        Args:
            case: dict with keys: title, context, problem, plan, actions,
                  result, reflection, success_score, tags, entities, evidence

        Returns:
            case_id
        """
        case_id = f"case_{uuid4().hex[:12]}"
        settings = get_settings()

        # Check max cases
        max_cases = getattr(settings, "case_memory_max_cases", 1000)
        min_score = getattr(settings, "case_memory_min_success_score", 0.5)

        if case.get("success_score", 0) < min_score:
            logger.info(f"Skipping case with low success score: {case.get('success_score', 0)}")
            return ""

        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                # Check count and prune if needed
                count_result = session.execute(text("SELECT COUNT(*) FROM case_records"))
                count = count_result.scalar() or 0

                if count >= max_cases:
                    # Delete oldest low-score cases
                    session.execute(
                        text(
                            "DELETE FROM case_records WHERE case_id IN "
                            "(SELECT case_id FROM case_records ORDER BY ts ASC LIMIT 100)"
                        )
                    )

                session.execute(
                    text(
                        "INSERT INTO case_records "
                        "(case_id, ts, title, context, problem, plan, actions_json, "
                        " result, reflection, success_score, tags_json, entities_json, evidence_json) "
                        "VALUES (:case_id, :ts, :title, :context, :problem, :plan, :actions_json, "
                        " :result, :reflection, :success_score, :tags_json, :entities_json, :evidence_json)"
                    ),
                    {
                        "case_id": case_id,
                        "ts": case.get("ts", time.time()),
                        "title": case.get("title", "")[:500],
                        "context": case.get("context", ""),
                        "problem": case.get("problem", ""),
                        "plan": case.get("plan", ""),
                        "actions_json": json.dumps(case.get("actions", []), ensure_ascii=False),
                        "result": case.get("result", ""),
                        "reflection": case.get("reflection", ""),
                        "success_score": case.get("success_score", 0),
                        "tags_json": json.dumps(case.get("tags", []), ensure_ascii=False),
                        "entities_json": json.dumps(case.get("entities", []), ensure_ascii=False),
                        "evidence_json": json.dumps(case.get("evidence", []), ensure_ascii=False),
                    },
                )
                session.commit()

            # Also index in ChromaDB for semantic search
            await self._index_case_vector(case_id, case)

            return case_id

        except Exception as e:
            logger.error(f"Failed to add case: {e}", exc_info=True)
            return ""

    async def search_cases(self, query: str, top_k: int = 5, min_score: float = 0.3) -> list[dict]:
        """Search case records by semantic similarity.

        Uses ChromaDB vector index for ANN search, falls back to SQLite text search.
        """
        try:
            return await self._search_vector(query, top_k, min_score)
        except Exception as e:
            logger.warning(f"Vector case search failed, falling back to text: {e}")
            return await self._search_text(query, top_k)

    async def _search_vector(self, query: str, top_k: int, min_score: float) -> list[dict]:
        """Search using ChromaDB vector index."""
        from app.core.embedding_manager import get_embedding_manager

        emb_mgr = get_embedding_manager()
        query_embedding = await emb_mgr.embed_text(query)

        from app.core.rag_engine import get_chroma_client
        client = get_chroma_client()
        collection = client.get_or_create_collection("case_records")

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        cases = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results["distances"] else 1.0
                score = 1.0 - distance
                if score < min_score:
                    continue

                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                cases.append({
                    "case_id": doc_id,
                    "title": metadata.get("title", ""),
                    "score": score,
                    "context": results["documents"][0][i] if results["documents"] else "",
                })

        return cases

    async def _search_text(self, query: str, top_k: int) -> list[dict]:
        """Fallback text search in SQLite."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(
                    text(
                        "SELECT case_id, title, context, success_score "
                        "FROM case_records WHERE title LIKE :q OR context LIKE :q "
                        "ORDER BY success_score DESC, ts DESC LIMIT :limit"
                    ),
                    {"q": f"%{query}%", "limit": top_k},
                )
                rows = result.fetchall()
                return [
                    {
                        "case_id": r[0],
                        "title": r[1],
                        "context": r[2],
                        "success_score": r[3],
                        "score": r[3] * 0.5,  # rough estimate
                    }
                    for r in rows
                ]
        except Exception:
            return []

    async def _index_case_vector(self, case_id: str, case: dict) -> None:
        """Index a case in ChromaDB for semantic search."""
        try:
            from app.core.embedding_manager import get_embedding_manager
            from app.core.rag_engine import get_chroma_client

            emb_mgr = get_embedding_manager()
            text_to_embed = f"{case.get('title', '')}\n{case.get('context', '')}\n{case.get('problem', '')}"
            embedding = await emb_mgr.embed_text(text_to_embed)

            client = get_chroma_client()
            collection = client.get_or_create_collection("case_records")
            collection.upsert(
                ids=[case_id],
                embeddings=[embedding],
                documents=[text_to_embed],
                metadatas=[{
                    "title": case.get("title", "")[:200],
                    "success_score": case.get("success_score", 0),
                    "ts": case.get("ts", time.time()),
                }],
            )
        except Exception as e:
            logger.warning(f"Failed to index case vector: {e}")

    async def get_stats(self) -> dict:
        """Get case memory statistics."""
        try:
            from app.core.database import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                result = session.execute(text("SELECT COUNT(*), AVG(success_score) FROM case_records"))
                row = result.fetchone()
                return {
                    "total": row[0] if row else 0,
                    "avg_success_score": round(row[1], 2) if row and row[1] else 0,
                }
        except Exception:
            return {"total": 0, "avg_success_score": 0}


# Singleton
_store: CaseMemoryStore | None = None


def get_case_memory_store() -> CaseMemoryStore:
    global _store
    if _store is None:
        _store = CaseMemoryStore()
    return _store
