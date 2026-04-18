"""Media Registry -- track, resolve, and inline media files produced during sessions."""

from __future__ import annotations

from app.core.media.registry import MediaRegistry
from app.core.media.resolver import file_to_data_uri, find_file_in_roots
from app.core.media.types import ImageFormat, MediaEntry, MediaType

__all__ = [
    "MediaRegistry",
    "MediaType",
    "ImageFormat",
    "MediaEntry",
    "file_to_data_uri",
    "find_file_in_roots",
    "get_registry",
    "register_file",
    "resolve_media",
]


def get_registry() -> MediaRegistry:
    """Return the global :class:`MediaRegistry` singleton."""
    return MediaRegistry.get()


def register_file(
    file_path: str,
    source: str = "",
    session_id: str | None = None,
    **kw,
) -> MediaEntry:
    """Convenience wrapper around :meth:`MediaRegistry.register`."""
    return get_registry().register(file_path, source, session_id, **kw)


def resolve_media(text: str, session_id: str = "") -> str:
    """Convenience wrapper around :meth:`MediaRegistry.resolve_text`."""
    return get_registry().resolve_text(text, session_id)
