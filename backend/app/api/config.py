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


@router.get("/settings")
async def get_app_settings():
    """
    Get application settings (excluding sensitive information).

    Returns all configuration values except API keys and other sensitive data.
    """
    try:
        from app.config import get_settings

        settings = get_settings()

        # Convert settings to dictionary, excluding sensitive fields
        settings_dict = {
            # Application
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "debug": settings.debug,

            # Server
            "host": settings.host,
            "port": settings.port,

            # LLM Configuration (without API keys)
            "llm_provider": settings.llm_provider,
            "openai_model": settings.openai_model,
            "openai_base_url": settings.openai_base_url,
            "deepseek_model": settings.deepseek_model,
            "deepseek_base_url": settings.deepseek_base_url,
            "qwen_model": settings.qwen_model,
            "qwen_base_url": settings.qwen_base_url,
            "ollama_base_url": settings.ollama_base_url,
            "ollama_model": settings.ollama_model,
            "claude_model": settings.claude_model,
            "claude_base_url": settings.claude_base_url,
            "gemini_model": settings.gemini_model,
            "gemini_base_url": settings.gemini_base_url,
            "custom_model": settings.custom_model,
            "custom_base_url": settings.custom_base_url,

            # File Paths
            "base_dir": settings.base_dir,
            "data_dir": settings.data_dir,
            "knowledge_base_dir": settings.knowledge_base_dir,
            "sessions_dir": settings.sessions_dir,
            "skills_dir": settings.skills_dir,
            "vector_store_dir": settings.vector_store_dir,
            "workspace_dir": settings.workspace_dir,

            # Tool Security
            "terminal_root_dir": settings.terminal_root_dir,
            "terminal_blocked_commands": settings.terminal_blocked_commands,
            "read_file_root_dir": settings.read_file_root_dir,
            "allowed_write_dirs": settings.allowed_write_dirs,

            # Python REPL Configuration
            "python_execution_mode": settings.python_execution_mode,
            "python_safe_timeout": settings.python_safe_timeout,
            "python_standard_timeout": settings.python_standard_timeout,
            "python_free_timeout": settings.python_free_timeout,
            "python_safe_memory_ratio": settings.python_safe_memory_ratio,
            "python_standard_memory_ratio": settings.python_standard_memory_ratio,
            "python_free_memory_ratio": settings.python_free_memory_ratio,
            "python_safe_max_operations": settings.python_safe_max_operations,
            "python_standard_max_operations": settings.python_standard_max_operations,
            "python_free_max_operations": settings.python_free_max_operations,
            "python_monitor_interval": settings.python_monitor_interval,
            "python_warning_threshold": settings.python_warning_threshold,

            # Tree of Thoughts Configuration
            "enable_tot": settings.enable_tot,
            "tot_max_depth": settings.tot_max_depth,
            "tot_branching_factor": settings.tot_branching_factor,
            "tot_quality_threshold": settings.tot_quality_threshold,
            "tot_auto_enable_keywords": settings.tot_auto_enable_keywords,
            "tot_checkpoint_path": settings.tot_checkpoint_path,
            "tot_enable_tool_validation": settings.tot_enable_tool_validation,
            "tot_max_tool_retries": settings.tot_max_tool_retries,
            "tot_enable_smart_stopping": settings.tot_enable_smart_stopping,
            "tot_min_successful_tools": settings.tot_min_successful_tools,
            "tot_redundancy_window": settings.tot_redundancy_window,
            "tot_score_plateau_threshold": settings.tot_score_plateau_threshold,
            "tot_enable_llm_evaluation": settings.tot_enable_llm_evaluation,
            "tot_llm_eval_interval": settings.tot_llm_eval_interval,
            "tot_max_depth_multiplier": settings.tot_max_depth_multiplier,
            "tot_enable_beam_search": settings.tot_enable_beam_search,
            "tot_beam_width": settings.tot_beam_width,
            "tot_path_score_weights": settings.tot_path_score_weights,
            "tot_enable_backtracking": settings.tot_enable_backtracking,
            "tot_backtrack_failure_threshold": settings.tot_backtrack_failure_threshold,
            "tot_backtrack_plateau_threshold": settings.tot_backtrack_plateau_threshold,
            "tot_enable_cache": settings.tot_enable_cache,
            "tot_cache_ttl": settings.tot_cache_ttl,

            # Deep Research Configuration
            "enable_deep_research": settings.enable_deep_research,
            "research_mode": settings.research_mode,
            "thinking_modes": settings.thinking_modes,
            "research_sources_priority": settings.research_sources_priority,

            # RAG / Knowledge Base
            "enable_rag": settings.enable_rag,
            "embedding_model": settings.embedding_model,
            "vector_store_type": settings.vector_store_type,
            "hybrid_search_alpha": settings.hybrid_search_alpha,
            "retrieval_top_k": settings.retrieval_top_k,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "max_file_size": settings.max_file_size,
            "large_file_threshold": settings.large_file_threshold,
            "allowed_file_types": settings.allowed_file_types,
            "max_batch_files": settings.max_batch_files,
            "max_folder_depth": settings.max_folder_depth,
            "embedding_fallback": settings.embedding_fallback,
            "embedding_warmup_enabled": settings.embedding_warmup_enabled,
            "embedding_warmup_timeout": settings.embedding_warmup_timeout,
            "embedding_hf_endpoint": settings.embedding_hf_endpoint,
            "embedding_hf_timeout": settings.embedding_hf_timeout,
            "embedding_hf_retries": settings.embedding_hf_retries,

            # Session Management
            "session_timeout": settings.session_timeout,
            "max_message_history": settings.max_message_history,

            # System Prompt
            "max_prompt_length": settings.max_prompt_length,
            "truncation_marker": settings.truncation_marker,

            # Agent Execution
            "max_tool_rounds": settings.max_tool_rounds,
            "enable_smart_stopping": settings.enable_smart_stopping,
            "sufficiency_evaluation_interval": settings.sufficiency_evaluation_interval,

            # Performance Optimization
            "enable_semantic_search_cache": settings.enable_semantic_search_cache,
            "semantic_search_cache_ttl": settings.semantic_search_cache_ttl,
            "enable_context_cache": settings.enable_context_cache,
            "context_cache_size": settings.context_cache_size,
            "enable_prompt_cache": settings.enable_prompt_cache,
            "enable_parallel_tool_execution": settings.enable_parallel_tool_execution,
            "enable_auto_fallback": settings.enable_auto_fallback,
            "parallel_tool_dependency_detection": settings.parallel_tool_dependency_detection,
            "max_concurrent_tools": settings.max_concurrent_tools,
            "enable_streaming_response": settings.enable_streaming_response,
            "streaming_chunk_size": settings.streaming_chunk_size,
            "enable_smart_truncation": settings.enable_smart_truncation,
            "max_prompt_tokens": settings.max_prompt_tokens,
            "prompt_token_budget": settings.prompt_token_budget,

            # Memory System
            "enable_memory_extraction": settings.enable_memory_extraction,
            "enable_semantic_search": settings.enable_semantic_search,
            "enable_user_profile_learning": settings.enable_user_profile_learning,
            "enable_long_term_memory": settings.enable_long_term_memory,
            "memory_extraction_interval": settings.memory_extraction_interval,
            "memory_min_confidence": settings.memory_min_confidence,
            "memory_max_conversations": settings.memory_max_conversations,
            "memory_extraction_max_retries": settings.memory_extraction_max_retries,
            "vector_indexing_max_retries": settings.vector_indexing_max_retries,
            "vector_indexing_retry_delay": settings.vector_indexing_retry_delay,
            "user_profile_update_interval": settings.user_profile_update_interval,
            "long_term_memory_max_items": settings.long_term_memory_max_items,
            "long_term_memory_prune_threshold": settings.long_term_memory_prune_threshold,
            "memory_db_path": settings.memory_db_path,
            "use_sqlite": settings.use_sqlite,
            "dual_write_mode": settings.dual_write_mode,
            "md_user_max_items": settings.md_user_max_items,
            "md_memory_max_items": settings.md_memory_max_items,
            "md_user_include_days": settings.md_user_include_days,
            "md_memory_include_days": settings.md_memory_include_days,
            "md_sync_interval": settings.md_sync_interval,
            "md_min_confidence": settings.md_min_confidence,
            "md_auto_sync": settings.md_auto_sync,

            # Skills Dependency Management
            "enable_skill_dependency_check": settings.enable_skill_dependency_check,
            "auto_install_python_dependencies": settings.auto_install_python_dependencies,
            "skill_dependency_install_timeout": settings.skill_dependency_install_timeout,

            # Logging Configuration
            "log_level": settings.log_level,
            "log_dir": settings.log_dir,
            "log_to_file": settings.log_to_file,
            "log_to_console": settings.log_to_console,
            "log_max_bytes": settings.log_max_bytes,
            "log_backup_count": settings.log_backup_count,
            "log_format": settings.log_format,
            "log_format_with_tracking": settings.log_format_with_tracking,
            "debug_agent": settings.debug_agent,
            "enable_json_logs": settings.enable_json_logs,
            "json_log_file": settings.json_log_file,
            "enable_agent_trajectory": settings.enable_agent_trajectory,
            "trajectory_log_dir": settings.trajectory_log_dir,
            "save_trajectory_to_file": settings.save_trajectory_to_file,
            "max_trajectory_size": settings.max_trajectory_size,
            "enable_langchain_callbacks": settings.enable_langchain_callbacks,
            "callback_capture_thoughts": settings.callback_capture_thoughts,
            "callback_capture_actions": settings.callback_capture_actions,
            "callback_capture_results": settings.callback_capture_results,
            "enable_log_sanitization": settings.enable_log_sanitization,
            "sanitize_user_input": settings.sanitize_user_input,
            "sanitize_file_paths": settings.sanitize_file_paths,
            "enable_error_context": settings.enable_error_context,
            "capture_locals_in_errors": settings.capture_locals_in_errors,
            "max_local_vars_to_capture": settings.max_local_vars_to_capture,
            "enable_business_metrics": settings.enable_business_metrics,
            "metrics_log_file": settings.metrics_log_file,
            "metrics_aggregation_interval": settings.metrics_aggregation_interval,
            "enable_error_aggregation": settings.enable_error_aggregation,
            "error_alert_threshold": settings.error_alert_threshold,
            "error_alert_window": settings.error_alert_window,

            # Layered Reflection Trigger Configuration
            "enable_agent_reflection": settings.enable_agent_reflection,
            "agent_reflection_quality_threshold": settings.agent_reflection_quality_threshold,

            # Structured Reflection Output Configuration
            "reflection_require_failure_type": settings.reflection_require_failure_type,
            "reflection_require_root_cause": settings.reflection_require_root_cause,
            "reflection_require_reusable_pattern": settings.reflection_require_reusable_pattern,
            "reward_quality_weight": settings.reward_quality_weight,
            "reward_shaping_weight": settings.reward_shaping_weight,

            # Pattern Memory Configuration
            "enable_pattern_memory": settings.enable_pattern_memory,
            "pattern_storage_path": settings.pattern_storage_path,
            "pattern_nn_path": settings.pattern_nn_path,
            "pattern_embedder_model_name": settings.pattern_embedder_model_name,
            "pattern_nn_embed_dim": settings.pattern_nn_embed_dim,
            "pattern_nn_hidden1": settings.pattern_nn_hidden1,
            "pattern_nn_hidden2": settings.pattern_nn_hidden2,
            "pattern_nn_num_patterns": settings.pattern_nn_num_patterns,
            "pattern_nn_learning_rate": settings.pattern_nn_learning_rate,
            "pattern_nn_dropout": settings.pattern_nn_dropout,
        }

        return settings_dict

    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get settings: {str(e)}",
        )
