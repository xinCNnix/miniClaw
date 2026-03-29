"""
Protocol interfaces for dependency injection.

Defines the contracts that services must fulfill, enabling
loose coupling and easier testing.
"""

from typing import Protocol, AsyncIterator, List, Dict, Any, Callable
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool


class LLMProvider(Protocol):
    """
    LLM provider interface.

    Provides contract for language model operations, both
    streaming and non-streaming.
    """

    async def astream(self, messages: List[Dict[str, Any]]) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream LLM responses asynchronously.

        Args:
            messages: List of message dictionaries with 'role' and 'content'

        Yields:
            Response chunks as they arrive from the LLM

        Example:
            >>> async for chunk in llm.astream([{"role": "user", "content": "Hello"}]):
            ...     print(chunk)
        """
        ...

    async def ainvoke(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Invoke LLM and get complete response.

        Args:
            messages: List of message dictionaries

        Returns:
            Response dictionary with LLM response

        Example:
            >>> response = await llm.ainvoke([{"role": "user", "content": "Hi"}])
            >>> print(response['content'])
        """
        ...


class EmbeddingProvider(Protocol):
    """
    Embedding provider interface.

    Provides contract for generating text embeddings.
    """

    def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of float values representing the embedding vector

        Example:
            >>> embedding = embedder.get_embedding("Hello world")
            >>> len(embedding)
            1536
        """
        ...

    async def aget_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings for multiple texts (async version).

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors

        Example:
            >>> embeddings = await embedder.aget_embeddings(["Hello", "World"])
            >>> len(embeddings)
            2
        """
        ...


class VectorStore(Protocol):
    """
    Vector store interface.

    Provides contract for vector storage and retrieval operations.
    """

    def add_nodes(self, nodes: List[Any]) -> None:
        """
        Add nodes to vector store.

        Args:
            nodes: List of nodes to add (Document objects, etc.)

        Example:
            >>> store.add_nodes([doc1, doc2])
        """
        ...

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: Dict[str, Any] | None = None
    ) -> List[Any]:
        """
        Search for similar documents.

        Args:
            query: Query text
            top_k: Number of results to return
            filter_dict: Optional metadata filters

        Returns:
            List of search results

        Example:
            >>> results = store.search("What is Python?", top_k=3)
            >>> len(results)
            3
        """
        ...

    def delete(self, ref_doc_id: str) -> None:
        """
        Delete documents by reference ID.

        Args:
            ref_doc_id: Reference ID of document to delete

        Example:
            >>> store.delete("doc-123")
        """
        ...

    def persist(self) -> None:
        """
        Persist vector store to disk.
        """
        ...


class MessageHistoryStore(Protocol):
    """
    Message history storage interface.

    Provides contract for storing and retrieving chat history.
    """

    def get_history(self, session_id: str, user_id: str | None = None) -> BaseChatMessageHistory:
        """
        Get chat history for a session.

        Args:
            session_id: Session identifier
            user_id: Optional user identifier

        Returns:
            ChatMessageHistory object for the session

        Example:
            >>> history = store.get_history("session-123")
            >>> len(list(history.messages))
            5
        """
        ...

    def add_message(
        self,
        session_id: str,
        message: Dict[str, Any],
        user_id: str | None = None
    ) -> None:
        """
        Add a message to history.

        Args:
            session_id: Session identifier
            message: Message dictionary with role, content, etc.
            user_id: Optional user identifier

        Example:
            >>> store.add_message("session-123", {"role": "user", "content": "Hi"})
        """
        ...

    def list_sessions(
        self,
        user_id: str | None = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List all sessions for a user.

        Args:
            user_id: Optional user identifier
            limit: Maximum number of sessions to return

        Returns:
            List of session information dictionaries

        Example:
            >>> sessions = store.list_sessions(user_id="user-123", limit=10)
            >>> len(sessions)
            10
        """
        ...


class ToolRegistry(Protocol):
    """
    Tool registry interface.

    Provides contract for managing available tools.
    """

    def get_tools(self) -> List[BaseTool]:
        """
        Get all available tools.

        Returns:
            List of BaseTool instances

        Example:
            >>> tools = registry.get_tools()
            >>> len(tools)
            5
        """
        ...

    def get_tool(self, name: str) -> BaseTool | None:
        """
        Get a specific tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found

        Example:
            >>> tool = registry.get_tool("read_file")
            >>> tool is not None
            True
        """
        ...

    def has_tool(self, name: str) -> bool:
        """
        Check if a tool is available.

        Args:
            name: Tool name

        Returns:
            True if tool exists, False otherwise

        Example:
            >>> registry.has_tool("read_file")
            True
        """
        ...


class SettingsProvider(Protocol):
    """
    Settings provider interface.

    Provides contract for accessing application settings.
    """

    def get(self, key: str, default: Any | None = None) -> Any:
        """
        Get a setting value.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Setting value

        Example:
            >>> settings.get("max_tool_rounds", default=5)
            5
        """
        ...

    def get_all(self) -> Dict[str, Any]:
        """
        Get all settings as dictionary.

        Returns:
            Dictionary of all settings

        Example:
            >>> all_settings = settings.get_all()
            >>> "max_tool_rounds" in all_settings
            True
        """
        ...


class ReasoningStrategy(Protocol):
    """
    Reasoning strategy interface for agent decision-making.

    This protocol defines the contract for different reasoning strategies
    that can be used by the agent to process user queries.

    Available strategies:
    - Simple: Direct LLM invocation without complex reasoning
    - ToT: Tree of Thoughts reasoning for complex tasks
    - ReAct: Reasoning + Acting loop
    - Custom: User-defined strategies

    Example:
        >>> from app.core.tot.router import ToTOrchestrator
        >>> from app.core.llm import create_llm
        >>>
        >>> llm = create_llm("qwen")
        >>> strategy = ToTOrchestrator(llm=llm, tools=tools)
        >>>
        >>> async for event in strategy.process(messages, system_prompt, tools):
        ...     print(event["type"])
        reasoning_start
        thinking
        tool_call
        reasoning_end
    """

    async def process(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[Any],
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Process messages using the reasoning strategy.

        This method implements the core reasoning logic for the strategy.
        It should yield streaming events that represent the reasoning process.

        Args:
            messages: Conversation messages with 'role' and 'content' keys
            system_prompt: System prompt for the agent
            tools: List of available tools (BaseTool instances)
            **kwargs: Additional strategy-specific parameters
                - max_depth: Maximum reasoning depth (for ToT)
                - max_branches: Maximum branches per node (for ToT)
                - timeout: Maximum time for reasoning (optional)
                - strategy: Specific strategy variant (optional)

        Yields:
            Streaming events with 'type' key:
            - 'reasoning_start': Strategy starting
            - 'reasoning_end': Strategy complete
            - 'thinking': Reasoning/thinking event
            - 'thought_generated': New thought generated (ToT)
            - 'thought_evaluated': Thought evaluation result (ToT)
            - 'tool_call': Tool being executed
            - 'tool_result': Tool execution result
            - 'content': Text content being generated
            - 'error': Error occurred

        Example:
            >>> async for event in strategy.process(messages, system_prompt, tools):
            ...     if event["type"] == "reasoning_start":
            ...         print(f"Starting {event.get('strategy', 'unknown')} reasoning")
            ...     elif event["type"] == "thinking":
            ...         print("Thinking...")
            ...     elif event["type"] == "content":
            ...         print(event["content"], end="")

        Note:
            - Strategies should handle both simple and complex tasks
            - Simple tasks should not use expensive reasoning
            - Complex tasks should yield progress events
            - Errors should be yielded as events, not raised
        """
        ...
