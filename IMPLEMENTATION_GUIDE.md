# LLM 配置系统重构 - 完整实施方案

> **目标**：实现所见即所得的多 LLM 配置系统，确保前端显示与后端使用一致
>
> **安全原则**：前端永远不接触明文 API Key
>
> **实施时间**：5-6 天

## 目录

1. [完整代码实现](#完整代码实现)
   - [后端代码](#后端代码)
   - [前端代码](#前端代码)
2. [测试用例](#测试用例)
3. [迁移脚本](#迁移脚本)
4. [实施步骤](#实施步骤)
5. [回滚方案](#回滚方案)

---

## 完整代码实现

### 后端代码

#### 1. `backend/app/config.py` - 完整替换

```python
"""
miniClaw Configuration Module - Multi-LLM Support

This module handles all configuration management with support for multiple LLM configurations.
"""

from functools import lru_cache
from typing import List, Dict, Any, Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from dataclasses import dataclass


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class LLMConfig:
    """
    单个 LLM 配置（不包含明文 API Key）

    注意：此类用于后端内部使用，包含明文 API Key 仅用于 LLM 初始化
    前端永远不应该接触到明文 Key
    """
    id: str
    provider: str
    name: str
    model: str
    base_url: str
    api_key: str  # 仅在后端内存中使用，不发送到前端

    def to_dict(self, include_api_key: bool = False) -> Dict[str, Any]:
        """转换为字典（前端显示时不包含 API Key）"""
        data = {
            "id": self.id,
            "provider": self.provider,
            "name": self.name,
            "model": self.model,
            "base_url": self.base_url,
        }

        if include_api_key:
            data["api_key"] = self.api_key
        else:
            # 前端显示：只返回脱敏信息
            data["has_api_key"] = bool(self.api_key)
            data["api_key_preview"] = f"{self.api_key[:8]}***" if self.api_key else ""

        return data


# ============================================================================
# Settings Class
# ============================================================================

class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "miniClaw"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8002
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # LLM Configuration（兼容旧版环境变量）
    llm_provider: Literal["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"] = Field(default="qwen", env="LLM_PROVIDER")

    # 兼容旧版配置（用于迁移）
    qwen_api_key: str = Field(default="", env="QWEN_API_KEY")
    qwen_model: str = Field(default="", env="QWEN_MODEL")
    qwen_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", env="QWEN_BASE_URL")

    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_model: str = Field(default="", env="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", env="OPENAI_BASE_URL")

    deepseek_api_key: str = Field(default="", env="DEEPSEEK_API_KEY")
    deepseek_model: str = Field(default="", env="DEEPSEEK_MODEL")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", env="DEEPSEEK_BASE_URL")

    custom_api_key: str = Field(default="", env="CUSTOM_API_KEY")
    custom_model: str = Field(default="", env="CUSTOM_MODEL")
    custom_base_url: str = Field(default="", env="CUSTOM_BASE_URL")

    ollama_base_url: str = Field(default="http://localhost:11434/v1", env="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="", env="OLLAMA_MODEL")

    claude_api_key: str = Field(default="", env="CLAUDE_API_KEY")
    claude_model: str = Field(default="", env="CLAUDE_MODEL")
    claude_base_url: str = Field(default="https://api.anthropic.com", env="CLAUDE_BASE_URL")

    gemini_api_key: str = Field(default="", env="GEMINI_API_KEY")
    gemini_model: str = Field(default="", env="GEMINI_MODEL")
    gemini_base_url: str = "https://generativelanguage.googleapis.com"

    # LangSmith Tracing
    langchain_api_key: str = Field(default="", env="LANGCHAIN_API_KEY")
    langchain_tracing_v2: bool = False
    langchain_project: str = "mini-openclaw"

    # File Paths
    base_dir: str = "."
    data_dir: str = "data"
    knowledge_base_dir: str = "data/knowledge_base"
    sessions_dir: str = "data/sessions"
    skills_dir: str = "data/skills"
    vector_store_dir: str = "data/vector_store"
    workspace_dir: str = "workspace"

    # Tool Security
    terminal_root_dir: str = "."
    terminal_blocked_commands: list[str] = [
        "rm -rf /", "rm -rf /.*", "rm -rf /*",
        "mkfs", "dd if=/dev/zero", "dd if=/dev/random", "dd if=/dev/urandom",
        ":(){ :|:& };:", "bomb() { bomb|bomb& }", "fork() { fork & }",
        "chmod 000", "chmod -r 000", "chmod -r 000 /", "chmod -r 777 /etc",
        "chown -r root:root",
        "format", "format c:", "format d:",
        "del /f /s /q", "del /f /q c:\\",
        "rd /s /q", "rmdir /s /q",
        "shutdown /s", "shutdown /r", "shutdown /p",
        "reg delete", "taskkill /f", "bcdedit /delete",
        "diskpart", "fdisk", "chkdsk /f", "sfc /scannow",
        "bootrec /fixmbr", "bootrec /fixboot",
        "mv /", "mv /*", "cp /", "cp /* /dev/null",
        "move /", "move /*",
    ]
    read_file_root_dir: str = "."

    # Python REPL
    python_execution_mode: Literal["safe", "standard", "free"] = "standard"
    python_safe_timeout: int = 60
    python_standard_timeout: int = 300
    python_free_timeout: int = 1800

    # Tree of Thoughts
    enable_tot: bool = True
    tot_max_depth: int = 2
    tot_branching_factor: int = 3
    tot_quality_threshold: float = 6.0
    tot_checkpoint_path: str = "data/tot_checkpoints.db"

    # RAG / Knowledge Base
    enable_rag: bool = True
    embedding_model: str = "text-embedding-ada-002"
    vector_store_type: Literal["chroma", "simple"] = "chroma"
    retrieval_top_k: int = 5

    # Memory System
    enable_memory_extraction: bool = True
    enable_semantic_search: bool = True
    memory_db_path: str = "data/memory.db"

    # Performance
    enable_streaming_response: bool = True
    streaming_chunk_size: int = 512

    # Logging
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_to_file: bool = True
    log_to_console: bool = True


# ============================================================================
# Configuration Loading (No Cache - Always Fresh)
# ============================================================================

def _load_obfuscated_config() -> None:
    """
    Load API keys from obfuscated storage and set as environment variables.

    优先级：加密存储 > 环境变量 > 默认值
    """
    try:
        from app.core.obfuscation import KeyObfuscator

        credentials = KeyObfuscator.load_credentials()

        # 检查是否是新格式
        if "llms" in credentials:
            # 新格式：多 LLM 配置
            current_llm_id = credentials.get("current_llm_id", "qwen-default")
            llms = credentials.get("llms", {})

            # 设置当前 LLM 的环境变量（兼容性）
            if current_llm_id in llms:
                current_llm = llms[current_llm_id]
                provider = current_llm.get("provider", "custom")
                os.environ["LLM_PROVIDER"] = provider

                if "api_key" in current_llm:
                    env_key = f"{provider.upper()}_API_KEY"
                    os.environ[env_key] = current_llm["api_key"]

                if "model" in current_llm:
                    env_key = f"{provider.upper()}_MODEL"
                    os.environ[env_key] = current_llm["model"]

                if "base_url" in current_llm:
                    env_key = f"{provider.upper()}_BASE_URL"
                    os.environ[env_key] = current_llm["base_url"]
        else:
            # 旧格式：单一提供商配置（兼容性）
            for provider, config in credentials.items():
                if provider.startswith("_"):
                    continue

                provider_upper = provider.upper()

                if "api_key" in config:
                    env_key = f"{provider_upper}_API_KEY"
                    os.environ[env_key] = config["api_key"]

                if "model" in config and config["model"]:
                    env_key = f"{provider_upper}_MODEL"
                    os.environ[env_key] = config["model"]

                if "base_url" in config and config["base_url"]:
                    env_key = f"{provider_upper}_BASE_URL"
                    os.environ[env_key] = config["base_url"]

            if "_current_provider" in credentials:
                provider = credentials["_current_provider"]
                os.environ["LLM_PROVIDER"] = provider

    except Exception:
        # Silently fail - allows fallback to environment variables
        pass


# ============================================================================
# Settings Access (No Cache)
# ============================================================================

def get_settings() -> Settings:
    """
    Get settings instance (always fresh, no caching).

    每次调用都重新加载配置，确保前端设置与后端使用一致。
    """
    _load_obfuscated_config()
    return Settings()


def get_available_providers() -> List[Dict[str, Any]]:
    """Get list of all available LLM providers."""
    return [
        {
            "id": "openai",
            "name": "OpenAI",
            "default_model": "gpt-4o-mini",
            "requires_api_key": True,
            "description": "OpenAI GPT models",
        },
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "default_model": "deepseek-chat",
            "requires_api_key": True,
            "description": "DeepSeek AI models",
        },
        {
            "id": "qwen",
            "name": "通义千问 (Qwen)",
            "default_model": "qwen-plus",
            "requires_api_key": True,
            "description": "阿里云通义千问模型",
        },
        {
            "id": "ollama",
            "name": "Ollama (本地)",
            "default_model": "qwen2.5",
            "requires_api_key": False,
            "description": "本地运行模型",
        },
        {
            "id": "claude",
            "name": "Claude (Anthropic)",
            "default_model": "claude-3-5-sonnet-20241022",
            "requires_api_key": True,
            "description": "Anthropic Claude models",
        },
        {
            "id": "gemini",
            "name": "Gemini (Google)",
            "default_model": "gemini-pro",
            "requires_api_key": True,
            "description": "Google Gemini models",
        },
        {
            "id": "custom",
            "name": "自定义",
            "default_model": "",
            "requires_api_key": True,
            "description": "自定义 OpenAI 兼容 API",
        },
    ]


# ============================================================================
# Convenience Exports
# ============================================================================

settings = get_settings()
```

#### 2. `backend/app/core/llm_config.py` - 新文件

```python
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

def generate_llm_id(provider: str, model: str) -> str:
    """
    Generate unique LLM ID from provider and model.

    Examples:
        - "qwen" + "qwen-plus" → "qwen-qwen-plus"
        - "custom" + "openrouter/hunter-alpha" → "custom-openrouter-hunter-alpha"

    Args:
        provider: Provider name (qwen, openai, custom, etc.)
        model: Model name

    Returns:
        Unique LLM ID
    """
    # 将模型名中的特殊字符替换为连字符
    model_slug = model.replace("/", "-").replace("_", "-").replace(".", "-")
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

    # 保存配置（加密 API Key）
    credentials["llms"][llm_config.id] = {
        "id": llm_config.id,
        "provider": llm_config.provider,
        "name": llm_config.name,
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

        new_credentials["llms"][llm_id] = {
            "id": llm_id,
            "provider": provider,
            "name": get_provider_display_name(provider),
            "model": config.get("model", get_default_model(provider)),
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
```

#### 3. `backend/app/core/llm.py` - 修改

```python
"""
LLM Module - Multi-LLM Provider Support

This module handles LLM initialization with support for multiple providers.
"""

from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.config import Settings
from app.core.llm_config import load_llm_config, get_current_llm_id


LLMProvider = Literal["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"]


def create_llm(
    llm_config,
) -> BaseChatModel:
    """
    Create an LLM instance from LLMConfig.

    Args:
        llm_config: LLMConfig object

    Returns:
        Configured ChatOpenAI instance

    Raises:
        ValueError: If configuration is invalid
    """
    # 验证配置
    if not llm_config.model:
        raise ValueError(f"Model name not configured for LLM {llm_config.id}")

    if llm_config.provider != "ollama" and not llm_config.api_key:
        raise ValueError(f"API key not found for LLM {llm_config.id}")

    # 创建 ChatOpenAI 实例
    llm = ChatOpenAI(
        base_url=llm_config.base_url,
        api_key=llm_config.api_key,
        model=llm_config.model,
        temperature=0.1,
        max_tokens=2000,
        streaming=True,  # Enable streaming for SSE
    )

    return llm


def create_current_llm() -> BaseChatModel:
    """
    Create LLM instance for current active configuration.

    Returns:
        Configured LLM instance

    Raises:
        ValueError: If current LLM not configured
    """
    current_llm_id = get_current_llm_id()
    llm_config = load_llm_config(current_llm_id)

    if llm_config is None:
        raise ValueError(f"Current LLM {current_llm_id} not found")

    return create_llm(llm_config)
```

#### 4. `backend/app/api/config.py` - 完整替换

```python
"""
Configuration API - Multi-LLM Management

This module provides endpoints for managing multiple LLM configurations.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from app.core.obfuscation import KeyObfuscator
from app.core.trusted_domains import is_trusted_domain
from app.core.llm_config import (
    load_all_llm_configs,
    load_llm_config,
    save_llm_config,
    delete_llm_config,
    get_current_llm_id,
    set_current_llm_id,
    llm_exists,
    generate_llm_id,
)


router = APIRouter(tags=["config"])
logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class LLMInfo(BaseModel):
    """LLM information (for frontend display, no API key)."""
    id: str
    provider: str
    name: str
    model: str
    base_url: str
    has_api_key: bool  # True if API key is configured
    api_key_preview: str  # 脱敏预览（sk-1234***）
    is_current: bool


class SaveLLMRequest(BaseModel):
    """Request for saving/updating LLM configuration."""
    id: Optional[str] = Field(None, description="LLM ID (auto-generated if empty)")
    provider: str = Field(..., description="Provider name (qwen, openai, custom, etc.)")
    name: str = Field(..., description="Display name")
    model: str = Field(..., description="Model name")
    base_url: str = Field(..., description="Base URL")
    api_key: Optional[str] = Field(None, description="API key (empty if not changing)")


class SwitchLLMRequest(BaseModel):
    """Request for switching LLM."""
    llm_id: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/llms", response_model=Dict)
async def list_llms():
    """
    List all configured LLMs (without API keys).

    ## Response
    ```json
    {
      "current_llm_id": "custom-openrouter-hunter-alpha",
      "llms": [
        {
          "id": "qwen-default",
          "provider": "qwen",
          "name": "通义千问",
          "model": "qwen-plus",
          "base_url": "https://...",
          "has_api_key": true,
          "api_key_preview": "sk-12345678***",
          "is_current": false
        }
      ]
    }
    ```
    """
    try:
        current_llm_id = get_current_llm_id()
        llms = load_all_llm_configs()

        return {
            "current_llm_id": current_llm_id,
            "llms": [
                {
                    **llm.to_dict(include_api_key=False),
                    "is_current": llm.id == current_llm_id
                }
                for llm in llms
            ]
        }

    except Exception as e:
        logger.error(f"Failed to list LLMs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list LLMs: {str(e)}",
        )


@router.post("/llms")
async def save_llm(request: SaveLLMRequest):
    """
    Save or update LLM configuration.

    如果 llm_id 为空，自动生成 ID。
    如果 llm_id 已存在，更新配置（API Key 可选）。

    ## Request
    ```json
    {
      "id": "custom-openrouter-hunter-alpha",
      "provider": "custom",
      "name": "OpenRouter Hunter",
      "model": "openrouter/hunter-alpha",
      "base_url": "https://openrouter.ai/api/v1/chat/completions",
      "api_key": "sk-xxx"
    }
    ```

    ## Response
    ```json
    {
      "success": true,
      "llm_id": "custom-openrouter-hunter-alpha"
    }
    ```
    """
    try:
        # 检查域名信任（如果提供 base_url）
        if request.base_url:
            domain = request.base_url.replace("https://", "").replace("http://", "").split("/")[0]
            domain = domain.split(":")[0]

            if not is_trusted_domain(domain):
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": f"⚠️ 域名 {domain} 不在预置的可信服务商列表中。请确认要使用此 API 吗？",
                    "domain": domain,
                }

        # 生成或使用提供的 ID
        llm_id = request.id or generate_llm_id(request.provider, request.model)

        # 如果是更新，加载现有配置
        existing_llm = None
        if request.id:
            existing_llm = load_llm_config(request.id)

        # 确定 API Key
        api_key = request.api_key
        if not api_key and existing_llm:
            # 未提供 API Key，保持原有
            api_key = existing_llm.api_key
        elif not api_key and not existing_llm:
            # 新建但未提供 API Key
            return {
                "success": False,
                "message": "新建 LLM 配置必须提供 API Key"
            }

        # 创建 LLMConfig
        from app.config import LLMConfig
        llm_config = LLMConfig(
            id=llm_id,
            provider=request.provider,
            name=request.name,
            model=request.model,
            base_url=request.base_url,
            api_key=api_key,
        )

        # 保存
        save_llm_config(llm_config)

        # 如果是第一个 LLM，自动设为当前
        all_llms = load_all_llm_configs()
        if len(all_llms) == 1:
            set_current_llm_id(llm_id)

        return {
            "success": True,
            "llm_id": llm_id
        }

    except Exception as e:
        logger.error(f"Failed to save LLM: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save LLM: {str(e)}",
        )


@router.post("/llms/switch")
async def switch_llm(request: SwitchLLMRequest):
    """
    Switch to a different LLM (hot-switch).

    ## Request
    ```json
    {
      "llm_id": "custom-openrouter-hunter-alpha"
    }
    ```

    ## Response
    ```json
    {
      "success": true,
      "current_llm_id": "custom-openrouter-hunter-alpha"
    }
    ```
    """
    try:
        if not llm_exists(request.llm_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM {request.llm_id} not found"
            )

        # 切换当前 LLM
        set_current_llm_id(request.llm_id)

        # 重置 Agent Manager 以使用新 LLM
        from app.api.chat import reset_agent_manager
        reset_agent_manager()

        return {
            "success": True,
            "current_llm_id": request.llm_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to switch LLM: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch LLM: {str(e)}",
        )


@router.delete("/llms/{llm_id}")
async def delete_llm(llm_id: str):
    """
    Delete LLM configuration.

    不能删除当前正在使用的 LLM。
    """
    try:
        current_llm_id = get_current_llm_id()

        if llm_id == current_llm_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete current LLM. Please switch to another LLM first."
            )

        if not delete_llm_config(llm_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM {llm_id} not found"
            )

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete LLM: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete LLM: {str(e)}",
        )


# ============================================================================
# Legacy Endpoints (兼容性)
# ============================================================================

@router.get("/status")
async def get_config_status():
    """Legacy endpoint for config status."""
    llms = load_all_llm_configs()
    return {
        "has_credentials": len(llms) > 0,
        "providers": list(set([llm.provider for llm in llms]))
    }


@router.get("/provider")
async def get_current_provider():
    """Legacy endpoint for current provider info."""
    current_llm_id = get_current_llm_id()
    current_llm = load_llm_config(current_llm_id)
    llms = load_all_llm_configs()

    return {
        "current_provider": current_llm.provider if current_llm else "qwen",
        "current_model": current_llm.model if current_llm else "",
        "current_llm_id": current_llm_id,
        "available_providers": [],  # Deprecated
        "configured_providers": list(set([llm.provider for llm in llms]))
    }
```

#### 5. `backend/app/api/chat.py` - 修改 get_agent_manager

```python
# 在文件开头添加导入
from app.core.llm_config import get_current_llm_id, load_llm_config

# 修改 get_agent_manager 函数
def get_agent_manager() -> AgentManager:
    """
    Get or create the global agent manager with current LLM.

    每次都重新加载当前 LLM 配置，确保前端设置与后端使用一致。
    """
    global _agent_manager, _current_llm_id

    try:
        # 获取当前 LLM ID
        current_llm_id = get_current_llm_id()

        # 检查是否需要重新创建 Agent Manager
        if _current_llm_id != current_llm_id or _agent_manager is None:
            import logging
            logging.info(f"=== LLM changed: {_current_llm_id} → {current_llm_id} ===")

            # 加载当前 LLM 配置
            llm_config = load_llm_config(current_llm_id)

            if llm_config is None:
                raise ValueError(f"Current LLM {current_llm_id} not found")

            # 创建 LLM 实例
            from app.core.llm import create_llm
            llm = create_llm(llm_config)

            # 创建 Agent Manager
            from app.tools import CORE_TOOLS
            _agent_manager = create_agent_manager(
                tools=CORE_TOOLS,
                llm=llm,
            )
            _current_llm_id = current_llm_id

            logging.info(f"=== Agent Manager recreated with LLM: {current_llm_id} ===")

        return _agent_manager

    except Exception as e:
        import traceback
        logging.error(f"=== Failed to create agent manager ===")
        logging.error(f"Error: {e}")
        logging.error(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize agent: {str(e)}",
        )


# 修改 create_agent_manager 函数签名
def create_agent_manager(
    tools: List[BaseTool],
    llm: Optional[BaseChatModel] = None,  # 新增：可以直接传入 LLM
    llm_provider: LLMProvider = "qwen",  # 兼容旧版
) -> AgentManager:
    """
    Create Agent Manager with LLM instance.

    Args:
        tools: List of available tools
        llm: LLM instance (优先使用)
        llm_provider: LLM provider (如果 llm 未提供)
    """
    # 如果未提供 LLM，从 provider 创建
    if llm is None:
        from app.core.llm import create_llm, create_current_llm
        try:
            llm = create_current_llm()
        except ValueError:
            # 回退到从 provider 创建
            llm = create_llm_from_provider(llm_provider)

    return AgentManager(tools=tools, llm=llm)
```

---

## 前端代码

### 1. `frontend/types/config.ts` - 新文件

```typescript
/**
 * LLM Configuration Types
 */

export interface LLMConfig {
  id: string
  provider: string
  name: string
  model: string
  base_url: string
  has_api_key: boolean       // 是否已配置 API Key
  api_key_preview: string    // 脱敏预览（sk-1234***）
  is_current?: boolean
}

export interface SaveLLMRequest {
  id?: string                 // 可选，编辑时提供
  provider: string
  name: string
  model: string
  base_url: string
  api_key?: string           // 可选，编辑时不修改则不传
}

export interface LLMListResponse {
  current_llm_id: string
  llms: LLMConfig[]
}

export interface SwitchLLMRequest {
  llm_id: string
}
```

### 2. `frontend/lib/api.ts` - 添加方法

```typescript
/**
 * APIClient - LLM Configuration Methods
 */
class APIClient {
  // ... 其他方法 ...

  /**
   * 获取所有已配置的 LLM（不包含明文 API Key）
   */
  async listLLMs(): Promise<LLMListResponse> {
    const response = await fetch(`${this.baseUrl}/api/config/llms`)

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Failed to list LLMs: ${error}`)
    }

    return response.json()
  }

  /**
   * 保存或更新 LLM 配置
   *
   * api_key 是可选的：
   * - 新增时：必须提供 api_key
   * - 编辑时：如果不修改 api_key 则不传此字段
   */
  async saveLLM(request: SaveLLMRequest): Promise<{ success: boolean; llm_id: string }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Failed to save LLM: ${error}`)
    }

    return response.json()
  }

  /**
   * 切换到指定 LLM
   */
  async switchLLM(llmId: string): Promise<{ success: boolean; current_llm_id: string }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms/switch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ llm_id: llmId }),
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Failed to switch LLM: ${error}`)
    }

    return response.json()
  }

  /**
   * 删除 LLM 配置
   */
  async deleteLLM(llmId: string): Promise<{ success: boolean }> {
    const response = await fetch(`${this.baseUrl}/api/config/llms/${llmId}`, {
      method: 'DELETE',
    })

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Failed to delete LLM: ${error}`)
    }

    return response.json()
  }
}
```

### 3. `frontend/components/layout/SettingsDialog.tsx` - 完整重写 LLM 部分

```typescript
"use client"

import { useState, useEffect } from "react"
import { X, Save, Plus, Trash2, CheckCircle, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { apiClient, type LLMConfig, type SaveLLMRequest } from "@/lib/api"
import { useTranslation } from "@/hooks/use-translation.hook"

interface LLMSettingsProps {
  open: boolean
  onClose: () => void
}

export function LLMSettings({ open, onClose }: LLMSettingsProps) {
  const { t } = useTranslation()
  const [llms, setLLMs] = useState<LLMConfig[]>([])
  const [currentLLMId, setCurrentLLMId] = useState<string>("")
  const [isLoading, setIsLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [editingLLM, setEditingLLM] = useState<LLMConfig | null>(null)
  const [switchingLLM, setSwitchingLLM] = useState<string | null>(null)

  // 加载 LLM 列表
  const loadLLMs = async () => {
    try {
      const response = await apiClient.listLLMs()
      setLLMs(response.llms)
      setCurrentLLMId(response.current_llm_id)
    } catch (error: any) {
      console.error("Failed to load LLMs:", error)
      setMessage(`加载失败: ${error.message}`)
    }
  }

  useEffect(() => {
    if (open) {
      loadLLMs()
    }
  }, [open])

  // 切换 LLM
  const handleSwitch = async (llmId: string) => {
    if (llmId === currentLLMId) return

    setSwitchingLLM(llmId)
    setMessage("")

    try {
      const result = await apiClient.switchLLM(llmId)
      setCurrentLLMId(result.current_llm_id)
      setMessage(`已切换到 ${llmId}`)
      setTimeout(() => setMessage(""), 2000)

      // 重新加载列表
      await loadLLMs()
    } catch (error: any) {
      setMessage(`切换失败: ${error.message}`)
      setTimeout(() => setMessage(""), 3000)
    } finally {
      setSwitchingLLM(null)
    }
  }

  // 删除 LLM
  const handleDelete = async (llmId: string) => {
    if (!confirm(`确定要删除 ${llmId} 吗？`)) return

    try {
      await apiClient.deleteLLM(llmId)
      setMessage("删除成功")
      await loadLLMs()
      setTimeout(() => setMessage(""), 2000)
    } catch (error: any) {
      setMessage(`删除失败: ${error.message}`)
      setTimeout(() => setMessage(""), 3000)
    }
  }

  return (
    <div className="llm-settings">
      {/* 当前 LLM */}
      <div className="mb-6">
        <h3 className="text-lg font-semibold mb-3">当前使用的 LLM</h3>
        {llms.find(llm => llm.id === currentLLMId) ? (
          <LLMCard
            llm={llms.find(llm => llm.id === currentLLMId)!}
            isCurrent={true}
            onSwitch={null}
            onEdit={(llm) => {
              setEditingLLM(llm)
              setShowAddDialog(true)
            }}
            onDelete={null}
          />
        ) : (
          <p className="text-gray-500">未配置 LLM</p>
        )}
      </div>

      {/* 所有 LLM 列表 */}
      <div>
        <h3 className="text-lg font-semibold mb-3">所有 LLM 配置 ({llms.length})</h3>
        <div className="space-y-3">
          {llms.map(llm => (
            llm.id !== currentLLMId && (
              <LLMCard
                key={llm.id}
                llm={llm}
                isCurrent={false}
                onSwitch={() => handleSwitch(llm.id)}
                onEdit={(llm) => {
                  setEditingLLM(llm)
                  setShowAddDialog(true)
                }}
                onDelete={() => handleDelete(llm.id)}
                switching={switchingLLM === llm.id}
              />
            )
          ))}
        </div>
      </div>

      {/* 添加按钮 */}
      <Button
        className="mt-4"
        onClick={() => {
          setEditingLLM(null)
          setShowAddDialog(true)
        }}
      >
        <Plus className="w-4 h-4 mr-2" />
        添加 LLM
      </Button>

      {/* 消息提示 */}
      {message && (
        <div className={`mt-4 p-3 rounded ${message.includes('失败') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
          {message}
        </div>
      )}

      {/* 添加/编辑对话框 */}
      {showAddDialog && (
        <AddLLMDialog
          llm={editingLLM}
          onSave={async (data) => {
            try {
              await apiClient.saveLLM(data)
              setShowAddDialog(false)
              setMessage("保存成功")
              await loadLLMs()
              setTimeout(() => setMessage(""), 2000)
            } catch (error: any) {
              setMessage(`保存失败: ${error.message}`)
              setTimeout(() => setMessage(""), 3000)
            }
          }}
          onCancel={() => {
            setShowAddDialog(false)
            setEditingLLM(null)
          }}
        />
      )}
    </div>
  )
}


// LLM 卡片组件
interface LLMCardProps {
  llm: LLMConfig
  isCurrent: boolean
  onSwitch: ((llmId: string) => void) | null
  onEdit: ((llm: LLMConfig) => void) | null
  onDelete: ((llmId: string) => void) | null
  switching?: boolean
}

function LLMCard({ llm, isCurrent, onSwitch, onEdit, onDelete, switching }: LLMCardProps) {
  return (
    <div className={`border rounded-lg p-4 ${isCurrent ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}`}>
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <h4 className="font-semibold">{llm.name}</h4>
            {isCurrent && (
              <Badge variant="default">当前使用</Badge>
            )}
          </div>

          <div className="text-sm text-gray-600 space-y-1">
            <div>提供商: {llm.provider}</div>
            <div>模型: {llm.model}</div>
            <div>URL: {llm.base_url}</div>
            {/* ✅ 只显示状态，不显示明文 */}
            {llm.has_api_key ? (
              <div className="text-green-600">✓ API Key 已配置</div>
            ) : (
              <div className="text-red-600">✗ API Key 未配置</div>
            )}
          </div>
        </div>

        <div className="flex gap-2">
          {onSwitch && (
            <Button
              size="sm"
              onClick={() => onSwitch(llm.id)}
              disabled={switching}
            >
              {switching ? '切换中...' : '切换'}
            </Button>
          )}
          {onEdit && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onEdit(llm)}
            >
              编辑
            </Button>
          )}
          {onDelete && (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => onDelete(llm.id)}
            >
              删除
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}


// 添加/编辑 LLM 对话框
interface AddLLMDialogProps {
  llm: LLMConfig | null
  onSave: (data: SaveLLMRequest) => void
  onCancel: () => void
}

function AddLLMDialog({ llm, onSave, onCancel }: AddLLMDialogProps) {
  const [formData, setFormData] = useState({
    provider: llm?.provider || "custom",
    name: llm?.name || "",
    model: llm?.model || "",
    base_url: llm?.base_url || "",
    api_key: ""  // ⚠️ 始终为空，不回填
  })

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg p-6 max-w-md w-full">
        <h2 className="text-xl font-semibold mb-4">
          {llm ? "编辑 LLM 配置" : "添加新 LLM"}
        </h2>

        {llm && (
          <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded">
            <p className="text-sm text-yellow-800">
              ⚠️ 编辑时不会显示已有 API Key，如需修改请重新输入。
              如不修改 API Key，请留空。
            </p>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSave({
              ...formData,
              id: llm?.id
            })
          }}
          className="space-y-4"
        >
          <div>
            <label className="block text-sm font-medium mb-1">显示名称</label>
            <input
              type="text"
              className="w-full border rounded px-3 py-2"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">提供商</label>
            <select
              className="w-full border rounded px-3 py-2"
              value={formData.provider}
              onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
            >
              <option value="custom">自定义</option>
              <option value="qwen">通义千问</option>
              <option value="openai">OpenAI</option>
              <option value="deepseek">DeepSeek</option>
              <option value="ollama">Ollama</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">模型名称</label>
            <input
              type="text"
              className="w-full border rounded px-3 py-2"
              placeholder="例如: openrouter/hunter-alpha"
              value={formData.model}
              onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Base URL</label>
            <input
              type="url"
              className="w-full border rounded px-3 py-2"
              placeholder="https://api.example.com/v1"
              value={formData.base_url}
              onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              API Key {llm && "(留空保持不变)"}
            </label>
            {/* ✅ 使用 password 类型，不回填 */}
            <input
              type="password"
              className="w-full border rounded px-3 py-2"
              placeholder={llm ? "如需修改请重新输入，否则留空" : "sk-..."}
              value={formData.api_key}
              onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              required={!llm}  // 新建时必填，编辑时可选
            />
          </div>

          <div className="flex gap-3 justify-end">
            <Button type="button" variant="outline" onClick={onCancel}>
              取消
            </Button>
            <Button type="submit">
              保存
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
```

---

由于篇幅限制，剩余内容（测试用例、迁移脚本、实施步骤）将在下一部分继续...

**当前进度**：
- ✅ 完整后端代码（5个文件）
- ✅ 完整前端代码（3个文件/组件）
- ⏳ 测试用例
- ⏳ 迁移脚本
- ⏳ 实施步骤
- ⏳ 回滚方案

需要我继续完成剩余部分吗？
