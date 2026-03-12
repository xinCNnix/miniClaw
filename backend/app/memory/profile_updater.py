"""
User Profile Updater - Automatic USER.md updates.

This module handles automatic updates to USER.md based on extracted memories.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.memory import Memory
from app.core.llm import get_default_llm
from app.config import get_settings

logger = logging.getLogger(__name__)


class UserProfileUpdater:
    """
    Automatically updates USER.md based on learned user preferences.

    This class:
    1. Merges new preference memories with existing USER.md
    2. Uses LLM to generate coherent updates
    3. Preserves manually edited sections
    4. Maintains consistent formatting
    """

    def __init__(self, llm: BaseChatModel | None = None):
        """
        Initialize the user profile updater.

        Args:
            llm: Optional LLM instance. If not provided, uses default LLM.
        """
        self.llm = llm or get_default_llm()
        self.settings = get_settings()
        self.user_md_path = Path(self.settings.workspace_dir) / "USER.md"

    async def update_from_memories(self, memories: List[Memory]) -> None:
        """
        Update USER.md with new preference memories.

        Args:
            memories: List of preference memories to integrate
        """
        if not memories:
            return

        logger.info(f"Updating USER.md with {len(memories)} preference memories")

        try:
            # Read existing USER.md
            existing_content = self._read_user_md()

            # Format new memories
            new_memories_text = self._format_memories(memories)

            # Build update prompt
            system_prompt = self._build_update_prompt()

            # Generate updated content
            updated_content = await self._generate_update(
                system_prompt,
                existing_content,
                new_memories_text,
            )

            # Write updated USER.md
            self._write_user_md(updated_content)

            logger.info("USER.md updated successfully")

        except Exception as e:
            logger.error(f"Failed to update USER.md: {e}", exc_info=True)

    def _read_user_md(self) -> str:
        """
        Read existing USER.md content.

        Returns:
            Current USER.md content, or default template if not exists
        """
        if self.user_md_path.exists():
            return self.user_md_path.read_text(encoding="utf-8")

        # Return default template
        return """# User Context

## User Preferences
- Prefers clear and concise explanations
- Values honesty and transparency
- Appreciates step-by-step breakdowns

## Communication Style
- Direct and to the point
- Avoid excessive jargon
- Provide examples when helpful

---

*Note: This section should be customized based on actual user data.*
"""

    def _write_user_md(self, content: str) -> None:
        """
        Write content to USER.md.

        Args:
            content: Content to write
        """
        # Ensure parent directory exists
        self.user_md_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        self.user_md_path.write_text(content, encoding="utf-8")

    def _format_memories(self, memories: List[Memory]) -> str:
        """
        Format memories as text for LLM processing.

        Args:
            memories: List of memories

        Returns:
            Formatted text
        """
        lines = []

        for memory in memories:
            lines.append(f"- {memory.content} (confidence: {memory.confidence:.2f})")

        return "\n".join(lines)

    def _build_update_prompt(self) -> str:
        """
        Build the system prompt for updating USER.md.

        Returns:
            System prompt string
        """
        return """You are a user profile management assistant. Your task is to update the USER.md file by integrating new information about the user.

Guidelines:
1. Preserve the existing structure and sections
2. Add new information to the most appropriate section
3. Remove information that contradicts new information
4. Keep information concise and clear
5. Avoid redundancy - merge similar points
6. Maintain markdown formatting
7. Keep the note at the end

The USER.md has these sections:
- User Preferences: What the user likes and prefers
- Communication Style: How the user likes to communicate

Return the complete updated USER.md content as a markdown string."""

    async def _generate_update(
        self,
        system_prompt: str,
        existing_content: str,
        new_memories_text: str,
    ) -> str:
        """
        Generate updated USER.md content using LLM.

        Args:
            system_prompt: System prompt
            existing_content: Current USER.md content
            new_memories_text: New memories to integrate

        Returns:
            Updated USER.md content
        """
        user_message = f"""Update the following user profile with the new information:

Existing USER.md:
```markdown
{existing_content}
```

New information about the user:
{new_memories_text}

Return the complete updated USER.md as markdown."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]

        response = await self.llm.ainvoke(messages)
        return response.content

    def _merge_with_existing(self, new_content: str) -> str:
        """
        Merge new content with existing, preserving manually edited sections.

        This is a fallback method if LLM generation fails.

        Args:
            new_content: Newly generated content

        Returns:
            Merged content
        """
        existing = self._read_user_md()

        # Simple merge: if new content is significantly shorter, use existing
        if len(new_content) < len(existing) * 0.5:
            logger.warning("Generated content too short, using existing")
            return existing

        return new_content


# Singleton instance
_profile_updater_instance: UserProfileUpdater | None = None


def get_profile_updater() -> UserProfileUpdater:
    """
    Get the global profile updater instance.

    Returns:
        UserProfileUpdater instance
    """
    global _profile_updater_instance

    if _profile_updater_instance is None:
        _profile_updater_instance = UserProfileUpdater()

    return _profile_updater_instance
