"""
Configuration API - Manage obfuscated LLM API keys and provider switching

This module provides endpoints for:
- Saving/loading obfuscated API keys
- Getting current provider info
- Hot-switching LLM providers
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import os

from app.core.obfuscation import KeyObfuscator
from app.core.trusted_domains import is_trusted_domain
from app.config import get_settings, get_available_providers, clear_settings_cache, get_settings_uncached


router = APIRouter(tags=["config"])


class SaveLLMConfigRequest(BaseModel):
    """Request model for saving LLM configuration."""

    provider: str = Field(..., description="LLM provider name (e.g., qwen, openai)")
    api_key: str = Field(..., description="API key for the provider")
    model: str = Field(default="", description="Model name")
    base_url: str = Field(default="", description="Custom base URL (optional)")
    user_confirmed: bool = Field(default=False, description="User confirmed non-trusted domain")


class ConfigStatusResponse(BaseModel):
    """Response model for configuration status."""

    has_credentials: bool
    providers: list[str]


class DomainCheckRequest(BaseModel):
    """Request model for checking if a domain is trusted."""

    domain: str = Field(..., description="Domain to check")


@router.post("/save")
async def save_llm_config(request: SaveLLMConfigRequest):
    """
    Save LLM configuration with obfuscated API key.

    The API key is obfuscated using device fingerprint before storage.
    This prevents Agent tools from accidentally reading the key.

    ## Request Example
    ```json
    {
      "provider": "qwen",
      "api_key": "sk-xxxxxxxx",
      "model": "qwen-turbo",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
    }
    ```
    """
    try:
        # Check domain trust if base_url provided
        if request.base_url:
            domain = request.base_url.replace("https://", "").replace("http://", "").split("/")[0]
            domain = domain.split(":")[0]  # Remove port

            if not is_trusted_domain(domain) and not request.user_confirmed:
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": f"⚠️ 域名 {domain} 不在预置的可信服务商列表中。请确认要使用此 API 吗？",
                    "domain": domain,
                }

        # Load existing credentials
        credentials = KeyObfuscator.load_credentials()

        # Add or update provider config
        provider_config = {
            "api_key": request.api_key,
        }

        if request.model:
            provider_config["model"] = request.model

        if request.base_url:
            provider_config["base_url"] = request.base_url

        if request.user_confirmed:
            provider_config["user_confirmed"] = True

        credentials[request.provider] = provider_config

        # Update current provider to ensure it persists after restart
        credentials["_current_provider"] = request.provider

        # Save obfuscated credentials
        KeyObfuscator.save_credentials(credentials)

        # Clear settings cache so new values are picked up immediately
        clear_settings_cache()

        return {
            "success": True,
            "message": f"Configuration saved for {request.provider}",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save configuration: {str(e)}",
        )


@router.get("/status", response_model=ConfigStatusResponse)
async def get_config_status():
    """
    Get current configuration status.

    Returns information about saved providers without revealing API keys.

    ## Response Example
    ```json
    {
      "has_credentials": true,
      "providers": ["qwen", "openai"]
    }
    ```
    """
    try:
        credentials = KeyObfuscator.load_credentials()
        providers = [k for k in credentials.keys() if not k.startswith("_")]

        return ConfigStatusResponse(
            has_credentials=len(providers) > 0,
            providers=providers,
        )

    except Exception:
        return ConfigStatusResponse(
            has_credentials=False,
            providers=[],
        )


@router.delete("/{provider}")
async def delete_provider_config(provider: str):
    """
    Delete configuration for a specific provider.

    Args:
        provider: Provider name (e.g., qwen, openai)

    ## Response Example
    ```json
    {
      "success": true,
      "message": "Configuration deleted for qwen"
    }
    ```
    """
    try:
        credentials = KeyObfuscator.load_credentials()

        if provider not in credentials:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No configuration found for provider: {provider}",
            )

        # Remove provider
        del credentials[provider]

        # Save updated credentials
        if credentials:
            KeyObfuscator.save_credentials(credentials)
        else:
            # Delete file if no providers left
            KeyObfuscator.CREDENTIALS_FILE.unlink(missing_ok=True)

        return {
            "success": True,
            "message": f"Configuration deleted for {provider}",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete configuration: {str(e)}",
        )


@router.post("/check-domain")
async def check_domain(request: DomainCheckRequest):
    """
    Check if a domain is in the trusted list.

    ## Request Example
    ```json
    {
      "domain": "api.example.com"
    }
    ```

    ## Response Example
    ```json
    {
      "trusted": false,
      "domain": "api.example.com"
    }
    ```
    """
    trusted = is_trusted_domain(request.domain)

    return {
        "trusted": trusted,
        "domain": request.domain,
    }


class CurrentProviderResponse(BaseModel):
    """Response model for current provider info."""
    current_provider: str
    current_model: str
    available_providers: List[Dict[str, Any]]
    configured_providers: List[str]


@router.get("/provider", response_model=CurrentProviderResponse)
async def get_current_provider():
    """
    Get current LLM provider information.

    Returns the current provider, model, and list of all available providers.

    ## Response Example
    ```json
    {
      "current_provider": "qwen",
      "current_model": "qwen-plus",
      "available_providers": [
        {
          "id": "openai",
          "name": "OpenAI",
          "default_model": "gpt-4o-mini",
          "requires_api_key": true,
          "description": "OpenAI GPT models"
        },
        ...
      ],
      "configured_providers": ["qwen", "openai"]
    }
    ```
    """
    try:
        # Use uncached settings to get latest configuration
        settings = get_settings_uncached()
        available = get_available_providers()

        # Get current provider from environment (source of truth)
        current_provider = os.environ.get("LLM_PROVIDER", settings.llm_provider)

        # Get current model from obfuscated storage (most reliable source)
        current_model = ""
        try:
            credentials = KeyObfuscator.load_credentials()
            if current_provider in credentials and "model" in credentials[current_provider]:
                current_model = credentials[current_provider]["model"]
        except Exception:
            pass

        # Fallback to environment variable if not in storage
        if not current_model:
            env_model_key = f"{current_provider.upper()}_MODEL"
            current_model = os.environ.get(env_model_key, "")

        # Get configured providers (exclude internal keys like _current_provider)
        try:
            credentials = KeyObfuscator.load_credentials()
            configured = [k for k in credentials.keys() if not k.startswith("_")]
        except Exception:
            configured = []

        return CurrentProviderResponse(
            current_provider=current_provider,
            current_model=current_model,
            available_providers=available,
            configured_providers=configured,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get provider info: {str(e)}",
        )


class SwitchProviderRequest(BaseModel):
    """Request model for switching provider."""
    provider: str = Field(..., description="Target provider ID (e.g., qwen, openai)")


class SwitchProviderResponse(BaseModel):
    """Response model for switch provider result."""
    success: bool
    provider: str
    model: str
    message: str


@router.post("/switch-provider", response_model=SwitchProviderResponse)
async def switch_provider(request: SwitchProviderRequest):
    """
    Switch to a different LLM provider (hot-switch).

    This endpoint allows switching between pre-configured LLM providers
    without restarting the service. The provider must have been
    previously configured via /save endpoint.

    ## Request Example
    ```json
    {
      "provider": "deepseek"
    }
    ```

    ## Response Example
    ```json
    {
      "success": true,
      "provider": "deepseek",
      "model": "deepseek-chat",
      "message": "Switched to deepseek (deepseek-chat)"
    }
    ```

    ## Errors
    - 400: Provider not in the supported list
    - 404: Provider not configured (use /save first)
    - 500: Failed to switch (internal error)
    """
    try:
        # Clear settings cache to ensure fresh reads
        clear_settings_cache()

        # Validate provider
        available = get_available_providers()
        available_ids = [p["id"] for p in available]

        if request.provider not in available_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported provider: {request.provider}. "
                f"Available providers: {', '.join(available_ids)}",
            )

        # Load credentials to check if configured and get model name
        credentials = KeyObfuscator.load_credentials()
        model = ""
        if request.provider in credentials:
            model = credentials[request.provider].get("model", "")

        if request.provider not in credentials:
            # Special case: ollama doesn't need API key
            if request.provider != "ollama":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Provider '{request.provider}' is not configured. "
                    f"Please use POST /api/config/save to configure it first.",
                )

        # Update environment variable
        os.environ['LLM_PROVIDER'] = request.provider

        # Persist provider choice in obfuscated storage
        credentials["_current_provider"] = request.provider
        KeyObfuscator.save_credentials(credentials)

        # Import here to avoid circular dependency
        from app.api.chat import get_agent_manager

        # Get new agent manager (will create with new provider)
        agent = get_agent_manager()

        return SwitchProviderResponse(
            success=True,
            provider=request.provider,
            model=model,
            message=f"Switched to {request.provider} ({model})",
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch provider: {str(e)}",
        )
