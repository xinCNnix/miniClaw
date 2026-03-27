"""
Write File Tool - Safe File Writing

This tool allows the Agent to write content to local files within a restricted directory.
Security features:
- Path restriction to root_dir
- Path traversal prevention
- Sensitive file protection
- Automatic directory creation
- Support for text and binary (image) files
"""

import os
import base64
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
        description="Content to write to the file (text or base64-encoded binary)",
    )

    mode: Literal["overwrite", "append", "base64"] = Field(
        default="overwrite",
        description="Write mode: 'overwrite' to replace content, 'append' to add to end, 'base64' for binary data (images)",
    )

    create_dirs: bool = Field(
        default=True,
        description="Create parent directories if they don't exist",
    )

    mime_type: Optional[str] = Field(
        default=None,
        description="MIME type for base64 content (e.g., 'image/png', 'image/jpeg')",
    )


class WriteFileTool(BaseTool):
    """
    Write File tool for safely writing content to local files.

    This tool restricts file writing to a specified root directory
    to prevent unauthorized file modification.
    """

    name: str = "write_file"
    description: str = """
    ⚠️ CRITICAL: This is the ONLY tool for writing files!

    ALWAYS use write_file for ALL file operations:
    - Creating new files
    - Saving code/scripts
    - Writing documentation
    - Updating configuration
    - Generating any file content
    - Saving images (base64 encoded)

    NEVER use python_repl or terminal to write files!
    - ❌ DON'T: python_repl with Path.write_text(), open(), etc.
    - ❌ DON'T: terminal with echo, redirect, etc.
    - ✅ DO: Use write_file tool

    Features:
    - Restricted to project directory
    - Prevents path traversal attacks
    - Automatic directory creation
    - Sensitive file protection
    - Proper path resolution
    - Image support via base64 encoding

    Modes:
    - overwrite: Replace existing file content (default)
    - append: Add content to the end of existing file
    - base64: Content is base64-encoded binary data (for images)

    Parameters:
    - path (required): File path (relative or absolute)
    - content (required): Content to write
    - mode (optional): "overwrite", "append", or "base64" (default: "overwrite")
    - create_dirs (optional): Auto-create parent directories (default: true)
    - mime_type (optional): MIME type for base64 content (e.g., "image/png")

    Examples:
    - write_file: path="config.json", content='{"key": "value"}'
    - write_file: path="scripts/myscript.py", content="print('Hello')", mode="overwrite"
    - write_file: path="data/skills/my-skill/SKILL.md", content="# My Skill\\n...", mode="overwrite"
    - write_file: path="log.txt", content="New entry\\n", mode="append"
    - write_file: path="downloads/chart.png", content="<base64_data>", mode="base64", mime_type="image/png"

    Security:
    - Cannot overwrite sensitive files (credentials, .env, etc.)
    - Path is restricted to project directory
    - Automatically validates file paths
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
        # Path objects are always truthy, so just check existence
        if not parent_dir.exists():
            parent_dir.mkdir(parents=True, exist_ok=True)

    def _run(
        self,
        path: str,
        content: str,
        mode: Literal["overwrite", "append", "base64"] = "overwrite",
        create_dirs: bool = True,
        mime_type: Optional[str] = None,
    ) -> str:
        """
        Write content to a file.

        Args:
            path: File path to write
            content: Content to write (text or base64-encoded binary)
            mode: Write mode (overwrite, append, or base64)
            create_dirs: Whether to create parent directories
            mime_type: MIME type for base64 content

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

            # Write file based on mode
            try:
                if mode == "base64":
                    # Decode base64 and write binary
                    try:
                        binary_data = base64.b64decode(content)
                        with open(file_path, 'wb') as f:
                            f.write(binary_data)
                        bytes_written = len(binary_data)
                        file_type = mime_type or "binary"
                    except Exception as e:
                        return f"Error decoding base64 content: {str(e)}"

                elif mode == "overwrite":
                    file_path.write_text(content, encoding="utf-8")
                    bytes_written = len(content.encode('utf-8'))
                    file_type = "text"

                else:  # append
                    with open(file_path, 'a', encoding='utf-8') as f:
                        f.write(content)
                    bytes_written = len(content.encode('utf-8'))
                    file_type = "text"

                # Verify write was successful
                if not file_path.exists():
                    return f"Error: Failed to write file (file doesn't exist after write)"

                # Get final file size
                final_size = file_path.stat().st_size

                # Provide clear success message
                if mode == "append":
                    return (
                        f"Successfully appended {bytes_written} bytes ({file_type}) to {path}. "
                        f"Total file size: {final_size} bytes."
                    )
                elif mode == "base64":
                    return (
                        f"Successfully wrote {bytes_written} bytes ({file_type}) to {path}. "
                        f"Final file size: {final_size} bytes."
                    )
                else:  # overwrite
                    return (
                        f"Successfully wrote {bytes_written} bytes ({file_type}) to {path}. "
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
        mode: Literal["overwrite", "append", "base64"] = "overwrite",
        create_dirs: bool = True,
        mime_type: Optional[str] = None,
    ) -> str:
        """Async version (wraps sync execution)."""
        return self._run(path, content, mode, create_dirs, mime_type)


# Create a singleton instance
write_file_tool = WriteFileTool()
