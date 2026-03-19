"""
LLM Configuration Manager - Multi-LLM Support

This module manages multiple LLM configurations with secure storage.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

from app.config import LLMConfig
from app.core.obfuscation import KeyObfuscator


logger = logging.getLogger(__name__)


# ============================================================================
# LLM ID Generation
# ============================================================================

def generate_llm_id(provider: str, model: str, base_url: str = "", name: str = "") -> str:
    """
    Generate unique LLM ID from provider, model, and optional base_url/name.

    Examples:
        - "qwen" + "qwen-plus" → "qwen-qwen-plus"
        - "custom" + "openrouter/hunter-alpha" → "custom-openrouter-hunter-alpha"
        - "custom" + "gpt-4" + "https://api.openai.com" → "custom-gpt-4-a1b2c3d4" (with URL hash)

    Args:
        provider: Provider name (qwen, openai, custom, etc.)
        model: Model name
        base_url: Base URL (optional, used for custom providers to ensure uniqueness)
        name: Display name (optional, used as alternative to base_url)

    Returns:
        Unique LLM ID
    """
    import hashlib

    # 将模型名中的特殊字符替换为连字符
    model_slug = model.replace("/", "-").replace("_", "-").replace(".", "-").replace(":", "-")

    # For custom providers, add hash to ensure uniqueness
    # Include both model and base_url/name to differentiate different models
    if provider == "custom":
        # Build unique string from model + base_url or name
        # This ensures different models get different IDs even with same base_url
        unique_parts = [model_slug]
        if base_url:
            unique_parts.append(base_url)
        elif name:
            unique_parts.append(name)

        unique_str = "-".join(unique_parts)
        url_hash = hashlib.md5(unique_str.encode()).hexdigest()[:8]
        return f"{provider}-{model_slug}-{url_hash}"

    return f"{provider}-{model_slug}"


# ============================================================================
# LLM Configuration Storage
# ============================================================================

CREDENTIALS_FILE = Path("data/credentials.encrypted")


def load_all_llm_configs() -> List[LLMConfig]:
    """
    Load all LLM configurations from encrypted storage.

    Returns:
        List of LLMConfig objects (with decrypted API keys)
    """
    try:
        # 加载加密的凭证
        credentials = KeyObfuscator.load_credentials()

        # 检查是否是新格式
        if "llms" not in credentials:
            # 旧格式，自动迁移
            logger.info("Detected old config format, migrating...")
            migrate_old_config_to_new(credentials)
            credentials = KeyObfuscator.load_credentials()

        llms_data = credentials.get("llms", {})
        llms = []

        for llm_id, llm_data in llms_data.items():
            try:
                # 解密 API Key（如果存在）
                api_key = ""
                if "api_key" in llm_data:
                    encrypted_key = llm_data["api_key"]
                    # 尝试解密
                    decrypted = KeyObfuscator.deobfuscate(encrypted_key)
                    if decrypted:
                        api_key = decrypted
                    else:
                        # 解密失败，可能是已经解密的（兼容性）
                        api_key = encrypted_key

                llm_config = LLMConfig(
                    id=llm_id,
                    provider=llm_data.get("provider", "custom"),
                    name=llm_data.get("name", llm_id),
                    model=llm_data.get("model", ""),
                    base_url=llm_data.get("base_url", ""),
                    api_key=api_key,
                )
                llms.append(llm_config)

            except Exception as e:
                logger.warning(f"Failed to load LLM config {llm_id}: {e}")
                continue

        return llms

    except Exception as e:
        logger.error(f"Failed to load LLM configs: {e}")
        return []


def load_llm_config(llm_id: str) -> Optional[LLMConfig]:
    """
    Load a specific LLM configuration.

    Args:
        llm_id: LLM ID (e.g., "custom-openrouter-hunter-alpha")

    Returns:
        LLMConfig object or None if not found
    """
    llms = load_all_llm_configs()
    for llm in llms:
        if llm.id == llm_id:
            return llm
    return None


def save_llm_config(llm_config: LLMConfig) -> None:
    """
    Save or update LLM configuration.

    Args:
        llm_config: LLMConfig object to save
    """
    # 加载现有配置
    credentials = KeyObfuscator.load_credentials()

    # 确保有 llms 字段
    if "llms" not in credentials:
        credentials["llms"] = {}

    # 加密 API Key
    encrypted_key = KeyObfuscator.obfuscate(llm_config.api_key)

    # Use the provided name directly - don't override it for custom providers
    # The user has explicitly set this name, so respect it
    display_name = llm_config.name if llm_config.name else llm_config.model

    # 保存配置（加密 API Key）
    credentials["llms"][llm_config.id] = {
        "id": llm_config.id,
        "provider": llm_config.provider,
        "name": display_name,
        "model": llm_config.model,
        "base_url": llm_config.base_url,
        "api_key": encrypted_key,  # 加密存储
    }

    # 保存到文件
    KeyObfuscator.save_credentials(credentials)
    logger.info(f"Saved LLM config: {llm_config.id}")


def delete_llm_config(llm_id: str) -> bool:
    """
    Delete LLM configuration.

    Args:
        llm_id: LLM ID to delete

    Returns:
        True if deleted, False if not found
    """
    credentials = KeyObfuscator.load_credentials()

    if "llms" not in credentials or llm_id not in credentials["llms"]:
        return False

    del credentials["llms"][llm_id]

    # 如果没有 LLM 了，删除 llms 字段
    if not credentials["llms"]:
        del credentials["llms"]

    KeyObfuscator.save_credentials(credentials)
    logger.info(f"Deleted LLM config: {llm_id}")
    return True


def get_current_llm_id() -> str:
    """
    Get current active LLM ID.

    Returns:
        Current LLM ID (e.g., "custom-openrouter-hunter-alpha")
    """
    try:
        credentials = KeyObfuscator.load_credentials()

        # 新格式
        if "current_llm_id" in credentials:
            return credentials["current_llm_id"]

        # 旧格式，自动迁移
        if "_current_provider" in credentials:
            old_provider = credentials["_current_provider"]
            # 尝试找到对应的 LLM ID
            llms = credentials.get("llms", {})
            for llm_id, llm_data in llms.items():
                if llm_data.get("provider") == old_provider:
                    set_current_llm_id(llm_id)
                    return llm_id

            # 没找到，使用默认 ID
            default_id = f"{old_provider}-default"
            if default_id in llms:
                set_current_llm_id(default_id)
                return default_id

    except Exception as e:
        logger.error(f"Failed to get current LLM ID: {e}")

    # 默认值
    return "qwen-default"


def set_current_llm_id(llm_id: str) -> None:
    """
    Set current active LLM.

    Args:
        llm_id: LLM ID to set as current
    """
    credentials = KeyObfuscator.load_credentials()

    # 确保 llms 字段存在
    if "llms" not in credentials:
        credentials["llms"] = {}

    # 验证 LLM 存在
    if llm_id not in credentials["llms"]:
        raise ValueError(f"LLM {llm_id} not found")

    credentials["current_llm_id"] = llm_id
    KeyObfuscator.save_credentials(credentials)
    logger.info(f"Set current LLM: {llm_id}")


def llm_exists(llm_id: str) -> bool:
    """
    Check if LLM configuration exists.

    Args:
        llm_id: LLM ID to check

    Returns:
        True if exists, False otherwise
    """
    try:
        credentials = KeyObfuscator.load_credentials()
        return "llms" in credentials and llm_id in credentials["llms"]
    except Exception:
        return False


# ============================================================================
# Migration
# ============================================================================

def migrate_old_config_to_new(old_credentials: Dict) -> None:
    """
    Migrate old config format to new format.

    旧格式：
    {
      "_current_provider": "qwen",
      "qwen": {"api_key": "...", "model": "..."}
    }

    新格式：
    {
      "current_llm_id": "qwen-default",
      "llms": {
        "qwen-default": {"provider": "qwen", "api_key": "...", "model": "..."}
      }
    }
    """
    logger.info("Starting config migration...")

    new_credentials = {
        "llms": {},
        "current_llm_id": "qwen-default"
    }

    # 迁移当前提供商
    current_provider = old_credentials.get("_current_provider", "qwen")
    new_credentials["current_llm_id"] = f"{current_provider}-default"

    # 迁移每个提供商
    for provider, config in old_credentials.items():
        if provider.startswith("_"):
            continue

        llm_id = f"{provider}-default"
        model_name = config.get("model", get_default_model(provider))

        # For custom providers, use the model name as the display name
        if provider == "custom":
            display_name = model_name
        else:
            display_name = get_provider_display_name(provider)

        new_credentials["llms"][llm_id] = {
            "id": llm_id,
            "provider": provider,
            "name": display_name,
            "model": model_name,
            "base_url": config.get("base_url", get_default_base_url(provider)),
            "api_key": config["api_key"],  # 保持原有加密
        }

    # 保存新格式
    KeyObfuscator.save_credentials(new_credentials)
    logger.info(f"Migration complete: {len(new_credentials['llms'])} LLM configs")


def get_provider_display_name(provider: str) -> str:
    """Get display name for provider."""
    names = {
        "qwen": "通义千问",
        "openai": "OpenAI",
        "deepseek": "DeepSeek",
        "custom": "自定义",
        "ollama": "Ollama (本地)",
        "claude": "Claude",
        "gemini": "Gemini",
    }
    return names.get(provider, provider)


def get_default_model(provider: str) -> str:
    """Get default model for provider."""
    models = {
        "qwen": "qwen-plus",
        "openai": "gpt-4o-mini",
        "deepseek": "deepseek-chat",
        "ollama": "qwen2.5",
        "claude": "claude-3-5-sonnet-20241022",
        "gemini": "gemini-pro",
        "custom": "",
    }
    return models.get(provider, "")


def get_default_base_url(provider: str) -> str:
    """Get default base URL for provider."""
    urls = {
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com",
        "ollama": "http://localhost:11434/v1",
        "claude": "https://api.anthropic.com",
        "gemini": "https://generativelanguage.googleapis.com",
        "custom": "",
    }
    return urls.get(provider, "")
