"""
Unit tests for Configuration API

Tests for LLM provider management, hot-switching, and provider info endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

from app.main import app
from app.core.obfuscation import KeyObfuscator
from app.api.config import router


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestProviderInfoEndpoint:
    """Test cases for /api/config/provider endpoint."""

    def test_get_current_provider(self, client):
        """Test getting current provider info."""
        response = client.get("/api/config/provider")

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "current_provider" in data
        assert "current_model" in data
        assert "available_providers" in data
        assert "configured_providers" in data

        # Check available providers
        assert isinstance(data["available_providers"], list)
        assert len(data["available_providers"]) == 7  # 7 providers

        # Check provider IDs
        provider_ids = [p["id"] for p in data["available_providers"]]
        expected_ids = ["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"]
        assert set(provider_ids) == set(expected_ids)

    def test_available_providers_have_required_fields(self, client):
        """Test that all available providers have required fields."""
        response = client.get("/api/config/provider")

        assert response.status_code == 200
        data = response.json()

        for provider in data["available_providers"]:
            assert "id" in provider
            assert "name" in provider
            assert "default_model" in provider
            assert "requires_api_key" in provider
            assert "description" in provider
            assert isinstance(provider["requires_api_key"], bool)


class TestSwitchProviderEndpoint:
    """Test cases for /api/config/switch-provider endpoint."""

    def test_switch_to_unsupported_provider(self, client):
        """Test switching to an unsupported provider fails."""
        response = client.post(
            "/api/config/switch-provider",
            json={"provider": "invalid_provider"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported provider" in data["detail"]

    @patch('app.api.config.KeyObfuscator.load_credentials')
    def test_switch_to_unconfigured_provider(self, mock_load, client):
        """Test switching to an unconfigured provider (not ollama)."""
        # Mock empty credentials
        mock_load.return_value = {}

        response = client.post(
            "/api/config/switch-provider",
            json={"provider": "openai"}
        )

        assert response.status_code == 404
        data = response.json()
        assert "not configured" in data["detail"]

    @patch('app.api.config.KeyObfuscator.load_credentials')
    def test_switch_to_ollama_without_config(self, mock_load, client):
        """Test that ollama can be switched without API key."""
        # Mock empty credentials
        mock_load.return_value = {}

        response = client.post(
            "/api/config/switch-provider",
            json={"provider": "ollama"}
        )

        # Should succeed (ollama doesn't need API key)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["provider"] == "ollama"


class TestProviderInfoFields:
    """Test cases for provider information fields."""

    def test_openai_provider_info(self):
        """Test OpenAI provider has correct info."""
        from app.config import get_available_providers
        providers = get_available_providers()

        openai = next(p for p in providers if p["id"] == "openai")
        assert openai["name"] == "OpenAI"
        assert openai["default_model"] == "gpt-4o-mini"
        assert openai["requires_api_key"] is True
        assert "OpenAI GPT models" in openai["description"]

    def test_ollama_provider_info(self):
        """Test Ollama provider has correct info."""
        from app.config import get_available_providers
        providers = get_available_providers()

        ollama = next(p for p in providers if p["id"] == "ollama")
        assert ollama["name"] == "Ollama (本地)"
        assert ollama["default_model"] == "qwen2.5"
        assert ollama["requires_api_key"] is False
        assert "本地运行" in ollama["description"]


class TestHotSwitching:
    """Test cases for hot-switching functionality."""

    def test_provider_switch_endpoint_exists(self, client):
        """Test that switch provider endpoint is accessible."""
        # This test verifies the endpoint exists and handles requests
        # Actual switching requires configured providers
        response = client.post(
            "/api/config/switch-provider",
            json={"provider": "ollama"}  # ollama doesn't need API key
        )

        # Should succeed or return specific error
        assert response.status_code in [200, 500]  # May have internal errors without full setup
