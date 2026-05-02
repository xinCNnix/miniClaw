"""Tests for runtime_config.json merge in get_settings()."""

import json
import os
import tempfile
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch):
    """Reset the cached settings and env overrides before and after each test."""
    import app.config as config_module
    config_module._cached_settings = None
    # Save env state for keys that runtime_config may have set
    import os
    from app.core.settings_registry import get_all_keys
    saved_env = {}
    all_keys = get_all_keys()
    for key in all_keys:
        upper = key.upper()
        if upper in os.environ:
            saved_env[upper] = os.environ[upper]
    yield
    config_module._cached_settings = None
    # Restore env state
    for key in all_keys:
        upper = key.upper()
        if upper in saved_env:
            os.environ[upper] = saved_env[upper]
        elif upper in os.environ:
            del os.environ[upper]


@pytest.fixture
def runtime_config_file(tmp_path, monkeypatch):
    """Create a temporary runtime_config.json."""
    config_file = tmp_path / "runtime_config.json"
    monkeypatch.setattr("app.config.RUNTIME_CONFIG_PATH", str(config_file))
    return config_file


def test_load_runtime_config_merges_values(runtime_config_file):
    """runtime_config.json values override defaults."""
    runtime_config_file.write_text(json.dumps({
        "_version": 1,
        "max_tool_rounds": 99,
        "enable_smart_stopping": False,
    }))

    from app.config import get_settings
    s = get_settings()
    assert s.max_tool_rounds == 99
    assert s.enable_smart_stopping is False


def test_load_runtime_config_ignores_metadata(runtime_config_file):
    """_version and _updated_at should not be treated as settings."""
    runtime_config_file.write_text(json.dumps({
        "_version": 1,
        "_updated_at": "2026-05-01",
        "max_tool_rounds": 80,
    }))

    from app.config import get_settings
    s = get_settings()
    assert s.max_tool_rounds == 80


def test_load_runtime_config_rejects_unknown_keys(runtime_config_file):
    """Unknown keys should be silently ignored."""
    runtime_config_file.write_text(json.dumps({
        "port": 9999,
        "cors_origins": ["http://evil.com"],
        "UNKNOWN_KEY": "should_be_ignored",
        "max_tool_rounds": 77,
    }))

    from app.config import get_settings
    s = get_settings()
    assert s.port != 9999  # Should NOT be overridden
    assert s.max_tool_rounds == 77  # Valid key should work


def test_load_runtime_config_no_file():
    """When runtime_config.json doesn't exist, defaults should be used."""
    from app.config import get_settings
    s = get_settings()
    assert s.max_tool_rounds == 50  # default


def test_concurrent_get_settings_safe(runtime_config_file):
    """Multiple threads calling get_settings() should not corrupt env."""
    import threading

    runtime_config_file.write_text(json.dumps({
        "max_tool_rounds": 88,
        "enable_smart_stopping": False,
    }))

    errors = []

    def worker():
        try:
            from app.config import get_settings
            s = get_settings()
            if s.max_tool_rounds != 88:
                errors.append(f"Expected 88, got {s.max_tool_rounds}")
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread safety errors: {errors}"
