"""
Skills Registry Module

Manages the skills_registry.json file that stores skill metadata including
refined descriptions for UI display.
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.config import get_settings


class SkillsRegistry:
    """
    Manages the skills registry (skills_registry.json).

    The registry stores metadata for all installed skills including:
    - Refined descriptions (short, UI-friendly)
    - Enable/disable status
    - Installation timestamp
    - Skill version and author info
    """

    def __init__(self):
        """Initialize the skills registry."""
        settings = get_settings()
        self.data_dir = Path(settings.data_dir)
        self.registry_file = self.data_dir / "skills" / "skills_registry.json"
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)

    def load_registry(self) -> Dict[str, Any]:
        """
        Load the skills registry from disk.

        Returns:
            Dictionary with registry data (empty if file doesn't exist)
        """
        if not self.registry_file.exists():
            return {"skills": {}, "last_updated": None}

        try:
            content = self.registry_file.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception as e:
            print(f"Error loading skills registry: {e}")
            return {"skills": {}, "last_updated": None}

    def save_registry(self, registry: Dict[str, Any]) -> None:
        """
        Save the skills registry to disk.

        Args:
            registry: Registry data to save
        """
        registry["last_updated"] = datetime.now().isoformat()

        try:
            self.registry_file.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"Error saving skills registry: {e}")
            raise

    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Skill metadata or None if not found
        """
        registry = self.load_registry()
        return registry["skills"].get(skill_name)

    def list_skills(self) -> Dict[str, Dict[str, Any]]:
        """
        List all skills in the registry.

        Returns:
            Dict mapping skill names to their metadata
        """
        registry = self.load_registry()
        return registry["skills"]

    def add_skill(
        self,
        name: str,
        description: str,
        description_en: str,
        enabled: bool = True,
        version: str = "1.0.0",
        author: str = "",
        tags: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Add or update a skill in the registry.

        Args:
            name: Skill name
            description: Refined Chinese description
            description_en: Refined English description
            enabled: Whether skill is enabled
            version: Skill version
            author: Skill author
            tags: Skill tags

        Returns:
            Created/updated skill metadata
        """
        registry = self.load_registry()

        skill_data = {
            "name": name,
            "description": description,
            "description_en": description_en,
            "enabled": enabled,
            "installed_at": datetime.now().isoformat(),
            "version": version,
            "author": author,
            "tags": tags or [],
        }

        # Preserve installation date if updating existing skill
        if name in registry["skills"]:
            skill_data["installed_at"] = registry["skills"][name].get("installed_at", skill_data["installed_at"])

        registry["skills"][name] = skill_data
        self.save_registry(registry)

        return skill_data

    def remove_skill(self, skill_name: str) -> bool:
        """
        Remove a skill from the registry.

        Args:
            skill_name: Name of the skill to remove

        Returns:
            True if skill was removed, False if not found
        """
        registry = self.load_registry()

        if skill_name not in registry["skills"]:
            return False

        del registry["skills"][skill_name]
        self.save_registry(registry)
        return True

    def toggle_skill(self, skill_name: str, enabled: bool) -> bool:
        """
        Enable or disable a skill.

        Args:
            skill_name: Name of the skill
            enabled: New enabled state

        Returns:
            True if updated, False if skill not found
        """
        registry = self.load_registry()

        if skill_name not in registry["skills"]:
            return False

        registry["skills"][skill_name]["enabled"] = enabled
        self.save_registry(registry)
        return True

    def scan_and_sync(self, skills_dir: Path) -> List[str]:
        """
        Scan skills directory and sync with registry.

        This removes registry entries for skills that no longer exist.

        Args:
            skills_dir: Path to skills directory

        Returns:
            List of skill names that were removed from registry
        """
        registry = self.load_registry()
        removed = []

        # Check each skill in registry
        for skill_name in list(registry["skills"].keys()):
            skill_path = skills_dir / skill_name / "SKILL.md"
            if not skill_path.exists():
                # Skill no longer exists, remove from registry
                del registry["skills"][skill_name]
                removed.append(skill_name)

        if removed:
            self.save_registry(registry)

        return removed


def get_skills_registry() -> SkillsRegistry:
    """
    Get the global skills registry instance.

    Returns:
        SkillsRegistry instance
    """
    return SkillsRegistry()
