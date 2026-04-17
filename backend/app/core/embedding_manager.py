"""
Embedding Model Manager

Handles async loading and lifecycle management of embedding models with proper
state tracking and graceful degradation.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class EmbeddingLoadStatus(str, Enum):
    """Status of embedding model loading."""
    NOT_STARTED = "not_started"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


class EmbeddingModelManager:
    """
    Manager for embedding model async loading and lifecycle.

    Features:
    - Async warmup with true timeout control (asyncio.wait_for)
    - State machine: NOT_STARTED → LOADING → READY/FAILED
    - Concurrent load protection (asyncio.Lock)
    - Status query API
    - Singleton access via get_embedding_manager()
    """

    def __init__(self, settings):
        """
        Initialize embedding model manager.

        Args:
            settings: Application settings from get_settings()
        """
        self.settings = settings
        self._status: EmbeddingLoadStatus = EmbeddingLoadStatus.NOT_STARTED
        self._model = None
        self._lock = asyncio.Lock()
        self._load_start_time: Optional[datetime] = None
        self._load_duration: Optional[float] = None
        self._error_message: Optional[str] = None

    async def warmup(self, timeout: int = 60) -> bool:
        """
        Asynchronously warm up (preload) the embedding model.

        This method runs in the background and does not block the caller.
        Uses asyncio.wait_for for true timeout control.

        Args:
            timeout: Maximum time to wait for model loading (seconds)

        Returns:
            True if model loaded successfully, False otherwise
        """
        async with self._lock:
            # Prevent duplicate loading
            if self._status == EmbeddingLoadStatus.READY:
                logger.info("Embedding model already loaded")
                return True
            if self._status == EmbeddingLoadStatus.LOADING:
                logger.info("Embedding model already loading, skipping duplicate warmup")
                return False

            self._status = EmbeddingLoadStatus.LOADING
            self._load_start_time = datetime.now()
            self._error_message = None

        try:
            logger.info("Starting embedding model warmup...")
            model = await self._load_with_timeout_async(timeout)
            self._model = model
            self._status = EmbeddingLoadStatus.READY
            self._load_duration = (datetime.now() - self._load_start_time).total_seconds()
            logger.info(f"[OK] Embedding model loaded successfully in {self._load_duration:.2f}s")
            return True

        except asyncio.TimeoutError:
            self._status = EmbeddingLoadStatus.FAILED
            self._error_message = f"Loading timed out after {timeout}s"
            logger.error(f"✗ {self._error_message}")
            return False

        except Exception as e:
            self._status = EmbeddingLoadStatus.FAILED
            self._error_message = str(e)
            logger.error(f"✗ Failed to load embedding model: {e}", exc_info=True)
            return False

    async def _load_with_timeout_async(self, timeout: int = 30):
        """
        Load embedding model from local path (no network access).

        Args:
            timeout: Timeout in seconds

        Returns:
            Loaded embedding model instance

        Raises:
            asyncio.TimeoutError: If loading exceeds timeout
            Exception: If loading fails
        """
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        import os

        # Set HuggingFace environment variables
        project_root = Path(__file__).parent.parent.parent
        hf_cache_dir = project_root / "data" / "models" / "embedding"
        hf_cache_dir.mkdir(parents=True, exist_ok=True)

        # Force offline mode - no network access
        os.environ['HF_HOME'] = str(hf_cache_dir)
        os.environ['HUGGINGFACE_HUB_CACHE'] = str(hf_cache_dir / "hub")
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'

        model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

        # Check if local model exists
        model_cache_dir = hf_cache_dir / "hub" / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"
        local_model_path = hf_cache_dir / "paraphrase-multilingual-MiniLM-L12-v2"

        # Determine which path to use
        actual_model_path = None
        if local_model_path.exists():
            actual_model_path = local_model_path
            logger.info(f"Using local model at: {local_model_path}")
        elif (model_cache_dir / "snapshots" / "main").exists():
            actual_model_path = model_cache_dir / "snapshots" / "main"
            logger.info(f"Using cached model at: {actual_model_path}")
        else:
            # Try to find any snapshot
            snapshots = list((model_cache_dir / "snapshots").glob("*")) if (model_cache_dir / "snapshots").exists() else []
            if snapshots:
                actual_model_path = snapshots[0]
                logger.info(f"Using cached model snapshot at: {actual_model_path}")
            else:
                raise RuntimeError(
                    f"Embedding model not found locally. "
                    f"Expected path: {local_model_path} or {model_cache_dir}. "
                    f"Please download the model first."
                )

        # Load model from local path
        try:
            logger.info(f"Loading embedding model from local path: {actual_model_path}")
            def load_model():
                return HuggingFaceEmbedding(model_name=str(actual_model_path))

            loop = asyncio.get_event_loop()
            model = await asyncio.wait_for(
                loop.run_in_executor(None, load_model),
                timeout=timeout
            )

            logger.info("[OK] Embedding model loaded successfully from local path")
            return model

        except asyncio.TimeoutError:
            raise
        except Exception as e:
            error_msg = f"Failed to load embedding model from local path: {e}"
            logger.error(f"✗ {error_msg}")
            raise RuntimeError(error_msg) from e

        # Try each endpoint with timeout
        last_error = None
        loop = asyncio.get_event_loop()

        for endpoint, endpoint_name in endpoints:
            try:
                if endpoint:
                    os.environ['HF_ENDPOINT'] = endpoint
                    logger.info(f"Trying {endpoint_name}...")
                else:
                    # Remove HF_ENDPOINT to use official HuggingFace
                    if 'HF_ENDPOINT' in os.environ:
                        del os.environ['HF_ENDPOINT']
                    logger.info(f"Trying {endpoint_name}...")

                def load_model():
                    return HuggingFaceEmbedding(model_name=model_name)

                model = await asyncio.wait_for(
                    loop.run_in_executor(None, load_model),
                    timeout=timeout
                )

                logger.info(f"[OK] Successfully loaded model from {endpoint_name}")
                return model

            except (asyncio.TimeoutError, Exception) as e:
                last_error = e
                endpoint_url = endpoint if endpoint else "official HuggingFace"
                logger.warning(f"✗ Failed to load from {endpoint_name}: {e}")
                # Clear offline mode if set (might be interfering)
                if 'HF_HUB_OFFLINE' in os.environ:
                    del os.environ['HF_HUB_OFFLINE']
                if 'TRANSFORMERS_OFFLINE' in os.environ:
                    del os.environ['TRANSFORMERS_OFFLINE']
                continue

        # All endpoints failed
        error_msg = f"Failed to load embedding model from all endpoints"
        if last_error:
            error_msg += f". Last error: {last_error}"
        logger.error(f"✗ {error_msg}")
        raise RuntimeError(error_msg) from last_error

    def get_model(self):
        """
        Get the embedding model instance.

        Only returns the model if it's in READY state.
        Returns None otherwise, allowing caller to implement graceful degradation.

        Returns:
            Embedding model instance or None if not ready
        """
        if self._status == EmbeddingLoadStatus.READY:
            return self._model
        return None

    def get_status(self) -> Dict[str, Any]:
        """
        Get current status information.

        Returns:
            Dict with status, load_duration, error, and model_name
        """
        return {
            "status": self._status.value,
            "load_duration": self._load_duration,
            "error": self._error_message,
            "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            if self._status == EmbeddingLoadStatus.READY else None,
        }


# Singleton instance
_embedding_manager_instance: Optional[EmbeddingModelManager] = None


def get_embedding_manager() -> EmbeddingModelManager:
    """
    Get the global embedding manager singleton instance.

    Returns:
        EmbeddingModelManager instance
    """
    global _embedding_manager_instance
    if _embedding_manager_instance is None:
        from app.config import get_settings
        settings = get_settings()
        _embedding_manager_instance = EmbeddingModelManager(settings)
    return _embedding_manager_instance
