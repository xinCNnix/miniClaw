# backend/tests/unit/test_settings_registry.py
"""Unit tests for settings_registry.py — registry structure, key lookup, group queries."""

import pytest
from app.core.settings_registry import (
    SETTINGS_DEFINITIONS,
    SETTINGS_GROUPS,
    get_setting_definition,
    get_all_keys,
    get_settings_by_group,
    get_sections_for_group,
)


@pytest.mark.unit
class TestRegistryStructure:
    def test_has_12_groups(self):
        assert len(SETTINGS_GROUPS) == 12

    def test_group_ids_are_unique(self):
        ids = [g["id"] for g in SETTINGS_GROUPS]
        assert len(ids) == len(set(ids))

    def test_every_group_has_required_fields(self):
        for g in SETTINGS_GROUPS:
            assert "id" in g
            assert "label_zh" in g
            assert "label_en" in g
            assert "icon" in g
            assert "restart_required" in g

    def test_setting_count_matches_expectation(self):
        assert len(SETTINGS_DEFINITIONS) >= 100  # At least 100 settings registered


@pytest.mark.unit
class TestSettingDefinition:
    def test_every_setting_has_required_fields(self):
        for s in SETTINGS_DEFINITIONS:
            assert s.key
            assert s.type in ("bool", "int", "float", "str", "select")
            assert s.group
            assert s.section
            assert s.description_zh
            assert s.description_en
            assert s.tooltip_zh
            assert s.tooltip_en

    def test_every_setting_belongs_to_valid_group(self):
        group_ids = {g["id"] for g in SETTINGS_GROUPS}
        for s in SETTINGS_DEFINITIONS:
            assert s.group in group_ids, f"Setting '{s.key}' has invalid group '{s.group}'"

    def test_number_settings_have_range(self):
        for s in SETTINGS_DEFINITIONS:
            if s.type in ("int", "float"):
                assert s.range_min is not None, f"Setting '{s.key}' ({s.type}) missing range_min"
                assert s.range_max is not None, f"Setting '{s.key}' ({s.type}) missing range_max"
                assert s.range_min < s.range_max, f"Setting '{s.key}' range_min >= range_max"

    def test_select_settings_have_options(self):
        for s in SETTINGS_DEFINITIONS:
            if s.type == "select":
                assert s.options is not None, f"Setting '{s.key}' (select) missing options"
                assert len(s.options) >= 2, f"Setting '{s.key}' has fewer than 2 options"
                for opt in s.options:
                    assert "value" in opt
                    assert "label_zh" in opt
                    assert "label_en" in opt


@pytest.mark.unit
class TestLookupFunctions:
    def test_get_setting_definition_found(self):
        s = get_setting_definition("max_tool_rounds")
        assert s is not None
        assert s.key == "max_tool_rounds"
        assert s.type == "int"

    def test_get_setting_definition_not_found(self):
        s = get_setting_definition("NONEXISTENT_KEY")
        assert s is None

    def test_get_all_keys_contains_known_keys(self):
        keys = get_all_keys()
        assert "max_tool_rounds" in keys
        assert "enable_tot" in keys
        assert "log_level" in keys

    def test_get_all_keys_no_infrastructure_keys(self):
        keys = get_all_keys()
        assert "port" not in keys
        assert "host" not in keys
        assert "cors_origins" not in keys
        assert "openai_api_key" not in keys

    def test_get_settings_by_group(self):
        agent_settings = get_settings_by_group("agent_behavior")
        assert len(agent_settings) > 0
        assert all(s.group == "agent_behavior" for s in agent_settings)

    def test_get_sections_for_group(self):
        sections = get_sections_for_group("agent_behavior")
        assert "agent_execution" in sections
        assert "reflection" in sections
        assert "watchdog" in sections

    def test_to_dict_includes_value(self):
        s = get_setting_definition("max_tool_rounds")
        d = s.to_dict(current_value=99)
        assert d["value"] == 99
        assert d["default"] == 50
        assert d["type"] == "int"
        assert "range" in d

    def test_to_dict_select_includes_options(self):
        s = get_setting_definition("log_level")
        d = s.to_dict(current_value="INFO")
        assert "options" in d
        assert len(d["options"]) == 4
