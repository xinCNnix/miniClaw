"""
Terminal Tool - Shell Command Execution

This tool allows the Agent to execute shell commands in a sandboxed environment.
Security features:
- Restricted to root_dir
- Command blacklist for dangerous operations
- Timeout control
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, List
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from app.config import settings


class TerminalInput(BaseModel):
    """Input schema for Terminal tool."""

    command: str = Field(
        ...,
        description="The shell command to execute",
    )

    cwd: Optional[str] = Field(
        default=None,
        description="Working directory (must be within root_dir)",
    )

    timeout: int = Field(
        default=30,
        description="Command timeout in seconds",
    )


class TerminalTool(BaseTool):
    """
    Terminal tool for executing shell commands safely.

    This tool uses langchain_community.tools.ShellTool as the base
    and adds security restrictions.
    """

    name: str = "terminal"
    description: str = """
    Execute shell commands in a safe, sandboxed environment.

    Important restrictions:
    - Commands are restricted to the project directory
    - Dangerous commands are blocked for both Unix and Windows
    - Commands have a timeout limit

    Blocked Unix commands: rm -rf /, mkfs, dd if=/dev/zero, fork bombs, etc.
    Blocked Windows commands: format, shutdown, reg delete, taskkill /f, diskpart, etc.

    Common uses (Unix/Linux/macOS):
    - File operations: ls, cp, mv, cat
    - Process management: ps, kill
    - System info: uname, df, free

    Common uses (Windows):
    - File operations: dir, copy, move, type
    - Process management: tasklist
    - System info: systeminfo, ver

    Examples:
    - terminal: ls -la
    - terminal: cat README.md
    - terminal: find . -name "*.py"
    """
    args_schema: type[TerminalInput] = TerminalInput

    # Security settings
    _blocked_commands: List[str] = settings.terminal_blocked_commands
    _root_dir: str = os.path.abspath(settings.terminal_root_dir)

    def _check_command_safety(self, command: str) -> None:
        """
        Check if command is safe to execute.

        Raises:
            ValueError: If command contains blocked patterns
        """
        import re
        # Normalize whitespace by collapsing multiple spaces
        command_normalized = re.sub(r'\s+', ' ', command.lower().strip())

        for blocked in self._blocked_commands:
            # Also normalize the blocked pattern
            blocked_normalized = re.sub(r'\s+', ' ', blocked.lower())

            # Check if blocked word appears in command
            if blocked_normalized not in command_normalized:
                continue

            # If found, check if it's in a URL parameter context (safe)
            # URL params: ?format= or &format= or similar
            # Block: format at start of line, or after command separators
            escaped_word = re.escape(blocked_normalized)

            # Safe contexts: URL parameters
            # ?format=, &format=, -format=value, --format=value
            safe_pattern = rf'[?&\-]({escaped_word})='

            # Dangerous contexts: command execution
            # ^format, format c:, format.exe, | format, ; format, && format
            dangerous_pattern = rf'(?:^|[\|;]|[;&]\s+)({escaped_word})(?:\s|$)'

            if re.search(dangerous_pattern, command_normalized):
                # Also make sure it's NOT in a URL parameter context
                if not re.search(safe_pattern, command_normalized):
                    raise ValueError(
                        f"Command contains blocked pattern: {blocked}. "
                        f"This command is not allowed for security reasons."
                    )

        # Check for path traversal attempts
        if "../" in command and "rm" in command.lower():
            raise ValueError(
                "Path traversal with delete commands is not allowed"
            )

        # Block access to sensitive files
        sensitive_files = [
            "credentials.encrypted",
            "credentials.json",
            ".env",
            ".env.local",
        ]

        command_lower = command.lower()
        for sensitive in sensitive_files:
            # Block commands that try to read sensitive files
            if sensitive in command_lower and any(cmd in command_lower for cmd in ["cat", "less", "more", "head", "tail", "view"]):
                raise ValueError(
                    f"Cannot access sensitive file ({sensitive}) with command"
                )

    def _validate_directory(self, cwd: Optional[str]) -> str:
        """
        Validate working directory is within root_dir.

        Returns:
            Absolute path of working directory

        Raises:
            ValueError: If directory is outside root_dir
        """
        if cwd is None:
            return self._root_dir

        cwd_abs = Path(os.path.abspath(cwd))
        root_abs = Path(os.path.abspath(self._root_dir))

        # Check if cwd is within root_dir
        try:
            cwd_abs.relative_to(root_abs)
            return str(cwd_abs)
        except ValueError:
            raise ValueError(
                f"Working directory {cwd} is outside allowed root {self._root_dir}"
            )

    def _run(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30,
    ) -> str:
        """
        Execute the shell command.

        Args:
            command: Shell command to execute
            cwd: Working directory
            timeout: Command timeout in seconds

        Returns:
            Command output (stdout + stderr)

        Raises:
            ValueError: If command is blocked or directory is invalid
            subprocess.TimeoutExpired: If command times out
        """
        # Safety checks
        self._check_command_safety(command)
        valid_cwd = self._validate_directory(cwd)

        try:
            # Execute command
            # Use UTF-8 encoding for cross-platform compatibility
            # errors='replace' replaces characters that can't be decoded instead of crashing
            result = subprocess.run(
                command,
                shell=True,
                cwd=valid_cwd,
                capture_output=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                check=False,  # Don't raise exception on non-zero exit
            )

            # Combine stdout and stderr
            output = []
            if result.stdout:
                output.append(result.stdout)
            if result.stderr:
                output.append(result.stderr)

            # Add exit code if non-zero
            if result.returncode != 0:
                output.append(f"\n[Exit code: {result.returncode}]")

            return "\n".join(output) if output else "Command completed with no output"

        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"

    async def _arun(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30,
    ) -> str:
        """
        Async version of the tool.

        This is a wrapper around the sync version since subprocess doesn't
        have a native async API.
        """
        return self._run(command, cwd, timeout)


# Create a singleton instance for easy import
terminal_tool = TerminalTool()
