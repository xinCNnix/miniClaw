"""
Knowledge Base Data Models

Pydantic models for knowledge base API validation and serialization.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class KBDocument(BaseModel):
    """Knowledge base document metadata."""

    id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="File name")
    file_type: str = Field(..., description="File extension (e.g., '.txt', '.pdf')")
    size: int = Field(..., description="File size in bytes")
    upload_date: str = Field(..., description="Upload timestamp (ISO format)")
    chunk_count: int = Field(..., description="Number of chunks after splitting")


class KBUploadResponse(BaseModel):
    """Response for document upload."""

    success: bool = Field(..., description="Upload success status")
    document: KBDocument = Field(..., description="Document metadata")
    message: str = Field(..., description="Status message")


class KBUploadStatus(str, Enum):
    """Upload task status."""

    PENDING = "pending"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class KBUploadTaskResponse(BaseModel):
    """Response for async upload task creation."""

    success: bool = Field(..., description="Task creation status")
    task_id: str = Field(..., description="Upload task ID")
    filename: str = Field(..., description="File name")
    message: str = Field(..., description="Status message")


class KBUploadProgress(BaseModel):
    """Upload task progress."""

    task_id: str = Field(..., description="Task ID")
    filename: str = Field(..., description="File name")
    status: KBUploadStatus = Field(..., description="Current status")
    progress: int = Field(..., description="Progress percentage (0-100)")
    message: str = Field(..., description="Status message")
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: str = Field(..., description="Task creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    document: Optional[KBDocument] = Field(None, description="Document metadata (when completed)")


class KBDocumentListResponse(BaseModel):
    """Response for document list."""

    documents: List[KBDocument] = Field(default_factory=list, description="List of documents")
    total: int = Field(..., description="Total number of documents")


class KBStats(BaseModel):
    """Knowledge base statistics."""

    total_documents: int = Field(..., description="Total number of documents")
    total_chunks: int = Field(..., description="Total number of chunks")
    total_size: int = Field(..., description="Total size in bytes")
    last_updated: Optional[str] = Field(None, description="Last update timestamp (ISO format)")


class KBDeleteResponse(BaseModel):
    """Response for document deletion."""

    success: bool = Field(..., description="Deletion success status")
    message: str = Field(..., description="Status message")


class KBLargeFileUploadRequest(BaseModel):
    """Request for uploading a large file that requires authorization."""

    filename: str = Field(..., description="File name")
    file_size: int = Field(..., description="File size in bytes")
    confirm: bool = Field(
        ...,
        description="User confirmation to proceed with large file upload",
    )


class KBLargeFileUploadResponse(BaseModel):
    """Response for large file upload request."""

    requires_authorization: bool = Field(..., description="Whether file requires authorization")
    file_size: int = Field(..., description="File size in bytes")
    file_size_mb: float = Field(..., description="File size in MB")
    threshold_mb: float = Field(..., description="Authorization threshold in MB")
    message: str = Field(..., description="Informational message")
    upload_token: Optional[str] = Field(None, description="Upload token if authorized")


class KBBatchUploadRequest(BaseModel):
    """Request for batch file upload."""

    confirm: bool = Field(
        ...,
        description="User confirmation to proceed with batch upload",
    )
    file_count: int = Field(..., description="Number of files to upload")
    total_size: int = Field(..., description="Total size of all files in bytes")


class KBBatchUploadResponse(BaseModel):
    """Response for batch upload request."""

    requires_authorization: bool = Field(..., description="Whether batch requires authorization")
    file_count: int = Field(..., description="Number of files")
    total_size_mb: float = Field(..., description="Total size in MB")
    threshold_mb: float = Field(..., description="Authorization threshold in MB")
    message: str = Field(..., description="Informational message")
    upload_token: Optional[str] = Field(None, description="Upload token if authorized")


class KBBatchUploadProgress(BaseModel):
    """Progress update for batch upload."""

    task_id: str = Field(..., description="Batch upload task ID")
    completed: int = Field(..., description="Number of completed uploads")
    total: int = Field(..., description="Total number of files")
    current_file: str = Field(..., description="Currently processing file")
    failed_files: list[str] = Field(default_factory=list, description="List of failed files")


class KBRejectedFile(BaseModel):
    """Information about a rejected file."""

    filename: str = Field(..., description="File name")
    path: str = Field(..., description="File path")
    reason: str = Field(..., description="Rejection reason")


class KBBatchUploadComplete(BaseModel):
    """Result of batch upload operation."""

    task_id: str = Field(..., description="Task ID")
    total: int = Field(..., description="Total files processed")
    successful: int = Field(..., description="Successfully uploaded files")
    failed: int = Field(..., description="Failed uploads")
    failed_files: list[KBRejectedFile] = Field(default_factory=list, description="List of failed files with reasons")
    message: str = Field(..., description="Status message")
