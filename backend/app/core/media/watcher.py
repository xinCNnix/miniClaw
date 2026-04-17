"""Background scanning utilities that discover unregistered media files."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from app.core.media.resolver import ALL_MEDIA_DIRS, find_file_in_roots, scan_text_for_paths
from app.core.media.registry import MediaRegistry
from app.core.media.types import MediaEntry

logger = logging.getLogger(__name__)


def scan_and_register(max_age_seconds: int = 60) -> list[MediaEntry]:
    """Scan ALL_MEDIA_DIRS for recently created files and register them.

    Only files whose modification time is within *max_age_seconds* of the
    current time and that are not already tracked by the registry will be
    registered.

    Args:
        max_age_seconds: Maximum file age in seconds (default 60).

    Returns:
        A list of newly registered :class:`MediaEntry` objects.
    """
    registry = MediaRegistry.get()
    now = time.time()
    threshold = now - max_age_seconds
    new_entries: list[MediaEntry] = []

    for root in ALL_MEDIA_DIRS:
        if not root.is_dir():
            continue

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            # Skip if already registered
            if registry.lookup_by_path(path) is not None:
                continue

            # Check file age
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue

            if mtime < threshold:
                continue

            try:
                entry = registry.register(path, source="watcher")
                new_entries.append(entry)
            except Exception:
                logger.warning("[MediaWatcher] Failed to register: %s", path)

    if new_entries:
        logger.info(
            "[MediaWatcher] scan_and_register: %d new file(s) registered",
            len(new_entries),
        )
    return new_entries


def scan_text_for_unregistered(text: str) -> list[Path]:
    """Extract paths from text, locate on disk, and return those not yet registered.

    This is useful for pre-populating the registry before calling
    :meth:`MediaRegistry.resolve_text`.

    Args:
        text: Text potentially containing file path references.

    Returns:
        A list of :class:`Path` objects for files that exist on disk but are
        not currently tracked by the registry.
    """
    registry = MediaRegistry.get()
    raw_paths = scan_text_for_paths(text)
    unregistered: list[Path] = []

    for raw_path in raw_paths:
        # Already tracked
        if registry.lookup_by_path(raw_path) is not None:
            continue

        found = find_file_in_roots(raw_path)
        if found is not None and registry.lookup_by_path(found) is None:
            unregistered.append(found)

    return unregistered
