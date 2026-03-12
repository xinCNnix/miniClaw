"""
Unit tests for EmbeddingModelManager class

Tests async model loading, state management, and graceful degradation.
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.core.embedding_manager import (
    EmbeddingModelManager,
    EmbeddingLoadStatus,
    get_embedding_manager,
)


class TestEmbeddingModelManager:
    """Test cases for EmbeddingModelManager class."""

    def test_initial_status_is_not_started(self):
        """Test that manager starts with NOT_STARTED status."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)
        status = manager.get_status()

        assert status["status"] == EmbeddingLoadStatus.NOT_STARTED
        assert status["load_duration"] is None
        assert status["error"] is None
        assert status["model_name"] is None

    def test_get_model_returns_none_when_not_ready(self):
        """Test that get_model returns None when model is not ready."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)
        model = manager.get_model()

        assert model is None

    @pytest.mark.asyncio
    async def test_warmup_returns_true_on_success(self):
        """Test that warmup returns True on successful load."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        # Mock the loading function to avoid actual model download
        with patch.object(manager, '_load_with_timeout_async', return_value=Mock()):
            success = await manager.warmup(timeout=30)

        assert success is True
        assert manager.get_status()["status"] == EmbeddingLoadStatus.READY

    @pytest.mark.asyncio
    async def test_warmup_returns_false_on_timeout(self):
        """Test that warmup returns False on timeout."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        # Mock the loading function to raise asyncio.TimeoutError
        # This simulates the actual timeout behavior without waiting
        async def mock_load(*args, **kwargs):
            await asyncio.sleep(10)  # Would normally sleep for 10 seconds
            return Mock()

        # Patch asyncio.wait_for to raise TimeoutError
        async def mock_wait_for(coro, timeout):
            # Simulate timeout by raising TimeoutError immediately
            raise asyncio.TimeoutError()

        with patch('app.core.embedding_manager.asyncio.wait_for', side_effect=mock_wait_for):
            success = await manager.warmup(timeout=1)  # Short timeout

        assert success is False
        assert manager.get_status()["status"] == EmbeddingLoadStatus.FAILED
        assert "timed out" in manager.get_status()["error"].lower()

    @pytest.mark.asyncio
    async def test_warmup_returns_false_on_exception(self):
        """Test that warmup returns False on exception."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        # Mock the loading function to raise exception (must be async)
        async def mock_load_error(*args, **kwargs):
            raise RuntimeError("Network error")

        with patch.object(
            manager, '_load_with_timeout_async',
            side_effect=mock_load_error
        ):
            success = await manager.warmup(timeout=30)

        assert success is False
        assert manager.get_status()["status"] == EmbeddingLoadStatus.FAILED
        assert "Network error" in manager.get_status()["error"]

    @pytest.mark.asyncio
    async def test_concurrent_warmup_only_executes_once(self):
        """Test that concurrent warmup calls only execute the load function once."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        # Track how many times the actual load function is called
        load_call_count = 0

        async def mock_load(*args, **kwargs):
            nonlocal load_call_count
            load_call_count += 1
            # Sleep to simulate loading time and allow other tasks to queue
            await asyncio.sleep(0.2)
            return Mock()

        with patch.object(manager, '_load_with_timeout_async', side_effect=mock_load):
            # Launch multiple warmup tasks concurrently
            tasks = [
                asyncio.create_task(manager.warmup(timeout=30))
                for _ in range(5)
            ]

            # Wait for all tasks with a timeout to prevent hanging
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=10.0
            )

        # At least one task should succeed
        success_count = sum(1 for r in results if isinstance(r, bool) and r)
        assert success_count >= 1
        # The critical invariant: load function should only be called once (lock ensures this)
        assert load_call_count == 1

    @pytest.mark.asyncio
    async def test_status_transitions_from_not_started_to_loading(self):
        """Test status transition from NOT_STARTED to LOADING."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        # Create a task that will take some time to complete
        async def slow_load(*args, **kwargs):
            await asyncio.sleep(0.3)  # Take some time
            return Mock()

        with patch.object(manager, '_load_with_timeout_async', side_effect=slow_load):
            # Start warmup but don't wait for it
            task = asyncio.create_task(manager.warmup(timeout=30))

            # Give it a moment to start (it should be in LOADING state now)
            await asyncio.sleep(0.05)

            # Check status is LOADING
            status = manager.get_status()
            if status["status"] != EmbeddingLoadStatus.READY:
                # If not ready yet, it should be LOADING
                assert status["status"] == EmbeddingLoadStatus.LOADING

            # Wait for the task to complete cleanly
            await task

            # After completion, status should be READY
            assert manager.get_status()["status"] == EmbeddingLoadStatus.READY

    @pytest.mark.asyncio
    async def test_get_model_returns_model_when_ready(self):
        """Test that get_model returns the model instance when READY."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        mock_model = Mock()

        # Mock successful warmup
        with patch.object(manager, '_load_with_timeout_async', return_value=mock_model):
            await manager.warmup(timeout=30)

        # Now get_model should return the model
        model = manager.get_model()
        assert model is mock_model

    @pytest.mark.asyncio
    async def test_get_status_includes_load_duration(self):
        """Test that get_status includes load duration after successful load."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        # Mock successful warmup
        with patch.object(manager, '_load_with_timeout_async', return_value=Mock()):
            await manager.warmup(timeout=30)

        status = manager.get_status()

        assert status["load_duration"] is not None
        assert status["load_duration"] > 0
        assert status["load_duration"] < 1.0  # Should be fast with mock

    @pytest.mark.asyncio
    async def test_warmup_when_already_ready_returns_true(self):
        """Test that calling warmup when already READY returns True immediately."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        # First warmup
        with patch.object(manager, '_load_with_timeout_async', return_value=Mock()):
            await manager.warmup(timeout=30)

        # Second warmup should return True immediately
        with patch.object(manager, '_load_with_timeout_async') as mock_load:
            success = await manager.warmup(timeout=30)

        assert success is True
        # Load should not be called again
        mock_load.assert_not_called()

    @pytest.mark.asyncio
    async def test_mirror_fallback_on_failure(self):
        """Test that loading falls back to official HuggingFace when mirror fails."""
        settings = Mock()
        settings.embedding_hf_endpoint = "https://hf-mirror.com"
        settings.embedding_hf_timeout = 20
        settings.embedding_hf_retries = 2

        manager = EmbeddingModelManager(settings)

        call_count = 0
        mock_model = Mock()

        # Mock HuggingFaceEmbedding to simulate mirror failure then official success
        # Use the actual import path from inside the function
        class MockHuggingFaceEmbedding:
            def __init__(self, *args, **kwargs):
                nonlocal call_count
                call_count += 1

                # First call (HF-Mirror) fails
                if call_count == 1:
                    raise ConnectionError("Mirror unreachable")

                # Second call (official HuggingFace) succeeds
                # Store mock model as instance attribute
                self._mock_model = mock_model

        # Patch at the llama_index module level
        with patch('llama_index.embeddings.huggingface.HuggingFaceEmbedding', MockHuggingFaceEmbedding):
            success = await manager.warmup(timeout=30)

        # Should succeed after fallback
        assert success is True
        # Should have tried twice (mirror + official)
        assert call_count == 2
        assert manager.get_status()["status"] == EmbeddingLoadStatus.READY


class TestGetEmbeddingManager:
    """Test cases for get_embedding_manager singleton function."""

    def test_returns_singleton_instance(self):
        """Test that get_embedding_manager returns the same instance."""
        # Clear any existing singleton
        import app.core.embedding_manager as em_module
        em_module._embedding_manager_instance = None

        manager1 = get_embedding_manager()
        manager2 = get_embedding_manager()

        assert manager1 is manager2

    def test_creates_manager_with_settings(self):
        """Test that singleton is created with proper settings."""
        # Clear any existing singleton
        import app.core.embedding_manager as em_module
        em_module._embedding_manager_instance = None

        manager = get_embedding_manager()

        assert isinstance(manager, EmbeddingModelManager)
        assert manager.settings is not None
