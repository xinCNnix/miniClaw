"""
Unified image embedding utility for all execution paths.

Scans output directories for recently generated images and embeds them
as base64 markdown in tool results, ensuring images reach the frontend
regardless of which execution path (ToT / PERV / Normal Agent) is used.

Usage:
    from app.core.streaming.image_embedder import embed_output_images
    result = embed_output_images(result_str)
"""

import base64
import logging
import re
import time
from pathlib import Path
from typing import Optional

# MediaRegistry integration (optional — graceful fallback if unavailable)
try:
    from app.core.media import register_file
    from app.core.media.resolver import file_to_api_url
except ImportError:
    register_file = None  # type: ignore[assignment]
    file_to_api_url = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Supported image formats
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}

MIME_MAP = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
}

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB per image

# Track already-reported file paths to avoid sending stale/duplicate images
# across multiple rounds within the same backend process.
_reported_paths: set[str] = set()

# Candidate output directories (resolved once at import)
_BACKEND_ROOT: Optional[Path] = None
_PROJECT_ROOT: Optional[Path] = None

# Regex to find image file paths in output text
_PATH_PATTERN = re.compile(
    r'(?:outputs?[/\\])[\w\-]+\.(?:png|jpg|jpeg|gif|webp|svg)',
    re.IGNORECASE,
)


def _get_roots() -> tuple[Path, Path]:
    """Resolve backend and project root directories (lazy, once)."""
    global _BACKEND_ROOT, _PROJECT_ROOT
    if _BACKEND_ROOT is None:
        # app/core/streaming/image_embedder.py -> backend/
        _BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
        _PROJECT_ROOT = _BACKEND_ROOT.parent
    return _BACKEND_ROOT, _PROJECT_ROOT


def _get_output_dirs() -> list[Path]:
    """Return candidate output directories to scan for images."""
    backend_root, project_root = _get_roots()
    return [
        project_root / "outputs",       # project_root/outputs/  (skill scripts default)
        backend_root / "outputs",       # backend/outputs/
        backend_root / "data" / "outputs",  # data/outputs/  (visual_base default)
    ]


def _scan_text_paths(result_str: str, roots: list[Path]) -> list[Path]:
    """Extract image file paths mentioned in the output text."""
    found: list[Path] = []
    for match in _PATH_PATTERN.finditer(result_str):
        rel = match.group(0).replace('\\', '/')
        for root in roots:
            full = root / rel
            if full.exists() and full not in found:
                found.append(full)
                break
    return found


def _scan_recent_files(roots: list[Path], max_age_seconds: int) -> list[Path]:
    """Scan output directories for recently modified image files."""
    now = time.time()
    found: list[Path] = []
    for outputs_dir in roots:
        if not outputs_dir.is_dir():
            continue
        for f in outputs_dir.iterdir():
            if f.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                if now - f.stat().st_mtime < max_age_seconds and f not in found:
                    found.append(f)
            except OSError:
                pass
    return found


def clear_reported_images():
    """Reset the set of already-reported image paths (call at session start)."""
    _reported_paths.clear()


def embed_output_images(
    result_str: str,
    max_age_seconds: int = 60,
) -> str:
    """Scan for generated images and embed them as base64 markdown.

    This is the **unified entry point** used by all execution paths
    (ToT skill_orchestrator, terminal tool, PERV executor, Normal Agent, etc.).

    Two detection methods:
    1. Scan output text for explicit image file paths (e.g. ``outputs/foo.png``)
    2. Scan output directories for recently modified image files

    Args:
        result_str: The tool output text so far.
        max_age_seconds: Only embed files modified within this window.

    Returns:
        result_str with base64-encoded image markdown appended.
    """
    # Skip if result already contains embedded images
    if "data:image/" in result_str:
        return result_str

    output_dirs = _get_output_dirs()
    all_roots = list(set(output_dirs + [d.parent for d in output_dirs if d.parent.exists()]))

    # Method 1: paths mentioned in output text
    found = _scan_text_paths(result_str, all_roots)

    # Method 2: recently modified files in output dirs
    recent = _scan_recent_files(output_dirs, max_age_seconds)
    for f in recent:
        if f not in found:
            found.append(f)

    if not found:
        return result_str

    # Filter out already-reported paths
    new_found = [f for f in found if str(f.resolve()) not in _reported_paths]
    if not new_found:
        return result_str

    for fpath in new_found:
        try:
            canonical = str(fpath.resolve())
            file_size = fpath.stat().st_size
            if file_size > MAX_IMAGE_SIZE:
                logger.debug(f"Skipping large image: {fpath.name} ({file_size} bytes)")
                continue
            data = fpath.read_bytes()
            b64 = base64.b64encode(data).decode('utf-8')
            mime = MIME_MAP.get(fpath.suffix.lower(), 'image/png')
            result_str += f"\n![{fpath.name}](data:{mime};base64,{b64})"
            _reported_paths.add(canonical)
            logger.info(f"[ImageEmbedder] Embedded: {fpath.name} ({file_size} bytes)")
            # Register with MediaRegistry so downstream resolvers can track it
            if register_file:
                try:
                    register_file(str(fpath), source="image_embedder")
                except Exception:
                    pass  # Non-critical — embed already succeeded
        except Exception as e:
            logger.debug(f"Failed to embed image {fpath.name}: {e}")

    return result_str


def embed_output_images_v2(
    result_str: str,
    max_age_seconds: int = 60,
) -> tuple[str, list[dict]]:
    """Scan for generated images and return structured metadata.

    Same detection logic as embed_output_images() but returns:
    - clean_output: original text WITHOUT base64 appended
    - generated_images: [{media_id, api_url, name, mime_type}]

    Args:
        result_str: The tool output text so far.
        max_age_seconds: Only include files modified within this window.

    Returns:
        Tuple of (clean_output, generated_images_list).
    """
    # Skip if result already contains embedded images (legacy path)
    if "data:image/" in result_str:
        return result_str, []

    output_dirs = _get_output_dirs()
    all_roots = list(set(output_dirs + [d.parent for d in output_dirs if d.parent.exists()]))

    # [DEBUG-LOG] Log directories being scanned
    logger.debug(
        "[ImageEmbedder:v2] Scanning %d dirs (max_age=%ds): %s",
        len(output_dirs), max_age_seconds,
        [str(d) for d in output_dirs],
    )

    # Method 1: paths mentioned in output text
    found = _scan_text_paths(result_str, all_roots)
    if found:
        logger.debug("[ImageEmbedder:v2] Text-path scan found: %s", [f.name for f in found])

    # Method 2: recently modified files in output dirs
    recent = _scan_recent_files(output_dirs, max_age_seconds)
    if recent:
        logger.debug("[ImageEmbedder:v2] Recent-file scan found: %s", [f.name for f in recent])
    else:
        logger.debug(
            "[ImageEmbedder:v2] Recent-file scan found 0 files (checked %d dirs, max_age=%ds)",
            len(output_dirs), max_age_seconds,
        )
    for f in recent:
        if f not in found:
            found.append(f)

    if not found:
        logger.debug("[ImageEmbedder:v2] No images found from any method")
        return result_str, []

    # Filter out already-reported paths to prevent stale/duplicate images
    canonical = [str(f.resolve()) for f in found]
    new_files = [(f, c) for f, c in zip(found, canonical) if c not in _reported_paths]
    if new_files:
        logger.debug(
            "[ImageEmbedder:v2] After dedup vs reported: %d/%d new files: %s",
            len(new_files), len(found), [f.name for f, _ in new_files],
        )
    else:
        logger.debug("[ImageEmbedder:v2] All %d found files already reported, skipping", len(found))
        return result_str, []

    images: list[dict] = []
    for fpath, canonical_path in new_files:
        try:
            file_size = fpath.stat().st_size
            if file_size > MAX_IMAGE_SIZE:
                logger.debug("Skipping large image: %s (%d bytes)", fpath.name, file_size)
                continue
            mime = MIME_MAP.get(fpath.suffix.lower(), 'image/png')

            # Register with MediaRegistry to get a media_id and serve via API
            entry = None
            if register_file:
                try:
                    entry = register_file(str(fpath), source="image_embedder_v2")
                except Exception:
                    pass

            if entry:
                images.append({
                    "media_id": entry.media_id,
                    "api_url": file_to_api_url(entry.media_id),
                    "name": fpath.name,
                    "mime_type": mime,
                })
                _reported_paths.add(canonical_path)
                logger.debug("[ImageEmbedder:v2] Registered %s | %s | %s", entry.media_id, fpath.name, mime)
            else:
                # Fallback: still track the image even without registry
                logger.warning("[ImageEmbedder:v2] Could not register %s, skipping", fpath.name)

        except Exception as e:
            logger.debug("[ImageEmbedder:v2] Failed to process %s: %s", fpath.name, e)

    # Deduplicate by media_id (same file may exist in multiple output dirs)
    seen_ids: set[str] = set()
    unique_images: list[dict] = []
    for img in images:
        if img["media_id"] not in seen_ids:
            seen_ids.add(img["media_id"])
            unique_images.append(img)

    logger.info("[ImageEmbedder:v2] Found %d images (%d after dedup) | %s", len(images), len(unique_images), ", ".join(i["name"] for i in unique_images))

    # Strip SVG content and large base64 blobs from result to prevent
    # them from being sent to the frontend as raw text (causes "double image").
    clean_result = result_str
    clean_result = re.sub(
        r"'svg_content':\s*'(<\?xml.*?</svg>)'",
        "'svg_content': '[stripped]'",
        clean_result,
        flags=re.DOTALL,
    )
    clean_result = re.sub(
        r'svg_content["\']?\s*:\s*["\']<\?xml.*?</svg>["\']?',
        'svg_content: "[stripped]"',
        clean_result,
        flags=re.DOTALL,
    )
    clean_result = re.sub(
        r"data:image/[^;]+;base64,[A-Za-z0-9+/=\n]+",
        "[base64 image stripped]",
        clean_result,
    )

    return clean_result, unique_images


def build_image_markdown(gen_images: list[dict]) -> str:
    """Convert structured generated_images to markdown image refs with API URLs.

    Used to append image refs to content text so ReactMarkdown renders them inline.
    """
    if not gen_images:
        return ""
    return "".join(
        f"\n\n![{img['name']}]({img['api_url']})"
        for img in gen_images
        if img.get("api_url")
    )
