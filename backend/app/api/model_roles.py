"""
Model Roles API — 角色管理 + 能力查询 + ASR/TTS/OCR 骨架
"""
from fastapi import APIRouter, HTTPException, status, File, UploadFile
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.core.model_roles import (
    MODEL_ROLES,
    ModelNotConfiguredError,
    load_role_bindings,
    save_role_binding,
    delete_role_binding,
    is_role_configured,
    get_capabilities as _get_capabilities,
)
from app.core.llm_config import load_llm_config
from app.core.llm import reset_agent_manager


router = APIRouter(tags=["model_roles"])
logger = logging.getLogger(__name__)


# ============================================================================
# 请求/响应模型
# ============================================================================

class RoleInfo(BaseModel):
    role_id: str
    name_zh: str
    name_en: str
    category: str
    description: str
    fallback: Optional[str]
    required: bool
    bound_llm_ids: list[str]
    bound_llm_names: list[str]
    is_configured: bool


class BindRoleRequest(BaseModel):
    llm_ids: list[str] = Field(..., description="有序优先级列表")


# ============================================================================
# 角色管理
# ============================================================================

@router.get("/roles")
async def list_roles():
    """返回所有角色定义 + 当前绑定状态"""
    bindings = load_role_bindings()

    roles = []
    for role_id, role_def in MODEL_ROLES.items():
        bound_ids = bindings.get(role_id, [])

        # main 特殊处理：无绑定时从 current_llm_id 获取
        if role_id == "main" and not bound_ids:
            from app.core.llm_config import get_current_llm_id
            current_id = get_current_llm_id()
            if current_id:
                bound_ids = [current_id]

        # 获取 LLM 显示名称
        bound_names = []
        for lid in bound_ids:
            config = load_llm_config(lid)
            bound_names.append(config.name if config else lid)

        roles.append(RoleInfo(
            role_id=role_id,
            name_zh=role_def["name_zh"],
            name_en=role_def["name_en"],
            category=role_def["category"],
            description=role_def["description"],
            fallback=role_def.get("fallback"),
            required=role_def["required"],
            bound_llm_ids=bound_ids,
            bound_llm_names=bound_names,
            is_configured=is_role_configured(role_id),
        ).dict())

    return {"roles": roles}


@router.put("/roles/{role_id}")
async def bind_role(role_id: str, request: BindRoleRequest):
    """绑定 LLM 到角色（热插拔，即时生效）"""
    if role_id not in MODEL_ROLES:
        raise HTTPException(status_code=404, detail=f"Role '{role_id}' not found")

    try:
        save_role_binding(role_id, request.llm_ids)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        if "cannot be empty" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    # 热插拔：重置 Agent Manager
    try:
        reset_agent_manager()
    except Exception:
        pass

    return {"success": True, "role_id": role_id}


@router.delete("/roles/{role_id}")
async def unbind_role(role_id: str):
    """解除角色绑定"""
    if role_id not in MODEL_ROLES:
        raise HTTPException(status_code=404, detail=f"Role '{role_id}' not found")

    try:
        delete_role_binding(role_id)
    except ValueError as e:
        error_msg = str(e)
        if "cannot be unbound" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    return {"success": True}


# ============================================================================
# 能力查询
# ============================================================================

@router.get("/capabilities")
async def get_capabilities():
    """前端查询已启用的能力"""
    return _get_capabilities()


# ============================================================================
# ASR/TTS/OCR 骨架端点（验证角色配置 + 格式校验 → 返回 503）
# ============================================================================

class AsrResponse(BaseModel):
    """ASR 语音识别响应模型。"""
    text: str = Field(..., description="识别结果文本")
    confidence: float = Field(..., description="置信度 (0.0-1.0)")


@router.post("/asr/transcribe", response_model=AsrResponse)
async def transcribe_audio(audio: UploadFile = File(...)):
    """ASR 语音识别骨架端点。

    当前阶段：验证角色已配置、验证音频格式，返回 503 表示后端尚未接入。
    真实接入时将根据角色配置的 base_url 调用 Whisper API 等服务。

    Args:
        audio: 音频文件（支持 webm/wav/mp3 格式）

    Returns:
        AsrResponse: 包含识别文本和置信度

    Raises:
        HTTPException 400: 音频格式不支持
        HTTPException 503: ASR 服务未配置或未接入
    """
    # 验证角色是否已配置
    if not is_role_configured("asr"):
        logger.warning("ASR 角色未配置，拒绝转录请求")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ASR service not configured. Please configure ASR role in settings.",
        )

    # 验证音频格式
    allowed_types = {"audio/webm", "audio/wav", "audio/mp3", "audio/mpeg", "audio/x-wav"}
    content_type = audio.content_type or ""
    if content_type not in allowed_types:
        logger.warning(f"ASR 不支持的音频格式: {content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {content_type}. Supported: {', '.join(allowed_types)}",
        )

    # 骨架阶段：记录日志并返回 503
    logger.info(f"ASR skeleton: 角色已配置但后端尚未接入，音频文件={audio.filename}, 格式={content_type}")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ASR service configured but not yet connected. Skeleton endpoint ready.",
    )


class TtsRequest(BaseModel):
    """TTS 语音合成请求模型。"""
    text: str = Field(..., description="要合成的文本", min_length=1, max_length=5000)
    voice: str = Field("default", description="语音标识符")


@router.post("/tts/synthesize")
async def synthesize_speech(request: TtsRequest):
    """TTS 语音合成骨架端点。

    当前阶段：验证角色已配置、验证文本输入，返回 503 表示后端尚未接入。
    真实接入时将根据角色配置的 base_url 调用 TTS API 返回音频流。

    Args:
        request: 包含合成文本和语音选择的请求体

    Returns:
        音频流 (audio/mpeg) — 骨架阶段暂不可用

    Raises:
        HTTPException 503: TTS 服务未配置或未接入
    """
    if not is_role_configured("tts"):
        logger.warning("TTS 角色未配置，拒绝合成请求")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS service not configured. Please configure TTS role in settings.",
        )

    # 骨架阶段：记录日志并返回 503
    logger.info(
        f"TTS skeleton: 角色已配置但后端尚未接入，文本长度={len(request.text)}, voice={request.voice}"
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="TTS service configured but not yet connected. Skeleton endpoint ready.",
    )


class OcrBlock(BaseModel):
    """OCR 识别的文本块。"""
    text: str = Field(..., description="识别出的文本")
    confidence: float = Field(..., description="置信度 (0.0-1.0)")
    bbox: list[float] | None = Field(None, description="文本区域边界框 [x1, y1, x2, y2]")


class OcrResponse(BaseModel):
    """OCR 文字识别响应模型。"""
    text: str = Field(..., description="完整识别文本")
    blocks: list[OcrBlock] = Field(default_factory=list, description="分块识别结果")


@router.post("/ocr/recognize", response_model=OcrResponse)
async def recognize_text(image: UploadFile = File(...)):
    """OCR 文字识别骨架端点。

    当前阶段：验证角色已配置、验证图片格式，返回 503 表示后端尚未接入。
    真实接入时将根据角色配置的 base_url 调用 OCR API 返回识别结果。

    Args:
        image: 图片文件（支持 png/jpg/jpeg/pdf 格式）

    Returns:
        OcrResponse: 包含完整识别文本和分块结果

    Raises:
        HTTPException 400: 图片格式不支持
        HTTPException 503: OCR 服务未配置或未接入
    """
    if not is_role_configured("ocr"):
        logger.warning("OCR 角色未配置，拒绝识别请求")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR service not configured. Please configure OCR role in settings.",
        )

    # 验证图片格式
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
    content_type = image.content_type or ""
    if content_type not in allowed_types:
        logger.warning(f"OCR 不支持的图片格式: {content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image format: {content_type}. Supported: {', '.join(allowed_types)}",
        )

    # 骨架阶段：记录日志并返回 503
    logger.info(f"OCR skeleton: 角色已配置但后端尚未接入，图片文件={image.filename}, 格式={content_type}")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="OCR service configured but not yet connected. Skeleton endpoint ready.",
    )


@router.get("/agents")
async def list_agents():
    """多 Agent 列表 — 预留"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Multi-agent not implemented yet.",
    )


@router.post("/agents/{agent_id}/llm")
async def set_agent_llm(agent_id: str):
    """多 Agent LLM 绑定 — 预留"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Multi-agent not implemented yet.",
    )
