"""
Dependency injection container for miniClaw.

Provides lightweight service container with lazy initialization
and singleton management. Enables loose coupling and testability.
"""

from typing import Dict, Callable, TypeVar, Any, Optional
import logging

from app.core.interfaces import (
    LLMProvider,
    EmbeddingProvider,
    VectorStore,
    MessageHistoryStore,
    ToolRegistry,
    SettingsProvider,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceContainer:
    """
    Lightweight dependency injection container.

    Manages service registration and lazy initialization.
    Supports both factory functions and singleton instances.
    Uses type-based lookup for service retrieval.

    Example:
        >>> container = ServiceContainer()
        >>> container.register(LLMProvider, lambda: ChatOpenAI(...))
        >>> llm = container.get(LLMProvider)
        >>> isinstance(llm, LLMProvider)
        True
    """

    def __init__(self) -> None:
        """Initialize empty service container."""
        self._factories: Dict[type, Callable[[], Any]] = {}
        self._singletons: Dict[type, Any] = {}
        self._aliases: Dict[str, type] = {}

    def register(
        self,
        service_type: type[T],
        factory: Callable[[], T],
        alias: str | None = None,
    ) -> None:
        """
        Register a factory function for a service type.

        The factory will be called lazily on first access.
        Subsequent accesses return the same instance (singleton).

        Args:
            service_type: Type protocol or class to register
            factory: Callable that creates service instance
            alias: Optional string alias for retrieval

        Raises:
            ValueError: If service_type already registered

        Example:
            >>> container.register(LLMProvider, lambda: ChatOpenAI(...))
            >>> container.register(EmbeddingProvider, lambda: OpenAIEmbeddings(...))
        """
        if service_type in self._factories:
            raise ValueError(f"Service {service_type.__name__} already registered")

        self._factories[service_type] = factory
        logger.debug(f"Registered factory for {service_type.__name__}")

        if alias:
            self._aliases[alias] = service_type
            logger.debug(f"Registered alias '{alias}' for {service_type.__name__}")

    def register_singleton(
        self,
        service_type: type[T],
        instance: T,
        alias: str | None = None,
    ) -> None:
        """
        Register a pre-created singleton instance.

        Use this for services that are already instantiated
        or require special initialization logic.

        Args:
            service_type: Type protocol or class
            instance: Pre-created service instance
            alias: Optional string alias for retrieval

        Raises:
            ValueError: If service_type already registered

        Example:
            >>> llm = ChatOpenAI(...)
            >>> container.register_singleton(LLMProvider, llm)
        """
        if service_type in self._factories or service_type in self._singletons:
            raise ValueError(f"Service {service_type.__name__} already registered")

        self._singletons[service_type] = instance
        logger.debug(f"Registered singleton instance for {service_type.__name__}")

        if alias:
            self._aliases[alias] = service_type
            logger.debug(f"Registered alias '{alias}' for {service_type.__name__}")

    def get(self, service_type: type[T]) -> T:
        """
        Get service instance by type.

        Creates instance on first access (lazy initialization).
        Returns cached instance on subsequent accesses.

        Args:
            service_type: Type protocol or class to retrieve

        Returns:
            Service instance

        Raises:
            LookupError: If service_type not registered

        Example:
            >>> llm = container.get(LLMProvider)
            >>> await llm.ainvoke([{"role": "user", "content": "Hi"}])
        """
        # Check if already instantiated
        if service_type in self._singletons:
            return self._singletons[service_type]

        # Check if factory registered
        if service_type not in self._factories:
            raise LookupError(
                f"Service {service_type.__name__} not registered. "
                f"Available: {list(self._factories.keys())}"
            )

        # Create and cache instance
        try:
            instance = self._factories[service_type]()
            self._singletons[service_type] = instance
            logger.debug(f"Created instance for {service_type.__name__}")
            return instance
        except Exception as e:
            logger.error(f"Failed to create {service_type.__name__}: {e}")
            raise

    def get_by_alias(self, alias: str) -> Any:
        """
        Get service instance by string alias.

        Args:
            alias: String alias registered with service

        Returns:
            Service instance

        Raises:
            LookupError: If alias not found

        Example:
            >>> container.register(LLMProvider, factory, alias="llm")
            >>> llm = container.get_by_alias("llm")
        """
        if alias not in self._aliases:
            raise LookupError(
                f"Alias '{alias}' not found. "
                f"Available: {list(self._aliases.keys())}"
            )

        service_type = self._aliases[alias]
        return self.get(service_type)

    def reset(self) -> None:
        """
        Clear all singletons and factories.

        Primarily used for testing to reset container state.
        Clears both instances and registrations.

        Example:
            >>> container.reset()
            >>> len(container._singletons)
            0
        """
        self._singletons.clear()
        self._factories.clear()
        self._aliases.clear()
        logger.debug("Container reset")

    def has(self, service_type: type[T]) -> bool:
        """
        Check if service type is registered.

        Args:
            service_type: Type to check

        Returns:
            True if registered, False otherwise

        Example:
            >>> container.has(LLMProvider)
            True
        """
        return service_type in self._factories or service_type in self._singletons


# Global container instance
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """
    Get global service container instance.

    Creates container on first call.

    Returns:
        Global ServiceContainer instance

    Example:
        >>> container = get_container()
        >>> llm = container.get(LLMProvider)
    """
    global _container
    if _container is None:
        _container = ServiceContainer()
        logger.info("Created global service container")
    return _container


def reset_container() -> None:
    """
    Reset global container.

    Primarily used for testing.
    """
    global _container
    if _container is not None:
        _container.reset()
    _container = None
    logger.info("Reset global service container")


def setup_container() -> ServiceContainer:
    """
    Initialize container with core miniClaw services.

    Registers all default services required by the application.
    Call this during application startup.

    Returns:
        Initialized ServiceContainer instance

    Raises:
        ImportError: If required dependencies not available
        ConfigurationError: If configuration is invalid

    Example:
        >>> from app.main import app
        >>> @app.on_event("startup")
        ... async def startup():
        ...     setup_container()
    """
    from app.core.agent import AgentManager
    from app.core.rag_engine import RAGEngine
    from app.core.embedding_manager import EmbeddingModelManager
    from app.memory.memory_manager import MemoryManager
    from app.config import settings
    from langchain_openai import ChatOpenAI
    from langchain_openai import OpenAIEmbeddings

    container = get_container()
    logger.info("Setting up service container")

    # Settings provider (singleton - already exists)
    container.register_singleton(SettingsProvider, settings, alias="settings")
    logger.debug("Registered settings provider")

    # LLM provider (factory - lazy initialization)
    def _create_llm() -> LLMProvider:
        """Create LLM instance based on configuration."""
        from app.core.llm import create_llm

        return create_llm(provider=settings.llm_provider)

    container.register(LLMProvider, _create_llm, alias="llm")
    logger.debug(f"Registered LLM provider: {settings.llm_provider}")

    # Embedding provider (factory)
    def _create_embeddings() -> EmbeddingProvider:
        """Create embeddings instance based on configuration."""
        return EmbeddingModelManager(settings=settings)

    container.register(EmbeddingProvider, _create_embeddings, alias="embeddings")
    logger.debug(f"Registered embedding provider")

    # Vector store (factory - lazy initialization)
    def _create_vector_store() -> VectorStore:
        """Create vector store instance."""
        return RAGEngine(settings=settings)

    container.register(VectorStore, _create_vector_store, alias="vector_store")
    logger.debug("Registered vector store")

    # Message history store (factory)
    def _create_history_store() -> MessageHistoryStore:
        """Create message history store."""
        return MemoryManager()

    container.register(MessageHistoryStore, _create_history_store, alias="history")
    logger.debug("Registered message history store")

    # Agent manager (factory - depends on LLM and tools)
    def _create_agent_manager() -> AgentManager:
        """Create agent manager with all dependencies."""
        from app.tools import CORE_TOOLS
        llm = container.get(LLMProvider)

        return AgentManager(
            tools=CORE_TOOLS,
            llm=llm,
            llm_provider=settings.llm_provider,
        )

    container.register(AgentManager, _create_agent_manager, alias="agent")
    logger.debug("Registered agent manager")

    logger.info("Service container setup complete")
    return container


# Convenience functions for common services
def get_llm() -> LLMProvider:
    """Get LLM provider instance."""
    return get_container().get(LLMProvider)


def get_embeddings() -> EmbeddingProvider:
    """Get embedding provider instance."""
    return get_container().get(EmbeddingProvider)


def get_vector_store() -> VectorStore:
    """Get vector store instance."""
    return get_container().get(VectorStore)


def get_history_store() -> MessageHistoryStore:
    """Get message history store instance."""
    return get_container().get(MessageHistoryStore)


def get_agent_manager() -> Any:
    """Get agent manager instance."""
    return get_container().get(AgentManager)


def get_settings() -> SettingsProvider:
    """Get settings provider instance."""
    return get_container().get(SettingsProvider)
