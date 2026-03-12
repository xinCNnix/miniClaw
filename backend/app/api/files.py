"""
Files API - File Management Endpoints

This module provides endpoints for reading and writing files.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.models.files import (
    FileListResponse,
    FileInfo,
    FileReadRequest,
    FileReadResponse,
    FileWriteRequest,
    FileWriteResponse,
)

from app.config import get_settings


router = APIRouter(tags=["files"])


def resolve_safe_path(path_str: str) -> Path:
    """
    Resolve and validate a file path.

    Args:
        path_str: Path string (can be relative or absolute)

    Returns:
        Resolved Path object

    Raises:
        HTTPException: If path is outside allowed directory
    """
    settings = get_settings()
    base_dir = Path(settings.base_dir).resolve()

    # Resolve path
    file_path = Path(path_str)

    if not file_path.is_absolute():
        file_path = (base_dir / file_path).resolve()
    else:
        file_path = file_path.resolve()

    # Security check: ensure path is within base_dir
    try:
        file_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Path is outside allowed directory",
        )

    return file_path


@router.get("")
async def list_files(path: str = ".") -> FileListResponse:
    """
    List files and directories in a given path.

    ## Query Parameters
    - **path**: Directory path (relative to project root, default: ".")

    ## Response Format
    ```json
    {
      "files": [
        {
          "name": "README.md",
          "path": "README.md",
          "type": "file",
          "size": 1234,
          "modified_time": "2024-03-04T10:00:00"
        }
      ],
      "current_path": "."
    }
    ```

    ## Example Usage
    ```bash
    curl "http://localhost:8002/api/files?path=backend/app"
    ```

    Args:
        path: Directory path to list

    Returns:
        FileListResponse with files/directories in the path

    Raises:
        HTTPException: If path doesn't exist or access denied
    """
    file_path = resolve_safe_path(path)
    settings = get_settings()
    base_dir = Path(settings.base_dir).resolve()

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path not found: {path}",
        )

    if not file_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {path}",
        )

    # List contents
    files = []

    try:
        for item in file_path.iterdir():
            item_type = "directory" if item.is_dir() else "file"

            # Return path relative to base_dir, not parent directory
            # This ensures read_file receives the correct path
            try:
                relative_path = item.relative_to(base_dir)
            except ValueError:
                # Fallback: if item is outside base_dir (shouldn't happen due to security check)
                relative_path = item.relative_to(file_path.parent)

            # Convert to forward slashes for consistency
            relative_path_str = str(relative_path).replace('\\', '/')

            file_info = FileInfo(
                name=item.name,
                path=relative_path_str,
                type=item_type,
                size=item.stat().st_size if item.is_file() else None,
                modified_time=datetime.fromtimestamp(item.stat().st_mtime).isoformat() if item.is_file() else None,
            )

            files.append(file_info)

        # Sort: directories first, then alphabetically
        files.sort(key=lambda f: (f.type != "directory", f.name.lower()))

    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {path}",
        )

    return FileListResponse(
        files=files,
        current_path=path,
    )


@router.get("/read")
async def read_file(path: str) -> FileReadResponse:
    """
    Read the contents of a file.

    ## Query Parameters
    - **path**: File path (relative to project root)

    ## Response Format
    ```json
    {
      "path": "README.md",
      "content": "# Project README...",
      "encoding": "utf-8"
    }
    ```

    ## Example Usage
    ```bash
    curl "http://localhost:8002/api/files/read?path=README.md"
    ```

    Args:
        path: File path to read

    Returns:
        FileReadResponse with file content

    Raises:
        HTTPException: If file doesn't exist, is binary, or access denied
    """
    file_path = resolve_safe_path(path)

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path}",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a file: {path}",
        )

    # Check for binary files
    binary_extensions = {
        '.exe', '.dll', '.so', '.dylib', '.bin',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
        '.mp3', '.mp4', '.avi', '.mov', '.zip', '.tar', '.gz',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    }

    if file_path.suffix.lower() in binary_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Binary files are not supported: {file_path.suffix}",
        )

    # Read file
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="latin-1")
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to read file: encoding issues",
            )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {path}",
        )

    return FileReadResponse(
        path=path,
        content=content,
        encoding="utf-8",
    )


@router.post("")
async def write_file(request: FileWriteRequest) -> FileWriteResponse:
    """
    Write content to a file (create or update).

    ## Request Format
    ```json
    {
      "path": "README.md",
      "content": "# Project README...",
      "create_directories": false
    }
    ```

    ## Example Usage
    ```bash
    curl -X POST http://localhost:8002/api/files \
      -H "Content-Type: application/json" \
      -d '{"path": "test.txt", "content": "Hello World!"}'
    ```

    Args:
        request: File write request

    Returns:
        FileWriteResponse indicating success/failure

    Raises:
        HTTPException: If path is invalid or access denied
    """
    file_path = resolve_safe_path(request.path)

    # Create parent directories if requested
    if request.create_directories:
        file_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if file exists and is directory
    if file_path.exists() and file_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is a directory, not a file: {request.path}",
        )

    # Write file
    try:
        file_path.write_text(request.content, encoding="utf-8")

        return FileWriteResponse(
            path=request.path,
            success=True,
            message=f"File saved successfully: {request.path}",
        )

    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {request.path}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file: {str(e)}",
        )


@router.delete("")
async def delete_file(path: str) -> dict:
    """
    Delete a file.

    ## Query Parameters
    - **path**: File path to delete

    ## Example Usage
    ```bash
    curl -X DELETE "http://localhost:8002/api/files?path=test.txt"
    ```

    Args:
        path: File path to delete

    Returns:
        Dict with success status

    Raises:
        HTTPException: If file doesn't exist, is protected, or access denied
    """
    file_path = resolve_safe_path(path)

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path}",
        )

    # Security: prevent deleting critical files
    protected_patterns = [
        "requirements.txt",
        "pyproject.toml",
        "main.py",
        "config.py",
        "__init__.py",
    ]

    if file_path.name in protected_patterns:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete protected file: {file_path.name}",
        )

    try:
        file_path.unlink()

        return {
            "success": True,
            "message": f"File deleted: {path}",
        }

    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {path}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}",
        )
