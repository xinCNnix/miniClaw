"""Utility functions for pattern memory component.

This module provides singleton instances and helper functions.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from sentence_transformers import SentenceTransformer

from app.config import get_settings
from .logging_config import setup_logger

if TYPE_CHECKING:
    from .memory import PatternMemory

logger = setup_logger(__name__)

# Global singletons
_embedder: Optional[SentenceTransformer] = None
_pattern_memory: Optional["PatternMemory"] = None


def get_embedder(
    model_name: str | None = None,
) -> SentenceTransformer:
    """Get or create SentenceTransformer singleton.

    This function implements the singleton pattern for the SentenceTransformer
    embedder, ensuring that only one instance is created and reused across
    the application. This improves performance by avoiding repeated model loading.

    Args:
        model_name: Optional model name. If None, uses the default from settings.
                    The default is typically "all-MiniLM-L6-v2".

    Returns:
        SentenceTransformer: The singleton embedder instance.

    Examples:
        >>> embedder = get_embedder()
        >>> embedding = embedder.encode("Hello world")

        >>> # Use custom model
        >>> embedder = get_embedder("all-mpnet-base-v2")
    """
    global _embedder

    if _embedder is None:
        settings = get_settings()
        model_name = model_name or settings.pattern_embedder_model_name

        logger.info(f"Loading sentence transformer: {model_name}")
        _embedder = SentenceTransformer(model_name)
        logger.info("Sentence transformer loaded successfully")

    return _embedder


def get_pattern_memory():
    """Get or create PatternMemory singleton.

    This function implements the singleton pattern for PatternMemory,
    ensuring that only one instance is created and reused across the application.
    This maintains consistency in pattern storage and retrieval.

    Returns:
        PatternMemory: The singleton pattern memory instance.

    Examples:
        >>> memory = get_pattern_memory()
        >>> patterns = memory.get_top_patterns("API error", top_k=3)
    """
    global _pattern_memory

    if _pattern_memory is None:
        from .memory import PatternMemory

        settings = get_settings()

        logger.info("Initializing PatternMemory")
        _pattern_memory = PatternMemory(
            data_dir=settings.pattern_storage_path.parent,
        )
        logger.info("PatternMemory initialized")

    return _pattern_memory


def get_pattern_extractor():
    """Get or create PatternExtractor singleton.

    This function creates a new PatternExtractor instance. Unlike get_embedder
    and get_pattern_memory, this does not implement a singleton pattern,
    as each extractor may need different LLM configurations.

    Returns:
        PatternExtractor: A new pattern extractor instance.

    Examples:
        >>> extractor = get_pattern_extractor()
        >>> pattern = await extractor.extract(
        ...     situation="API timeout",
        ...     outcome="Failed after 30s",
        ...     fix="Increased timeout to 60s"
        ... )
    """
    from .extractor import PatternExtractor

    logger.info("Creating PatternExtractor")
    return PatternExtractor()


def setup_pattern_memory(
    storage_path: Path | None = None,
) -> None:
    """Initialize pattern memory system.

    This function ensures the data directory exists and prepares
    the pattern memory system for use. It should be called before
    using any pattern memory functionality.

    Args:
        storage_path: Optional custom storage path. If None, uses the
                     default from settings (typically "data/patterns.json").

    Examples:
        >>> setup_pattern_memory()
        >>> memory = get_pattern_memory()

        >>> # Use custom path
        >>> setup_pattern_memory(storage_path=Path("custom/patterns.json"))
    """
    settings = get_settings()

    # Use custom path or default
    storage_path = storage_path or settings.pattern_storage_path

    # Ensure data directory exists
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Pattern Memory storage path: {storage_path}")
    logger.info("Pattern Memory system ready")


def reset_pattern_memory() -> None:
    """Reset pattern memory singletons.

    This function clears all cached singletons, forcing
    reinitialization on next access. This is useful for:
    - Testing: Isolate test cases
    - Configuration changes: Apply new settings immediately
    - Resource cleanup: Free memory when shutting down

    Examples:
        >>> # Before test
        >>> reset_pattern_memory()
        >>> memory = get_pattern_memory()
        >>> # ... run test ...
        >>> # After test
        >>> reset_pattern_memory()
    """
    global _embedder, _pattern_memory

    _embedder = None
    _pattern_memory = None

    logger.info("Pattern Memory singletons reset")
