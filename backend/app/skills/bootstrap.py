"""
Skills Bootstrap Module

This module handles the initialization and snapshot generation for the Skills system.
It scans the skills directory and generates SKILLS_SNAPSHOT.md.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml

from app.config import get_settings

logger = logging.getLogger(__name__)


class SkillMetadata:
    """Metadata for a single skill."""

    def __init__(
        self,
        name: str,
        description: str,
        location: str,
        version: str = "1.0.0",
        author: str = "",
        tags: List[str] = None,
        frontmatter: Dict[str, Any] = None,
    ):
        self.name = name
        self.description = description
        self.location = location
        self.version = version
        self.author = author
        self.tags = tags or []
        self.frontmatter = frontmatter or {}

    def to_markdown(self) -> str:
        """
        Convert skill metadata to Markdown format.

        Returns:
            Markdown string
        """
        md_parts = [
            f"### {self.name}",
            f"**Description**: {self.description}",
            f"**Location**: `{self.location}`",
        ]

        if self.version:
            md_parts.append(f"**Version**: {self.version}")

        if self.author:
            md_parts.append(f"**Author**: {self.author}")

        if self.tags:
            md_parts.append(f"**Tags**: {', '.join(self.tags)}")

        return "\n".join(md_parts)

    def to_xml(self) -> str:
        """
        Convert skill metadata to XML format (for AGENTS.md).

        Returns:
            XML string
        """
        xml_parts = [
            "  <skill>",
            f"    <name>{self.name}</name>",
            f"    <description>{self.description}</description>",
            f"    <location>{self.location}</location>",
            "  </skill>",
        ]

        return "\n".join(xml_parts)


class SkillsBootstrap:
    """
    Bootstrap manager for the Skills system.

    This class handles scanning, loading, and snapshot generation.
    """

    def __init__(self):
        """Initialize the skills bootstrap."""
        settings = get_settings()
        self.skills_dir = Path(settings.skills_dir)
        self.skills: Dict[str, SkillMetadata] = {}

    def scan_skills(self, check_dependencies: bool = True) -> Dict[str, SkillMetadata]:
        """
        Scan the skills directory and load all skill metadata.

        Args:
            check_dependencies: If True, check and auto-install dependencies

        Returns:
            Dict mapping skill names to metadata

        Raises:
            ValueError: If skills directory doesn't exist
        """
        if not self.skills_dir.exists():
            raise ValueError(f"Skills directory not found: {self.skills_dir}")

        self.skills = {}

        # Scan for SKILL.md files
        for skill_path in self.skills_dir.rglob("SKILL.md"):
            try:
                metadata = self._load_skill_metadata(skill_path)
                if metadata:
                    self.skills[metadata.name] = metadata

                    # Check dependencies if enabled
                    if check_dependencies and metadata.frontmatter:
                        self._check_skill_dependencies(metadata.name, metadata.frontmatter)

            except Exception as e:
                logger.error(f"Error loading skill from {skill_path}: {e}")
                continue

        return self.skills

    def _check_skill_dependencies(self, skill_name: str, frontmatter: Dict[str, Any]) -> None:
        """
        Check and auto-install dependencies for a skill.

        Args:
            skill_name: Name of the skill
            frontmatter: Parsed YAML frontmatter
        """
        try:
            from app.skills.dependencies import get_dependency_manager

            dep_manager = get_dependency_manager()
            success, messages = dep_manager.ensure_skill_dependencies(skill_name, frontmatter)

            if messages:
                for msg in messages:
                    logger.info(f"[{skill_name}] {msg}")

            if not success:
                logger.warning(f"[{skill_name}] Some dependencies could not be installed")

        except Exception as e:
            logger.error(f"Error checking dependencies for {skill_name}: {e}")

    def _load_skill_metadata(self, skill_path: Path) -> Optional[SkillMetadata]:
        """
        Load metadata from a SKILL.md file.

        Args:
            skill_path: Path to SKILL.md

        Returns:
            SkillMetadata or None if loading fails
        """
        try:
            content = skill_path.read_text(encoding="utf-8")

            # Parse frontmatter (YAML between --- markers)
            frontmatter = {}
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        frontmatter = yaml.safe_load(parts[1])
                    except yaml.YAMLError:
                        pass

            # Extract required fields
            name = frontmatter.get("name", skill_path.parent.name)
            description = frontmatter.get("description", "No description")

            # Calculate relative location from base_dir
            # Location should be the skill directory (without SKILL.md filename)
            # This ensures the path works correctly when Agent uses read_file tool
            settings = get_settings()
            base_dir = Path(settings.base_dir).resolve()

            # Get the skill directory (parent of SKILL.md)
            skill_dir = skill_path.parent

            # Convert skill directory to absolute path first
            skill_dir_abs = skill_dir.resolve() if not skill_dir.is_absolute() else skill_dir

            try:
                rel_path = skill_dir_abs.relative_to(base_dir)
                location = rel_path.as_posix()
            except ValueError:
                # Fallback: if skill is outside base_dir (shouldn't happen)
                rel_path = skill_dir.relative_to(self.skills_dir.parent)
                location = f"./{rel_path.as_posix()}"

            # Optional fields
            version = frontmatter.get("version", "1.0.0")
            author = frontmatter.get("author", "")
            tags = frontmatter.get("tags", [])

            return SkillMetadata(
                name=name,
                description=description,
                location=location,
                version=version,
                author=author,
                tags=tags,
                frontmatter=frontmatter,
            )

        except Exception as e:
            print(f"Error parsing {skill_path}: {e}")
            return None

    def generate_skills_snapshot(self, output_format: str = "markdown") -> str:
        """
        Generate SKILLS_SNAPSHOT.md content.

        Args:
            output_format: 'markdown' or 'xml'

        Returns:
            Snapshot content

        Raises:
            ValueError: If no skills found
        """
        # Ensure skills are scanned
        if not self.skills:
            self.scan_skills()

        if not self.skills:
            raise ValueError("No skills found in skills directory")

        if output_format == "xml":
            return self._generate_xml_snapshot()
        else:
            return self._generate_markdown_snapshot()

    def _generate_markdown_snapshot(self) -> str:
        """Generate Markdown format snapshot."""
        lines = [
            "# Available Skills\n",
            "This document lists all available skills that the Agent can use.\n",
            f"**Total Skills**: {len(self.skills)}\n",
            "---\n\n",
        ]

        for skill in self.skills.values():
            lines.append(skill.to_markdown())
            lines.append("\n\n")

        return "".join(lines)

    def _generate_xml_snapshot(self) -> str:
        """Generate XML format snapshot (for System Prompt)."""
        lines = [
            "<available_skills>",
        ]

        for skill in self.skills.values():
            lines.append(skill.to_xml())

        lines.append("</available_skills>")

        return "\n".join(lines)

    def save_snapshot(
        self,
        output_path: str = None,
        output_format: str = "markdown",
    ) -> str:
        """
        Save the snapshot to a file.

        Args:
            output_path: Path to save snapshot (default: workspace/SKILLS_SNAPSHOT.md)
            output_format: 'markdown' or 'xml'

        Returns:
            Path where snapshot was saved

        Raises:
            ValueError: If unable to save
        """
        if output_path is None:
            settings = get_settings()
            workspace_dir = Path(settings.workspace_dir)
            workspace_dir.mkdir(parents=True, exist_ok=True)
            output_path = workspace_dir / "SKILLS_SNAPSHOT.md"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        content = self.generate_skills_snapshot(output_format)

        output_path.write_text(content, encoding="utf-8")

        return str(output_path)

    def get_skill_count(self) -> int:
        """
        Get the number of available skills.

        Returns:
            Number of skills
        """
        return len(self.skills)

    def get_skill_names(self) -> List[str]:
        """
        Get list of skill names.

        Returns:
            List of skill names
        """
        return list(self.skills.keys())


def bootstrap_skills() -> SkillsBootstrap:
    """
    Bootstrap the skills system.

    Returns:
        SkillsBootstrap instance with loaded skills

    Examples:
        >>> from app.skills.bootstrap import bootstrap_skills
        >>> bootstrap = bootstrap_skills()
        >>> snapshot = bootstrap.generate_skills_snapshot()
        >>> print(snapshot)
    """
    bootstrap = SkillsBootstrap()
    bootstrap.scan_skills()
    return bootstrap


def generate_skills_snapshot() -> str:
    """
    Generate SKILLS_SNAPSHOT.md content.

    Returns:
        Snapshot content

    Examples:
        >>> from app.skills.bootstrap import generate_skills_snapshot
        >>> snapshot = generate_skills_snapshot()
        >>> print(snapshot)
    """
    bootstrap = bootstrap_skills()
    return bootstrap.generate_skills_snapshot()
