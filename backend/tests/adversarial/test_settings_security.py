# backend/tests/adversarial/test_settings_security.py
"""Adversarial tests for settings API — injection, boundary, and security tests.

Covers: AC-6 edge cases, injection prevention.
"""

import pytest
from unittest.mock import patch
from pathlib import Path


@pytest.fixture
def settings_client(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    config_path = str(tmp_path / "runtime_config.json")
    with patch("app.config.RUNTIME_CONFIG_PATH", config_path), \
         patch("app.api.settings.RUNTIME_CONFIG_PATH", config_path):
        with TestClient(app) as c:
            yield c


@pytest.mark.adversarial
class TestInfrastructureKeyInjection:
    """Verify infrastructure/sensitive keys cannot be changed via settings API."""

    def test_cannot_change_port(self, settings_client):
        resp = settings_client.put("/api/settings", json={"port": 9999})
        assert resp.status_code == 400

    def test_cannot_change_host(self, settings_client):
        resp = settings_client.put("/api/settings", json={"host": "evil.com"})
        assert resp.status_code == 400

    def test_cannot_change_cors_origins(self, settings_client):
        resp = settings_client.put("/api/settings", json={"cors_origins": ["http://evil.com"]})
        assert resp.status_code == 400

    def test_cannot_inject_api_key(self, settings_client):
        resp = settings_client.put("/api/settings", json={"openai_api_key": "sk-stolen-key"})
        assert resp.status_code == 400

    def test_cannot_inject_custom_api_key(self, settings_client):
        resp = settings_client.put("/api/settings", json={"custom_api_key": "injected"})
        assert resp.status_code == 400

    def test_cannot_change_data_dir(self, settings_client):
        resp = settings_client.put("/api/settings", json={"data_dir": "/etc"})
        assert resp.status_code == 400


@pytest.mark.adversarial
class TestBoundaryValues:
    """Test extreme boundary values."""

    def test_int_at_exact_min(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": 1})
        assert resp.status_code == 200

    def test_int_at_exact_max(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": 200})
        assert resp.status_code == 200

    def test_int_one_below_min(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": 0})
        assert resp.status_code == 400

    def test_int_one_above_max(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": 201})
        assert resp.status_code == 400

    def test_negative_int(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": -1})
        assert resp.status_code == 400

    def test_very_large_int(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": 999999999})
        assert resp.status_code == 400

    def test_float_edge_case_zero(self, settings_client):
        resp = settings_client.put("/api/settings", json={"agent_reflection_quality_threshold": 0.0})
        assert resp.status_code == 200

    def test_float_edge_case_max(self, settings_client):
        resp = settings_client.put("/api/settings", json={"agent_reflection_quality_threshold": 10.0})
        assert resp.status_code == 200


@pytest.mark.adversarial
class TestTypeConfusion:
    """Test type confusion attacks."""

    def test_send_string_as_int(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": "50"})
        assert resp.status_code == 400

    def test_send_float_as_bool(self, settings_client):
        resp = settings_client.put("/api/settings", json={"enable_smart_stopping": 1.0})
        assert resp.status_code == 400

    def test_send_list_as_value(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": [1, 2, 3]})
        assert resp.status_code == 400

    def test_send_null_as_value(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": None})
        assert resp.status_code == 400

    def test_send_nested_object(self, settings_client):
        resp = settings_client.put("/api/settings", json={"max_tool_rounds": {"value": 50}})
        assert resp.status_code == 400


@pytest.mark.adversarial
class TestMetadataInjection:
    """Verify metadata fields cannot be injected via PUT."""

    def test_cannot_inject_version(self, settings_client, tmp_path):
        config_path = tmp_path / "runtime_config.json"
        resp = settings_client.put("/api/settings", json={
            "max_tool_rounds": 77,
            "_version": 999,
        })
        assert resp.status_code == 200

        # _version should be managed by the system, not user input
        data = __import__("json").loads(config_path.read_text())
        assert data["_version"] == 1  # System-controlled
