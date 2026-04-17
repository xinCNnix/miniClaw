"""Ingest nodes — EventLog write + chunking/embedding.

Phase 2.7: ingest_eventlog with SHA256 dedup (红线1).
"""

import hashlib
import json
import logging
import time
from uuid import uuid4

from app.memory.engine.state import MemoryState

logger = logging.getLogger(__name__)


async def ingest_eventlog(state: MemoryState) -> MemoryState:
    """Write new events to event_log with SHA256 hash dedup.

    Dedup: same payload hash → skip. This prevents duplicate events
    when the same conversation is processed multiple times.
    """
    new_events = state.get("new_events", [])
    if not new_events:
        return state

    logs = state.get("logs", [])
    settings = _get_settings()

    try:
        from app.core.database import get_db_session
    except ImportError:
        logs.append("[ingest_eventlog] database not available, skipping")
        state["logs"] = logs
        return state

    inserted = 0
    skipped = 0

    with get_db_session() as session:
        for evt in new_events:
            payload = evt.get("payload", {})
            payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            content_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

            # Check dedup
            from sqlalchemy import text
            result = session.execute(
                text("SELECT 1 FROM event_log WHERE hash = :hash LIMIT 1"),
                {"hash": content_hash},
            )
            if result.scalar() is not None:
                skipped += 1
                continue

            event_id = evt.get("event_id") or f"evt_{uuid4().hex[:12]}"
            session_id = evt.get("session_id", state.get("session_id", ""))
            user_id = evt.get("user_id", state.get("user_id", ""))
            event_type = evt.get("event_type", "unknown")
            source_type = evt.get("source_type", "conversation")
            source_ref = evt.get("source_ref", "")
            meta = evt.get("meta", {})

            # Enforce payload size limit
            max_size = getattr(settings, "event_log_max_payload_size", 10000)
            if len(payload_str) > max_size:
                payload_str = payload_str[:max_size]
                logs.append(f"[ingest_eventlog] payload truncated for event {event_id}")

            session.execute(
                text(
                    "INSERT INTO event_log "
                    "(event_id, ts, session_id, user_id, event_type, source_type, "
                    " payload_json, hash, source_ref, meta_json) "
                    "VALUES (:event_id, :ts, :session_id, :user_id, :event_type, :source_type, "
                    " :payload_json, :hash, :source_ref, :meta_json)"
                ),
                {
                    "event_id": event_id,
                    "ts": evt.get("ts", time.time()),
                    "session_id": session_id,
                    "user_id": user_id,
                    "event_type": event_type,
                    "source_type": source_type,
                    "payload_json": payload_str,
                    "hash": content_hash,
                    "source_ref": source_ref,
                    "meta_json": json.dumps(meta, ensure_ascii=False),
                },
            )
            inserted += 1

    logs.append(
        f"[ingest_eventlog] inserted={inserted}, skipped_dedup={skipped}"
    )
    state["logs"] = logs
    return state


def _get_settings():
    """Lazy import settings."""
    from app.config import get_settings
    return get_settings()


async def chunk_and_embed(state: MemoryState) -> MemoryState:
    """Split events into chunks, embed them, and store in ChromaDB.

    Processes events from the EventLog (written by ingest_eventlog),
    splits them into ~500-char chunks with overlap, embeds via
    EmbeddingManager, and upserts into ChromaDB with chunk_hash dedup.
    """
    new_events = state.get("new_events", [])
    session_id = state.get("session_id", "")
    if not new_events:
        return state

    logs = state.get("logs", [])
    chunks = state.get("chunks", [])
    chunk_size = 500
    chunk_overlap = 100

    try:
        from app.core.embedding_manager import get_embedding_manager
        from app.core.rag_engine import get_chroma_client
        emb_mgr = get_embedding_manager()
        client = get_chroma_client()
        collection = client.get_or_create_collection("memory_chunks")
    except Exception as e:
        logs.append(f"[chunk_and_embed] Embedding/ChromaDB not available: {e}")
        state["logs"] = logs
        return state

    chunked = 0
    deduped = 0

    for evt in new_events:
        payload = evt.get("payload", {})
        content = payload.get("content", "")
        if not content or len(content.strip()) < 20:
            continue

        # Split into chunks
        event_chunks = _split_text(content, chunk_size, chunk_overlap)

        for i, chunk_text in enumerate(event_chunks):
            # Chunk hash dedup (红线1)
            chunk_hash = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()
            doc_id = f"{session_id}_{chunk_hash[:16]}"

            # Check existing
            try:
                existing = collection.get(ids=[doc_id])
                if existing and existing["ids"]:
                    deduped += 1
                    continue
            except Exception:
                pass

            # Embed
            try:
                embedding = await emb_mgr.embed_text(chunk_text)
            except Exception as e:
                logs.append(f"[chunk_and_embed] Embedding failed for chunk {i}: {e}")
                continue

            # Upsert to ChromaDB
            try:
                collection.upsert(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[chunk_text],
                    metadatas=[{
                        "session_id": session_id,
                        "event_type": evt.get("event_type", "unknown"),
                        "source_type": evt.get("source_type", "conversation"),
                        "chunk_index": i,
                        "chunk_hash": chunk_hash,
                        "ts": evt.get("ts", time.time()),
                    }],
                )
            except Exception as e:
                logs.append(f"[chunk_and_embed] ChromaDB upsert failed: {e}")
                continue

            chunks.append({
                "text": chunk_text,
                "chunk_hash": chunk_hash,
                "doc_id": doc_id,
                "source_event": evt.get("event_id", ""),
                "layer": "episodic",
            })
            chunked += 1

    logs.append(f"[chunk_and_embed] chunked={chunked}, deduped={deduped}")
    state["chunks"] = chunks
    state["logs"] = logs
    return state


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks, breaking at sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence-ending punctuation
            for sep in ["。", ".", "！", "!", "？", "?", "\n"]:
                pos = text.rfind(sep, start + chunk_size // 2, end)
                if pos != -1:
                    end = pos + 1
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap
        if start >= len(text):
            break

    return chunks
