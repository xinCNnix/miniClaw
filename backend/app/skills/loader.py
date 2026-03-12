"""
Skills Loader Module

This module handles dynamic loading of Skills.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import get_settings


class SkillLoader:
    """
    Dynamic loader for Skills.

    This class handles loading skills from the file system.
    """

    def __init__(self):
        """Initialize the skill loader."""
        settings = get_settings()
        self.skills_dir = Path(settings.skills_dir)
        self.loaded_skills: Dict[str, Any] = {}

    def load_skill_from_file(self, skill_path: Path) -> Optional[str]:
        """
        Load skill content from SKILL.md file.

        Args:
            skill_path: Path to SKILL.md

        Returns:
            Skill content or None if loading fails

        Examples:
            >>> loader = SkillLoader()
            >>> content = loader.load_skill_from_file(Path("skills/get_weather/SKILL.md"))
            >>> print(content)
        """
        try:
            if not skill_path.exists():
                return None

            content = skill_path.read_text(encoding="utf-8")
            return content

        except Exception as e:
            print(f"Error loading skill from {skill_path}: {e}")
            return None

    def load_skill_module(self, skill_name: str) -> Optional[Any]:
        """
        Load a skill as a Python module (if it has Python code).

        Args:
            skill_name: Name of the skill

        Returns:
            Loaded module or None

        Note:
            Most skills are just Markdown files (SKILL.md) and don't
            have associated Python code. This method is for advanced
            skills that include Python implementations.
        """
        skill_dir = self.skills_dir / skill_name

        # Look for Python files in the skill directory
        py_files = list(skill_dir.glob("*.py"))

        if not py_files:
            return None

        # Load the first Python file found
        py_file = py_files[0]

        try:
            spec = importlib.util.spec_from_file_location(
                f"skill_{skill_name}",
                py_file,
            )

            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[f"skill_{skill_name}"] = module
            spec.loader.exec_module(module)

            self.loaded_skills[skill_name] = module

            return module

        except Exception as e:
            print(f"Error loading skill module {skill_name}: {e}")
            return None

    def get_skill_path(self, skill_name: str) -> Optional[Path]:
        """
        Get the path to a skill's SKILL.md file.

        Args:
            skill_name: Name of the skill

        Returns:
            Path to SKILL.md or None if not found
        """
        skill_dir = self.skills_dir / skill_name
        skill_file = skill_dir / "SKILL.md"

        if skill_file.exists():
            return skill_file

        # Try subdirectories
        for subdir in self.skills_dir.rglob(skill_name):
            if subdir.is_dir():
                skill_file = subdir / "SKILL.md"
                if skill_file.exists():
                    return skill_file

        return None

    def list_available_skills(self) -> Dict[str, str]:
        """
        List all available skills.

        Returns:
            Dict mapping skill names to descriptions

        Examples:
            >>> loader = SkillLoader()
            >>> skills = loader.list_available_skills()
            >>> for name, desc in skills.items():
            ...     print(f"{name}: {desc}")
        """
        skills = {}

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            # Read frontmatter to get description
            try:
                content = skill_file.read_text(encoding="utf-8")

                # Parse description from frontmatter
                description = ""
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 2:
                        import yaml
                        try:
                            frontmatter = yaml.safe_load(parts[1])
                            description = frontmatter.get("description", "")
                        except:
                            pass

                name = skill_dir.name
                skills[name] = description

            except Exception:
                # If we can't read it, skip it
                continue

        return skills

    def validate_skill(self, skill_name: str) -> tuple[bool, str]:
        """
        Validate a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Tuple of (is_valid, error_message)

        Examples:
            >>> loader = SkillLoader()
            >>> is_valid, error = loader.validate_skill("get_weather")
            >>> if is_valid:
            ...     print("Skill is valid!")
            ... else:
            ...     print(f"Error: {error}")
        """
        skill_path = self.get_skill_path(skill_name)

        if skill_path is None:
            return False, f"Skill '{skill_name}' not found"

        try:
            content = skill_path.read_text(encoding="utf-8")

            # Check for required frontmatter fields
            if not content.startswith("---"):
                return False, "SKILL.md must start with frontmatter (---)"

            parts = content.split("---", 2)
            if len(parts) < 3:
                return False, "Invalid frontmatter format"

            import yaml
            try:
                frontmatter = yaml.safe_load(parts[1])
            except yaml.YAMLError:
                return False, "Invalid YAML in frontmatter"

            # Check required fields
            if "name" not in frontmatter:
                return False, "Missing required field: name"

            if "description" not in frontmatter:
                return False, "Missing required field: description"

            # Check if there's actual content
            main_content = parts[2].strip()
            if not main_content:
                return False, "SKILL.md has no content"

            return True, ""

        except Exception as e:
            return False, f"Error validating skill: {str(e)}"

    def reload_skill(self, skill_name: str) -> Optional[str]:
        """
        Reload a skill from disk.

        Args:
            skill_name: Name of the skill

        Returns:
            Updated skill content or None

        Examples:
            >>> loader = SkillLoader()
            >>> content = loader.reload_skill("get_weather")
        """
        # Clear from cache
        if skill_name in self.loaded_skills:
            del self.loaded_skills[skill_name]

        # Reload from file
        skill_path = self.get_skill_path(skill_name)
        if skill_path:
            return self.load_skill_from_file(skill_path)

        return None


def get_skill_loader() -> SkillLoader:
    """
    Get the global skill loader instance.

    Returns:
        SkillLoader instance

    Examples:
        >>> from app.skills.loader import get_skill_loader
        >>> loader = get_skill_loader()
        >>> skills = loader.list_available_skills()
    """
    return SkillLoader()


def load_skill_content(skill_name: str) -> Optional[str]:
    """
    Load skill content by name.

    Args:
        skill_name: Name of the skill

    Returns:
        Skill content or None if not found

    Examples:
        >>> from app.skills.loader import load_skill_content
        >>> content = load_skill_content("get_weather")
        >>> print(content)
    """
    loader = get_skill_loader()
    skill_path = loader.get_skill_path(skill_name)

    if skill_path:
        return loader.load_skill_from_file(skill_path)

    return None
