"""
Settings API — Read/write runtime configuration.

GET  /api/settings              — Return all groups with current values
PUT  /api/settings              — Batch update settings (writes runtime_config.json)
POST /api/settings/reset        — Delete runtime_config.json (restore defaults)
GET  /api/settings/external-keys — Return external service key status
PUT  /api/settings/external-keys/{service} — Save external service key (encrypted)
"""

import json
import os
import logging
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.settings_registry import (
    SETTINGS_DEFINITIONS,
    SETTINGS_GROUPS,
    SECTIONS_REGISTRY,
    SettingDefinition,
    get_setting_definition,
    get_all_keys,
    get_sections_for_group,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])

_config_write_lock = threading.Lock()

RUNTIME_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "runtime_config.json"
)

# External service keys (managed via encrypted storage, not runtime_config.json)
EXTERNAL_SERVICES = [
    {
        "key": "BAIDU_API_KEY",
        "name_zh": "百度搜索",
        "name_en": "Baidu Search",
        "description_zh": "百度搜索 API Key，用于 baidu-search 技能",
        "description_en": "Baidu Search API Key for baidu-search skill",
    },
]


class UpdateSettingsRequest(BaseModel):
    """Flat key-value pairs to update. (Not used directly — endpoint takes Dict[str, Any])"""
    pass


class SaveExternalKeyRequest(BaseModel):
    api_key: str


def _read_runtime_config() -> dict:
    try:
        p = Path(RUNTIME_CONFIG_PATH)
        if not p.exists():
            return {}
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"[settings] runtime_config.json has invalid JSON: {e}")
        return {}
    except Exception as e:
        logger.warning(f"[settings] Failed to read runtime_config.json: {e}")
        return {}


def _write_runtime_config(config: dict) -> None:
    p = Path(RUNTIME_CONFIG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing file
    if p.exists():
        shutil.copy2(str(p), str(p) + ".bak")

    config["_version"] = 1
    config["_updated_at"] = datetime.now().isoformat()

    with open(p, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    logger.info(f"[settings] Wrote runtime_config.json ({len(config)} keys)")


def _validate_setting(key: str, value: Any) -> Optional[str]:
    """Validate a setting value against its definition. Returns error message or None."""
    defn = get_setting_definition(key)
    if defn is None:
        return f"Setting '{key}' is not in the allowed registry."

    if defn.type == "bool":
        if not isinstance(value, bool):
            return f"Setting '{key}' expects bool, got {type(value).__name__}."
    elif defn.type == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            return f"Setting '{key}' expects int, got {type(value).__name__}."
        if defn.range_min is not None and value < defn.range_min:
            return f"Setting '{key}' value {value} is below minimum {defn.range_min}."
        if defn.range_max is not None and value > defn.range_max:
            return f"Setting '{key}' value {value} exceeds maximum {defn.range_max}."
    elif defn.type == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"Setting '{key}' expects float, got {type(value).__name__}."
        if defn.range_min is not None and value < defn.range_min:
            return f"Setting '{key}' value {value} is below minimum {defn.range_min}."
        if defn.range_max is not None and value > defn.range_max:
            return f"Setting '{key}' value {value} exceeds maximum {defn.range_max}."
    elif defn.type == "select":
        valid = [o["value"] for o in (defn.options or [])]
        if value not in valid:
            return f"Setting '{key}' value '{value}' not in allowed options: {valid}."
    elif defn.type == "str":
        if not isinstance(value, str):
            return f"Setting '{key}' expects str, got {type(value).__name__}."

    logger.debug(f"[settings] Validated '{key}' = {value!r} (type={defn.type})")
    return None


@router.get("/settings")
async def get_all_settings():
    """Return all settings groups with current values.

    Returns the runtime_config.json values (pending restart) if they exist,
    otherwise falls back to the cached Settings values.
    """
    from app.config import get_settings
    current = get_settings()

    # Read pending runtime config values (written but not yet applied)
    pending = _read_runtime_config()

    allowed_keys = get_all_keys()
    groups = []

    logger.debug(f"[settings] GET /settings — building {len(SETTINGS_GROUPS)} groups")

    for group_def in SETTINGS_GROUPS:
        group_id = group_def["id"]
        section_ids = get_sections_for_group(group_id)
        sections = []

        for section_id in section_ids:
            section_settings = []
            for sdef in SETTINGS_DEFINITIONS:
                if sdef.group != group_id or sdef.section != section_id:
                    continue
                # Prefer pending runtime_config value over cached Settings value
                if sdef.key in pending:
                    current_val = pending[sdef.key]
                else:
                    current_val = getattr(current, sdef.key, sdef.default)
                section_settings.append(sdef.to_dict(current_value=current_val))

            if section_settings:
                sections.append({
                    "id": section_id,
                    "label_zh": SECTIONS_REGISTRY.get(section_id, {}).get("label_zh", section_id),
                    "label_en": SECTIONS_REGISTRY.get(section_id, {}).get("label_en", section_id),
                    "settings": section_settings,
                })

        groups.append({
            **group_def,
            "sections": sections,
        })

    total_settings = sum(len(s["settings"]) for g in groups for s in g["sections"])
    logger.info(f"[settings] GET /settings — returned {len(groups)} groups, {total_settings} settings")
    return {"groups": groups}


@router.put("/settings")
async def update_settings(request: Dict[str, Any]):
    """Batch update settings. Only whitelisted keys accepted."""
    allowed = get_all_keys()
    errors = []
    clean_updates = {}

    logger.debug(f"[settings] PUT /settings — received {len(request)} keys")

    for key, value in request.items():
        if key.startswith("_"):
            continue
        if key not in allowed:
            errors.append(f"Key '{key}' is not an allowed runtime setting.")
            continue
        err = _validate_setting(key, value)
        if err:
            errors.append(err)
            continue
        clean_updates[key] = value

    if errors:
        logger.warning(f"[settings] PUT /settings rejected {len(errors)} invalid keys: {errors[:3]}")
        raise HTTPException(status_code=400, detail="; ".join(errors))

    with _config_write_lock:
        config = _read_runtime_config()
        config.update(clean_updates)
        _write_runtime_config(config)

    # Determine restart requirement
    restart_required = any(
        get_setting_definition(k) and SETTINGS_GROUPS[
            [g["id"] for g in SETTINGS_GROUPS].index(get_setting_definition(k).group)
        ].get("restart_required", True)
        for k in clean_updates
    )

    logger.info(f"[settings] PUT /settings — updated {len(clean_updates)} keys, restart_required={restart_required}")
    return {"success": True, "restart_required": restart_required}


@router.post("/settings/reset")
async def reset_settings():
    """Delete runtime_config.json to restore all defaults."""
    p = Path(RUNTIME_CONFIG_PATH)
    if p.exists():
        shutil.copy2(str(p), str(p) + ".bak")
        p.unlink()
        logger.info("[settings] POST /settings/reset — deleted runtime_config.json, backup saved")
    else:
        logger.debug("[settings] POST /settings/reset — no runtime_config.json to delete")
    return {"success": True}


@router.get("/settings/external-keys")
async def get_external_keys():
    """Return external service key status (configured or not, no values)."""
    services = []
    for svc in EXTERNAL_SERVICES:
        has_key = bool(os.environ.get(svc["key"], ""))
        services.append({
            **svc,
            "has_key": has_key,
        })
    return {"services": services}


@router.put("/settings/external-keys/{service}")
async def save_external_key(service: str, request: SaveExternalKeyRequest):
    """Save an external service API key using encrypted storage."""
    valid_keys = [s["key"] for s in EXTERNAL_SERVICES]
    if service not in valid_keys:
        logger.warning(f"[settings] PUT external-keys — rejected unknown service: {service}")
        raise HTTPException(status_code=400, detail=f"Unknown service: {service}")

    try:
        from app.core.obfuscation import KeyObfuscator
        ext_keys_path = Path(RUNTIME_CONFIG_PATH).parent / "external_keys.json"
        ext_keys = {}
        if ext_keys_path.exists():
            ext_keys = json.loads(ext_keys_path.read_text(encoding="utf-8"))
        ext_keys[service] = KeyObfuscator.obfuscate(request.api_key)
        ext_keys_path.write_text(json.dumps(ext_keys, indent=2, ensure_ascii=False), encoding="utf-8")

        # Inject into current process env
        os.environ[service] = request.api_key

        logger.info(f"[settings] Saved external key for {service}")
        return {"success": True}
    except Exception as e:
        logger.error(f"[settings] Failed to save external key for {service}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
