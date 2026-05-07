"""
Multi-Model Roles — 角色注册表 + 绑定管理 + Failover

预定义角色（main/supervisor/planner/asr/tts/ocr），
用户为每个角色绑定已配置的 LLM（有序列表，支持 failover）。
"""
import logging
from typing import Optional

from app.core.llm_config import load_llm_config, llm_exists, get_current_llm_id
from app.core.llm import create_llm_from_config
from app.core.obfuscation import KeyObfuscator
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


# ============================================================================
# 异常
# ============================================================================

class ModelNotConfiguredError(Exception):
    """角色未配置且无回落时抛出"""
    def __init__(self, role_id: str):
        self.role_id = role_id
        super().__init__(f"Model role '{role_id}' not configured and has no fallback")


class AllModelsFailedError(Exception):
    """角色 failover 链全部失败时抛出"""
    def __init__(self, role_id: str, errors: list):
        self.role_id = role_id
        self.errors = errors
        super().__init__(f"All models failed for role '{role_id}': {len(errors)} errors")


# ============================================================================
# 角色注册表
# ============================================================================

MODEL_ROLES = {
    "main": {
        "name_zh": "主 LLM", "name_en": "Main LLM",
        "category": "chat",
        "description": "对话、工具调用、生成回答",
        "fallback": None,
        "required": True,
        "hot_plug": True,
    },
    "supervisor": {
        "name_zh": "监督 LLM", "name_en": "Supervisor LLM",
        "category": "chat",
        "description": "反思评估、ToT 评分、复杂度评估",
        "fallback": "main",
        "required": False,
        "hot_plug": True,
    },
    "planner": {
        "name_zh": "规划 LLM", "name_en": "Planner LLM",
        "category": "chat",
        "description": "ToT/PERV 规划步骤",
        "fallback": "main",
        "required": False,
        "hot_plug": True,
    },
    "asr": {
        "name_zh": "语音识别", "name_en": "ASR",
        "category": "speech",
        "description": "语音转文字",
        "fallback": None,
        "required": False,
        "hot_plug": True,
    },
    "tts": {
        "name_zh": "语音合成", "name_en": "TTS",
        "category": "speech",
        "description": "文字转语音，核心功能是语音对话",
        "fallback": None,
        "required": False,
        "hot_plug": True,
    },
    "ocr": {
        "name_zh": "OCR", "name_en": "OCR",
        "category": "vision",
        "description": "图片/PDF 文字识别",
        "fallback": None,
        "required": False,
        "hot_plug": True,
    },
}


# ============================================================================
# 绑定管理
# ============================================================================

def normalize_role_bindings(raw: dict) -> dict[str, list[str]]:
    """将旧格式（字符串）转为新格式（列表）"""
    result = {}
    for role_id, value in raw.items():
        if isinstance(value, str):
            result[role_id] = [value]
        elif isinstance(value, list):
            result[role_id] = value
        else:
            logger.warning(f"Invalid role binding for {role_id}: {type(value)}, skipping")
    return result


def load_role_bindings() -> dict[str, list[str]]:
    """从 credentials.encrypted 加载 role_bindings（兼容旧格式）"""
    try:
        credentials = KeyObfuscator.load_credentials()
        raw = credentials.get("role_bindings", {})
        return normalize_role_bindings(raw)
    except Exception as e:
        logger.debug(f"Failed to load role bindings: {e}")
        return {}


def save_role_binding(role_id: str, llm_ids: list[str]) -> None:
    """保存角色绑定（有序列表，热插拔）"""
    if role_id not in MODEL_ROLES:
        raise ValueError(f"Unknown role: {role_id}")

    if role_id == "main" and not llm_ids:
        raise ValueError("Main role binding cannot be empty")

    # 去重，保持顺序
    seen = set()
    unique_ids = []
    for lid in llm_ids:
        if lid not in seen:
            seen.add(lid)
            unique_ids.append(lid)
    llm_ids = unique_ids

    # 校验所有 LLM 存在
    credentials = KeyObfuscator.load_credentials()
    llms = credentials.get("llms", {})
    for lid in llm_ids:
        if lid not in llms:
            raise ValueError(f"LLM {lid} not found")

    # 写入 role_bindings
    if "role_bindings" not in credentials:
        credentials["role_bindings"] = {}
    credentials["role_bindings"][role_id] = llm_ids

    # main 角色同步 current_llm_id
    if role_id == "main" and llm_ids:
        credentials["current_llm_id"] = llm_ids[0]

    KeyObfuscator.save_credentials(credentials)
    logger.info(f"Saved role binding: {role_id} -> {llm_ids}")


def delete_role_binding(role_id: str) -> None:
    """删除角色绑定"""
    if role_id == "main":
        raise ValueError("Main role cannot be unbound")

    credentials = KeyObfuscator.load_credentials()
    bindings = credentials.get("role_bindings", {})

    if role_id in bindings:
        del bindings[role_id]
        if not bindings:
            del credentials["role_bindings"]
        KeyObfuscator.save_credentials(credentials)
        logger.info(f"Deleted role binding: {role_id}")


# ============================================================================
# 角色解析 + Failover
# ============================================================================

def get_role_llm(role_id: str) -> BaseChatModel:
    """
    获取角色主力 LLM 实例（优先级列表第一项）。
    支持回落链：绑定列表 → fallback 角色 → 抛出异常。
    """
    chain = _resolve_llm_chain(role_id)
    if chain:
        return chain[0]

    # 尝试 fallback 角色
    role_def = MODEL_ROLES.get(role_id, {})
    fallback_role = role_def.get("fallback")
    if fallback_role:
        return get_role_llm(fallback_role)

    raise ModelNotConfiguredError(role_id)


def get_role_llm_chain(role_id: str) -> list[BaseChatModel]:
    """获取角色完整 failover 链（所有可用 LLM 实例）"""
    return _resolve_llm_chain(role_id)


def get_role_llm_config(role_id: str):
    """获取角色主力 LLM 的原始配置（非实例），供需要自定义参数的调用点使用。

    某些模块（如在线蒸馏）需要获取 base_url/api_key 等原始配置参数
    来构造自定义的 LLM 实例，而非直接使用 get_role_llm 返回的 BaseChatModel。

    Args:
        role_id: 角色标识符，如 "main", "planner", "supervisor"

    Returns:
        LLMConfig: 角色主力 LLM 的原始配置对象

    Raises:
        ModelNotConfiguredError: 当角色未配置任何 LLM 且无可用 fallback 时
    """
    logger.debug(f"获取角色 '{role_id}' 的原始 LLM 配置")

    bindings = load_role_bindings()

    if role_id == "main":
        # main 角色特殊处理：无绑定时从 current_llm_id 获取
        llm_ids = bindings.get("main", [])
        if not llm_ids:
            current_id = get_current_llm_id()
            if current_id:
                llm_ids = [current_id]
    else:
        llm_ids = bindings.get(role_id, [])

    # 按优先级查找第一个可用的 LLM 配置
    for lid in llm_ids:
        if llm_exists(lid):
            config = load_llm_config(lid)
            if config:
                logger.debug(f"角色 '{role_id}' 使用 LLM 配置: {lid}")
                return config

    # fallback: 尝试角色的 fallback 链
    role_def = MODEL_ROLES.get(role_id, {})
    fallback_role = role_def.get("fallback")
    if fallback_role:
        logger.info(f"角色 '{role_id}' 无可用 LLM，回落到 '{fallback_role}'")
        return get_role_llm_config(fallback_role)

    logger.error(f"角色 '{role_id}' 未配置任何 LLM 且无可用 fallback")
    raise ModelNotConfiguredError(role_id)


def _resolve_llm_chain(role_id: str) -> list[BaseChatModel]:
    """解析角色的有序 LLM 实例列表，跳过无效配置"""
    bindings = load_role_bindings()

    # 特殊处理 main：无绑定时从 current_llm_id 获取
    if role_id == "main":
        llm_ids = bindings.get("main", [])
        if not llm_ids:
            current_id = get_current_llm_id()
            if current_id:
                llm_ids = [current_id]
    else:
        llm_ids = bindings.get(role_id, [])

    instances = []
    for lid in llm_ids:
        try:
            if not llm_exists(lid):
                logger.warning(f"Role {role_id}: LLM {lid} not found, skipping")
                continue
            config = load_llm_config(lid)
            if config:
                instances.append(create_llm_from_config(config))
        except Exception as e:
            logger.warning(f"Role {role_id}: failed to create LLM {lid}: {e}")
            continue

    return instances


def try_role_llm(role_id: str):
    """
    获取角色 LLM + failover 生成器。
    返回 (llm_instance, failover_fn)。
    调用方在 LLM 调用失败时调用 failover_fn() 获取下一个。
    全部失败抛出 AllModelsFailedError。
    """
    chain = _resolve_llm_chain(role_id)

    # 无实例时尝试 fallback
    if not chain:
        role_def = MODEL_ROLES.get(role_id, {})
        fallback_role = role_def.get("fallback")
        if fallback_role:
            return try_role_llm(fallback_role)
        raise ModelNotConfiguredError(role_id)

    index = [0]  # 用 list 以便闭包修改

    def failover():
        index[0] += 1
        if index[0] < len(chain):
            return chain[index[0]]
        raise AllModelsFailedError(role_id, [])

    return chain[0], failover


# ============================================================================
# 状态查询
# ============================================================================

def is_role_configured(role_id: str) -> bool:
    """检查角色是否已配置"""
    bindings = load_role_bindings()

    if role_id == "main":
        llm_ids = bindings.get("main", [])
        if llm_ids:
            return True
        # main 也可能通过 current_llm_id 配置
        return bool(get_current_llm_id())

    llm_ids = bindings.get(role_id, [])
    if not llm_ids:
        return False
    # 至少有一个存在的 LLM
    return any(llm_exists(lid) for lid in llm_ids)


def get_capabilities() -> dict[str, bool]:
    """获取所有非 main 角色的配置状态（前端用）"""
    caps = {}
    for role_id, role_def in MODEL_ROLES.items():
        if role_id == "main":
            continue
        caps[role_id] = is_role_configured(role_id)
    return caps
