"""
Files Models - Pydantic models for file API
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """Information about a file or directory."""

    name: str = Field(..., description="File/directory name")
    path: str = Field(..., description="Relative path from project root")
    type: str = Field(..., description="'file' or 'directory'")
    size: Optional[int] = Field(
        default=None,
        description="File size in bytes (files only)",
    )

    modified_time: Optional[str] = Field(
        default=None,
        description="Last modified time (ISO 8601)",
    )


class FileListResponse(BaseModel):
    """Response model for file listing."""

    files: List[FileInfo] = Field(
        ...,
        description="List of files/directories",
    )

    current_path: str = Field(
        ...,
        description="Current directory path",
    )


class FileReadRequest(BaseModel):
    """Request model for reading a file."""

    path: str = Field(
        ...,
        description="File path (relative to project root)",
    )


class FileReadResponse(BaseModel):
    """Response model for file reading."""

    path: str = Field(..., description="File path")
    content: str = Field(..., description="File content")
    encoding: str = Field(
        default="utf-8",
        description="File encoding",
    )


class FileWriteRequest(BaseModel):
    """Request model for writing a file."""

    path: str = Field(
        ...,
        description="File path (relative to project root)",
    )

    content: str = Field(
        ...,
        description="File content",
    )

    create_directories: bool = Field(
        default=False,
        description="Create parent directories if they don't exist",
    )


class FileWriteResponse(BaseModel):
    """Response model for file writing."""

    path: str = Field(..., description="File path")
    success: bool = Field(..., description="Whether write was successful")
    message: Optional[str] = Field(
        default=None,
        description="Additional message",
    )
