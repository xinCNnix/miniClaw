"""Central MediaRegistry -- singleton that tracks media files produced during sessions."""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import ClassVar, DefaultDict, Dict, List, Optional, Set

from app.core.media.resolver import (
    ALL_MEDIA_DIRS,
    OUTPUT_DIRS,
    file_to_api_url,
    file_to_data_uri,
    find_file_in_roots,
    is_embeddable_image,
    guess_mime_type,
    normalize_path,
    scan_text_for_paths,
)
from app.core.media.types import MediaEntry, MediaType, classify_extension

logger = logging.getLogger(__name__)


class MediaRegistry:
    """Singleton registry that tracks media files and resolves text references.

    The registry maintains an in-memory index of media files on disk and can
    replace path references in text with inline data-URIs (for images) or
    HTTP API URLs (for large / non-image files).

    Usage::

        entry = MediaRegistry.get().register("/tmp/plot.png", source="tool:python")
        processed = MediaRegistry.get().resolve_text(response_text, session_id)
    """

    _instance: ClassVar[Optional["MediaRegistry"]] = None

    # ------------------------------------------------------------------
    # Construction & singleton access
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self._entries: Dict[str, MediaEntry] = {}
        # normalized path string -> media_id
        self._path_index: Dict[str, str] = {}
        # session_id -> set of media_ids
        self._session_index: DefaultDict[str, Set[str]] = defaultdict(set)

    @classmethod
    def get(cls) -> "MediaRegistry":
        """Return the global singleton instance, creating it if necessary."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        file_path: str | Path,
        source: str = "",
        session_id: Optional[str] = None,
        description: str = "",
    ) -> MediaEntry:
        """Register a file that already exists on disk.

        If the file has already been registered (matched by normalised path)
        the existing entry is returned without modification.

        Args:
            file_path: Path to the file.
            source: Provenance tag (e.g. ``"tool:python_repl"``).
            session_id: Optional session identifier.  When ``None`` the
                current tracking-context session is used if available.
            description: Optional human-readable description.

        Returns:
            The registered :class:`MediaEntry`.

        Raises:
            FileNotFoundError: If *file_path* does not point to an existing file.
        """
        resolved = Path(file_path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Cannot register non-existent file: {resolved}")

        norm = normalize_path(str(resolved))
        if norm in self._path_index:
            existing_id = self._path_index[norm]
            return self._entries[existing_id]

        # Auto-detect session_id from tracking_context when not supplied
        if session_id is None:
            try:
                from app.core.tracking_context import get_session_id

                session_id = get_session_id() or ""
            except ImportError:
                session_id = ""

        mime = guess_mime_type(resolved)
        media_type, _ = classify_extension(resolved.suffix)
        file_size = resolved.stat().st_size

        entry = MediaEntry(
            media_id=uuid.uuid4().hex[:12],
            media_type=media_type,
            file_path=str(resolved),
            mime_type=mime,
            file_size=file_size,
            source=source,
            session_id=session_id or "",
            description=description,
        )

        self._entries[entry.media_id] = entry
        self._path_index[norm] = entry.media_id
        if entry.session_id:
            self._session_index[entry.session_id].add(entry.media_id)

        logger.info(
            "[MediaRegistry] Registered: %s | %s | %s | %dB | session=%s",
            entry.media_id,
            entry.source,
            entry.name,
            entry.file_size,
            entry.session_id,
        )
        return entry

    def register_bytes(
        self,
        data: bytes,
        filename: str,
        source: str = "",
        session_id: Optional[str] = None,
        mime_type: str = "",
        description: str = "",
    ) -> MediaEntry:
        """Write raw bytes to disk and register the resulting file.

        The file is saved to the first writable directory in
        :pydata:`OUTPUT_DIRS`.

        Args:
            data: Raw file content.
            filename: Desired file name (a short UUID prefix is added to
                avoid collisions).
            source: Provenance tag.
            session_id: Optional session identifier.
            mime_type: Optional MIME type override.
            description: Optional description.

        Returns:
            The registered :class:`MediaEntry`.

        Raises:
            RuntimeError: If no writable output directory is available.
        """
        # Choose output directory
        out_dir: Optional[Path] = None
        for d in OUTPUT_DIRS:
            d.mkdir(parents=True, exist_ok=True)
            if d.is_dir():
                out_dir = d
                break

        if out_dir is None:
            raise RuntimeError("No writable output directory found for media bytes")

        # Build unique filename
        unique_prefix = uuid.uuid4().hex[:8]
        safe_name = f"{unique_prefix}_{filename}"
        target = out_dir / safe_name

        target.write_bytes(data)

        entry = self.register(
            file_path=target,
            source=source,
            session_id=session_id,
            description=description,
        )

        # Override mime_type if caller supplied one
        if mime_type:
            entry.mime_type = mime_type

        return entry

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_entry(self, media_id: str) -> Optional[MediaEntry]:
        """Look up an entry by its short identifier.

        Args:
            media_id: The 12-char hex identifier.

        Returns:
            The matching :class:`MediaEntry`, or ``None``.
        """
        return self._entries.get(media_id)

    def lookup_by_path(self, file_path: str | Path) -> Optional[MediaEntry]:
        """Look up an entry by normalised file path.

        Args:
            file_path: A file path to search for.

        Returns:
            The matching :class:`MediaEntry`, or ``None``.
        """
        norm = normalize_path(str(Path(file_path).resolve()))
        mid = self._path_index.get(norm)
        if mid is not None:
            return self._entries.get(mid)
        return None

    def get_session_media(self, session_id: str) -> list[MediaEntry]:
        """Return all entries associated with *session_id*.

        Args:
            session_id: The session identifier.

        Returns:
            A list of :class:`MediaEntry` objects.
        """
        ids = self._session_index.get(session_id, set())
        return [self._entries[mid] for mid in ids if mid in self._entries]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_session(self, session_id: str) -> None:
        """Remove all registry entries for the given session.

        Args:
            session_id: The session identifier to clear.
        """
        ids = self._session_index.pop(session_id, set())
        for mid in ids:
            entry = self._entries.pop(mid, None)
            if entry is not None:
                norm = normalize_path(entry.file_path)
                self._path_index.pop(norm, None)
        logger.info(
            "[MediaRegistry] Cleared session %s (%d entries removed)",
            session_id,
            len(ids),
        )

    def cleanup(self, max_age_seconds: int = 3600) -> None:
        """Remove entries older than *max_age_seconds*.

        Args:
            max_age_seconds: Maximum age in seconds (default 1 hour).
        """
        now = time.time()
        threshold = now - max_age_seconds
        to_remove: list[str] = []

        for mid, entry in self._entries.items():
            if entry.created_at < threshold:
                to_remove.append(mid)

        for mid in to_remove:
            entry = self._entries.pop(mid, None)
            if entry is not None:
                norm = normalize_path(entry.file_path)
                self._path_index.pop(norm, None)
                if entry.session_id:
                    self._session_index[entry.session_id].discard(mid)

        if to_remove:
            logger.info(
                "[MediaRegistry] Cleanup removed %d expired entries", len(to_remove)
            )

    def register_existing_files(self, output_dirs: list | None = None) -> int:
        """Scan output directories and register all existing media files.

        Called at startup to recover registry entries after a restart.

        Args:
            output_dirs: Optional list of directories to scan.
                Defaults to OUTPUT_DIRS from resolver.

        Returns:
            Number of files registered.
        """
        dirs = output_dirs or OUTPUT_DIRS
        count = 0
        for d in dirs:
            d = Path(d)
            if not d.is_dir():
                continue
            for f in d.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    self.register(f, source="startup_recovery")
                    count += 1
                except Exception:
                    pass
        if count:
            logger.info("[MediaRegistry] Startup recovery: registered %d existing files", count)
        return count

    # ------------------------------------------------------------------
    # Text resolution (core method)
    # ------------------------------------------------------------------

    def resolve_text(self, text: str, session_id: str = "") -> str:
        """Replace media path references in *text* with inline URIs or URLs.

        Resolution strategy:

        1. Extract candidate paths from the text via
           :func:`~app.core.media.resolver.scan_text_for_paths`.
        2. For each candidate, check if it is already in the registry.
        3. If not, attempt to find the file on disk and auto-register it.
        4. Replace the path reference:

           - **Embeddable images** (< 10 MB) are replaced with base64 data-URIs.
           - **Other files** (PDFs, large images, etc.) are replaced with the
             HTTP API URL.

        5. After replacements, any media entries belonging to *session_id*
           that were **not** referenced in the text are appended as a
           Markdown image / link section.

        Args:
            text: The response text containing path references.
            session_id: Optional session identifier for scoping.

        Returns:
            The processed text with paths replaced by inline URIs / URLs.
        """
        referenced_ids: set[str] = set()
        paths = scan_text_for_paths(text)

        for raw_path in paths:
            # Try registry lookup first
            entry = self.lookup_by_path(raw_path)

            # Try finding on disk and auto-registering
            if entry is None:
                found = find_file_in_roots(raw_path)
                if found is not None:
                    try:
                        entry = self.register(
                            found, source="auto", session_id=session_id or None
                        )
                    except Exception:
                        logger.warning(
                            "[MediaRegistry] Auto-register failed for %s", raw_path
                        )
                        continue

            if entry is None:
                continue

            referenced_ids.add(entry.media_id)

            # Build replacement URI/URL
            replacement = self._build_replacement(entry)

            # Replace in text (raw_path and normalised variants)
            text = text.replace(raw_path, replacement)
            norm = normalize_path(raw_path)
            if norm != raw_path:
                text = text.replace(norm, replacement)

        # Append unreferenced session media
        if session_id:
            text = self._append_unreferenced_session_media(text, session_id, referenced_ids)

        return text

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_replacement(self, entry: MediaEntry) -> str:
        """Return a data-URI or API URL for *entry*."""
        path = Path(entry.file_path)
        if entry.is_image and is_embeddable_image(path):
            # Use cached data-URI if available
            if entry._base64_cache is not None:
                return entry._base64_cache
            uri = file_to_data_uri(path)
            entry._base64_cache = uri
            return uri
        return file_to_api_url(entry.media_id)

    def _append_unreferenced_session_media(
        self,
        text: str,
        session_id: str,
        referenced_ids: set[str],
    ) -> str:
        """Append Markdown links/images for session media not yet in text."""
        entries = self.get_session_media(session_id)
        unreferenced = [e for e in entries if e.media_id not in referenced_ids]
        if not unreferenced:
            return text

        lines = [text, "", "---", "**Generated media:**", ""]

        for entry in unreferenced:
            replacement = self._build_replacement(entry)
            if entry.is_image:
                lines.append(f"![{entry.description or entry.name}]({replacement})")
            else:
                label = entry.description or entry.name
                lines.append(f"- [{label}]({replacement})")

        lines.append("")
        return "\n".join(lines)
