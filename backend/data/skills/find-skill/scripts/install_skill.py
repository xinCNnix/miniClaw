#!/usr/bin/env python3
"""
Skill Installation Script

Install agent skills from Git repositories.

Usage:
    python install_skill.py --url "https://github.com/user/skill-repo" --name "skill-name"
    python install_skill.py --url "https://github.com/user/repo" --subdir "skills/weather"
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def validate_skill(skill_path: Path) -> tuple[bool, str]:
    """
    Validate that a directory contains a valid skill.

    Args:
        skill_path: Path to skill directory

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check for SKILL.md
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    try:
        content = skill_md.read_text(encoding="utf-8")

        # Check for frontmatter
        if not content.startswith("---"):
            return False, "SKILL.md must start with YAML frontmatter"

        # Parse frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            return False, "Invalid frontmatter format"

        # Check required fields
        frontmatter_text = parts[1]
        try:
            import yaml
            frontmatter = yaml.safe_load(frontmatter_text)
        except ImportError:
            # Fallback: simple check for name and description
            frontmatter = {}
            for line in frontmatter_text.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip()] = value.strip()

        if "name" not in frontmatter:
            return False, "Missing 'name' field in frontmatter"
        if "description" not in frontmatter:
            return False, "Missing 'description' field in frontmatter"

        # Check for symlinks (security)
        for item in skill_path.rglob("*"):
            if item.is_symlink():
                return False, f"Security: Symlinks not allowed: {item}"

        return True, "Skill is valid"

    except Exception as e:
        return False, f"Validation error: {str(e)}"


def install_skill(
    url: str,
    name: Optional[str] = None,
    target: str = "./data/skills",
    branch: Optional[str] = None,
    tag: Optional[str] = None,
    subdir: Optional[str] = None,
) -> dict:
    """
    Install a skill from a Git repository.

    Args:
        url: Git repository URL
        name: Skill/directory name (default: derived from URL)
        target: Target installation directory
        branch: Git branch to checkout
        tag: Git tag to checkout
        subdir: Subdirectory in repo containing the skill

    Returns:
        Dictionary with installation result
    """
    target_path = Path(target).resolve()

    # Determine skill name
    if name:
        skill_name = name
    else:
        # Extract from URL
        # e.g., https://github.com/user/weather-skill -> weather-skill
        skill_name = url.rstrip("/").split("/")[-1]
        if skill_name.endswith(".git"):
            skill_name = skill_name[:-4]

    install_path = target_path / skill_name

    # Check if already exists
    if install_path.exists():
        return {
            "error": f"Directory already exists: {install_path}",
            "path": str(install_path)
        }

    # Create temp directory for cloning
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        clone_path = temp_path / "repo"

        # Build git clone command
        git_cmd = ["git", "clone"]

        if branch:
            git_cmd.extend(["--branch", branch])
        elif tag:
            git_cmd.extend(["--branch", tag])
        else:
            git_cmd.append("--depth", "1")  # Shallow clone for faster download

        git_cmd.extend([url, str(clone_path)])

        print(f"Cloning repository: {url}")

        try:
            # Run git clone
            result = subprocess.run(
                git_cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,  # 5 minute timeout
            )
        except subprocess.CalledProcessError as e:
            return {
                "error": f"Git clone failed: {e.stderr}",
                "details": e.stderr
            }
        except subprocess.TimeoutExpired:
            return {"error": "Git clone timed out"}
        except FileNotFoundError:
            return {"error": "Git is not installed or not in PATH"}

        # Determine source path
        if subdir:
            source_path = clone_path / subdir
        else:
            source_path = clone_path

        # Validate source exists
        if not source_path.exists():
            return {
                "error": f"Source path not found: {source_path}",
                "hint": "Use --subdir to specify the skill subdirectory"
            }

        # Validate skill structure
        print("Validating skill structure...")
        is_valid, message = validate_skill(source_path)

        if not is_valid:
            return {
                "error": f"Skill validation failed: {message}",
                "path": str(source_path)
            }

        print(f"✓ {message}")

        # Create target directory
        target_path.mkdir(parents=True, exist_ok=True)

        # Copy skill to target
        print(f"Installing to: {install_path}")

        try:
            if source_path == clone_path:
                # Copy entire clone
                shutil.copytree(source_path, install_path)
            else:
                # Copy subdirectory
                shutil.copytree(source_path, install_path)

        except Exception as e:
            return {
                "error": f"Failed to copy skill: {str(e)}",
                "source": str(source_path),
                "target": str(install_path)
            }

        # Update skills registry if it exists
        registry_path = target_path / "skills_registry.json"
        if registry_path.exists():
            try:
                with open(registry_path, "r+", encoding="utf-8") as f:
                    registry = json.load(f)
                    registry[skill_name] = {
                        "name": skill_name,
                        "source": url,
                        "installed_at": None  # Will be set by caller
                    }
                    f.seek(0)
                    json.dump(registry, f, indent=2)
                    f.truncate()
                print(f"✓ Updated skills registry")
            except Exception as e:
                print(f"Warning: Could not update registry: {e}")

    return {
        "success": True,
        "name": skill_name,
        "path": str(install_path),
        "message": f"Skill '{skill_name}' installed successfully"
    }


def main():
    parser = argparse.ArgumentParser(
        description="Install agent skills from Git repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Install from GitHub
  python install_skill.py --url "https://github.com/user/weather-skill"

  # Install with custom name
  python install_skill.py --url "https://github.com/user/repo" --name "weather"

  # Install specific branch
  python install_skill.py --url "https://github.com/user/repo" --branch "develop"

  # Install specific tag
  python install_skill.py --url "https://github.com/user/repo" --tag "v1.0.0"

  # Install from subdirectory
  python install_skill.py --url "https://github.com/user/skills-collection" --subdir "skills/weather"

  # Install to custom location
  python install_skill.py --url "https://github.com/user/repo" --target "./custom/skills"
        """,
    )

    parser.add_argument(
        "--url",
        required=True,
        help="Git repository URL (GitHub, GitLab, etc.)"
    )
    parser.add_argument(
        "--name",
        help="Skill/directory name (default: derived from URL)"
    )
    parser.add_argument(
        "--target",
        default="./data/skills",
        help="Installation directory (default: ./data/skills)"
    )
    parser.add_argument(
        "--branch",
        help="Git branch to checkout"
    )
    parser.add_argument(
        "--tag",
        help="Git tag to checkout"
    )
    parser.add_argument(
        "--subdir",
        help="Subdirectory in repo containing the skill"
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip skill validation (not recommended)"
    )

    args = parser.parse_args()

    # Check for conflicting options
    if args.branch and args.tag:
        print("Error: --branch and --tag are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    # Perform installation
    result = install_skill(
        url=args.url,
        name=args.name,
        target=args.target,
        branch=args.branch,
        tag=args.tag,
        subdir=args.subdir,
    )

    # Handle result
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        if "hint" in result:
            print(f"Hint: {result['hint']}", file=sys.stderr)
        sys.exit(1)

    # Success
    print(f"\n✓ {result['message']}")
    print(f"  Location: {result['path']}")

    # Suggest validation
    print("\nNext steps:")
    print(f"  1. Review the skill: {result['path']}")
    print(f"  2. Validate: python data/skills/skill-creator/scripts/quick_validate.py '{result['path']}'")


if __name__ == "__main__":
    main()
