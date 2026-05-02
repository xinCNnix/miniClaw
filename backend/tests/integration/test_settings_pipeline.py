# backend/tests/integration/test_settings_pipeline.py
"""Integration tests for the full settings write -> read pipeline.

Covers: AC-4 (save & reload consistency), AC-5 (reset), AC-11 (concurrent writes).
"""

import json
import pytest
import threading
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def isolated_runtime_config(tmp_path):
    """Provide an isolated runtime_config.json path."""
    config_path = str(tmp_path / "runtime_config.json")
    return config_path


@pytest.fixture
def settings_client(isolated_runtime_config):
    """FastAPI test client with isolated config path."""
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.config.RUNTIME_CONFIG_PATH", isolated_runtime_config), \
         patch("app.api.settings.RUNTIME_CONFIG_PATH", isolated_runtime_config):
        with TestClient(app) as c:
            yield c


@pytest.mark.integration
class TestSaveReloadPipeline:
    """AC-4: Save -> read back -> verify consistency."""

    def test_save_and_read_back_single_value(self, settings_client, isolated_runtime_config):
        """Write one value via API, read it back, verify match."""
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": 77})
        assert resp.status_code == 200

        resp = settings_client.get("/api/settings")
        data = resp.json()
        for group in data["groups"]:
            for section in group["sections"]:
                for s in section["settings"]:
                    if s["key"] == "max_tool_rounds":
                        assert s["value"] == 77

    def test_save_and_read_back_multiple_values(self, settings_client):
        """Write multiple values, read back, all match."""
        resp = settings_client.put("/api/settings", json={
            "max_tool_rounds": 88,
            "enable_smart_stopping": False,
            "log_level": "DEBUG",
        })
        assert resp.status_code == 200

        resp = settings_client.get("/api/settings")
        data = resp.json()
        found = {}
        for group in data["groups"]:
            for section in group["sections"]:
                for s in section["settings"]:
                    found[s["key"]] = s["value"]

        assert found["max_tool_rounds"] == 88
        assert found["enable_smart_stopping"] is False
        assert found["log_level"] == "DEBUG"

    def test_save_preserves_previous_values(self, settings_client):
        """Second save doesn't lose first save's values."""
        settings_client.put("/api/settings", json={"max_tool_rounds": 77})
        settings_client.put("/api/settings", json={"enable_smart_stopping": False})

        resp = settings_client.get("/api/settings")
        data = resp.json()
        found = {}
        for group in data["groups"]:
            for section in group["sections"]:
                for s in section["settings"]:
                    found[s["key"]] = s["value"]

        assert found["max_tool_rounds"] == 77
        assert found["enable_smart_stopping"] is False

    def test_save_creates_backup(self, settings_client, isolated_runtime_config):
        """Writing creates a .bak backup of previous config."""
        settings_client.put("/api/settings", json={"max_tool_rounds": 60})
        settings_client.put("/api/settings", json={"max_tool_rounds": 70})

        backup_path = isolated_runtime_config + ".bak"
        assert Path(backup_path).exists()
        backup = json.loads(Path(backup_path).read_text())
        assert backup["max_tool_rounds"] == 60


@pytest.mark.integration
class TestResetPipeline:
    """AC-5: Reset restores defaults."""

    def test_reset_deletes_config_file(self, settings_client, isolated_runtime_config):
        """POST /api/settings/reset deletes runtime_config.json."""
        settings_client.put("/api/settings", json={"max_tool_rounds": 99})
        assert Path(isolated_runtime_config).exists()

        resp = settings_client.post("/api/settings/reset")
        assert resp.status_code == 200
        assert not Path(isolated_runtime_config).exists()

    def test_reset_restores_default_values(self, settings_client):
        """After reset, GET returns default values."""
        settings_client.put("/api/settings", json={"max_tool_rounds": 99})
        settings_client.post("/api/settings/reset")

        resp = settings_client.get("/api/settings")
        data = resp.json()
        for group in data["groups"]:
            for section in group["sections"]:
                for s in section["settings"]:
                    if s["key"] == "max_tool_rounds":
                        assert s["value"] == 50  # default

    def test_reset_creates_backup_before_delete(self, settings_client, isolated_runtime_config):
        """Reset backs up the config file before deleting."""
        settings_client.put("/api/settings", json={"max_tool_rounds": 99})
        settings_client.post("/api/settings/reset")

        backup_path = isolated_runtime_config + ".bak"
        assert Path(backup_path).exists()


@pytest.mark.integration
class TestConcurrentWrites:
    """AC-11: Concurrent PUT requests don't corrupt the file."""

    def test_concurrent_writes_no_corruption(self, settings_client, isolated_runtime_config):
        """10 concurrent writes produce a valid JSON file."""
        errors = []
        results = [None] * 10

        def writer(idx, value):
            try:
                resp = settings_client.put("/api/settings", json={"max_tool_rounds": value})
                results[idx] = resp.status_code
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=writer, args=(i, 50 + i))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent write errors: {errors}"
        assert all(r == 200 for r in results), f"Some writes failed: {results}"

        # File should be valid JSON
        data = json.loads(Path(isolated_runtime_config).read_text())
        assert "max_tool_rounds" in data
        assert isinstance(data["max_tool_rounds"], int)

    def test_concurrent_gets_dont_pollute_env(self, settings_client):
        """20 concurrent GET requests don't leave stale env vars."""
        settings_client.put("/api/settings", json={"max_tool_rounds": 55})

        errors = []

        def reader():
            try:
                import os
                resp = settings_client.get("/api/settings")
                assert resp.status_code == 200
                # Runtime config keys should NOT leak into os.environ
                # (they're cleaned up after get_settings())
                if "MAX_TOOL_ROUNDS" in os.environ:
                    errors.append("MAX_TOOL_ROUNDS leaked into os.environ")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=reader) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Env pollution detected: {errors}"
