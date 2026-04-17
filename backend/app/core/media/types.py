"""Data models for the Media Registry system."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MediaType(Enum):
    """Top-level classification of media artifacts."""

    IMAGE = "image"
    DOCUMENT = "document"


class ImageFormat(Enum):
    """Supported image file formats."""

    PNG = "png"
    JPEG = "jpeg"
    SVG = "svg"
    GIF = "gif"
    WEBP = "webp"


# Mapping from file extension to ImageFormat / MediaType helpers
_EXTENSION_TO_IMAGE_FORMAT: dict[str, ImageFormat] = {
    ".png": ImageFormat.PNG,
    ".jpg": ImageFormat.JPEG,
    ".jpeg": ImageFormat.JPEG,
    ".svg": ImageFormat.SVG,
    ".gif": ImageFormat.GIF,
    ".webp": ImageFormat.WEBP,
}

_IMAGE_MIME_TYPES: set[str] = {
    "image/png",
    "image/jpeg",
    "image/svg+xml",
    "image/gif",
    "image/webp",
}

_DOCUMENT_EXTENSIONS: set[str] = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".csv",
    ".xlsx",
    ".xls",
    ".json",
    ".xml",
    ".html",
    ".md",
}


def classify_extension(ext: str) -> tuple[MediaType, Optional[ImageFormat]]:
    """Return (MediaType, optional ImageFormat) for a file extension.

    Args:
        ext: Lower-cased file extension including the leading dot.

    Returns:
        A tuple of MediaType and, for images, the specific ImageFormat.
    """
    ext = ext.lower()
    if ext in _EXTENSION_TO_IMAGE_FORMAT:
        return MediaType.IMAGE, _EXTENSION_TO_IMAGE_FORMAT[ext]
    if ext in _DOCUMENT_EXTENSIONS:
        return MediaType.DOCUMENT, None
    # Default to DOCUMENT for unknown types
    return MediaType.DOCUMENT, None


def is_image_mime(mime: str) -> bool:
    """Return True if the MIME type is a recognised image type."""
    return mime.lower().split(";")[0].strip() in _IMAGE_MIME_TYPES


@dataclass
class MediaEntry:
    """A single registered media artifact.

    Attributes:
        media_id: Short unique identifier (first 12 hex chars of a UUID4).
        media_type: Whether this is an IMAGE or DOCUMENT.
        file_path: Absolute path to the file on disk.
        mime_type: MIME type guessed from the file extension / content.
        file_size: Size of the file in bytes.
        source: Provenance string (e.g. ``"tool:python_repl"``).
        session_id: Optional session that produced this media.
        created_at: POSIX timestamp when the entry was registered.
        description: Optional human-readable description.
    """

    media_type: MediaType
    file_path: str
    mime_type: str
    file_size: int
    source: str
    session_id: str = ""
    description: str = ""
    media_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=lambda: __import__("time").time())
    _base64_cache: Optional[str] = field(default=None, repr=False, compare=False)

    # -- convenience helpers --------------------------------------------------

    @property
    def is_image(self) -> bool:
        """Return True when the entry is an image type."""
        return self.media_type == MediaType.IMAGE

    @property
    def name(self) -> str:
        """Return the file name component of :pyattr:`file_path`."""
        from pathlib import PurePath

        return PurePath(self.file_path).name
