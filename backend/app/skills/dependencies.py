"""
Skills Dependency Management Module

This module handles automatic dependency checking and installation for skills.
"""

import subprocess
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PythonDependency:
    """Represents a Python package dependency."""

    package: str  # Package name with version spec, e.g., "arxiv>=2.0.0"
    installed: bool = False
    version: Optional[str] = None


@dataclass
class SystemDependency:
    """Represents a system/CLI dependency."""

    name: str
    bins: List[str] = field(default_factory=list)
    install_hints: List[str] = field(default_factory=list)
    installed: bool = False


@dataclass
class SkillDependencies:
    """Dependencies for a single skill."""

    skill_name: str
    python_deps: List[PythonDependency] = field(default_factory=list)
    system_deps: List[SystemDependency] = field(default_factory=list)

    @property
    def has_uninstalled_python(self) -> bool:
        """Check if there are uninstalled Python dependencies."""
        return any(not d.installed for d in self.python_deps)

    @property
    def has_uninstalled_system(self) -> bool:
        """Check if there are uninstalled system dependencies."""
        return any(not d.installed for d in self.system_deps)

    @property
    def needs_python_install(self) -> List[str]:
        """Get list of Python packages that need installation."""
        return [d.package for d in self.python_deps if not d.installed]

    @property
    def system_install_hints(self) -> List[str]:
        """Get installation hints for missing system dependencies."""
        hints = []
        for dep in self.system_deps:
            if not dep.installed and dep.install_hints:
                hints.extend(dep.install_hints)
        return hints


class SkillDependencyManager:
    """
    Manages skill dependencies.

    Handles:
    - Scanning dependency declarations in SKILL.md frontmatter
    - Checking if dependencies are installed
    - Auto-installing Python packages
    - Providing installation hints for system dependencies
    """

    def __init__(self):
        """Initialize the dependency manager."""
        self.settings = get_settings()
        self.skills_dir = Path(self.settings.skills_dir)
        self._dependency_cache: Dict[str, SkillDependencies] = {}
        self._auto_installed: Set[str] = set()  # Track auto-installed packages

    def scan_skill_dependencies(self, skill_name: str, frontmatter: dict) -> SkillDependencies:
        """
        Scan dependencies from SKILL.md frontmatter.

        Args:
            skill_name: Name of the skill
            frontmatter: Parsed YAML frontmatter from SKILL.md

        Returns:
            SkillDependencies object
        """
        deps = SkillDependencies(skill_name=skill_name)

        # Parse dependencies from frontmatter
        deps_dict = frontmatter.get("dependencies", {})

        # Python dependencies
        python_deps = deps_dict.get("python", [])
        if isinstance(python_deps, str):
            python_deps = [python_deps]

        for pkg_spec in python_deps:
            pkg = self._parse_package_spec(pkg_spec)
            deps.python_deps.append(pkg)

        # System dependencies (support both new and legacy format)
        system_deps = deps_dict.get("system", [])

        # Legacy format: check for metadata.requires
        if not system_deps:
            metadata = frontmatter.get("metadata", {})
            if isinstance(metadata, dict):
                miniclaw_meta = metadata.get("miniclaw", {})
                if isinstance(miniclaw_meta, dict):
                    legacy_reqs = miniclaw_meta.get("requires", {})
                    if isinstance(legacy_reqs, dict) and "bins" in legacy_reqs:
                        # Convert legacy format to new format
                        bins = legacy_reqs.get("bins", [])
                        for bin_name in bins:
                            system_deps.append({"name": bin_name, "bins": [bin_name]})

        # Parse system dependencies
        for sys_dep in system_deps:
            if isinstance(sys_dep, str):
                sys_dep = {"name": sys_dep, "bins": [sys_dep]}

            name = sys_dep.get("name", "unknown")
            bins = sys_dep.get("bins", [name])
            install = sys_dep.get("install", [])

            # Convert install instructions to hints
            hints = []
            if install:
                for inst in install:
                    if isinstance(inst, dict):
                        kind = inst.get("kind", "")
                        label = inst.get("label", "")
                        if kind == "pip":
                            package = inst.get("package", "")
                            hints.append(f"pip install {package}")
                        elif kind == "brew":
                            formula = inst.get("formula", name)
                            hints.append(f"brew install {formula}")
                        elif kind == "apt":
                            package = inst.get("package", name)
                            hints.append(f"sudo apt install {package}")
                        elif label:
                            hints.append(label)

            deps.system_deps.append(
                SystemDependency(
                    name=name,
                    bins=bins,
                    install_hints=hints,
                )
            )

        # Check installation status
        self._check_dependencies(deps)

        return deps

    def _parse_package_spec(self, spec: str) -> PythonDependency:
        """
        Parse a package specification string.

        Args:
            spec: Package spec like "arxiv>=2.0.0" or "requests"

        Returns:
            PythonDependency object
        """
        # Extract package name without version spec
        import re
        match = re.match(r'^([a-zA-Z0-9_-]+)', spec)
        if match:
            package_name = match.group(1)
        else:
            package_name = spec

        # Check if installed
        installed, version = self._check_python_package(package_name)

        return PythonDependency(
            package=spec,
            installed=installed,
            version=version,
        )

    def _check_python_package(self, package_name: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a Python package is installed.

        Args:
            package_name: Name of the package (without version spec)

        Returns:
            Tuple of (is_installed, version)
        """
        try:
            import importlib.metadata
            version = importlib.metadata.version(package_name)
            return True, version
        except importlib.metadata.PackageNotFoundError:
            return False, None
        except Exception:
            return False, None

    def _check_dependencies(self, deps: SkillDependencies) -> None:
        """
        Check the installation status of all dependencies.

        Args:
            deps: SkillDependencies to update
        """
        # Python dependencies are already checked in _parse_package_spec
        # Just need to check system dependencies

        for sys_dep in deps.system_deps:
            sys_dep.installed = self._check_system_dependency(sys_dep.bins)

    def _check_system_dependency(self, bins: List[str]) -> bool:
        """
        Check if a system dependency (CLI tool) is available.

        Args:
            bins: List of binary names to check

        Returns:
            True if any binary is found
        """
        import shutil

        for bin_name in bins:
            if shutil.which(bin_name):
                return True

        return False

    def install_python_dependencies(
        self,
        packages: List[str],
        auto_confirm: bool = True,
    ) -> Tuple[bool, str]:
        """
        Install Python packages using pip.

        Args:
            packages: List of package specifications to install
            auto_confirm: If True, install without asking

        Returns:
            Tuple of (success, message)
        """
        if not packages:
            return True, "No packages to install"

        logger.info(f"Installing Python packages: {packages}")

        try:
            # Use subprocess to call pip
            cmd = [sys.executable, "-m", "pip", "install"]

            # Note: --yes is only available in pip 23.1+
            # For compatibility with older pip versions, we don't use it
            # The user can upgrade pip with: python -m pip install --upgrade pip

            cmd.extend(packages)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.settings.skill_dependency_install_timeout,
            )

            if result.returncode == 0:
                # Track auto-installed packages
                for pkg in packages:
                    pkg_name = pkg.split(">=")[0].split("==")[0].split("<=")[0]
                    self._auto_installed.add(pkg_name)

                logger.info(f"Successfully installed: {packages}")
                return True, f"Successfully installed: {', '.join(packages)}"
            else:
                # Analyze the error to provide helpful feedback
                error_output = result.stderr or result.stdout
                error_msg = self._analyze_pip_error(error_output, packages)
                logger.error(f"Failed to install packages: {error_msg}")
                return False, error_msg

        except subprocess.TimeoutExpired:
            timeout_msg = (
                f"Installation timed out after {self.settings.skill_dependency_install_timeout} seconds. "
                f"This might be due to large package size or network issues. "
                f"Please try installing manually: pip install {' '.join(packages)}"
            )
            logger.error(timeout_msg)
            return False, timeout_msg
        except Exception as e:
            error_msg = f"Unexpected error during installation: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def _analyze_pip_error(self, error_output: str, packages: List[str]) -> str:
        """
        Analyze pip error output and provide helpful error messages.

        Args:
            error_output: The stderr/stdout from pip
            packages: The packages that failed to install

        Returns:
            Formatted error message with solutions
        """
        error_lower = error_output.lower()
        packages_str = ", ".join(packages)

        # Check for dependency conflicts
        if "conflict" in error_lower or "resolutionerror" in error_lower:
            return (
                f"[ERROR] Dependency conflict detected while installing: {packages_str}\n\n"
                f"This happens when the required packages conflict with already installed packages.\n"
                f"Error details:\n{error_output[:500]}\n\n"
                f"[Solutions]\n"
                f"  1. Create a virtual environment and install dependencies there\n"
                f"  2. Try: pip install --upgrade pip setuptools wheel\n"
                f"  3. Try: pip install --force-reinstall {' '.join(packages)}\n"
                f"  4. Check if you have conflicting packages: pip list\n"
            )

        # Check for network issues
        if "network" in error_lower or "connection" in error_lower or "timeout" in error_lower:
            return (
                f"[ERROR] Network error while installing: {packages_str}\n\n"
                f"Could not download packages from PyPI.\n"
                f"[Solutions]\n"
                f"  1. Check your internet connection\n"
                f"  2. Try using a mirror: pip install -i https://pypi.tuna.tsinghua.edu.cn/simple {' '.join(packages)}\n"
                f"  3. Wait a moment and try again\n"
            )

        # Check for permission issues
        if "permission" in error_lower or "access denied" in error_lower or "read-only" in error_lower:
            return (
                f"[ERROR] Permission denied while installing: {packages_str}\n\n"
                f"[Solutions]\n"
                f"  1. Use a virtual environment (recommended): python -m venv venv\n"
                f"  2. Try: pip install --user {' '.join(packages)}\n"
                f"  3. Run with admin/sudo privileges (not recommended)\n"
            )

        # Check for disk space
        if "no space" in error_lower or "disk" in error_lower:
            return (
                f"[ERROR] Disk space error while installing: {packages_str}\n\n"
                f"[Solutions]\n"
                f"  1. Free up disk space\n"
                f"  2. Clear pip cache: pip cache purge\n"
                f"  3. Install to a different location\n"
            )

        # Check for package not found
        if "could not find" in error_lower or "no matching distribution" in error_lower:
            return (
                f"[ERROR] Package not found: {packages_str}\n\n"
                f"The requested package could not be found on PyPI.\n"
                f"Error details:\n{error_output[:500]}\n\n"
                f"[Solutions]\n"
                f"  1. Check the package name for typos\n"
                f"  2. Search for the package: pip search <package-name>\n"
                f"  3. Check if the package name is correct in the skill definition\n"
            )

        # Generic error with truncated output
        return (
            f"[ERROR] Failed to install: {packages_str}\n\n"
            f"Error details:\n{error_output[:800]}\n\n"
            f"[Solution] Please try installing manually:\n"
            f"   pip install {' '.join(packages)}\n"
        )

    def ensure_skill_dependencies(
        self,
        skill_name: str,
        frontmatter: dict,
    ) -> Tuple[bool, List[str]]:
        """
        Ensure all dependencies for a skill are installed.

        - Python dependencies: Auto-install
        - System dependencies: Return installation hints

        Args:
            skill_name: Name of the skill
            frontmatter: Parsed YAML frontmatter from SKILL.md

        Returns:
            Tuple of (all_ready, messages)
        """
        deps = self.scan_skill_dependencies(skill_name, frontmatter)
        self._dependency_cache[skill_name] = deps

        messages = []

        # Auto-install Python dependencies
        if deps.has_uninstalled_python:
            missing = deps.needs_python_install
            logger.info(f"Installing missing Python packages for {skill_name}: {missing}")

            success, msg = self.install_python_dependencies(missing)

            if success:
                messages.append(f"✓ Auto-installed Python packages: {', '.join(missing)}")
                # Re-check to update status
                for pkg in deps.python_deps:
                    if not pkg.installed:
                        installed, version = self._check_python_package(
                            pkg.package.split(">=")[0].split("==")[0]
                        )
                        pkg.installed = installed
                        pkg.version = version
            else:
                messages.append(f"✗ Failed to install Python packages: {msg}")
                return False, messages

        # Check system dependencies
        if deps.has_uninstalled_system:
            hints = deps.system_install_hints
            if hints:
                messages.append("⚠ Missing system dependencies. Please install:")
                for hint in hints:
                    messages.append(f"  - {hint}")
                # Don't fail on system dependencies, just warn
                # The skill will fail with a clear error when used

        return True, messages

    def get_skill_status(self, skill_name: str) -> Optional[SkillDependencies]:
        """
        Get dependency status for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            SkillDependencies or None if not found
        """
        return self._dependency_cache.get(skill_name)

    def format_import_error(self, skill_name: str, import_error: ImportError) -> str:
        """
        Format an ImportError with helpful dependency information.

        Args:
            skill_name: Name of the skill that failed
            import_error: The ImportError exception

        Returns:
            Formatted error message
        """
        deps = self.get_skill_status(skill_name)

        # Extract missing module name from error
        error_msg = str(import_error)
        missing_module = None

        # Try to extract module name from "No module named 'xxx'"
        import re
        match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_msg)
        if match:
            missing_module = match.group(1)

        # Build helpful error message
        lines = [
            f"Skill '{skill_name}' failed to load due to missing dependencies.",
            "",
        ]

        if missing_module:
            lines.append(f"Missing module: {missing_module}")

        if deps:
            if deps.python_deps:
                lines.append("\nRequired Python packages:")
                for pkg in deps.python_deps:
                    status = "✓" if pkg.installed else "✗"
                    version = f" ({pkg.version})" if pkg.version else ""
                    lines.append(f"  {status} {pkg.package}{version}")

            if deps.system_deps:
                lines.append("\nRequired system tools:")
                for dep in deps.system_deps:
                    status = "✓" if dep.installed else "✗"
                    lines.append(f"  {status} {dep.name}")
                    if not dep.installed and dep.install_hints:
                        for hint in dep.install_hints:
                            lines.append(f"    Install: {hint}")

        lines.append(f"\nOriginal error: {error_msg}")

        return "\n".join(lines)


# Singleton instance
_dependency_manager_instance: Optional[SkillDependencyManager] = None


def get_dependency_manager() -> SkillDependencyManager:
    """
    Get the global dependency manager instance.

    Returns:
        SkillDependencyManager instance
    """
    global _dependency_manager_instance

    if _dependency_manager_instance is None:
        _dependency_manager_instance = SkillDependencyManager()

    return _dependency_manager_instance
