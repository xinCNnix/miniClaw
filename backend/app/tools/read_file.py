"""
Read File Tool - Safe File Reading

This tool allows reading local files within a restricted directory.
Security features:
- Path restriction to root_dir
- Path traversal prevention
- Binary file detection
"""

import os
from typing import Optional
from pathlib import Path
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from app.config import settings


class ReadFileInput(BaseModel):
    """Input schema for Read File tool."""

    path: str = Field(
        ...,
        description="Path to the file to read (relative or absolute)",
    )

    encoding: str = Field(
        default="utf-8",
        description="File encoding (default: utf-8)",
    )


class ReadFileTool(BaseTool):
    """
    Read File tool for safely reading local files.

    This tool restricts file reading to a specified root directory
    to prevent unauthorized file access.
    """

    name: str = "read_file"
    description: str = """
    Read the contents of a file from the local filesystem.

    Features:
    - Restricted to project directory
    - Prevents path traversal attacks
    - Automatic encoding detection
    - Binary file detection

    Common uses:
    - Read configuration files
    - Read Markdown documentation (SKILL.md)
    - Read source code
    - Read data files

    Examples:
    - read_file: README.md
    - read_file: data/skills/get_weather/SKILL.md
    - read_file: app/config.py

    Note: Only files within the project directory can be read.
    Binary files will return an error message.
    """
    args_schema: type[ReadFileInput] = ReadFileInput

    # Security settings
    _root_dir: str = os.path.abspath(settings.read_file_root_dir)

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

        # Block access to sensitive files
        blocked_paths = [
            "credentials.encrypted",
            "credentials.json",
            ".env",
            ".env.local",
            ".env.production",
        ]

        path_str = str(file_path)
        for blocked in blocked_paths:
            if blocked in path_str:
                raise ValueError(
                    f"Access denied: Cannot read sensitive file ({blocked})"
                )

        return file_path

    def _check_binary(self, file_path: Path) -> bool:
        """
        Check if file is binary.

        Args:
            file_path: Path to check

        Returns:
            True if file appears to be binary
        """
        # 1. Check file extension blacklist first
        binary_extensions = {
            '.exe', '.dll', '.so', '.dylib', '.bin',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
            '.mp3', '.mp4', '.avi', '.mov', '.zip', '.tar', '.gz',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        }

        if file_path.suffix.lower() in binary_extensions:
            return True

        # 2. Try to read first few bytes
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(4096)  # Read first 4KB

                # Empty file is not binary
                if len(chunk) == 0:
                    return False

                # Check for null bytes (common in binary files)
                if b'\x00' in chunk:
                    return True

                # 3. Priority: Try UTF-8 decoding (supports Chinese/multibyte characters)
                try:
                    chunk.decode('utf-8')
                    return False  # Successfully decoded as UTF-8, it's a text file
                except UnicodeDecodeError:
                    pass  # Fall through to byte-level checking

                # 4. Fallback: Check high ratio of non-text bytes
                # Only if UTF-8 decoding fails
                # Define text characters: control chars 7-13, printable chars 32-126 (excluding 127 DEL)
                text_bytes = bytes([7, 8, 9, 10, 12, 13, 27]) + bytes(range(0x20, 0x7f))
                text_chars = set(text_bytes)
                non_text = sum(1 for byte in chunk if byte not in text_chars)

                # Use 80% threshold (more tolerant for files with multibyte characters)
                threshold = 0.8
                if non_text / len(chunk) > threshold:
                    return True

        except Exception:
            # If we can't read, assume binary
            return True

        return False

    def _run(
        self,
        path: str,
        encoding: str = "utf-8",
    ) -> str:
        """
        Read file contents.

        Args:
            path: File path to read
            encoding: File encoding

        Returns:
            File contents or error message
        """
        try:
            # Resolve and validate path
            file_path = self._resolve_path(path)

            # Check if file exists
            if not file_path.exists():
                return f"File not found: {path}"

            # Check if it's a file (not directory)
            if not file_path.is_file():
                return f"Path is not a file: {path}"

            # Check if binary
            if self._check_binary(file_path):
                return (
                    f"Binary file detected: {file_path.name}. "
                    f"Cannot read binary files. "
                    f"If this is actually a text file, please report this."
                )

            # Read file content
            try:
                content = file_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                # Try with different encoding
                try:
                    content = file_path.read_text(encoding="latin-1")
                    content += "\n\n[Note: File was read with latin-1 encoding due to encoding issues]"
                except Exception:
                    return f"Failed to read file with encoding: {encoding}"

            return content

        except ValueError as e:
            return str(e)
        except PermissionError:
            return f"Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {str(e)}"

    async def _arun(
        self,
        path: str,
        encoding: str = "utf-8",
    ) -> str:
        """Async version (wraps sync execution)."""
        # For file I/O, async doesn't provide much benefit
        # so we just wrap the sync version
        return self._run(path, encoding)


# Create a singleton instance
read_file_tool = ReadFileTool()
