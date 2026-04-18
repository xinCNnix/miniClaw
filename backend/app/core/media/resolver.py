"""Stateless helper functions for media path resolution and URI construction."""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory constants
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]  # miniclaw/

OUTPUT_DIRS: list[Path] = [
    PROJECT_ROOT / "outputs",
    PROJECT_ROOT / "backend" / "outputs",
    PROJECT_ROOT / "backend" / "data" / "outputs",
]

DOWNLOAD_DIRS: list[Path] = [
    PROJECT_ROOT / "downloads",
    PROJECT_ROOT / "backend" / "downloads",
]

ALL_MEDIA_DIRS: list[Path] = OUTPUT_DIRS + DOWNLOAD_DIRS

# ---------------------------------------------------------------------------
# URI / URL helpers
# ---------------------------------------------------------------------------


def file_to_data_uri(path: Path) -> str:
    """Read a file from disk and return a base64 data-URI string.

    Args:
        path: Absolute or relative path to the file.

    Returns:
        A ``data:{mime};base64,{encoded}`` string.

    Raises:
        FileNotFoundError: If *path* does not exist on disk.
    """
    resolved = Path(path).resolve()
    mime = guess_mime_type(resolved)
    data = resolved.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    uri = f"data:{mime};base64,{encoded}"
    logger.info(
        "[MediaResolver] data-uri generated | %s | %s | %dB",
        resolved.name,
        mime,
        len(data),
    )
    return uri


def file_to_api_url(media_id: str) -> str:
    """Return the HTTP API URL that serves a registered media entry.

    Args:
        media_id: The short identifier of a :class:`MediaEntry`.

    Returns:
        An absolute URL string pointing to the local API server.
    """
    try:
        from app.config import get_settings

        settings = get_settings()
        host = settings.host if settings.host != "0.0.0.0" else "localhost"
        port = settings.port
    except Exception:
        host, port = "localhost", 8002
    return f"http://{host}:{port}/api/media/{media_id}"


# ---------------------------------------------------------------------------
# MIME / format detection
# ---------------------------------------------------------------------------


def guess_mime_type(path: Path) -> str:
    """Guess the MIME type for a file path.

    Uses the :mod:`mimetypes` standard library module with a fallback of
    ``application/octet-stream`` when the type cannot be determined.

    Args:
        path: File path to inspect.

    Returns:
        A MIME type string.
    """
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def is_embeddable_image(path: Path, max_size: int = 10 * 1024 * 1024) -> bool:
    """Return True when the file is an image small enough to embed inline.

    Args:
        path: File path to inspect.
        max_size: Maximum file size in bytes (default 10 MB).

    Returns:
        ``True`` if the file looks like an image and is within *max_size*.
    """
    mime = guess_mime_type(path)
    if not mime.startswith("image/"):
        return False
    try:
        return path.stat().st_size <= max_size
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Path search
# ---------------------------------------------------------------------------

# Partial segment pattern: avoid trivial short strings
_MIN_SEGMENT_LEN = 3


def find_file_in_roots(partial_path: str) -> Optional[Path]:
    """Search ALL_MEDIA_DIRS for a file whose path contains *partial_path*.

    The search is performed as a suffix/contains match on the resolved
    path string.  The first existing match is returned.

    Args:
        partial_path: A relative fragment such as ``"outputs/plot.png"`` or
            just ``"plot.png"``.

    Returns:
        The resolved :class:`Path` if found, or ``None``.
    """
    normalized = partial_path.replace("\\", "/")

    # 1. Try as-is under each media root
    for root in ALL_MEDIA_DIRS:
        candidate = (root / normalized).resolve()
        if candidate.is_file():
            logger.debug(
                "[MediaResolver] find_file_in_roots hit (direct): %s", candidate
            )
            return candidate

    # 2. Search recursively for filename match
    filename = Path(normalized).name
    if len(filename) >= _MIN_SEGMENT_LEN:
        for root in ALL_MEDIA_DIRS:
            if not root.is_dir():
                continue
            for match in root.rglob(filename):
                if match.is_file():
                    logger.debug(
                        "[MediaResolver] find_file_in_roots hit (rglob): %s", match
                    )
                    return match

    logger.debug("[MediaResolver] find_file_in_roots miss: %s", partial_path)
    return None


# ---------------------------------------------------------------------------
# Text scanning
# ---------------------------------------------------------------------------

# Patterns for extracting file paths from markdown / tool output text.
_PATH_PATTERNS: list[re.Pattern[str]] = [
    # Markdown images:  ![alt](path)
    re.compile(r"!\[[^\]]*\]\(([^)]+)\)"),
    # Explicit key-value:  image_path: path  / file_path: path
    re.compile(r"(?:image_path|file_path|filepath|output_path)\s*[:=]\s*[\"']?([^\s\"',;)\]]+)", re.IGNORECASE),
    # Generic quoted paths containing outputs/ or downloads/
    re.compile(r'["\'`]([^"\'`]*?(?:outputs|downloads)[/\\][^"\'`]*?)["\'`]', re.IGNORECASE),
    # Bare paths containing outputs/ or downloads/ (must start at word boundary,
    # not inside markdown image syntax like ![alt](outputs/...))
    re.compile(r'(?<![=(/\w])([A-Za-z]:[\\/][^\s:<>"|*?]*?(?:outputs|downloads)[/\\][^\s)<>"|*?]+)', re.IGNORECASE),
    re.compile(r'(?<![=(/\w])(?<![A-Za-z]:)((?:\.{0,2}/)*[^\s:()<>"|*?]*?(?:outputs|downloads)[/\\][^\s)<>"|*?]+)', re.IGNORECASE),
]


def scan_text_for_paths(text: str) -> list[str]:
    """Extract potential file paths from free-form text.

    Scans for Markdown image syntax, explicit ``image_path`` key-value pairs,
    and bare paths containing ``outputs/`` or ``downloads/`` segments.

    Args:
        text: The text to scan.

    Returns:
        A deduplicated list of raw path strings (preserving insertion order).
    """
    seen: set[str] = set()
    results: list[str] = []

    for pattern in _PATH_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group(1).strip()
            # Skip data URIs and http URLs — these are already resolved
            if not candidate or candidate.startswith(("data:", "http://", "https://")):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            results.append(candidate)

    return results


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

_STRIP_PREFIXES = ("outputs", "downloads", "output", "download")


def normalize_path(raw_path: str) -> str:
    """Normalize a raw path string to a forward-slash relative form.

    Back-slashes are converted to forward-slashes.  If the path contains a
    segment named ``outputs`` or ``downloads``, everything before and
    including that segment is stripped so the result is relative to that
    root directory.

    Args:
        raw_path: The raw path string.

    Returns:
        A normalized relative path string.
    """
    normalized = raw_path.replace("\\", "/").strip()

    # Remove leading ./
    while normalized.startswith("./"):
        normalized = normalized[2:]

    # Try to extract the relative part after outputs/ or downloads/
    parts = normalized.split("/")
    for idx, part in enumerate(parts):
        if part.lower() in _STRIP_PREFIXES:
            return "/".join(parts[idx + 1:])

    return normalized
