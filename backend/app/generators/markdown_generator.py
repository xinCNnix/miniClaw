"""
Markdown Generator - Generate USER.md and MEMORY.md from Database

This module generates human-readable Markdown files from SQLite database,
maintaining transparency while storing all data in the database.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.repositories.memory_repository import MemoryRepository
from app.models.database import MemoryDB, UserProfileDB
from app.config import get_settings, Settings

logger = logging.getLogger(__name__)


class MarkdownGenerator:
    """
    Generate Markdown files from database.

    This class generates USER.md and MEMORY.md from the database,
    applying time and confidence filters to keep files manageable.
    """

    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
    ):
        """
        Initialize the markdown generator.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings or get_settings()
        self.repo = MemoryRepository(session)

    def generate_user_md(self) -> str:
        """
        Generate USER.md content from database.

        Returns:
            Markdown content for USER.md
        """
        logger.info("Generating USER.md from database")

        # Get recent high-confidence preference memories
        memories = self.repo.get_memories_for_md(
            days=self.settings.md_user_include_days,
            min_confidence=self.settings.md_min_confidence,
            max_items=self.settings.md_user_max_items,
            memory_type="preference",
        )

        # Get user profile entries
        profile_entries = self.repo.get_profile_entries(limit=50)

        # Build markdown content
        content = self._build_user_md_content(memories, profile_entries)

        logger.info(f"Generated USER.md with {len(memories)} memories")
        return content

    def generate_memory_md(self) -> str:
        """
        Generate MEMORY.md content from database.

        Returns:
            Markdown content for MEMORY.md
        """
        logger.info("Generating MEMORY.md from database")

        # Get recent high-confidence memories for each type
        fact_memories = self.repo.get_memories_for_md(
            days=self.settings.md_memory_include_days,
            min_confidence=self.settings.md_min_confidence,
            max_items=self.settings.md_memory_max_items,
            memory_type="fact",
        )

        preference_memories = self.repo.get_memories_for_md(
            days=self.settings.md_memory_include_days,
            min_confidence=self.settings.md_min_confidence,
            max_items=self.settings.md_memory_max_items,
            memory_type="preference",
        )

        context_memories = self.repo.get_memories_for_md(
            days=self.settings.md_memory_include_days,
            min_confidence=self.settings.md_min_confidence,
            max_items=self.settings.md_memory_max_items,
            memory_type="context",
        )

        # Also include pattern memories in context
        pattern_memories = self.repo.get_memories_for_md(
            days=self.settings.md_memory_include_days,
            min_confidence=self.settings.md_min_confidence,
            max_items=25,  # Fewer patterns
            memory_type="pattern",
        )

        # Merge context and pattern memories
        all_context_memories = context_memories + pattern_memories
        # Sort by confidence
        all_context_memories.sort(key=lambda m: m.confidence, reverse=True)
        # Limit to max_items
        all_context_memories = all_context_memories[:self.settings.md_memory_max_items]

        # Build markdown content
        content = self._build_memory_md_content(
            fact_memories,
            preference_memories,
            all_context_memories,
        )

        total_memories = len(fact_memories) + len(preference_memories) + len(all_context_memories)
        logger.info(f"Generated MEMORY.md with {total_memories} memories")

        return content

    def write_user_md(self, path: Path | None = None) -> None:
        """
        Generate and write USER.md to file.

        Args:
            path: Custom file path (default: workspace/USER.md)
        """
        if path is None:
            path = Path(self.settings.workspace_dir) / "USER.md"

        content = self.generate_user_md()

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        path.write_text(content, encoding="utf-8")

        logger.info(f"USER.md written to: {path}")

    def write_memory_md(self, path: Path | None = None) -> None:
        """
        Generate and write MEMORY.md to file.

        Args:
            path: Custom file path (default: workspace/MEMORY.md)
        """
        if path is None:
            path = Path(self.settings.workspace_dir) / "MEMORY.md"

        content = self.generate_memory_md()

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        path.write_text(content, encoding="utf-8")

        logger.info(f"MEMORY.md written to: {path}")

    def sync_markdown_files(self) -> None:
        """
        Synchronize both USER.md and MEMORY.md from database.

        This method generates both files and updates the md_included flags.
        """
        logger.info("Starting markdown file synchronization")

        # Generate and write files
        self.write_user_md()
        self.write_memory_md()

        # Update metadata
        self._update_sync_metadata()

        logger.info("Markdown file synchronization completed")

    def _build_user_md_content(
        self,
        memories: List[MemoryDB],
        profile_entries: List[UserProfileDB],
    ) -> str:
        """Build USER.md content from memories and profile entries."""
        lines = []

        # Header with metadata
        since_date = datetime.utcnow() - timedelta(days=self.settings.md_user_include_days)
        lines.append("---")
        lines.append(f"generated_at: {datetime.utcnow().isoformat()}")
        lines.append(f"data_range: {since_date.strftime('%Y-%m-%d')} to {datetime.utcnow().strftime('%Y-%m-%d')}")
        lines.append(f"total_memories: {len(memories)}")
        lines.append(f"min_confidence: {self.settings.md_min_confidence}")
        lines.append("---")
        lines.append("")
        lines.append("# User Context")
        lines.append("")
        lines.append(f"> Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> Data range: Recent {self.settings.md_user_include_days} days")
        lines.append("")

        # Group preferences by category
        categories = self._categorize_preferences(memories)

        # Communication Style
        if "communication" in categories:
            lines.append("## Communication Style")
            lines.append("")
            for memory in categories["communication"]:
                lines.append(f"- {memory.content}")
            lines.append("")

        # Technical Preferences
        if "technical" in categories:
            lines.append("## Technical Preferences")
            lines.append("")
            for memory in categories["technical"]:
                lines.append(f"- {memory.content}")
            lines.append("")

        # Work Style
        if "work" in categories:
            lines.append("## Work Style")
            lines.append("")
            for memory in categories["work"]:
                lines.append(f"- {memory.content}")
            lines.append("")

        # Learning Preferences
        if "learning" in categories:
            lines.append("## Learning Preferences")
            lines.append("")
            for memory in categories["learning"]:
                lines.append(f"- {memory.content}")
            lines.append("")

        # Other Preferences
        other_categories = [cat for cat in categories.keys() if cat not in ["communication", "technical", "work", "learning"]]
        if other_categories:
            lines.append("## Other Preferences")
            lines.append("")
            for cat in other_categories:
                lines.append(f"### {cat.title()}")
                for memory in categories[cat]:
                    lines.append(f"- {memory.content}")
                lines.append("")

        # Profile entries (if different from memories)
        if profile_entries:
            lines.append("## Profile Details")
            lines.append("")
            for entry in profile_entries[:20]:  # Limit to 20
                lines.append(f"**{entry.category}**: {entry.content}")
            lines.append("")

        return "\n".join(lines)

    def _build_memory_md_content(
        self,
        fact_memories: List[MemoryDB],
        preference_memories: List[MemoryDB],
        context_memories: List[MemoryDB],
    ) -> str:
        """Build MEMORY.md content from memories."""
        lines = []

        # Header with metadata
        since_date = datetime.utcnow() - timedelta(days=self.settings.md_memory_include_days)
        total_memories = len(fact_memories) + len(preference_memories) + len(context_memories)
        lines.append("---")
        lines.append(f"generated_at: {datetime.utcnow().isoformat()}")
        lines.append(f"data_range: {since_date.strftime('%Y-%m-%d')} to {datetime.utcnow().strftime('%Y-%m-%d')}")
        lines.append(f"total_memories: {total_memories}")
        lines.append(f"min_confidence: {self.settings.md_min_confidence}")
        lines.append("---")
        lines.append("")
        lines.append("# Long-term Memory")
        lines.append("")
        lines.append(f"> Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> Data range: Recent {self.settings.md_memory_include_days} days")
        lines.append(f"> Total entries: {total_memories}")
        lines.append("")

        # Previous Interactions (facts)
        if fact_memories:
            lines.append("## Previous Interactions")
            lines.append("")
            for memory in fact_memories:
                date_str = memory.created_at.strftime("%Y-%m-%d")
                lines.append(f"- **{date_str}** (confidence: {memory.confidence:.2f}): {memory.content}")
            lines.append("")

        # Learned Preferences
        if preference_memories:
            lines.append("## Learned Preferences")
            lines.append("")
            for memory in preference_memories:
                date_str = memory.created_at.strftime("%Y-%m-%d")
                lines.append(f"- **{date_str}** (confidence: {memory.confidence:.2f}): {memory.content}")
            lines.append("")

        # Important Context (context + patterns)
        if context_memories:
            lines.append("## Important Context")
            lines.append("")
            for memory in context_memories:
                date_str = memory.created_at.strftime("%Y-%m-%d")
                mem_type = memory.type.capitalize()
                lines.append(f"- **{date_str}** [{mem_type}] (confidence: {memory.confidence:.2f}): {memory.content}")
            lines.append("")

        return "\n".join(lines)

    def _categorize_preferences(self, memories: List[MemoryDB]) -> Dict[str, List[MemoryDB]]:
        """
        Categorize preference memories into groups.

        Args:
            memories: List of memory objects

        Returns:
            Dictionary mapping category to list of memories
        """
        categories: Dict[str, List[MemoryDB]] = {
            "communication": [],
            "technical": [],
            "work": [],
            "learning": [],
            "other": [],
        }

        for memory in memories:
            content_lower = memory.content.lower()

            # Simple keyword-based categorization
            if any(word in content_lower for word in ["沟通", "交流", "communication", "说话", "表达", "简洁", "详细"]):
                categories["communication"].append(memory)
            elif any(word in content_lower for word in ["技术", "代码", "programming", "开发", "代码风格", "技术栈", "python", "javascript"]):
                categories["technical"].append(memory)
            elif any(word in content_lower for word in ["工作", "效率", "productivity", "任务", "协作", "workflow"]):
                categories["work"].append(memory)
            elif any(word in content_lower for word in ["学习", "learn", "理解", "解释", "示例", "教程"]):
                categories["learning"].append(memory)
            else:
                categories["other"].append(memory)

        # Remove empty categories
        return {k: v for k, v in categories.items() if v}

    def _update_sync_metadata(self) -> None:
        """Update synchronization metadata in database."""
        # Store last sync time
        self.repo.set_metadata("last_md_sync", datetime.utcnow().isoformat())

        # Store configuration used
        config = {
            "user_days": self.settings.md_user_include_days,
            "memory_days": self.settings.md_memory_include_days,
            "min_confidence": self.settings.md_min_confidence,
            "user_max_items": self.settings.md_user_max_items,
            "memory_max_items": self.settings.md_memory_max_items,
        }
        self.repo.set_metadata("md_sync_config", config)
