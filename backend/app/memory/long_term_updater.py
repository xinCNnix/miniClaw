"""
Long-term Memory Updater - Automatic MEMORY.md updates.

This module handles automatic updates to MEMORY.md based on extracted memories.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.memory import Memory
from app.core.llm import get_default_llm
from app.config import get_settings

logger = logging.getLogger(__name__)


class LongTermMemoryUpdater:
    """
    Automatically updates MEMORY.md with long-term memories.

    This class:
    1. Categorizes memories into sections (Previous Interactions, Learned Preferences, Important Context)
    2. De-duplicates similar memories
    3. Limits total entries to prevent bloat
    4. Prunes old/low-confidence memories
    """

    def __init__(self, llm: BaseChatModel | None = None):
        """
        Initialize the long-term memory updater.

        Args:
            llm: Optional LLM instance. If not provided, uses default LLM.
        """
        self.llm = llm or get_default_llm()
        self.settings = get_settings()
        self.memory_md_path = Path(self.settings.workspace_dir) / "MEMORY.md"

        # Metadata file for tracking memory timestamps and confidence
        self.metadata_path = Path(self.settings.data_dir) / "memory_metadata.json"

    async def update_from_memories(self, memories: List[Memory]) -> None:
        """
        Update MEMORY.md with new long-term memories.

        Args:
            memories: List of memories to integrate
        """
        if not memories:
            return

        logger.info(f"Updating MEMORY.md with {len(memories)} memories")

        try:
            # Load existing memory metadata
            metadata = self._load_metadata()

            # Categorize new memories
            categorized = self._categorize_memories(memories)

            # Merge with existing memories and deduplicate
            merged = self._merge_and_deduplicate(metadata, categorized)

            # Limit entries and prune old ones
            pruned = self._prune_memories(merged)

            # Save updated metadata
            self._save_metadata(pruned)

            # Generate and write MEMORY.md
            await self._write_memory_md(pruned)

            logger.info("MEMORY.md updated successfully")

        except Exception as e:
            logger.error(f"Failed to update MEMORY.md: {e}", exc_info=True)

    def _load_metadata(self) -> Dict[str, Any]:
        """
        Load existing memory metadata.

        Returns:
            Metadata dict with sections for each memory type
        """
        if self.metadata_path.exists():
            try:
                content = self.metadata_path.read_text(encoding="utf-8")
                return json.loads(content)
            except Exception as e:
                logger.warning(f"Failed to load memory metadata: {e}")

        # Return default structure
        return {
            "previous_interactions": [],
            "learned_preferences": [],
            "important_context": [],
        }

    def _save_metadata(self, metadata: Dict[str, Any]) -> None:
        """
        Save memory metadata to file.

        Args:
            metadata: Metadata dict to save
        """
        # Ensure parent directory exists
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(self.metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def _categorize_memories(self, memories: List[Memory]) -> Dict[str, List[Dict]]:
        """
        Categorize memories into sections.

        Args:
            memories: List of memories

        Returns:
            Dict with categorized memories
        """
        categorized = {
            "previous_interactions": [],
            "learned_preferences": [],
            "important_context": [],
        }

        for memory in memories:
            entry = {
                "content": memory.content,
                "timestamp": memory.timestamp,
                "confidence": memory.confidence,
                "session_id": memory.session_id,
            }

            if memory.type == "fact":
                categorized["previous_interactions"].append(entry)
            elif memory.type == "preference":
                categorized["learned_preferences"].append(entry)
            elif memory.type in ["context", "pattern"]:
                categorized["important_context"].append(entry)

        return categorized

    def _merge_and_deduplicate(
        self,
        existing: Dict[str, Any],
        new_memories: Dict[str, List[Dict]],
    ) -> Dict[str, Any]:
        """
        Merge new memories with existing and deduplicate.

        Args:
            existing: Existing metadata
            new_memories: New categorized memories

        Returns:
            Merged metadata
        """
        merged = {}

        for section in ["previous_interactions", "learned_preferences", "important_context"]:
            existing_items = existing.get(section, [])
            new_items = new_memories.get(section, [])

            # Simple deduplication: check for similar content
            combined = existing_items.copy()

            for new_item in new_items:
                is_duplicate = False

                for existing_item in existing_items:
                    # Check if content is very similar (simple check)
                    if self._are_similar(
                        new_item["content"],
                        existing_item["content"]
                    ):
                        # Update with higher confidence
                        if new_item["confidence"] > existing_item["confidence"]:
                            existing_item.update(new_item)
                        is_duplicate = True
                        break

                if not is_duplicate:
                    combined.append(new_item)

            merged[section] = combined

        return merged

    def _are_similar(self, text1: str, text2: str) -> bool:
        """
        Check if two text contents are similar (simple heuristic).

        Args:
            text1: First text
            text2: Second text

        Returns:
            True if texts are similar
        """
        # Simple similarity check: one is substring of the other
        # or they share significant word overlap
        t1_lower = text1.lower()
        t2_lower = text2.lower()

        # Check substring
        if t1_lower in t2_lower or t2_lower in t1_lower:
            return True

        # Check word overlap
        words1 = set(t1_lower.split())
        words2 = set(t2_lower.split())

        if not words1 or not words2:
            return False

        overlap = len(words1 & words2)
        avg_length = (len(words1) + len(words2)) / 2

        # If more than 60% word overlap, consider similar
        return overlap / avg_length > 0.6

    def _prune_memories(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Limit entries and prune old/low-confidence memories.

        Args:
            metadata: Metadata dict

        Returns:
            Pruned metadata
        """
        max_items = self.settings.long_term_memory_max_items
        prune_threshold = self.settings.long_term_memory_prune_threshold
        now = datetime.now()

        pruned = {}

        for section, items in metadata.items():
            # Filter by confidence threshold
            filtered = [
                item for item in items
                if item["confidence"] >= prune_threshold
            ]

            # Sort by confidence (descending) and timestamp (descending)
            filtered.sort(
                key=lambda x: (x["confidence"], x["timestamp"]),
                reverse=True,
            )

            # Limit to max items
            filtered = filtered[:max_items]

            pruned[section] = filtered

        return pruned

    async def _write_memory_md(self, metadata: Dict[str, Any]) -> None:
        """
        Generate and write MEMORY.md file.

        Args:
            metadata: Memory metadata
        """
        lines = ["# Long-term Memory\n"]

        # Previous Interactions
        lines.append("\n## Previous Interactions")
        items = metadata.get("previous_interactions", [])
        if items:
            for item in items[:10]:  # Show up to 10 items
                lines.append(f"- {item['content']}")
        else:
            lines.append("*(No previous interactions recorded yet)*")

        # Learned Preferences
        lines.append("\n## Learned Preferences")
        items = metadata.get("learned_preferences", [])
        if items:
            for item in items[:10]:
                lines.append(f"- {item['content']}")
        else:
            lines.append("*(No learned preferences recorded yet)*")

        # Important Context
        lines.append("\n## Important Context")
        items = metadata.get("important_context", [])
        if items:
            for item in items[:10]:
                lines.append(f"- {item['content']}")
        else:
            lines.append("*(No important context recorded yet)*")

        # Footer
        lines.append("\n---")
        lines.append("\n*Memory is managed automatically by the system. This section updates as you learn more about the user.*")

        # Write to file
        content = "\n".join(lines)

        # Ensure parent directory exists
        self.memory_md_path.parent.mkdir(parents=True, exist_ok=True)

        self.memory_md_path.write_text(content, encoding="utf-8")


# Singleton instance
_long_term_updater_instance: LongTermMemoryUpdater | None = None


def get_long_term_updater() -> LongTermMemoryUpdater:
    """
    Get the global long-term memory updater instance.

    Returns:
        LongTermMemoryUpdater instance
    """
    global _long_term_updater_instance

    if _long_term_updater_instance is None:
        _long_term_updater_instance = LongTermMemoryUpdater()

    return _long_term_updater_instance
