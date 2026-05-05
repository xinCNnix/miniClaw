"""
LLM Module — LLM 创建、热切换、Agent 管理的唯一入口。

所有 LLM 相关逻辑都在这里:
- create_current_llm():     从当前 credentials 创建 LLM
- create_llm_from_config(): 从指定 LLMConfig 创建 LLM
- create_llm():             兼容旧调用，委托给 create_current_llm
- get_default_llm():        同 create_current_llm
- get_agent_manager():      Agent 单例 + 热切换检测
- reset_agent_manager():    重置（切换 LLM 时调用）

数据源: llm_config 模块 → credentials.encrypted（每次实时读取，不依赖缓存 settings）

禁止在本文件以外的地方创建 AgentManager 或绕过 create_current_llm 创建 LLM。
"""

import importlib
import logging
import threading
from typing import List, Literal, Optional, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.config import LLMConfig, get_settings
from app.core.llm_config import get_current_llm_id, load_llm_config

logger = logging.getLogger(__name__)

LLMProvider = Literal["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"]

# ── 单例状态 ──────────────────────────────────────────────
_lock = threading.Lock()
_agent_manager = None
_current_llm_id: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# LLM 创建（核心）
# ═══════════════════════════════════════════════════════════

def _build_llm(llm_config: LLMConfig) -> BaseChatModel:
    """
    从 LLMConfig 构建 ChatOpenAI 实例。

    Args:
        llm_config: 包含 provider, model, base_url, api_key 的配置对象

    Returns:
        ChatOpenAI 实例

    Raises:
        ValueError: model 或 api_key 未配置
    """
    settings = get_settings()

    if not llm_config.model:
        raise ValueError(f"Model name not configured for LLM '{llm_config.id}'")
    if not llm_config.api_key and llm_config.provider != "ollama":
        raise ValueError(f"API key not configured for LLM '{llm_config.id}'")

    return ChatOpenAI(
        base_url=llm_config.base_url,
        api_key=llm_config.api_key,
        model=llm_config.model,
        temperature=0.1,
        max_tokens=4000,
        streaming=True,
        stream_usage=True,
        request_timeout=settings.llm_request_timeout,
    )


def create_current_llm() -> BaseChatModel:
    """
    从当前活跃的 LLM 配置创建实例（实时读取 credentials，不依赖缓存）。

    Returns:
        ChatOpenAI 实例

    Raises:
        ValueError: 当前 LLM 未配置
    """
    llm_id = get_current_llm_id()
    llm_config = load_llm_config(llm_id)
    if llm_config is None:
        raise ValueError(f"Current LLM '{llm_id}' not found in credentials")
    return _build_llm(llm_config)


def create_llm_from_config(llm_config: LLMConfig) -> BaseChatModel:
    """
    从指定的 LLMConfig 创建 LLM 实例。

    Args:
        llm_config: LLM 配置对象

    Returns:
        ChatOpenAI 实例
    """
    return _build_llm(llm_config)


def create_llm(
    provider: LLMProvider = "qwen",
    settings_override: dict = None,
) -> BaseChatModel:
    """
    创建 LLM 实例（兼容旧接口）。

    无 settings_override 时统一走 create_current_llm()，从 credentials 实时读取。
    传 settings_override 时走旧路径（按 provider 读取 settings 字段）。

    Args:
        provider: LLM provider name（兼容参数，无 override 时忽略）
        settings_override: 显式传入 settings 时走旧路径

    Returns:
        ChatOpenAI 实例
    """
    if settings_override is not None:
        return _create_llm_legacy(provider, settings_override)
    return create_current_llm()


def _create_llm_legacy(provider: LLMProvider, settings) -> BaseChatModel:
    """旧路径：按 provider 名读取 settings 中的 base_url/api_key/model。"""
    provider_configs = {
        "openai": {
            "base_url": settings.openai_base_url,
            "api_key": settings.openai_api_key,
            "model": settings.openai_model,
            "temperature": 0.1,
            "default_model": "gpt-4o-mini",
        },
        "deepseek": {
            "base_url": settings.deepseek_base_url,
            "api_key": settings.deepseek_api_key,
            "model": settings.deepseek_model,
            "temperature": 0.1,
            "default_model": "deepseek-chat",
        },
        "qwen": {
            "base_url": settings.qwen_base_url,
            "api_key": settings.qwen_api_key,
            "model": settings.qwen_model,
            "temperature": 0.1,
            "default_model": "qwen-plus",
        },
        "ollama": {
            "base_url": settings.ollama_base_url,
            "api_key": "ollama",
            "model": settings.ollama_model,
            "temperature": 0.1,
            "default_model": "qwen2.5",
        },
        "claude": {
            "base_url": settings.claude_base_url,
            "api_key": settings.claude_api_key,
            "model": settings.claude_model,
            "temperature": 0.1,
            "default_model": "claude-3-5-sonnet-20241022",
        },
        "custom": {
            "base_url": settings.custom_base_url,
            "api_key": settings.custom_api_key,
            "model": settings.custom_model,
            "temperature": 0.1,
            "default_model": None,
        },
    }

    if provider not in provider_configs:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Supported providers: {list(provider_configs.keys())}"
        )

    config = provider_configs[provider]

    if not config["model"]:
        if config["default_model"]:
            logger.warning(
                f"{provider.upper()}_MODEL not configured, using default: {config['default_model']}"
            )
            config["model"] = config["default_model"]
        else:
            raise ValueError(
                f"Model name not configured for provider '{provider}'. "
                f"Please set {provider.upper()}_MODEL environment variable."
            )

    if provider != "ollama" and not config["api_key"]:
        raise ValueError(
            f"API key not found for provider '{provider}'. "
            f"Please set {provider.upper()}_API_KEY environment variable."
        )

    return ChatOpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config["model"],
        temperature=config["temperature"],
        max_tokens=4000,
        streaming=True,
        stream_usage=True,
        request_timeout=settings.llm_request_timeout,
    )


def get_default_llm() -> BaseChatModel:
    """获取当前默认 LLM（等价于 create_current_llm）。"""
    return create_current_llm()


def get_available_providers() -> list[LLMProvider]:
    """获取支持的 provider 列表。"""
    return ["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"]


def validate_provider_config(provider: LLMProvider) -> Tuple[bool, str]:
    """
    校验 provider 是否有有效配置。

    Args:
        provider: Provider 名称

    Returns:
        (is_valid, error_message)
    """
    settings = get_settings()

    provider_keys = {
        "openai": settings.openai_api_key,
        "deepseek": settings.deepseek_api_key,
        "qwen": settings.qwen_api_key,
        "ollama": "always_valid",
        "claude": settings.claude_api_key,
        "custom": settings.custom_api_key,
        "gemini": settings.gemini_api_key,
    }

    api_key = provider_keys.get(provider)

    if provider == "gemini":
        if not api_key:
            return False, "Gemini API key not set (GEMINI_API_KEY)"
        elif not api_key.startswith("AIza"):
            return False, "Gemini API key should start with 'AIza'"
        else:
            return True, ""

    if provider == "ollama":
        return True, ""
    elif not api_key:
        return False, f"API key not set for provider '{provider}'"
    elif len(api_key) < 10:
        return False, f"API key appears invalid for provider '{provider}'"
    else:
        return True, ""


# ═══════════════════════════════════════════════════════════
# Agent Manager（单例 + 热切换）
# ═══════════════════════════════════════════════════════════

def get_agent_manager():
    """
    获取全局 AgentManager（单例），支持热切换。

    通过比较 current_llm_id 检测 LLM 是否切换，
    切换了就用新配置重建 AgentManager。

    Returns:
        AgentManager 实例

    Raises:
        HTTPException: 初始化失败时抛出 500
    """
    from fastapi import HTTPException, status

    global _agent_manager, _current_llm_id

    with _lock:
        try:
            new_llm_id = get_current_llm_id()

            if _current_llm_id != new_llm_id or _agent_manager is None:
                logger.info(f"=== LLM switch: {_current_llm_id} → {new_llm_id} ===")

                from app.tools import CORE_TOOLS

                llm = create_current_llm()
                logger.info(
                    f"LLM created: {_llm_display(new_llm_id)}, "
                    f"tools={[t.name for t in CORE_TOOLS]}"
                )

                from app.core.agent import AgentManager

                _agent_manager = AgentManager(tools=CORE_TOOLS, llm=llm)
                _current_llm_id = new_llm_id

                logger.info("=== Agent manager recreated successfully ===")

            return _agent_manager

        except Exception as e:
            import traceback

            logger.error(f"Failed to create agent manager: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initialize agent: {str(e)}",
            )


def reset_agent_manager() -> None:
    """
    重置 AgentManager，下次 get_agent_manager() 时用新配置重建。

    切换 LLM 时由 config API 调用，同时重置所有持有旧 LLM 实例的子系统。
    """
    global _agent_manager, _current_llm_id

    with _lock:
        _agent_manager = None
        _current_llm_id = None

    _reset_subsystems()


# ═══════════════════════════════════════════════════════════
# 内部工具函数
# ═══════════════════════════════════════════════════════════

def _reset_subsystems() -> None:
    """重置所有持有 LLM 实例引用的子系统。"""
    for module_path, func_name in [
        ("app.memory.memory_manager", "reset_memory_manager"),
        ("app.memory.retriever_factory", "reset_memory_retriever"),
        ("app.core.reflection.evaluator", "reset_unified_evaluator"),
    ]:
        try:
            mod = importlib.import_module(module_path)
            getattr(mod, func_name)()
        except Exception as e:
            logger.warning(f"Failed to reset {module_path}.{func_name}: {e}")


def _llm_display(llm_id: str) -> str:
    """返回 LLM 配置的简要描述（用于日志）。"""
    try:
        cfg = load_llm_config(llm_id)
        if cfg:
            domain = (cfg.base_url or "").replace("https://", "").replace("http://", "").split("/")[0]
            return f"{cfg.model}@{domain}"
    except Exception:
        pass
    return llm_id
