"""Media API -- serve registered images via /api/media/{media_id}."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import logging

from app.core.media import get_registry

router = APIRouter(tags=["media"])
logger = logging.getLogger(__name__)


@router.get("/{media_id}")
async def serve_media(media_id: str):
    """Serve a registered media file by its ID."""
    registry = get_registry()
    entry = registry.get_entry(media_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Media not found: {media_id}")

    file_size_kb = entry.file_size / 1024
    logger.info(
        "[MediaAPI] Serving %s | %s | %s | %.0fKB",
        media_id,
        entry.name,
        entry.mime_type,
        file_size_kb,
    )

    return FileResponse(
        entry.file_path,
        media_type=entry.mime_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
