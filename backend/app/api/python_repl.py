"""
Python REPL API - Execution control and monitoring

This module provides endpoints for controlling Python REPL execution,
including stopping execution and getting status updates.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.tools.python_repl import python_repl_tool
from app.config import settings


router = APIRouter(tags=["python_repl"])


class StopExecutionResponse(BaseModel):
    """Response model for stop execution request."""
    success: bool
    message: str


class ExecutionStatusResponse(BaseModel):
    """Response model for execution status."""
    is_running: bool
    operations: int
    elapsed: float
    mode: str


class SystemResourcesResponse(BaseModel):
    """Response model for system resources."""
    total_memory_mb: float
    available_memory_mb: float
    used_memory_mb: float
    memory_usage_percent: float
    cpu_percent: float


@router.post("/stop", response_model=StopExecutionResponse)
async def stop_execution():
    """
    Stop the current Python REPL execution.

    This endpoint requests the current python_repl execution to stop.
    It sets a flag that the monitoring thread checks periodically.

    ## Response Example
    ```json
    {
      "success": true,
      "message": "Stop request sent"
    }
    ```
    """
    try:
        python_repl_tool.stop_execution()
        return StopExecutionResponse(
            success=True,
            message="Stop request sent"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop execution: {str(e)}"
        )


@router.get("/status", response_model=ExecutionStatusResponse)
async def get_execution_status():
    """
    Get the current Python REPL execution status.

    Returns statistics about the current or last execution,
    including operation count, elapsed time, and running state.

    ## Response Example
    ```json
    {
      "is_running": false,
      "operations": 15234,
      "elapsed": 12.5,
      "mode": "standard"
    }
    ```
    """
    try:
        stats = python_repl_tool.get_execution_stats()
        return ExecutionStatusResponse(
            is_running=stats["is_running"],
            operations=stats["operations"],
            elapsed=stats["elapsed"],
            mode=settings.python_execution_mode,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )


@router.get("/resources", response_model=SystemResourcesResponse)
async def get_system_resources():
    """
    Get current system resource usage.

    Returns information about available memory and CPU usage,
    useful for determining if the system can handle a large task.

    ## Response Example
    ```json
    {
      "total_memory_mb": 16384.0,
      "available_memory_mb": 8192.0,
      "used_memory_mb": 8192.0,
      "memory_usage_percent": 50.0,
      "cpu_percent": 15.2
    }
    ```
    """
    try:
        import psutil

        # Memory info
        memory = psutil.virtual_memory()
        total_mb = memory.total / 1024 / 1024
        available_mb = memory.available / 1024 / 1024
        used_mb = memory.used / 1024 / 1024
        percent = memory.percent

        # CPU info
        cpu_percent = psutil.cpu_percent(interval=1)

        return SystemResourcesResponse(
            total_memory_mb=round(total_mb, 2),
            available_memory_mb=round(available_mb, 2),
            used_memory_mb=round(used_mb, 2),
            memory_usage_percent=round(percent, 1),
            cpu_percent=round(cpu_percent, 1),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get system resources: {str(e)}"
        )


@router.get("/config")
async def get_python_config():
    """
    Get the current Python REPL configuration.

    Returns information about the current execution mode,
    timeout, memory limits, and operation limits.

    ## Response Example
    ```json
    {
      "mode": "standard",
      "timeout": 300,
      "memory_limit_mb": 4096,
      "max_operations": 10000000,
      "monitor_interval": 5,
      "warning_threshold": 0.7
    }
    ```
    """
    try:
        import psutil

        config = python_repl_tool._get_execution_config(settings.python_execution_mode)

        return {
            "mode": config["mode"],
            "timeout": config["timeout"],
            "memory_limit_mb": round(config["memory_limit"] / 1024 / 1024, 2),
            "max_operations": config["max_operations"],
            "monitor_interval": settings.python_monitor_interval,
            "warning_threshold": settings.python_warning_threshold,
            "allowed_dirs": [str(d) for d in python_repl_tool._allowed_dirs],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get config: {str(e)}"
        )


@router.post("/update_dirs")
async def update_allowed_dirs(dirs: list[str]):
    """
    Update the list of allowed directories for Python REPL file I/O.

    This endpoint reloads the allowed directories from settings,
    allowing the user to add new directories without restarting the server.

    ## Request Example
    ```json
    {
      "dirs": ["C:/Users/YourName/Documents", "D:/Workspace"]
    }
    ```

    ## Response Example
    ```json
    {
      "success": true,
      "allowed_dirs": [".", "C:/Users/YourName/Documents", "D:/Workspace"]
    }
    ```
    """
    try:
        # Update settings (temporary, not persisted)
        settings.allowed_write_dirs = dirs

        # Update python_repl tool
        python_repl_tool._update_allowed_dirs()

        return {
            "success": True,
            "allowed_dirs": [str(d) for d in python_repl_tool._allowed_dirs],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update directories: {str(e)}"
        )
