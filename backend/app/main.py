"""
FastAPI Application Entry Point

This is the main entry point for the miniClaw backend API.
"""

import sys
sys.dont_write_bytecode = True

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
import asyncio
import logging
import re
from typing import Callable

from app.config import get_settings
from app.logging_config import setup_logging
from app.api import chat_router, files_router, sessions_router
from app.api import config as config_api
from app.api import python_repl as python_repl_api
from app.api import knowledge_base
from app.api import skills as skills_api
from app.api import memory as memory_api
from app.api import websocket as websocket_api
from app.api import memory_sync as memory_sync_api
from app.api import embedding as embedding_api
from app.api import media as media_api
from app.api import wiki as wiki_api
from app.api import dream as dream_api
from app.api import settings as settings_api


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
settings = get_settings()

# Setup detailed logging (must be after settings initialization)
setup_logging()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A lightweight, transparent AI Agent system",
    docs_url="/docs",
    redoc_url="/redoc",
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
def _sanitize_error_message(error_msg: str) -> str:
    """
    Remove sensitive information (API keys, passwords, etc.) from error messages.

    This prevents sensitive data from being exposed in error responses even in debug mode.
    """
    # Remove common API key patterns
    patterns = [
        # Generic patterns
        r'(api[_-]?key|token|password|secret|authorization)["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{10,}',
        # OpenAI API keys
        r'sk-[a-zA-Z0-9_-]{20,}',
        # Anthropic API keys
        r'sk-ant-[a-zA-Z0-9_-]{20,}',
        # Bearer tokens
        r'Bearer\s+[a-zA-Z0-9_-]{20,}',
        # URL with API key
        r'key=[a-zA-Z0-9_-]{10,}(&|$)',
    ]
    for pattern in patterns:
        error_msg = re.sub(pattern, '[REDACTED]', error_msg, flags=re.IGNORECASE)
    return error_msg


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Sanitize error message to remove sensitive information
    error_msg = str(exc) if settings.debug else "An error occurred"
    error_msg = _sanitize_error_message(error_msg)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "message": error_msg,
        },
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    """Run application startup tasks."""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"CORS Origins: {settings.cors_origins}")

    # Create necessary directories
    import os
    from pathlib import Path

    dirs_to_create = [
        settings.data_dir,
        settings.knowledge_base_dir,
        settings.sessions_dir,
        settings.skills_dir,
        settings.vector_store_dir,
        settings.workspace_dir,
    ]

    for dir_path in dirs_to_create:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directory exists: {dir_path}")

    # Generate SKILLS_SNAPSHOT.md
    try:
        from app.skills.bootstrap import bootstrap_skills

        bootstrap = bootstrap_skills()
        bootstrap.scan_skills()
        snapshot_path = bootstrap.save_snapshot()
        logger.info(f"Generated SKILLS_SNAPSHOT.md at {snapshot_path}")
        logger.info(f"Found {bootstrap.get_skill_count()} skills: {', '.join(bootstrap.get_skill_names())}")
    except Exception as e:
        logger.warning(f"Failed to generate SKILLS_SNAPSHOT.md: {e}")

    # Recover MediaRegistry from existing output files
    try:
        from app.core.media import get_registry
        registry = get_registry()
        recovered = registry.register_existing_files()
        logger.info(f"MediaRegistry recovery: {recovered} files re-registered")
    except Exception as e:
        logger.warning(f"MediaRegistry recovery failed: {e}")

    # Initialize agent (warmup)
    try:
        from app.tools import CORE_TOOLS
        from app.core.llm import get_agent_manager

        logger.info(f"Loaded {len(CORE_TOOLS)} tools")

        # Warm up agent
        agent_manager = get_agent_manager()
        logger.info("Agent manager initialized successfully")

    except Exception as e:
        logger.warning(f"Agent warmup failed (will retry on first request): {e}")

    # Warm up embedding model (async, non-blocking)
    try:
        from app.core.embedding_manager import get_embedding_manager
        embedding_manager = get_embedding_manager()

        if settings.embedding_warmup_enabled:
            # Create background task for warmup
            asyncio.create_task(_warmup_embedding_model(embedding_manager, settings.embedding_warmup_timeout))
            logger.info("Embedding model warmup task started (running in background)")
        else:
            logger.info("Embedding model warmup disabled")
    except Exception as e:
        logger.warning(f"Failed to start embedding warmup: {e}")

    # Start MemoryJanitor for periodic decay/cleanup (红线4)
    try:
        if getattr(settings, "memory_decay_cron_hours", 0) > 0:
            from app.memory.engine.cron import get_memory_janitor
            janitor = get_memory_janitor()
            interval = settings.memory_decay_cron_hours * 3600
            asyncio.create_task(janitor.run_periodically(interval))
            logger.info(
                f"MemoryJanitor started (interval={settings.memory_decay_cron_hours}h)"
            )
        else:
            logger.info("MemoryJanitor disabled (memory_decay_cron_hours=0)")
    except Exception as e:
        logger.warning(f"Failed to start MemoryJanitor: {e}")

    # 启动 Watchdog 运行监控服务
    try:
        from app.config import get_settings as _get_ws
        _ws = _get_ws()
        if getattr(_ws, "enable_watchdog", True):
            from app.core.watchdog import get_watchdog_service
            _wd_service = get_watchdog_service()
            await _wd_service.start()
            logger.info("[Watchdog] 服务已启动")
        else:
            logger.info("[Watchdog] 已通过配置禁用")
    except Exception as e:
        logger.warning(f"[Watchdog] 启动失败: {e}")

    # Dream module status + auto-scheduler (Phase 2)
    if getattr(settings, "enable_dream", False):
        schedule = getattr(settings, "dream_schedule", "")
        if schedule:
            max_samples = getattr(settings, "dream_max_samples", 3)
            executor_mode = getattr(settings, "dream_executor_mode", "simulated")
            asyncio.create_task(
                _dream_scheduler_loop(schedule, max_samples, executor_mode)
            )
            logger.info(
                f"[Dream] Auto-scheduler started (schedule={schedule}, "
                f"max_samples={max_samples}, mode={executor_mode})"
            )
        else:
            logger.info("[Dream] Module enabled, manual trigger at POST /api/dream/trigger")
    else:
        logger.info("[Dream] Module disabled")


def _cron_field_matches(field: str, value: int, lo: int, hi: int) -> bool:
    """Check if a cron field matches a value. Supports *, */N, and specific numbers."""
    if field == "*":
        return True
    if field.startswith("*/"):
        step = int(field[2:])
        return value % step == 0
    # Comma-separated or range values
    for part in field.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            if int(a) <= value <= int(b):
                return True
        elif int(part) == value:
            return True
    return False


def _next_cron_time(cron_expr: str) -> "datetime.datetime":
    """Calculate next fire time from a 5-field cron expression."""
    import datetime as _dt

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Expected 5-field cron, got: {cron_expr}")

    minute_f, hour_f, dom_f, month_f, dow_f = parts
    now = _dt.datetime.now()
    candidate = now.replace(second=0, microsecond=0) + _dt.timedelta(minutes=1)

    # Scan forward (max 1 year)
    for _ in range(525960):
        if (
            _cron_field_matches(minute_f, candidate.minute, 0, 59)
            and _cron_field_matches(hour_f, candidate.hour, 0, 23)
            and _cron_field_matches(dom_f, candidate.day, 1, 31)
            and _cron_field_matches(month_f, candidate.month, 1, 12)
            and _cron_field_matches(dow_f, candidate.weekday(), 0, 6)
        ):
            return candidate
        candidate += _dt.timedelta(minutes=1)

    return now + _dt.timedelta(hours=24)


async def _dream_scheduler_loop(
    schedule: str, max_samples: int, executor_mode: str
) -> None:
    """Background task that runs Dream sessions on a cron schedule."""
    import datetime as _dt

    while True:
        try:
            next_run = _next_cron_time(schedule)
        except Exception as e:
            logger.error(f"[Dream Scheduler] Invalid schedule '{schedule}': {e}")
            return

        now = _dt.datetime.now()
        wait = max(0, (next_run - now).total_seconds())
        logger.info(f"[Dream Scheduler] Next run at {next_run} (in {wait:.0f}s)")
        await asyncio.sleep(wait)

        try:
            from app.core.dream import run_dream

            logger.info("[Dream Scheduler] Starting scheduled Dream session")
            await run_dream(
                mode="nightly",
                max_samples=max_samples,
                executor_mode=executor_mode,
            )
            logger.info("[Dream Scheduler] Session completed")
        except Exception as e:
            logger.error(f"[Dream Scheduler] Session failed: {e}", exc_info=True)

        # Minimum gap between runs
        await asyncio.sleep(60)


async def _warmup_embedding_model(embedding_manager, timeout: int):
    """
    Background task to warm up the embedding model.

    This runs asynchronously after startup and does not block the application.

    Args:
        embedding_manager: EmbeddingModelManager instance
        timeout: Maximum time to wait for model loading (seconds)
    """
    try:
        logger.info(f"Starting embedding model warmup (timeout: {timeout}s)...")
        success = await embedding_manager.warmup(timeout=timeout)
        if success:
            logger.info("[OK] Embedding model warmed up successfully")
        else:
            logger.warning("[FAILED] Embedding model warmup failed or timed out (requests will skip semantic search)")
    except Exception as e:
        logger.error(f"Embedding warmup error: {e}", exc_info=True)


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run application shutdown tasks."""
    # 停止 Watchdog 服务
    try:
        from app.core.watchdog import get_watchdog_service
        service = get_watchdog_service()
        if service.is_running:
            await service.stop()
    except Exception as e:
        logger.warning(f"[Watchdog] 停止失败: {e}")

    logger.info(f"Shutting down {settings.app_name}")


# Root endpoint
@app.get("/")
async def root():
    """
    Root endpoint - API information.

    Returns basic API information and available endpoints.
    """
    try:
        from app.core.llm import _agent_manager as _llm_mgr_agent
        agent_ready = _llm_mgr_agent is not None
    except Exception:
        agent_ready = False

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "A lightweight, transparent AI Agent system",
        "status": "running",
        "agent_ready": agent_ready,
        "llm_provider": settings.llm_provider,
        "endpoints": {
            "chat": "/api/chat",
            "files": "/api/files",
            "sessions": "/api/sessions",
            "docs": "/docs",
            "health": "/health",
        },
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
        },
    }


# Health check endpoint
@app.get("/health")
async def health():
    """
    Health check endpoint.

    Returns API health status and component status.
    """
    try:
        from app.core.llm import _agent_manager as _llm_mgr_agent
        agent_initialized = _llm_mgr_agent is not None
    except Exception:
        agent_initialized = False

    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "llm_provider": settings.llm_provider,
        "agent_initialized": agent_initialized,
    }


# Include routers
app.include_router(chat_router, prefix="/api/chat")
app.include_router(files_router, prefix="/api/files")
app.include_router(sessions_router, prefix="/api/sessions")
app.include_router(config_api.router, prefix="/api/config")
app.include_router(python_repl_api.router, prefix="/api/python_repl")
app.include_router(knowledge_base.router, prefix="/api/kb")
app.include_router(skills_api.router, prefix="/api/skills")
app.include_router(memory_api.router, prefix="/api")
app.include_router(memory_sync_api.router)
app.include_router(websocket_api.router, prefix="/api")
app.include_router(embedding_api.router, prefix="/api/embedding")
app.include_router(media_api.router, prefix="/api/media")
app.include_router(wiki_api.router, prefix="/api")
app.include_router(dream_api.router, prefix="/api/dream")
app.include_router(settings_api.router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
