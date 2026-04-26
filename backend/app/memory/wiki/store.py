"""
WikiStore — Three-layer storage for LLM Wiki pages.

- MD files: data/wiki/pages/{page_id}.md
- SQLite metadata: wiki_pages table (via get_db_session)
- Vector index: ChromaDB "wiki_pages" collection (via EmbeddingModelManager)
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.config import Settings, get_settings
from app.core.database import get_db_session, ensure_database
from app.memory.wiki.models import WikiPage, WikiPatchOp
from app.memory.wiki.patch import WikiPatcher

logger = logging.getLogger(__name__)


class WikiStore:
    """Three-layer Wiki page storage: MD file + SQLite meta + ChromaDB vector."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._pages_dir = Path(self._settings.wiki_pages_dir)
        self._patcher = WikiPatcher()
        self._chroma_collection = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create tables, directories, and ChromaDB collection."""
        if self._initialized:
            return

        ensure_database(self._settings)

        # Create pages directory
        self._pages_dir.mkdir(parents=True, exist_ok=True)

        # Create SQLite table
        with get_db_session(self._settings) as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS wiki_pages (
                    page_id       TEXT PRIMARY KEY,
                    title         TEXT    NOT NULL,
                    aliases       TEXT    DEFAULT '[]',
                    tags          TEXT    DEFAULT '[]',
                    summary       TEXT    DEFAULT '',
                    content_hash  TEXT    DEFAULT '',
                    evidence      TEXT    DEFAULT '[]',
                    confidence    REAL    DEFAULT 0.7,
                    access_count  INTEGER DEFAULT 0,
                    created_at    TEXT    DEFAULT (datetime('now')),
                    updated_at    TEXT    DEFAULT (datetime('now'))
                )
            """))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_wiki_pages_title ON wiki_pages(title)"
            ))
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_wiki_pages_tags ON wiki_pages(tags)"
            ))

        # Initialize ChromaDB collection
        try:
            from app.core.embedding_manager import get_embedding_manager
            from app.core.rag_engine import get_rag_engine

            rag_engine = get_rag_engine()
            chroma_client = rag_engine.chroma_client
            if chroma_client is not None:
                self._chroma_collection = chroma_client.get_or_create_collection(
                    name="wiki_pages",
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("Wiki ChromaDB collection ready: wiki_pages")
        except Exception as e:
            logger.warning(f"Wiki ChromaDB collection init skipped: {e}")

        self._initialized = True
        logger.info("WikiStore initialized")

    async def close(self) -> None:
        """No-op: resources are managed externally."""
        pass

    async def health_check(self) -> bool:
        """Return True if the wiki_pages table is accessible."""
        try:
            with get_db_session(self._settings) as session:
                session.execute(text("SELECT 1 FROM wiki_pages LIMIT 1"))
            return True
        except Exception as exc:
            logger.error("Wiki health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_page(self, page: WikiPage) -> str:
        """Create a new Wiki page. Returns page_id."""
        if not page.page_id:
            page.page_id = str(uuid.uuid4())[:8]

        now = datetime.utcnow().isoformat()
        page.created_at = now
        page.updated_at = now
        page.content_hash = hashlib.md5(page.content.encode()).hexdigest()

        # Write MD file
        self._write_md_file(page)

        # Upsert SQLite metadata
        with get_db_session(self._settings) as session:
            session.execute(text("""
                INSERT INTO wiki_pages
                    (page_id, title, aliases, tags, summary, content_hash,
                     evidence, confidence, access_count, created_at, updated_at)
                VALUES
                    (:pid, :title, :aliases, :tags, :summary, :chash,
                     :evidence, :confidence, 0, :now, :now)
            """), {
                "pid": page.page_id,
                "title": page.title,
                "aliases": json.dumps(page.aliases, ensure_ascii=False),
                "tags": json.dumps(page.tags, ensure_ascii=False),
                "summary": page.summary,
                "chash": page.content_hash,
                "evidence": json.dumps(page.evidence, ensure_ascii=False),
                "confidence": page.confidence,
                "now": now,
            })

        # Embed index text
        await self._embed_page(page)

        logger.info(f"Wiki page created: {page.page_id} ({page.title})")
        return page.page_id

    async def update_page(self, page_id: str, ops: List[WikiPatchOp]) -> None:
        """Apply patch operations to an existing Wiki page."""
        page = await self.read(page_id)
        if page is None:
            logger.warning(f"Wiki page not found for update: {page_id}")
            return

        # Apply patches
        new_content = page.content
        for op in ops:
            new_content = self._patcher.apply(new_content, op)

        page.content = new_content
        page.content_hash = hashlib.md5(new_content.encode()).hexdigest()
        page.updated_at = datetime.utcnow().isoformat()

        # Write updated MD file
        self._write_md_file(page)

        # Update SQLite metadata (including evidence field)
        evidence_json = json.dumps(
            [ev if isinstance(ev, dict) else ev for ev in page.evidence],
            ensure_ascii=False,
        ) if page.evidence else "[]"

        with get_db_session(self._settings) as session:
            session.execute(text("""
                UPDATE wiki_pages
                SET content_hash = :chash,
                    title = :title,
                    aliases = :aliases,
                    tags = :tags,
                    confidence = :confidence,
                    summary = :summary,
                    evidence = :evidence,
                    updated_at = :now
                WHERE page_id = :pid
            """), {
                "chash": page.content_hash,
                "title": page.title,
                "aliases": json.dumps(page.aliases) if page.aliases else "[]",
                "tags": json.dumps(page.tags) if page.tags else "[]",
                "confidence": page.confidence,
                "summary": page.summary,
                "evidence": evidence_json,
                "now": page.updated_at,
                "pid": page_id,
            })

        # Re-embed
        await self._embed_page(page)
        logger.info(f"Wiki page updated: {page_id} ({len(ops)} ops)")

    async def read(self, page_id: str) -> Optional[WikiPage]:
        """Read a Wiki page by ID."""
        meta = await self.get_meta(page_id)
        if meta is None:
            return None

        # Read MD file content
        md_path = self._pages_dir / f"{page_id}.md"
        if md_path.exists():
            content = md_path.read_text(encoding="utf-8")
        else:
            content = ""

        meta.content = content
        return meta

    async def get_meta(self, page_id: str) -> Optional[WikiPage]:
        """Get page metadata (no MD content)."""
        with get_db_session(self._settings) as session:
            row = session.execute(
                text("SELECT * FROM wiki_pages WHERE page_id = :pid"),
                {"pid": page_id},
            ).fetchone()

            if row is None:
                return None

            return WikiPage(
                page_id=row.page_id,
                title=row.title,
                aliases=json.loads(row.aliases) if row.aliases else [],
                tags=json.loads(row.tags) if row.tags else [],
                summary=row.summary or "",
                content="",
                content_hash=row.content_hash or "",
                evidence=json.loads(row.evidence) if row.evidence else [],
                confidence=row.confidence,
                created_at=row.created_at,
                updated_at=row.updated_at,
                access_count=row.access_count,
            )

    async def list_pages(self, tags: List[str] | None = None) -> List[WikiPage]:
        """List all pages, optionally filtered by tags."""
        with get_db_session(self._settings) as session:
            if tags:
                rows = session.execute(
                    text("SELECT * FROM wiki_pages ORDER BY updated_at DESC")
                ).fetchall()
                # Filter by tags (any overlap)
                result = []
                for row in rows:
                    page_tags = json.loads(row.tags) if row.tags else []
                    if any(t in page_tags for t in tags):
                        result.append(self._row_to_meta(row))
                return result
            else:
                rows = session.execute(
                    text("SELECT * FROM wiki_pages ORDER BY updated_at DESC")
                ).fetchall()
                return [self._row_to_meta(r) for r in rows]

    async def delete_page(self, page_id: str) -> bool:
        """Delete a Wiki page."""
        # Delete MD file
        md_path = self._pages_dir / f"{page_id}.md"
        if md_path.exists():
            md_path.unlink()

        # Delete from SQLite
        with get_db_session(self._settings) as session:
            session.execute(
                text("DELETE FROM wiki_pages WHERE page_id = :pid"),
                {"pid": page_id},
            )

        # Delete from ChromaDB
        if self._chroma_collection is not None:
            try:
                self._chroma_collection.delete(ids=[page_id])
            except Exception as e:
                logger.warning(f"Failed to delete wiki vector for {page_id}: {e}")

        logger.info(f"Wiki page deleted: {page_id}")
        return True

    async def get_pages_summary(self) -> str:
        """Get a condensed summary of all pages for write-judge context."""
        pages = await self.list_pages()
        if not pages:
            return "No existing wiki pages."

        lines = []
        for p in pages:
            aliases_str = ", ".join(p.aliases) if p.aliases else "none"
            tags_str = ", ".join(p.tags) if p.tags else "none"
            lines.append(
                f"- [{p.page_id}] {p.title} "
                f"(aliases: {aliases_str}, tags: {tags_str}, "
                f"summary: {p.summary[:100]})"
            )
        return "\n".join(lines)

    async def consolidate_page(self, page_id: str) -> None:
        """Consolidate a page when it exceeds wiki_max_page_size.

        Uses LLM to compress Details section, preserving Summary,
        Key Facts, and Evidence.
        """
        page = await self.read(page_id)
        if page is None:
            return

        if len(page.content) <= self._settings.wiki_max_page_size:
            return

        try:
            from app.core.llm import get_default_llm

            llm = get_default_llm()
            prompt = (
                "You are a knowledge consolidation assistant. "
                "Compress the following Wiki page while preserving:\n"
                "1. The Summary section (keep as-is)\n"
                "2. The Key Facts section (keep, deduplicate)\n"
                "3. The Evidence section (keep as-is)\n"
                "4. Compress Details section into concise bullet points\n\n"
                f"Page content:\n{page.content}\n\n"
                "Return the consolidated page in the same Markdown format."
            )
            response = await llm.ainvoke(prompt)
            consolidated = response.content

            page.content = consolidated
            page.content_hash = hashlib.md5(consolidated.encode()).hexdigest()
            page.updated_at = datetime.utcnow().isoformat()

            self._write_md_file(page)

            with get_db_session(self._settings) as session:
                session.execute(text("""
                    UPDATE wiki_pages
                    SET content_hash = :chash, updated_at = :now
                    WHERE page_id = :pid
                """), {
                    "chash": page.content_hash,
                    "now": page.updated_at,
                    "pid": page_id,
                })

            await self._embed_page(page)
            logger.info(f"Wiki page consolidated: {page_id}")

        except Exception as e:
            logger.error(f"Wiki consolidation failed for {page_id}: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """Get Wiki statistics."""
        pages = await self.list_pages()
        total_size = 0
        for p in pages:
            md_path = self._pages_dir / f"{p.page_id}.md"
            if md_path.exists():
                total_size += md_path.stat().st_size

        return {
            "total_pages": len(pages),
            "total_size_bytes": total_size,
            "pages": [
                {"page_id": p.page_id, "title": p.title, "tags": p.tags}
                for p in pages
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_md_file(self, page: WikiPage) -> None:
        """Write a WikiPage to its MD file."""
        md_path = self._pages_dir / f"{page.page_id}.md"
        md_path.write_text(page.content, encoding="utf-8")

    async def _embed_page(self, page: WikiPage) -> None:
        """Embed a page's index_text into ChromaDB.

        Index text = title + aliases + summary + key fact headings.
        Only 1 vector per page, not chunk-level.
        """
        if self._chroma_collection is None:
            return

        # Build index text
        parts = [page.title]
        if page.aliases:
            parts.append("Aliases: " + ", ".join(page.aliases))
        if page.summary:
            parts.append(page.summary)
        # Extract ## headings from content
        for line in page.content.split("\n"):
            if line.startswith("## ") and not line.startswith("## Open Questions"):
                parts.append(line.strip("# ").strip())

        index_text = "\n".join(parts)
        if not index_text.strip():
            return

        try:
            from app.core.embedding_manager import get_embedding_manager

            mgr = get_embedding_manager()
            model = mgr.get_model()
            if model is None:
                logger.debug("Embedding model not ready, skipping wiki embed")
                return

            embedding = model.encode([index_text]).tolist()

            self._chroma_collection.upsert(
                ids=[page.page_id],
                embeddings=embedding,
                documents=[index_text],
                metadatas=[{"title": page.title, "tags": json.dumps(page.tags)}],
            )
        except Exception as e:
            logger.warning(f"Failed to embed wiki page {page.page_id}: {e}")

    def _row_to_meta(self, row: Any) -> WikiPage:
        """Convert a DB row to WikiPage (no content)."""
        return WikiPage(
            page_id=row.page_id,
            title=row.title,
            aliases=json.loads(row.aliases) if row.aliases else [],
            tags=json.loads(row.tags) if row.tags else [],
            summary=row.summary or "",
            content="",
            content_hash=row.content_hash or "",
            evidence=json.loads(row.evidence) if row.evidence else [],
            confidence=row.confidence,
            created_at=row.created_at,
            updated_at=row.updated_at,
            access_count=row.access_count,
        )


# Singleton
_wiki_store_instance: WikiStore | None = None


def get_wiki_store() -> WikiStore:
    """Get or create the global WikiStore singleton."""
    global _wiki_store_instance
    if _wiki_store_instance is None:
        _wiki_store_instance = WikiStore()
    return _wiki_store_instance


def reset_wiki_store() -> None:
    """Reset the WikiStore singleton."""
    global _wiki_store_instance
    _wiki_store_instance = None
