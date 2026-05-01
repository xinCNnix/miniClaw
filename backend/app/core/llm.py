"""
LLM Module - Multi-LLM Provider Support

This module handles LLM initialization with support for multiple providers:
- OpenAI
- DeepSeek
- Qwen (通义千问)
- Ollama (Local)
- Claude (Anthropic via OpenAI-compatible mode)
- Gemini (Google)
- Custom OpenAI-compatible APIs
"""

from typing import Literal, Optional
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.config import settings, get_settings
from app.config import LLMConfig as PydanticLLMConfig

LLMProvider = Literal["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"]


def create_llm(
    provider: LLMProvider = "qwen",
    settings_override: dict = None,
) -> BaseChatModel:
    """
    Create an LLM instance for the specified provider.

    Args:
        provider: LLM provider name
        settings_override: Optional settings to override

    Returns:
        Configured ChatOpenAI instance

    Raises:
        ValueError: If provider is unsupported or configuration is invalid

    Examples:
        >>> llm = create_llm("qwen")
        >>> llm = create_llm("openai", settings_override={"temperature": 0.5})
    """
    settings = settings_override or get_settings()

    # Map provider to configuration
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
            "api_key": "ollama",  # Ollama doesn't need real API key
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

    # Check for model name (use default if not specified)
    if not config["model"]:
        if config["default_model"]:
            import logging
            logging.warning(
                f"{provider.upper()}_MODEL not configured, using default: {config['default_model']}. "
                f"Please set {provider.upper()}_MODEL environment variable for production use."
            )
            config["model"] = config["default_model"]
        else:
            raise ValueError(
                f"Model name not configured for provider '{provider}'. "
                f"Please set {provider.upper()}_MODEL environment variable with the desired model name. "
                f"Model names evolve quickly, please check the provider's official documentation for the latest available models."
            )

    # Check for API key (except Ollama which doesn't need it)
    if provider != "ollama" and not config["api_key"]:
        raise ValueError(
            f"API key not found for provider '{provider}'. "
            f"Please set {provider.upper()}_API_KEY environment variable."
        )

    # Create ChatOpenAI instance
    llm = ChatOpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config["model"],
        temperature=config["temperature"],
        max_tokens=4000,  # Increased from 2000 to prevent truncation
        streaming=True,  # Enable streaming for SSE
        stream_usage=True,  # Return token usage even when streaming
        request_timeout=settings.llm_request_timeout,  # 超时保护，防止 API 无响应时永久挂起
    )

    return llm


def get_default_llm() -> BaseChatModel:
    """
    Get the default LLM instance based on configuration.

    Returns:
        Configured LLM instance
    """
    settings = get_settings()
    return create_llm(settings.llm_provider)


def get_available_providers() -> list[LLMProvider]:
    """
    Get list of available LLM providers.

    Returns:
        List of provider names
    """
    return ["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"]


def validate_provider_config(provider: LLMProvider) -> tuple[bool, str]:
    """
    Validate if a provider has valid configuration.

    Args:
        provider: Provider name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    settings = get_settings()

    provider_keys = {
        "openai": settings.openai_api_key,
        "deepseek": settings.deepseek_api_key,
        "qwen": settings.qwen_api_key,
        "ollama": "always_valid",  # Ollama doesn't need API key
        "claude": settings.claude_api_key,
        "custom": settings.custom_api_key,
        "gemini": settings.gemini_api_key,
    }

    api_key = provider_keys.get(provider)

    # Gemini requires special handling
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


# ============================================================================
# New Multi-LLM Support Functions
# ============================================================================

def create_llm_from_config(llm_config: PydanticLLMConfig) -> BaseChatModel:
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

    provider = llm_config.provider
    if provider != "ollama" and not llm_config.api_key:
        raise ValueError(f"API key not found for LLM {llm_config.id}")

    # 创建 ChatOpenAI 实例
    llm = ChatOpenAI(
        base_url=llm_config.base_url,
        api_key=llm_config.api_key,
        model=llm_config.model,
        temperature=0.1,
        max_tokens=4000,  # Increased from 2000 to prevent truncation
        streaming=True,  # Enable streaming for SSE
        stream_usage=True,  # Return token usage even when streaming
        request_timeout=settings.llm_request_timeout,  # 超时保护
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
    from app.core.llm_config import get_current_llm_id, load_llm_config

    current_llm_id = get_current_llm_id()
    llm_config = load_llm_config(current_llm_id)

    if llm_config is None:
        raise ValueError(f"Current LLM {current_llm_id} not found")

    return create_llm_from_config(llm_config)
