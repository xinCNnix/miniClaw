"""Tests for /api/settings endpoints."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def client(tmp_path):
    """Create test client with isolated runtime_config path."""
    from fastapi.testclient import TestClient
    from app.main import app

    config_path = str(tmp_path / "runtime_config.json")

    with patch("app.config.RUNTIME_CONFIG_PATH", config_path), \
         patch("app.api.settings.RUNTIME_CONFIG_PATH", config_path):
        with TestClient(app) as c:
            yield c


def test_get_settings_returns_groups(client):
    """GET /api/settings returns all groups with settings."""
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data
    assert len(data["groups"]) == 12


def test_get_settings_has_values(client):
    """Each setting has value, default, type, descriptions, tooltip."""
    resp = client.get("/api/settings")
    data = resp.json()
    first_setting = data["groups"][0]["sections"][0]["settings"][0]
    assert "key" in first_setting
    assert "value" in first_setting
    assert "default" in first_setting
    assert "type" in first_setting
    assert "description_zh" in first_setting
    assert "description_en" in first_setting
    assert "tooltip_zh" in first_setting
    assert "tooltip_en" in first_setting


def test_put_settings_updates_value(client, tmp_path):
    """PUT /api/settings writes to runtime_config.json."""
    resp = client.put("/api/settings", json={
        "max_tool_rounds": 99,
        "enable_smart_stopping": False,
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["restart_required"] is True

    config_file = tmp_path / "runtime_config.json"
    assert config_file.exists()
    saved = json.loads(config_file.read_text())
    assert saved["max_tool_rounds"] == 99


def test_put_settings_rejects_unknown_key(client):
    """PUT rejects keys not in whitelist."""
    resp = client.put("/api/settings", json={
        "port": 9999,
    })
    assert resp.status_code == 400
    assert "not" in resp.json()["detail"].lower() and "allowed" in resp.json()["detail"].lower()


def test_put_settings_validates_range(client):
    """PUT rejects values outside allowed range."""
    resp = client.put("/api/settings", json={
        "max_tool_rounds": 9999,
    })
    assert resp.status_code == 400


def test_put_settings_validates_type(client):
    """PUT rejects wrong type values."""
    resp = client.put("/api/settings", json={
        "max_tool_rounds": "not_a_number",
    })
    assert resp.status_code == 400


def test_reset_settings(client, tmp_path):
    """POST /api/settings/reset deletes runtime_config.json."""
    config_file = tmp_path / "runtime_config.json"
    config_file.write_text(json.dumps({"max_tool_rounds": 99}))

    resp = client.post("/api/settings/reset")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert not config_file.exists()


def test_get_external_keys(client):
    """GET /api/settings/external-keys returns key status."""
    resp = client.get("/api/settings/external-keys")
    assert resp.status_code == 200
    data = resp.json()
    assert "services" in data
    assert any(s["key"] == "BAIDU_API_KEY" for s in data["services"])
