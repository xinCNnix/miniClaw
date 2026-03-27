"""
FastAPI Application Entry Point

This is the main entry point for the miniClaw backend API.
"""

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
from app.api import chat_router, files_router, sessions_router, debug_config
from app.api import config as config_api
from app.api import python_repl as python_repl_api
from app.api import knowledge_base
from app.api import skills as skills_api
from app.api import memory as memory_api
from app.api import websocket as websocket_api
from app.api import memory_sync as memory_sync_api
from app.api import embedding as embedding_api


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

    # Initialize DI container
    try:
        from app.core.container import setup_container

        container = setup_container()
        logger.info("Service container initialized successfully")
        logger.info("Registered services: LLMProvider, EmbeddingProvider, VectorStore, MessageHistoryStore, AgentManager")
    except Exception as e:
        logger.error(f"Failed to initialize service container: {e}", exc_info=True)
        logger.warning("Application will continue with direct instantiation")

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

    # Initialize agent (warmup)
    try:
        from app.tools import CORE_TOOLS
        from app.api.chat import get_agent_manager

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
    logger.info(f"Shutting down {settings.app_name}")

    # Reset DI container
    try:
        from app.core.container import get_container

        container = get_container()
        container.reset()
        logger.info("Service container reset successfully")
    except Exception as e:
        logger.warning(f"Failed to reset service container: {e}")


# Root endpoint
@app.get("/")
async def root():
    """
    Root endpoint - API information.

    Returns basic API information and available endpoints.
    """
    try:
        from app.api.chat import _agent_manager
        agent_ready = _agent_manager is not None
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
        from app.api.chat import _agent_manager
        agent_initialized = _agent_manager is not None
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
app.include_router(debug_config.router, prefix="/api")  # Debug endpoint


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
