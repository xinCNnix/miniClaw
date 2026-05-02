# backend/tests/regression/test_settings_regression.py
"""Regression tests — verify settings system doesn't break existing functionality.

Covers: AC-10 (running agent not affected), AC-2 (LLM config untouched).
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def settings_client(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    config_path = str(tmp_path / "runtime_config.json")
    with patch("app.config.RUNTIME_CONFIG_PATH", config_path), \
         patch("app.api.settings.RUNTIME_CONFIG_PATH", config_path):
        with TestClient(app) as c:
            yield c


@pytest.mark.regression
class TestExistingEndpointsNotBroken:
    """Settings API should not affect existing endpoints."""

    def test_health_endpoint_still_works(self, settings_client):
        resp = settings_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_root_endpoint_still_works(self, settings_client):
        resp = settings_client.get("/")
        assert resp.status_code == 200
        assert "name" in resp.json()

    def test_llm_config_endpoints_still_work(self, settings_client):
        """LLM config endpoints are independent of settings API."""
        resp = settings_client.get("/api/config/llms")
        assert resp.status_code == 200

    def test_config_status_still_works(self, settings_client):
        resp = settings_client.get("/api/config/status")
        assert resp.status_code == 200

    def test_provider_endpoint_still_works(self, settings_client):
        resp = settings_client.get("/api/config/provider")
        assert resp.status_code == 200


@pytest.mark.regression
class TestGetSettingsDefaultBehavior:
    """get_settings() should return valid Settings objects unchanged."""

    def test_get_settings_returns_valid_object(self):
        from app.config import get_settings, Settings
        s = get_settings()
        assert isinstance(s, Settings)
        assert hasattr(s, "max_tool_rounds")
        assert hasattr(s, "enable_smart_stopping")

    def test_default_values_unchanged(self):
        """Default values should not change after adding runtime_config support."""
        from app.config import get_settings
        s = get_settings()
        assert s.max_tool_rounds == 50
        assert s.enable_smart_stopping is True
        assert s.enable_tot is True
        assert s.log_level == "INFO"

    def test_settings_attributes_still_accessible(self):
        """All original Settings attributes still accessible."""
        from app.config import get_settings
        s = get_settings()
        # Spot-check attributes from various categories
        assert hasattr(s, "app_name")
        assert hasattr(s, "port")
        assert hasattr(s, "llm_provider")
        assert hasattr(s, "enable_rag")
        assert hasattr(s, "chunk_size")
        assert hasattr(s, "enable_watchdog")


@pytest.mark.regression
class TestRuntimeConfigIsolation:
    """AC-10: Writing settings should not affect running code until restart."""

    def test_save_does_not_change_current_settings(self, settings_client):
        """After PUT /api/settings, current get_settings() still returns cached values.
        The new value is written to runtime_config.json but get_settings() uses a cache,
        so the running backend is unaffected until restart."""
        from app.config import get_settings, reload_settings

        # Force reload to get current baseline
        s = reload_settings()
        original_val = s.max_tool_rounds

        # Save new value
        settings_client.put("/api/settings", json={"max_tool_rounds": original_val + 1})

        # get_settings() should STILL return the cached value (unchanged)
        s = get_settings()
        assert s.max_tool_rounds == original_val

        # After reload_settings(), the new value is picked up
        s = reload_settings()
        assert s.max_tool_rounds == original_val + 1
