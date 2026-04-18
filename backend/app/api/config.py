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
    save_llm_config as save_llm_config_to_storage,
    delete_llm_config as delete_llm_from_storage,
    get_current_llm_id,
    set_current_llm_id as set_current_llm,
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
    user_confirmed: Optional[bool] = Field(False, description="User confirmed untrusted domain")


class SwitchLLMRequest(BaseModel):
    """Request for switching LLM."""
    llm_id: str


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/llms")
async def list_llms():
    """
    List all configured LLMs (without API keys).
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
    """Save or update LLM configuration."""
    try:
        # 检查域名信任（仅在用户未确认时）
        if request.base_url and not request.user_confirmed:
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
        llm_id = request.id or generate_llm_id(
            provider=request.provider,
            model=request.model,
            base_url=request.base_url or "",
            name=request.name or ""
        )

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
        save_llm_config_to_storage(llm_config)

        # 如果是第一个 LLM，自动设为当前
        all_llms = load_all_llm_configs()
        if len(all_llms) == 1:
            set_current_llm(llm_id)
            # 重置 Agent Manager 以使用新的 LLM
            from app.api.chat import reset_agent_manager
            reset_agent_manager()

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
    """Switch to a different LLM (hot-switch)."""
    try:
        if not llm_exists(request.llm_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM {request.llm_id} not found"
            )

        # 切换当前 LLM
        set_current_llm(request.llm_id)

        # 重置 Agent Manager
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
    """Delete LLM configuration."""
    try:
        current_llm_id = get_current_llm_id()

        if llm_id == current_llm_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete current LLM. Please switch to another LLM first."
            )

        if not delete_llm_from_storage(llm_id):
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

class LegacySaveRequest(BaseModel):
    """Legacy request format for frontend compatibility."""
    provider: str = Field(..., description="Provider name")
    api_key: Optional[str] = Field(None, description="API key")
    model: Optional[str] = Field(None, description="Model name")
    base_url: Optional[str] = Field(None, description="Base URL")
    user_confirmed: Optional[bool] = Field(False, description="User confirmed untrusted domain")
    name: Optional[str] = Field(None, description="Display name")


@router.post("/save")
async def save_config(request: LegacySaveRequest):
    """
    Legacy endpoint for saving LLM config (compatibility with frontend).
    Maps to the new /llms endpoint.
    """
    try:
        # Generate name if not provided - use better logic for display name
        if request.name:
            display_name = request.name
        elif request.model:
            # Use model name as display name (e.g., "gpt-4", "claude-3-opus")
            display_name = request.model
        else:
            # Fallback to provider name
            display_name = request.provider.capitalize()

        # Check domain trust
        if request.base_url and not request.user_confirmed:
            domain = request.base_url.replace("https://", "").replace("http://", "").split("/")[0]
            domain = domain.split(":")[0]

            if not is_trusted_domain(domain):
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": f"⚠️ 域名 {domain} 不在预置的可信服务商列表中。请确认要使用此 API 吗？",
                    "domain": domain,
                }

        # Generate LLM ID (pass base_url and name for uniqueness)
        llm_id = generate_llm_id(
            provider=request.provider,
            model=request.model or "default",
            base_url=request.base_url or "",
            name=display_name
        )

        # Check if updating existing config
        existing_llm = load_llm_config(llm_id)

        # Determine API key
        api_key = request.api_key
        if not api_key and existing_llm:
            api_key = existing_llm.api_key
        elif not api_key and not existing_llm:
            return {
                "success": False,
                "message": "新建 LLM 配置必须提供 API Key"
            }

        # Create LLMConfig
        from app.config import LLMConfig
        llm_config = LLMConfig(
            id=llm_id,
            provider=request.provider,
            name=display_name,
            model=request.model or "default",
            base_url=request.base_url or "",
            api_key=api_key,
        )

        # Save
        save_llm_config_to_storage(llm_config)

        # Auto-set as current if first LLM
        all_llms = load_all_llm_configs()
        if len(all_llms) == 1:
            set_current_llm(llm_id)
            # 重置 Agent Manager 以使用新的 LLM
            from app.api.chat import reset_agent_manager
            reset_agent_manager()

        return {
            "success": True,
            "message": f"已保存 {display_name} 配置",
            "llm_id": llm_id
        }

    except Exception as e:
        logger.error(f"Failed to save config (legacy endpoint): {e}")
        return {
            "success": False,
            "message": f"保存失败: {str(e)}"
        }


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
        "available_providers": [],
        "configured_providers": list(set([llm.provider for llm in llms]))
    }
