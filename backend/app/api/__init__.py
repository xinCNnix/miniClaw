"""
API Module - FastAPI Routes

This module contains all API route handlers.
"""

from .chat import router as chat_router
from .files import router as files_router
from .sessions import router as sessions_router
from . import knowledge_base
from . import debug_config

__all__ = [
    "chat_router",
    "files_router",
    "sessions_router",
    "knowledge_base",
    "debug_config",
]
