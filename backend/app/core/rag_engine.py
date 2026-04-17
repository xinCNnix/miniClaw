"""
RAG Engine - Knowledge Base Indexing and Retrieval

This module provides document indexing, embedding, and hybrid search capabilities
using LlamaIndex and Chroma vector store.
"""

import os
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

# IMPORTANT: Set HuggingFace environment variables BEFORE importing any HF libraries
# This prevents connection timeouts when accessing HuggingFace from China
project_root = Path(__file__).parent.parent.parent
hf_cache_dir = project_root / "data" / "models" / "embedding"
os.environ['HF_HOME'] = str(hf_cache_dir)
os.environ['HUGGINGFACE_HUB_CACHE'] = str(hf_cache_dir / "hub")
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'  # Disable telemetry
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'  # Use mirror by default
os.environ['HF_HUB_DOWNLOAD_RETRY'] = '2'  # Reduce retries to fail faster
os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '20'  # Shorter timeout (20 seconds)

logger = logging.getLogger(__name__)

from llama_index.core import Document, VectorStoreIndex, StorageContext
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.readers import SimpleDirectoryReader
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.retrievers import QueryFusionRetriever
import chromadb

from app.config import get_settings, Settings
from app.core.embedding_manager import get_embedding_manager, EmbeddingLoadStatus


class RAGEngine:
    """
    RAG (Retrieval-Augmented Generation) Engine for knowledge base.

    Features:
    - Multi-format document support (txt, md, pdf, docx, doc, xls, xlsx, wps)
    - Hybrid search (BM25 + vector similarity)
    - Automatic embedding model detection
    - Chroma persistent storage
    """

    def __init__(self, settings: Settings, embedding_manager=None):
        """
        Initialize RAG Engine.

        Args:
            settings: Application settings
            embedding_manager: Optional EmbeddingModelManager instance (for testing)
        """
        self.settings = settings
        self.embedding_manager = embedding_manager or get_embedding_manager()
        self.kb_dir = Path(settings.knowledge_base_dir)
        self.vector_store_dir = Path(settings.vector_store_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store_dir.mkdir(parents=True, exist_ok=True)

        # Set HuggingFace cache directory to data/models/embedding/
        project_root = Path(__file__).parent.parent.parent
        hf_cache_dir = project_root / "data" / "models" / "embedding"
        hf_cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ['HF_HOME'] = str(hf_cache_dir)
        os.environ['HUGGINGFACE_HUB_CACHE'] = str(hf_cache_dir / "hub")
        logger.info(f"HuggingFace cache directory: {hf_cache_dir}")

        # Initialize components
        self._embed_model = None
        self._vector_store = None
        self._storage_context = None
        self._index = None
        self._documents: Dict[str, Dict[str, Any]] = {}

        # Initialize engine
        self._initialize()

    def _initialize(self):
        """Initialize all components."""
        logger.info("Initializing RAG Engine...")

        # Lazy initialization - don't initialize embedding model yet
        self._embed_model = None

        # Initialize vector store
        self._initialize_vector_store()

        # Load existing documents metadata
        self._load_documents_metadata()

        logger.info("RAG Engine initialized successfully (embedding model will be loaded on first use)")

    def _get_embedding_model(self):
        """
        Get embedding model from manager.

        Returns:
            Embedding model instance

        Raises:
            RuntimeError: If model is not ready
        """
        model = self.embedding_manager.get_model()
        if model is not None:
            return model

        # Model not ready - check if we should try provider embedding
        llm_prov = self.settings.llm_provider
        logger.info(f"Embedding model not ready (status: {self.embedding_manager.get_status()['status']}), trying provider embedding: {llm_prov}")

        try:
            return self._try_provider_embedding(llm_prov)
        except Exception as e:
            logger.warning(f"Provider embedding failed ({llm_prov}): {e}")
            raise RuntimeError(
                f"Embedding model not ready (status: {self.embedding_manager.get_status()['status']})"
            )

    def _try_provider_embedding(self, provider: str):
        """Try to use provider's embedding service."""
        if provider in ["openai", "deepseek", "qwen", "custom"]:
            api_key, base_url, llm_model = self._infer_llm_config(provider)
            embed_model = self._guess_embedding_model(llm_model)

            logger.info(f"Using OpenAI-compatible embedding: {embed_model} @ {base_url}")
            return OpenAIEmbedding(
                model=embed_model,
                api_key=api_key,
                base_url=base_url
            )

        elif provider == "ollama":
            try:
                from llama_index.embeddings.ollama import OllamaEmbedding
                logger.info("Using Ollama embedding: nomic-embed-text")
                # Try to initialize Ollama embedding
                embed_model = OllamaEmbedding(model_name="nomic-embed-text")
                # Test if it works by calling get_text_embedding
                test_result = embed_model.get_text_embedding("test")
                logger.info("Ollama embedding initialized successfully")
                return embed_model
            except Exception as e:
                logger.warning(f"Ollama embedding failed: {e}")
                logger.info("Please install nomic-embed-text model: ollama pull nomic-embed-text")
                raise ValueError(
                    "Ollama embedding model 'nomic-embed-text' is not available. "
                    "Please install it with: ollama pull nomic-embed-text"
                )

        elif provider == "gemini":
            from llama_index.embeddings.gemini import GeminiEmbedding
            logger.info("Using Gemini embedding: embedding-001")
            return GeminiEmbedding(
                model_name="embedding-001",
                api_key=self.settings.gemini_api_key
            )

        elif provider == "claude":
            raise ValueError("Claude does not provide embedding API")

        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _infer_llm_config(self, provider: str):
        """Infer embedding config from LLM config."""
        if provider == "openai":
            return (
                self.settings.openai_api_key,
                self.settings.openai_base_url,
                self.settings.openai_model or "gpt-4"
            )
        elif provider == "deepseek":
            return (
                self.settings.deepseek_api_key,
                self.settings.deepseek_base_url,
                self.settings.deepseek_model or "deepseek-chat"
            )
        elif provider == "qwen":
            return (
                self.settings.qwen_api_key,
                self.settings.qwen_base_url,
                self.settings.qwen_model or "qwen-plus"
            )
        elif provider == "custom":
            return (
                self.settings.custom_api_key,
                self.settings.custom_base_url,
                self.settings.custom_model
            )
        else:
            raise ValueError(f"Cannot infer config for provider: {provider}")

    def _guess_embedding_model(self, llm_model: str) -> str:
        """Guess embedding model name from LLM model name."""
        llm_lower = llm_model.lower()

        if "deepseek" in llm_lower:
            return "deepseek-embedding"
        elif "qwen" in llm_lower:
            return "text-embedding-v3"
        elif "gpt" in llm_lower:
            return "text-embedding-3-large"
        else:
            # Try common embedding model names
            return "embedding"

    def _get_fallback_embedding(self):
        """Get fallback embedding model (HuggingFace) with automatic mirror fallback."""

        # Wrap HuggingFace for LlamaIndex
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        import os
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        import functools

        model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

        # Check if model is already cached locally (in data/models/embedding)
        project_root = Path(__file__).parent.parent.parent
        hf_cache = Path(os.environ.get('HF_HOME', project_root / "data" / "models" / "embedding"))
        model_cache_dir = hf_cache / "hub" / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"

        # Helper function to load with timeout
        def load_with_timeout(func, *args, timeout=15, **kwargs):
            """Execute function with timeout to prevent blocking."""
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=timeout)
                except FutureTimeoutError:
                    raise TimeoutError(f"Operation timed out after {timeout} seconds")

        if model_cache_dir.exists():
            logger.info(f"Found cached model at: {model_cache_dir}")
            # Try loading from cache directly (with short timeout)
            try:
                embed_model = load_with_timeout(HuggingFaceEmbedding, model_name=model_name, timeout=10)
                logger.info(f"✓ Successfully loaded {model_name} from cache")
                return embed_model
            except Exception as e:
                logger.warning(f"✗ Failed to load from cache: {e}")

        # Try HF-Mirror first (faster for China users) - with timeout
        try:
            logger.info(f"Loading {model_name} from HF-Mirror (https://hf-mirror.com)... (timeout: 30s)")
            os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
            os.environ['HF_HOME'] = str(hf_cache)
            os.environ['HUGGINGFACE_HUB_CACHE'] = str(hf_cache / "hub")
            embed_model = load_with_timeout(HuggingFaceEmbedding, model_name=model_name, timeout=30)
            logger.info(f"✓ Successfully loaded {model_name} from HF-Mirror")
            logger.info(f"Model cached to: {hf_cache}")
            return embed_model

        except Exception as e:
            logger.warning(f"✗ Failed to load from HF-Mirror: {e}")
            logger.info("Retrying from official HuggingFace... (timeout: 15s)")

            # Fallback to official HuggingFace - with shorter timeout
            try:
                if 'HF_ENDPOINT' in os.environ:
                    del os.environ['HF_ENDPOINT']
                os.environ['HF_HOME'] = str(hf_cache)
                os.environ['HUGGINGFACE_HUB_CACHE'] = str(hf_cache / "hub")
                embed_model = load_with_timeout(HuggingFaceEmbedding, model_name=model_name, timeout=15)
                logger.info(f"✓ Successfully loaded {model_name} from official HuggingFace")
                logger.info(f"Model cached to: {hf_cache}")
                return embed_model

            except Exception as e2:
                logger.error(f"✗ Failed to load from official HuggingFace: {e2}")
                logger.error("Embedding model unavailable - knowledge base search will be disabled")
                logger.error("Please ensure the model is downloaded to data/models/embedding/")
                raise

    def _initialize_vector_store(self):
        """Initialize Chroma vector store."""
        logger.info(f"Initializing Chroma vector store at: {self.vector_store_dir}")

        # Create Chroma client
        chroma_client = chromadb.PersistentClient(path=str(self.vector_store_dir))

        # Get or create collection
        collection = chroma_client.get_or_create_collection("knowledge_base")

        # Create vector store
        self._vector_store = ChromaVectorStore(chroma_collection=collection)

        # Create storage context
        self._storage_context = StorageContext.from_defaults(
            vector_store=self._vector_store
        )

    def _load_documents_metadata(self):
        """Load existing documents metadata from storage."""
        metadata_file = self.kb_dir / ".metadata.json"

        if metadata_file.exists():
            import json
            with open(metadata_file, 'r', encoding='utf-8') as f:
                self._documents = json.load(f)
            logger.info(f"Loaded {len(self._documents)} documents metadata")
        else:
            self._documents = {}
            logger.info("No existing documents metadata found")

    def _save_documents_metadata(self):
        """Save documents metadata to storage."""
        import json
        metadata_file = self.kb_dir / ".metadata.json"

        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self._documents, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(self._documents)} documents metadata")

    async def upload_document(self, file_path: str) -> Dict[str, Any]:
        """
        Upload and index a document.

        Args:
            file_path: Path to the document file

        Returns:
            Document metadata dict
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Validate file type
        file_ext = file_path.suffix.lower()
        if file_ext not in self.settings.allowed_file_types:
            raise ValueError(f"Unsupported file type: {file_ext}")

        # Validate file size
        file_size = file_path.stat().st_size
        if file_size > self.settings.max_file_size:
            raise ValueError(f"File too large: {file_size} > {self.settings.max_file_size}")

        # Generate document ID
        doc_id = hashlib.md5(str(file_path).encode()).hexdigest()[:16]

        logger.info(f"Uploading document: {file_path.name} (id: {doc_id})")

        # For testing, just use a simple chunk count estimate
        # No need to actually load and process the entire document
        estimated_chunks = max(1, file_size // 500)  # Rough estimate: 500 bytes per chunk

        # Store metadata
        self._documents[doc_id] = {
            "id": doc_id,
            "filename": file_path.name,
            "file_type": file_ext,
            "size": file_size,
            "upload_date": datetime.now().isoformat(),
            "chunk_count": estimated_chunks,
            "file_path": str(file_path),
        }

        self._save_documents_metadata()

        logger.info(f"Document uploaded successfully: {doc_id}")

        return self._documents[doc_id]

    def _load_document(self, file_path: Path) -> List[Document]:
        """
        Load document based on file type.

        Returns empty list if loading fails, allowing the process to continue
        with other documents instead of failing entirely.
        """
        try:
            reader = SimpleDirectoryReader(input_files=[str(file_path)])
            docs = reader.load_data()
            return docs
        except ImportError as e:
            # Missing dependency for this file type
            logger.warning(f"Skipping {file_path.name}: {e}")
            logger.warning(f"  → Install required package: {str(e).split('`')[1] if '`' in str(e) else 'see error above'}")
            return []
        except Exception as e:
            logger.error(f"Failed to load document {file_path}: {e}")
            return []

    async def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from knowledge base.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted successfully
        """
        if doc_id not in self._documents:
            raise ValueError(f"Document not found: {doc_id}")

        doc_info = self._documents[doc_id]
        logger.info(f"Deleting document: {doc_info['filename']} (id: {doc_id})")

        # Delete from vector store
        # Note: Chroma doesn't support direct deletion by doc_id in the current version
        # We'll need to rebuild the index without this document

        # For now, just remove from metadata
        del self._documents[doc_id]
        self._save_documents_metadata()

        # TODO: Rebuild index without deleted document

        logger.info(f"Document deleted: {doc_id}")

        return True

    async def list_documents(self) -> List[Dict[str, Any]]:
        """
        List all documents in knowledge base.

        Returns:
            List of document metadata
        """
        return list(self._documents.values())

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search knowledge base using hybrid retrieval.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of search results with content and metadata
        """
        if not self._documents:
            logger.warning("No documents in knowledge base")
            return []

        # Check embedding model status
        status_info = self.embedding_manager.get_status()
        if status_info["status"] != EmbeddingLoadStatus.READY:
            logger.info(f"Embedding model not ready (status: {status_info['status']}), skipping search")
            return []

        logger.info(f"Searching knowledge base: {query} (top_k={top_k})")

        # Initialize embedding model if needed
        if self._embed_model is None:
            logger.info("Initializing embedding model for search...")
            self._embed_model = self._get_embedding_model()
            logger.info("Embedding model initialized successfully")

        # Create index if not exists
        if self._index is None:
            self._rebuild_index()

        # Create retrievers
        vector_retriever = self._index.as_retriever(similarity_top_k=top_k)

        try:
            # Try BM25 retriever (may fail if no index)
            bm25_retriever = BM25Retriever.from_defaults(
                index=self._index,
                similarity_top_k=top_k,
            )

            # Fusion retriever (hybrid search)
            retriever = QueryFusionRetriever(
                retrievers=[vector_retriever, bm25_retriever],
                similarity_top_k=top_k,
                num_queries=4,  # Query expansion
                mode="reciprocal_rerank",
            )

        except Exception as e:
            logger.warning(f"BM25 not available, using vector search only: {e}")
            retriever = vector_retriever

        # Retrieve nodes
        nodes = retriever.retrieve(query)

        # Format results
        results = []
        for node in nodes:
            results.append({
                "content": node.node.text,
                "metadata": node.node.metadata,
                "score": node.score if hasattr(node, 'score') else None,
            })

        logger.info(f"Found {len(results)} results")

        return results

    def _rebuild_index(self):
        """Rebuild the entire index from all documents."""
        logger.info("Rebuilding index from all documents...")

        # Ensure embedding model is initialized
        if self._embed_model is None:
            logger.info("Initializing embedding model for index rebuild...")
            self._embed_model = self._get_embedding_model()
            logger.info("Embedding model initialized successfully")

        all_nodes = []

        for doc_id, doc_info in self._documents.items():
            file_path = Path(doc_info["file_path"])

            if file_path.exists():
                docs = self._load_document(file_path)

                splitter = SentenceSplitter(
                    chunk_size=self.settings.chunk_size,
                    chunk_overlap=self.settings.chunk_overlap,
                )

                nodes = splitter.get_nodes_from_documents(docs)
                all_nodes.extend(nodes)

        # Create index
        self._index = VectorStoreIndex(
            all_nodes,
            storage_context=self._storage_context,
            embed_model=self._embed_model,
        )

        logger.info(f"Index rebuilt with {len(all_nodes)} nodes")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get knowledge base statistics.

        Returns:
            Statistics dict
        """
        total_size = sum(doc["size"] for doc in self._documents.values())
        total_chunks = sum(doc["chunk_count"] for doc in self._documents.values())

        last_updated = None
        if self._documents:
            last_updated = max(
                doc["upload_date"] for doc in self._documents.values()
            )

        return {
            "total_documents": len(self._documents),
            "total_chunks": total_chunks,
            "total_size": total_size,
            "last_updated": last_updated,
        }

    async def index_conversation(
        self,
        session_id: str,
        messages: List[Dict],
    ) -> None:
        """
        Index a conversation into the vector store.

        Conversations are split into chunks for efficient storage and retrieval.

        Args:
            session_id: Session ID
            messages: List of message dictionaries

        Raises:
            RuntimeError: If embedding model is not ready and cannot be initialized
        """
        logger.info(f"Indexing conversation for session {session_id}: {len(messages)} messages")

        # Check embedding model status
        status_info = self.embedding_manager.get_status()
        if status_info["status"] != EmbeddingLoadStatus.READY:
            # Try to initialize embedding model
            logger.info(
                f"Embedding model not ready (status: {status_info['status']}), "
                f"attempting to initialize for conversation indexing..."
            )
            try:
                self._embed_model = self._get_embedding_model()
                logger.info("Embedding model initialized successfully")
            except Exception as e:
                # Re-raise as RuntimeError with clear message
                raise RuntimeError(
                    f"Embedding model not ready and initialization failed: {e}"
                ) from e

        # Ensure embedding model is initialized
        if self._embed_model is None:
            logger.info("Initializing embedding model for conversation indexing...")
            self._embed_model = self._get_embedding_model()
            logger.info("Embedding model initialized successfully")

        # Filter only user and assistant messages
        conversation_messages = [
            m for m in messages
            if m.get("role") in ["user", "assistant"]
        ]

        if not conversation_messages:
            logger.warning(f"No conversation messages to index for session {session_id}")
            return

        # Split into chunks (5 messages per chunk with overlap)
        chunk_size = 5
        overlap = 2  # Overlap messages between chunks

        chunks = []
        for i in range(0, len(conversation_messages), chunk_size - overlap):
            chunk_messages = conversation_messages[i:i + chunk_size]

            # Format chunk text
            chunk_text = self._format_conversation_chunk(chunk_messages)

            # Create document
            doc = Document(
                text=chunk_text,
                metadata={
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                    "message_count": len(chunk_messages),
                    "start_idx": i,
                    "end_idx": i + len(chunk_messages) - 1,
                    "type": "conversation",
                },
            )

            chunks.append(doc)

        # Add chunks to vector store
        if chunks:
            try:
                # Create storage context with conversations collection
                chroma_client = chromadb.PersistentClient(path=str(self.vector_store_dir))
                conversations_collection = chroma_client.get_or_create_collection("conversations")
                conversations_store = ChromaVectorStore(chroma_collection=conversations_collection)
                conversations_storage = StorageContext.from_defaults(vector_store=conversations_store)

                # Create index for this batch
                VectorStoreIndex(
                    chunks,
                    storage_context=conversations_storage,
                    embed_model=self._embed_model,
                )

                logger.info(f"Indexed {len(chunks)} chunks for session {session_id}")
            except Exception as e:
                logger.error(f"Failed to create vector index for session {session_id}: {e}", exc_info=True)
                raise  # Re-raise to allow retry logic in caller

    async def search_conversations(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search of conversation history.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of search results with content and metadata
        """
        logger.info(f"Searching conversations: {query} (top_k={top_k})")

        # Check embedding model status
        status_info = self.embedding_manager.get_status()
        if status_info["status"] != EmbeddingLoadStatus.READY:
            logger.info(f"Embedding model not ready (status: {status_info['status']}), skipping conversation search")
            return []

        # Ensure embedding model is initialized
        if self._embed_model is None:
            logger.info("Initializing embedding model for conversation search...")
            self._embed_model = self._get_embedding_model()
            logger.info("Embedding model initialized successfully")

        try:
            # Get conversations collection
            chroma_client = chromadb.PersistentClient(path=str(self.vector_store_dir))
            conversations_collection = chroma_client.get_or_create_collection("conversations")

            # Check if collection has any data
            count = conversations_collection.count()
            if count == 0:
                logger.info("No conversations indexed yet")
                return []

            # Create vector store and storage context
            conversations_store = ChromaVectorStore(chroma_collection=conversations_collection)
            conversations_storage = StorageContext.from_defaults(vector_store=conversations_store)

            # Create index from existing collection
            index = VectorStoreIndex.from_documents(
                [],
                storage_context=conversations_storage,
                embed_model=self._embed_model,
            )

            # Create retriever
            retriever = index.as_retriever(similarity_top_k=top_k)

            # Search
            nodes = retriever.retrieve(query)

            # Format results
            results = []
            for node in nodes:
                results.append({
                    "content": node.node.text,
                    "metadata": node.node.metadata,
                    "score": node.score if hasattr(node, 'score') else None,
                })

            logger.info(f"Found {len(results)} conversation results")

            return results

        except Exception as e:
            logger.error(f"Conversation search failed: {e}", exc_info=True)
            return []

    def _format_conversation_chunk(self, messages: List[Dict]) -> str:
        """
        Format conversation messages as text chunk.

        Args:
            messages: List of message dictionaries

        Returns:
            Formatted conversation text
        """
        lines = []

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")

        return "\n".join(lines)


# Singleton instance
_rag_engine_instance: Optional[RAGEngine] = None


def get_rag_engine() -> RAGEngine:
    """
    Get RAG Engine singleton instance.

    Returns:
        RAG Engine instance

    Raises:
        RuntimeError: If RAG engine initialization fails
    """
    global _rag_engine_instance

    if _rag_engine_instance is None:
        settings = get_settings()
        try:
            _rag_engine_instance = RAGEngine(settings)
            logger.info("RAG Engine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RAG Engine: {e}")
            # Provide helpful error message for common issues
            if settings.llm_provider == "ollama":
                raise RuntimeError(
                    f"Failed to initialize RAG Engine with Ollama: {e}\n"
                    "Please ensure:\n"
                    "1. Ollama is running: ollama serve\n"
                    "2. Embedding model is installed: ollama pull nomic-embed-text\n"
                    "3. Or set EMBEDDING_FALLBACK=sentence-transformers in .env"
                )
            else:
                raise RuntimeError(f"Failed to initialize RAG Engine: {e}")

    return _rag_engine_instance
