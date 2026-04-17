"""
Wiki Management API.

REST endpoints for browsing, searching, and managing Wiki pages.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.memory.wiki.models import WikiPage, WikiPatchOp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wiki", tags=["wiki"])


async def _ensure_initialized():
    """Ensure WikiStore is initialized before any operation."""
    from app.memory.wiki.store import get_wiki_store
    store = get_wiki_store()
    await store.initialize()
    return store


@router.get("/pages", response_model=List[Dict[str, Any]])
async def list_pages(tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)")):
    """List all Wiki pages."""
    store = await _ensure_initialized()
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    pages = await store.list_pages(tag_list)
    return [
        {
            "page_id": p.page_id,
            "title": p.title,
            "aliases": p.aliases,
            "tags": p.tags,
            "summary": p.summary,
            "confidence": p.confidence,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "access_count": p.access_count,
        }
        for p in pages
    ]


@router.get("/pages/{page_id}", response_model=Dict[str, Any])
async def get_page(page_id: str):
    """Get a Wiki page with full content."""
    store = await _ensure_initialized()
    page = await store.read(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Wiki page not found: {page_id}")
    return page.model_dump()


@router.post("/pages", response_model=Dict[str, Any])
async def create_page(page: WikiPage):
    """Manually create a new Wiki page."""
    store = await _ensure_initialized()
    page_id = await store.create_page(page)
    return {"page_id": page_id, "status": "created"}


@router.put("/pages/{page_id}", response_model=Dict[str, Any])
async def update_page(page_id: str, ops: List[WikiPatchOp]):
    """Manually update a Wiki page with patch operations."""
    store = await _ensure_initialized()
    await store.update_page(page_id, ops)
    return {"page_id": page_id, "status": "updated", "ops_count": len(ops)}


@router.delete("/pages/{page_id}", response_model=Dict[str, Any])
async def delete_page(page_id: str):
    """Delete a Wiki page."""
    store = await _ensure_initialized()
    success = await store.delete_page(page_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Wiki page not found: {page_id}")
    return {"page_id": page_id, "status": "deleted"}


@router.get("/search", response_model=Dict[str, Any])
async def search_wiki(q: str = Query(..., description="Search query"), top_k: int = Query(5, description="Max results")):
    """Search Wiki pages."""
    store = await _ensure_initialized()
    from app.memory.wiki.retriever import WikiRetriever
    from app.core.rag_engine import get_rag_engine

    retriever = WikiRetriever(store, get_rag_engine())
    result = await retriever.retrieve(q, top_k=top_k)
    return {
        "page_ids": result.page_ids,
        "wiki_context": result.wiki_context,
        "confidence_scores": result.confidence_scores,
        "source": result.source,
    }


@router.get("/stats", response_model=Dict[str, Any])
async def wiki_stats():
    """Get Wiki statistics."""
    store = await _ensure_initialized()
    return await store.get_stats()


@router.post("/consolidate/{page_id}", response_model=Dict[str, Any])
async def consolidate_page(page_id: str):
    """Manually trigger page consolidation."""
    store = await _ensure_initialized()
    await store.consolidate_page(page_id)
    return {"page_id": page_id, "status": "consolidated"}
