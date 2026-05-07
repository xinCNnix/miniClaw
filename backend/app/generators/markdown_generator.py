"""
Markdown Generator - Generate USER.md and MEMORY.md from database.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.config import Settings

logger = logging.getLogger(__name__)


class MarkdownGenerator:
    """Generates Markdown files from database content."""

    def __init__(self, db_session: Session, settings: Optional[Settings] = None):
        self.db = db_session
        self.settings = settings

    def sync_markdown_files(self) -> None:
        """Synchronize USER.md and MEMORY.md from database."""
        self._sync_user_md()
        self._sync_memory_md()

    def _sync_user_md(self) -> None:
        from app.models.database import UserProfileDB
        entries = self.db.query(UserProfileDB).order_by(
            UserProfileDB.category,
            UserProfileDB.updated_at.desc(),
        ).all()

        if not entries:
            logger.info("No profile entries to sync to USER.md")
            return

        lines = ["# User Profile\n"]
        current_category = None
        for entry in entries:
            if entry.category != current_category:
                current_category = entry.category
                lines.append(f"\n## {current_category}\n")
            lines.append(f"- {entry.content}")

        content = "\n".join(lines) + "\n"

        if self.settings:
            from pathlib import Path
            md_path = Path(self.settings.data_dir) / "USER.md"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(content, encoding="utf-8")
            logger.info(f"USER.md synced ({len(entries)} entries)")

    def _sync_memory_md(self) -> None:
        from app.models.database import MemoryDB
        memories = self.db.query(MemoryDB).order_by(
            MemoryDB.importance_score.desc(),
            MemoryDB.created_at.desc(),
        ).limit(100).all()

        if not memories:
            logger.info("No memories to sync to MEMORY.md")
            return

        lines = ["# Long-term Memory\n"]
        for mem in memories:
            lines.append(f"- [{mem.type}] {mem.content} (confidence: {mem.confidence:.2f})")

        content = "\n".join(lines) + "\n"

        if self.settings:
            from pathlib import Path
            md_path = Path(self.settings.data_dir) / "MEMORY.md"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(content, encoding="utf-8")
            logger.info(f"MEMORY.md synced ({len(memories)} entries)")
