"""
Knowledge Base API

Endpoints for managing knowledge base documents and retrieval.
"""

import os
import shutil
import uuid
from pathlib import Path
from typing import Optional
import asyncio
import hashlib
import time

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks, Body
from fastapi.responses import JSONResponse

from app.core.rag_engine import RAGEngine, get_rag_engine
from app.utils.file_detector import FileDetector
from app.core.upload_progress import (
    get_upload_progress_manager,
    UploadStatus,
)
from app.models.knowledge_base import (
    KBDocument,
    KBUploadResponse,
    KBUploadTaskResponse,
    KBUploadProgress,
    KBDocumentListResponse,
    KBStats,
    KBDeleteResponse,
    KBUploadStatus,
    KBLargeFileUploadRequest,
    KBLargeFileUploadResponse,
    KBBatchUploadRequest,
    KBBatchUploadResponse,
    KBBatchUploadProgress,
    KBBatchUploadComplete,
    KBRejectedFile,
)
from app.config import get_settings, Settings

router = APIRouter()
settings = get_settings()

# Store upload tokens for authorized large files (token -> expiry time)
_upload_tokens: dict[str, float] = {}


def _generate_upload_token() -> str:
    """Generate a time-limited upload token for large files."""
    token = hashlib.sha256(f"{uuid.uuid4()}{time.time()}".encode()).hexdigest()[:32]
    # Token valid for 10 minutes
    expiry = time.time() + 600
    _upload_tokens[token] = expiry
    return token


def _validate_upload_token(token: str) -> bool:
    """Validate an upload token."""
    if token not in _upload_tokens:
        return False
    # Check if token is expired
    if time.time() > _upload_tokens[token]:
        del _upload_tokens[token]
        return False
    return True


async def _process_upload_task(
    task_id: str,
    file_path: Path,
    filename: str,
    rag_engine: RAGEngine,
):
    """
    Background task to process document upload.

    Args:
        task_id: Upload task ID
        file_path: Path to uploaded file
        filename: Original filename
        rag_engine: RAG engine instance
    """
    progress_manager = get_upload_progress_manager()

    try:
        # Update status to indexing
        progress_manager.update_task(
            task_id,
            status=UploadStatus.INDEXING,
            progress=50,
            message="Indexing document...",
        )

        # Index document
        doc_metadata = await rag_engine.upload_document(str(file_path))

        # Update status to completed
        progress_manager.update_task(
            task_id,
            status=UploadStatus.COMPLETED,
            progress=100,
            message="Document uploaded successfully",
        )

        # Add document metadata to progress
        task = progress_manager.get_task(task_id)
        if task:
            task_dict = task.model_dump()
            task_dict["document"] = KBDocument(**doc_metadata)
            progress_manager._tasks[task_id] = KBUploadProgress(**task_dict)

    except Exception as e:
        # Clean up file if processing fails
        file_path.unlink(missing_ok=True)

        # Update status to failed
        progress_manager.update_task(
            task_id,
            status=UploadStatus.FAILED,
            message="Upload failed",
            error=str(e),
        )


@router.post("/upload/check-large-file", response_model=KBLargeFileUploadResponse)
async def check_large_file(
    request: KBLargeFileUploadRequest,
):
    """
    Check if a file requires authorization due to its size.

    Files larger than large_file_threshold (default: 100MB) require explicit user authorization.
    Returns authorization requirements and can generate an upload token if confirmed.
    """
    file_size_mb = request.file_size / (1024 * 1024)
    threshold_mb = settings.large_file_threshold / (1024 * 1024)
    max_size_mb = settings.max_file_size / (1024 * 1024)

    # Check if file exceeds maximum size
    if request.file_size > settings.max_file_size:
        return KBLargeFileUploadResponse(
            requires_authorization=False,
            file_size=request.file_size,
            file_size_mb=file_size_mb,
            threshold_mb=threshold_mb,
            message=f"File too large: {file_size_mb:.2f}MB exceeds maximum {max_size_mb:.2f}MB",
        )

    # Check if file requires authorization
    requires_auth = request.file_size > settings.large_file_threshold

    if requires_auth:
        if request.confirm:
            # User has confirmed, generate upload token
            token = _generate_upload_token()
            return KBLargeFileUploadResponse(
                requires_authorization=True,
                file_size=request.file_size,
                file_size_mb=file_size_mb,
                threshold_mb=threshold_mb,
                message=f"Large file upload authorized. Token valid for 10 minutes.",
                upload_token=token,
            )
        else:
            # File requires authorization but not confirmed
            return KBLargeFileUploadResponse(
                requires_authorization=True,
                file_size=request.file_size,
                file_size_mb=file_size_mb,
                threshold_mb=threshold_mb,
                message=f"File size {file_size_mb:.2f}MB exceeds threshold {threshold_mb:.2f}MB. "
                       f"Please confirm to proceed with upload.",
            )
    else:
        # File does not require authorization
        return KBLargeFileUploadResponse(
            requires_authorization=False,
            file_size=request.file_size,
            file_size_mb=file_size_mb,
            threshold_mb=threshold_mb,
            message=f"File size {file_size_mb:.2f}MB is within normal limits.",
        )


@router.post("/upload", response_model=KBUploadTaskResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    upload_token: Optional[str] = None,
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Upload a document to the knowledge base (async).

    Supported formats: .txt, .md, .pdf, .docx, .doc, .xls, .xlsx, .wps
    Max file size: 1GB
    Large files (>100MB) require authorization via /upload/check-large-file endpoint

    Parameters:
    - upload_token: Required for files larger than large_file_threshold (100MB)

    Returns a task ID for progress tracking.
    """
    # Generate task ID
    task_id = str(uuid.uuid4())[:16]
    progress_manager = get_upload_progress_manager()

    # Validate file type
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.allowed_file_types:
        progress_manager.create_task(task_id, file.filename)
        progress_manager.update_task(
            task_id,
            status=UploadStatus.FAILED,
            message="Validation failed",
            error=f"Unsupported file type: {file_ext}",
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Supported: {settings.allowed_file_types}",
        )

    # Create task
    progress_manager.create_task(task_id, file.filename)
    progress_manager.update_task(
        task_id,
        status=UploadStatus.VALIDATING,
        progress=10,
        message="Validating file...",
    )

    # Validate file size
    content = await file.read()
    file_size = len(content)

    # Check if file exceeds maximum size
    if file_size > settings.max_file_size:
        progress_manager.update_task(
            task_id,
            status=UploadStatus.FAILED,
            message="Validation failed",
            error=f"File too large: {file_size} > {settings.max_file_size}",
        )
        max_mb = settings.max_file_size / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size / (1024 * 1024):.2f}MB exceeds maximum {max_mb:.0f}MB",
        )

    # Check if file requires authorization
    if file_size > settings.large_file_threshold:
        if not upload_token:
            progress_manager.update_task(
                task_id,
                status=UploadStatus.FAILED,
                message="Validation failed",
                error=f"Large file requires authorization token",
            )
            threshold_mb = settings.large_file_threshold / (1024 * 1024)
            raise HTTPException(
                status_code=403,
                detail=f"File size {file_size / (1024 * 1024):.2f}MB exceeds threshold {threshold_mb:.0f}MB. "
                       f"Please call /upload/check-large-file to authorize this upload.",
            )

        # Validate upload token
        if not _validate_upload_token(upload_token):
            progress_manager.update_task(
                task_id,
                status=UploadStatus.FAILED,
                message="Validation failed",
                error=f"Invalid or expired upload token",
            )
            raise HTTPException(
                status_code=403,
                detail="Invalid or expired upload token. Please authorize the upload again.",
            )

        # Token is valid, consume it
        del _upload_tokens[upload_token]

    # Save to knowledge base directory
    kb_dir = Path(settings.knowledge_base_dir)
    kb_dir.mkdir(parents=True, exist_ok=True)

    file_path = kb_dir / file.filename

    # Handle duplicate filenames
    counter = 1
    original_path = file_path
    while file_path.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        file_path = kb_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    # Write file
    with open(file_path, "wb") as f:
        f.write(content)

    # Update status to uploading
    progress_manager.update_task(
        task_id,
        status=UploadStatus.UPLOADING,
        progress=30,
        message="File saved, starting indexing...",
    )

    # Add background task to process upload
    background_tasks.add_task(
        _process_upload_task,
        task_id,
        file_path,
        file.filename,
        rag_engine,
    )

    return KBUploadTaskResponse(
        success=True,
        task_id=task_id,
        filename=file.filename,
        message="Upload task created",
    )


@router.post("/upload/sync", response_model=KBUploadResponse)
async def upload_document_sync(
    file: UploadFile = File(...),
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Upload a document to the knowledge base (synchronous).

    This endpoint waits for the upload to complete before returning.
    For large files, consider using the async /upload endpoint instead.

    Supported formats: .txt, .md, .pdf, .docx
    Max file size: 10MB
    """
    # Validate file type
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.allowed_file_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Supported: {settings.allowed_file_types}",
        )

    # Validate file size
    content = await file.read()
    file_size = len(content)
    if file_size > settings.max_file_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size} > {settings.max_file_size}",
        )

    # Save to knowledge base directory
    kb_dir = Path(settings.knowledge_base_dir)
    kb_dir.mkdir(parents=True, exist_ok=True)

    file_path = kb_dir / file.filename

    # Handle duplicate filenames
    counter = 1
    original_path = file_path
    while file_path.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        file_path = kb_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    # Write file
    with open(file_path, "wb") as f:
        f.write(content)

    # Index document
    try:
        doc_metadata = await rag_engine.upload_document(str(file_path))
    except Exception as e:
        # Clean up file if indexing fails
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to index document: {str(e)}")

    return KBUploadResponse(
        success=True,
        document=KBDocument(**doc_metadata),
        message=f"Document uploaded successfully: {file.filename}",
    )


@router.get("/upload/{task_id}/progress", response_model=KBUploadProgress)
async def get_upload_progress(
    task_id: str,
):
    """
    Get upload task progress.

    Args:
        task_id: Upload task ID

    Returns:
        Upload progress information
    """
    progress_manager = get_upload_progress_manager()
    task = progress_manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    # Convert to API model
    return KBUploadProgress(
        task_id=task.task_id,
        filename=task.filename,
        status=KBUploadStatus(task.status.value),
        progress=task.progress,
        message=task.message,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        document=None,
    )


@router.get("/documents", response_model=KBDocumentListResponse)
async def list_documents(
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    List all documents in the knowledge base.
    """
    documents = await rag_engine.list_documents()

    return KBDocumentListResponse(
        documents=[KBDocument(**doc) for doc in documents],
        total=len(documents),
    )


@router.delete("/documents/{doc_id}", response_model=KBDeleteResponse)
async def delete_document(
    doc_id: str,
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Delete a document from the knowledge base.
    """
    try:
        # Get document info before deleting
        documents = await rag_engine.list_documents()
        doc_info = None
        for doc in documents:
            if doc["id"] == doc_id:
                doc_info = doc
                break

        if not doc_info:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

        # Delete from RAG engine
        await rag_engine.delete_document(doc_id)

        # Delete source file
        file_path = Path(doc_info["file_path"])
        if file_path.exists():
            file_path.unlink()

        return KBDeleteResponse(
            success=True,
            message=f"Document deleted successfully: {doc_info['filename']}",
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@router.get("/stats", response_model=KBStats)
async def get_stats(
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Get knowledge base statistics.
    """
    stats = rag_engine.get_stats()
    return KBStats(**stats)


@router.post("/delete-all")
async def delete_all_documents(
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Delete all documents from knowledge base.
    """
    try:
        # Get all documents from metadata
        documents = await rag_engine.list_documents()

        # Delete each document file from metadata
        for doc_info in documents:
            file_path = Path(doc_info["file_path"])
            if file_path.exists():
                file_path.unlink()

        # Also clean up any orphaned files in KB directory
        kb_dir = Path(settings.knowledge_base_dir)
        for file_path in kb_dir.glob("*"):
            if file_path.suffix in ['.txt', '.md', '.pdf', '.docx']:
                file_path.unlink(missing_ok=True)

        # Clear metadata
        rag_engine._documents.clear()
        rag_engine._save_documents_metadata()

        return {"success": True, "message": f"Deleted {len(documents)} documents"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete all documents: {str(e)}")


# Batch upload endpoints
@router.post("/upload/batch/check", response_model=KBBatchUploadResponse)
async def check_batch_upload(
    request: KBBatchUploadRequest,
):
    """
    Check if batch upload requires authorization.

    Checks total file count and total size.
    Returns authorization requirements if thresholds are exceeded.
    """
    # Calculate thresholds
    total_size_mb = request.total_size / (1024 * 1024)
    threshold_mb = (settings.large_file_threshold * settings.max_batch_files) / (1024 * 1024)

    # Check if exceeds file count limit
    if request.file_count > settings.max_batch_files:
        return KBBatchUploadResponse(
            requires_authorization=False,
            file_count=request.file_count,
            total_size_mb=total_size_mb,
            threshold_mb=0,
            message=f"Too many files: {request.file_count} exceeds maximum {settings.max_batch_files}",
        )

    # Check if exceeds size threshold
    if request.total_size > settings.large_file_threshold * settings.max_batch_files:
        if request.confirm:
            # User has confirmed, generate upload token
            token = _generate_upload_token()
            return KBBatchUploadResponse(
                requires_authorization=True,
                file_count=request.file_count,
                total_size_mb=total_size_mb,
                threshold_mb=threshold_mb,
                message=f"Batch upload authorized. Token valid for 10 minutes.",
                upload_token=token,
            )
        else:
            return KBBatchUploadResponse(
                requires_authorization=True,
                file_count=request.file_count,
                total_size_mb=total_size_mb,
                threshold_mb=threshold_mb,
                message=f"Batch size {total_size_mb:.1f}MB exceeds threshold {threshold_mb:.1f}MB. Please confirm to proceed.",
            )

    # Batch is within limits
    return KBBatchUploadResponse(
        requires_authorization=False,
        file_count=request.file_count,
        total_size_mb=total_size_mb,
        threshold_mb=threshold_mb,
        message="Batch upload is within normal limits.",
    )


@router.post("/upload/batch", response_model=KBUploadTaskResponse)
async def upload_batch(
    background_tasks: BackgroundTasks,
    upload_token: Optional[str] = None,
    files: list[UploadFile] = File(...),
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Upload multiple files to the knowledge base.

    Supports batch upload with up to max_batch_files (default: 20).
    Large batches (>100MB total or >20 files) require authorization via /upload/batch/check.

    Parameters:
    - upload_token: Required for large batches (from /upload/batch/check)
    - files: List of files to upload

    Returns:
        Task response with task ID for progress tracking.
    """
    # Generate batch task ID
    batch_task_id = str(uuid.uuid4())[:16]
    progress_manager = get_upload_progress_manager()

    # Calculate total size
    total_size = 0
    for file in files:
        content = await file.read()
        total_size += len(content)
        # Rewind for later use
        await file.seek(0)

    # Check batch limits
    if len(files) > settings.max_batch_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files: {len(files)} exceeds maximum {settings.max_batch_files}",
        )

    # Check authorization for large batches
    batch_threshold = settings.large_file_threshold * settings.max_batch_files
    if total_size > batch_threshold:
        if not upload_token:
            raise HTTPException(
                status_code=403,
                detail=f"Batch size {total_size / (1024 * 1024):.1f}MB exceeds threshold {batch_threshold / (1024 * 1024):.1f}MB. "
                       f"Please call /upload/batch/check to authorize.",
            )
        if not _validate_upload_token(upload_token):
            raise HTTPException(
                status_code=403,
                detail="Invalid or expired batch upload token",
            )
        del _upload_tokens[upload_token]

    # Create main batch task
    progress_manager.create_task(batch_task_id, f"batch_upload_{batch_task_id}")
    progress_manager.update_task(
        batch_task_id,
        status=UploadStatus.VALIDATING,
        progress=0,
        message=f"Validating {len(files)} files...",
    )

    # Process each file
    successful = 0
    failed = 0
    failed_files = []

    for idx, file in enumerate(files):
        try:
            content = await file.read()

            # Validate file type using intelligent detection
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in settings.allowed_file_types:
                # Try intelligent detection
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = Path(tmp.name)

                try:
                    is_allowed, detected_type, reason = FileDetector.is_file_allowed(
                        tmp_path,
                        settings.allowed_file_types,
                        content
                    )

                    if not is_allowed:
                        failed += 1
                        failed_files.append({
                            "filename": file.filename,
                            "path": str(file.filename),
                            "reason": reason
                        })
                        continue
                finally:
                    tmp_path.unlink(missing_ok=True)
            else:
                # Valid extension, proceed
                pass

            # Validate individual file size
            if len(content) > settings.max_file_size:
                failed += 1
                failed_files.append({
                    "filename": file.filename,
                    "path": str(file.filename),
                    "reason": f"File too large: {len(content) / (1024 * 1024):.1f}MB"
                })
                continue

            # Check for large file authorization
            if len(content) > settings.large_file_threshold:
                if not upload_token or not _validate_upload_token(upload_token):
                    failed += 1
                    failed_files.append({
                        "filename": file.filename,
                        "path": str(file.filename),
                        "reason": "Large file requires authorization"
                    })
                    continue

            # Upload file
            file_task_id = str(uuid.uuid4())[:16]

            # Save to knowledge base directory
            kb_dir = Path(settings.knowledge_base_dir)
            kb_dir.mkdir(parents=True, exist_ok=True)

            file_path = kb_dir / file.filename

            # Handle duplicate filenames
            counter = 1
            original_path = file_path
            while file_path.exists():
                stem = original_path.stem
                suffix = original_path.suffix
                file_path = kb_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            # Write file
            with open(file_path, "wb") as f:
                f.write(content)

            # Index document
            try:
                doc_metadata = await rag_engine.upload_document(str(file_path))
                successful += 1
            except Exception as e:
                failed += 1
                failed_files.append({
                    "filename": file.filename,
                    "path": str(file.filename),
                    "reason": f"Indexing failed: {str(e)}"
                })
                # Clean up file on failure
                file_path.unlink(missing_ok=True)

            # Update progress
            progress = int(((idx + 1) / len(files)) * 100)
            progress_manager.update_task(
                batch_task_id,
                status=UploadStatus.INDEXING,
                progress=progress,
                message=f"Processed {idx + 1}/{len(files)} files",
            )

        except Exception as e:
            failed += 1
            failed_files.append({
                "filename": file.filename,
                "path": str(file.filename),
                "reason": f"Upload error: {str(e)}"
            })

    # Update final status
    progress_manager.update_task(
        batch_task_id,
        status=UploadStatus.COMPLETED if failed == 0 else UploadStatus.FAILED,
        progress=100,
        message=f"Batch upload completed: {successful} successful, {failed} failed",
    )

    return KBUploadTaskResponse(
        success=True,
        task_id=batch_task_id,
        filename=f"batch_upload_{batch_task_id}",
        message=f"Batch upload completed: {successful} succeeded, {failed} failed",
    )


@router.post("/upload/folder")
async def upload_folder(
    background_tasks: BackgroundTasks,
    folder: UploadFile = File(..., description="Folder to upload (as ZIP archive)"),
    rag_engine: RAGEngine = Depends(get_rag_engine),
):
    """
    Upload a folder's contents to the knowledge base.

    Uploads all supported files from a folder (provided as ZIP archive).
    Recursively processes files up to max_folder_depth (default: 5).
    Skips unsupported file types.

    Parameters:
    - folder: ZIP archive containing the folder

    Returns:
        Task response with task ID for progress tracking.
    """
    import zipfile
    import tempfile

    # Generate task ID
    batch_task_id = str(uuid.uuid4())[:16]
    progress_manager = get_upload_progress_manager()

    progress_manager.create_task(batch_task_id, folder.filename)
    progress_manager.update_task(
        batch_task_id,
        status=UploadStatus.VALIDATING,
        progress=0,
        message="Extracting and validating folder...",
    )

    try:
        # Save uploaded ZIP temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
            tmp_zip.write(await folder.read())
            tmp_zip_path = Path(tmp_zip.name)

        # Extract ZIP
        extract_dir = Path(tmp_zip_path).parent / f"extract_{batch_task_id}"
        extract_dir.mkdir(exist_ok=True)

        with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # Clean up ZIP
        tmp_zip_path.unlink()

        # Collect all files
        all_files = []
        for root, dirs, files in os.walk(extract_dir):
            # Limit depth
            depth = len(Path(root).relative_to(extract_dir).parts)
            if depth > settings.max_folder_depth:
                continue

            for file in files:
                file_path = Path(root) / file
                if file_path.is_file():
                    all_files.append(file_path)

        # Limit number of files
        if len(all_files) > settings.max_batch_files:
            # Clean up
            import shutil
            shutil.rmtree(extract_dir, ignore_errors=True)

            raise HTTPException(
                status_code=400,
                detail=f"Too many files in folder: {len(all_files)} exceeds maximum {settings.max_batch_files}",
            )

        # Process files
        successful = 0
        failed = 0
        failed_files = []

        for idx, file_path in enumerate(all_files):
            try:
                # Detect file type intelligently
                is_allowed, detected_type, reason = FileDetector.is_file_allowed(
                    file_path,
                    settings.allowed_file_types
                )

                if not is_allowed:
                    failed += 1
                    failed_files.append({
                        "filename": file_path.name,
                        "path": str(file_path.relative_to(extract_dir)),
                        "reason": reason
                    })
                    continue

                # Check file size
                file_size = file_path.stat().st_size
                if file_size > settings.max_file_size:
                    failed += 1
                    failed_files.append({
                        "filename": file_path.name,
                        "path": str(file_path.relative_to(extract_dir)),
                        "reason": f"File too large: {file_size / (1024 * 1024):.1f}MB"
                    })
                    continue

                # Copy to KB directory and index
                kb_dir = Path(settings.knowledge_base_dir)
                kb_dir.mkdir(parents=True, exist_ok=True)

                # Preserve relative path structure
                rel_path = file_path.relative_to(extract_dir)
                dest_path = kb_dir / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Copy file
                import shutil
                shutil.copy2(file_path, dest_path)

                # Index document
                try:
                    await rag_engine.upload_document(str(dest_path))
                    successful += 1
                except Exception as e:
                    failed += 1
                    failed_files.append({
                        "filename": file_path.name,
                        "path": str(file_path.relative_to(extract_dir)),
                        "reason": f"Indexing failed: {str(e)}"
                    })
                    # Clean up
                    dest_path.unlink(missing_ok=True)

                # Update progress
                progress = int(((idx + 1) / len(all_files)) * 100)
                progress_manager.update_task(
                    batch_task_id,
                    status=UploadStatus.INDEXING,
                    progress=progress,
                    message=f"Processed {idx + 1}/{len(all_files)} files",
                )

            except Exception as e:
                failed += 1
                failed_files.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "reason": f"Processing error: {str(e)}"
                })

        # Clean up extraction directory
        import shutil
        shutil.rmtree(extract_dir, ignore_errors=True)

        # Final status
        progress_manager.update_task(
            batch_task_id,
            status=UploadStatus.COMPLETED if failed == 0 else UploadStatus.FAILED,
            progress=100,
            message=f"Folder upload completed: {successful} succeeded, {failed} failed",
        )

        return KBUploadTaskResponse(
            success=True,
            task_id=batch_task_id,
            filename=folder.filename,
            message=f"Folder upload completed: {successful} succeeded, {failed} failed",
        )

    except zipfile.BadZipFile:
        progress_manager.update_task(
            batch_task_id,
            status=UploadStatus.FAILED,
            message="Validation failed",
            error="Invalid ZIP archive",
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid ZIP archive. Please upload a valid ZIP file containing the folder.",
        )
    except Exception as e:
        progress_manager.update_task(
            batch_task_id,
            status=UploadStatus.FAILED,
            message="Upload failed",
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Folder upload failed: {str(e)}",
        )
