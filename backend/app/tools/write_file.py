"""
Write File Tool - Safe File Writing

This tool allows the Agent to write content to local files within a restricted directory.
Security features:
- Path restriction to root_dir
- Path traversal prevention
- Sensitive file protection
- Automatic directory creation
"""

import os
from typing import Literal, Optional
from pathlib import Path
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from app.config import settings


class WriteFileInput(BaseModel):
    """Input schema for Write File tool."""

    path: str = Field(
        ...,
        description="Path to the file to write (relative or absolute)",
    )

    content: str = Field(
        ...,
        description="Content to write to the file",
    )

    mode: Literal["overwrite", "append"] = Field(
        default="overwrite",
        description="Write mode: 'overwrite' to replace content, 'append' to add to end",
    )

    create_dirs: bool = Field(
        default=True,
        description="Create parent directories if they don't exist",
    )


class WriteFileTool(BaseTool):
    """
    Write File tool for safely writing content to local files.

    This tool restricts file writing to a specified root directory
    to prevent unauthorized file modification.
    """

    name: str = "write_file"
    description: str = """
    Write content to a file on the local filesystem.

    Features:
    - Restricted to project directory
    - Prevents path traversal attacks
    - Automatic directory creation
    - Sensitive file protection

    Modes:
    - overwrite: Replace existing file content (default)
    - append: Add content to the end of existing file

    Common uses:
    - Create configuration files
    - Save generated code
    - Write log files
    - Update documentation

    Examples:
    - write_file: path="config.json", content='{"key": "value"}'
    - write_file: path="output.txt", content="Hello World", mode="overwrite"
    - write_file: path="log.txt", content="New entry\\n", mode="append"

    Security:
    - Cannot overwrite sensitive files (credentials, .env, etc.)
    - Path is restricted to project directory
    """

    args_schema: type[WriteFileInput] = WriteFileInput

    # Security settings
    _root_dir: str = os.path.abspath(settings.write_file_root_dir if hasattr(settings, 'write_file_root_dir') else settings.terminal_root_dir)

    # Sensitive files that cannot be overwritten
    _protected_files: set[str] = {
        "credentials.encrypted",
        "credentials.json",
        ".env",
        ".env.local",
        ".env.production",
        ".git",
        ".gitignore",
        "package-lock.json",
        "yarn.lock",
    }

    def _resolve_path(self, path: str) -> Path:
        """
        Resolve and validate file path.

        Args:
            path: File path (can be relative or absolute)

        Returns:
            Resolved absolute Path object

        Raises:
            ValueError: If path is outside root_dir or invalid
        """
        # Convert to Path object
        file_path = Path(path)

        # If relative, resolve from root_dir
        if not file_path.is_absolute():
            file_path = (Path(self._root_dir) / file_path).resolve()
        else:
            file_path = file_path.resolve()

        # Check if path is within root_dir
        try:
            file_path.relative_to(self._root_dir)
        except ValueError:
            raise ValueError(
                f"Access denied: Path {path} is outside allowed directory {self._root_dir}"
            )

        return file_path

    def _check_sensitive_file(self, file_path: Path) -> None:
        """
        Check if file is sensitive and should not be overwritten.

        Args:
            file_path: Path to check

        Raises:
            ValueError: If file is protected
        """
        path_str = str(file_path)

        # Check if any protected pattern is in the path
        for protected in self._protected_files:
            if protected in path_str:
                raise ValueError(
                    f"Access denied: Cannot modify protected file ({protected})"
                )

        # Check if trying to write to executable files
        if file_path.suffix.lower() in {'.exe', '.dll', '.so', '.dylib', '.bin'}:
            raise ValueError(
                f"Access denied: Cannot write to binary files"
            )

    def _create_parent_dirs(self, file_path: Path) -> None:
        """
        Create parent directories if they don't exist.

        Args:
            file_path: File path whose parent directories should be created
        """
        parent_dir = file_path.parent
        if parent_dir and not parent_dir.exists():
            parent_dir.mkdir(parents=True, exist_ok=True)

    def _run(
        self,
        path: str,
        content: str,
        mode: Literal["overwrite", "append"] = "overwrite",
        create_dirs: bool = True,
    ) -> str:
        """
        Write content to a file.

        Args:
            path: File path to write
            content: Content to write
            mode: Write mode (overwrite or append)
            create_dirs: Whether to create parent directories

        Returns:
            Success message with file size information

        Raises:
            ValueError: If path is invalid or file is protected
            PermissionError: If cannot write to file
            Exception: For other errors
        """
        try:
            # Resolve and validate path
            file_path = self._resolve_path(path)

            # Check if file is sensitive
            self._check_sensitive_file(file_path)

            # Create parent directories if needed
            if create_dirs:
                self._create_parent_dirs(file_path)

            # Write file
            try:
                if mode == "overwrite":
                    file_path.write_text(content, encoding="utf-8")
                    bytes_written = len(content.encode('utf-8'))
                else:  # append
                    with open(file_path, 'a', encoding='utf-8') as f:
                        f.write(content)
                    bytes_written = len(content.encode('utf-8'))

                # Verify write was successful
                if not file_path.exists():
                    return f"Error: Failed to write file (file doesn't exist after write)"

                # Get final file size
                final_size = file_path.stat().st_size

                return (
                    f"Successfully wrote {bytes_written} bytes to {path}. "
                    f"Final file size: {final_size} bytes."
                )

            except PermissionError:
                return f"Permission denied: Cannot write to {path}"

        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Error writing file: {str(e)}"

    async def _arun(
        self,
        path: str,
        content: str,
        mode: Literal["overwrite", "append"] = "overwrite",
        create_dirs: bool = True,
    ) -> str:
        """Async version (wraps sync execution)."""
        return self._run(path, content, mode, create_dirs)


# Create a singleton instance
write_file_tool = WriteFileTool()
