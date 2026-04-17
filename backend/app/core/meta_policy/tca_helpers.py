"""TCA 集成辅助 — 统一的 TCA 决策获取入口。

避免在各集成点重复 TCA 初始化、嵌入编码、部署阶段判断等逻辑。
"""

import logging
from typing import Optional

import torch

logger = logging.getLogger(__name__)


def get_tca_decision(
    query: str,
    ctx: str = "",
    cap_map: Optional[object] = None,
) -> Optional[object]:
    """获取 TCA 任务分解决策。

    处理 feature flag 检查、部署阶段判断、嵌入编码、模型推理全流程。

    Args:
        query: 用户查询文本
        ctx: 上下文文本 (可选)
        cap_map: CapabilityMap 实例 (可选，默认自动创建)

    Returns:
        DecompositionDecision 实例，或 None (TCA 未启用/未到注入阶段)
    """
    from app.config import get_settings

    settings = get_settings()
    if not getattr(settings, "enable_tca", False):
        return None

    try:
        from app.core.meta_policy.complexity_trainer import get_tca_trainer
        from app.core.meta_policy.capability_map import CapabilityMap
        from app.core.meta_policy.injection import PolicyInjector
        from app.memory.auto_learning.utils import get_embedder

        trainer = get_tca_trainer()
        phase = trainer.get_deployment_phase()

        # collection 和 shadow 阶段不注入
        if phase in ("collection", "shadow"):
            return None

        # 按阶段概率决定是否注入
        if not trainer.should_inject():
            return None

        # 编码查询
        embedder = get_embedder()
        task_emb = torch.tensor(embedder.encode(query), dtype=torch.float32)

        # 编码上下文 (可选)
        ctx_emb = None
        if ctx:
            ctx_emb = torch.tensor(embedder.encode(ctx), dtype=torch.float32)

        # 获取 capability_map
        if cap_map is None:
            cap_map = CapabilityMap.from_core_tools()

        # 调用模型分析
        decision = trainer.model.analyze(
            task_emb=task_emb,
            ctx_emb=ctx_emb,
            tool_embs=None,
            skill_embs=None,
            capability_map=cap_map,
            decompose_threshold=settings.tca_decompose_threshold,
        )

        # 生成注入文本
        injector = PolicyInjector()
        decision.injection_text = injector.build_tca_injection_text(decision, phase)

        if decision.injection_text:
            logger.debug(
                "[TCA] Decision: decompose=%s, complexity=%s, subtasks=%d, confidence=%.2f",
                decision.should_decompose,
                decision.complexity,
                decision.suggested_subtask_count,
                decision.confidence,
            )

        return decision

    except Exception as e:
        logger.debug("[TCA] get_tca_decision failed: %s", e)
        return None


def record_tca_episode(
    query: str,
    tool_calls: list,
    plan_steps: int = 0,
    task_completed: bool = True,
) -> None:
    """从 PERV/ToT 执行结果中提取 TCA 训练标签并记录。

    在后执行学习环节 (post-learning) 中调用。无论 TCA 是否启用都尝试记录，
    因为数据收集应在模型生效前就开始。

    标签提取规则（按计划）：
    - PERV planner 生成 3+ 步 → decompose=1；direct_answer → decompose=0
    - 计划步数 → complexity: 1=low, 2-3=medium, 4+=high
    - 实际工具调用数 → subtask_count_label
    - 使用的工具/技能 → capability_label (multi-hot)

    Args:
        query: 用户查询文本
        tool_calls: 工具调用列表 [{"name": ..., "success": bool}, ...]
        plan_steps: PERV 计划步数 / ToT 思考深度
        task_completed: 任务是否成功完成
    """
    from app.config import get_settings

    settings = get_settings()
    if not getattr(settings, "enable_tca", False):
        return

    try:
        from app.core.meta_policy.complexity_trainer import get_tca_trainer
        from app.core.meta_policy.capability_map import CapabilityMap
        from app.memory.auto_learning.utils import get_embedder

        trainer = get_tca_trainer()
        cap_map = CapabilityMap.from_core_tools()

        # 编码查询
        embedder = get_embedder()
        task_emb = torch.tensor(embedder.encode(query), dtype=torch.float32)

        # --- 提取标签 ---
        # decompose_label: 有计划且步数>=2 或 工具调用>=3 → 分解
        effective_steps = max(plan_steps, len(tool_calls))
        decompose_label = 1 if effective_steps >= 2 else 0

        # complexity_label: 0=low, 1=medium, 2=high
        if effective_steps <= 1:
            complexity_label = 0
        elif effective_steps <= 3:
            complexity_label = 1
        else:
            complexity_label = 2

        # subtask_count_label: 0-4 (实际子任务数-1)，clamp 到 [0, 4]
        subtask_count_label = min(max(effective_steps - 1, 0), 4)

        # capability_label: multi-hot
        total_slots = trainer.model.max_tool_slots + trainer.model.max_skill_slots
        capability_label = torch.zeros(total_slots)
        unique_tools = set()
        for tc in tool_calls:
            name = tc.get("name", "") if isinstance(tc, dict) else str(tc)
            if name:
                unique_tools.add(name)

        for name in unique_tools:
            tool_slot = cap_map.get_tool_slot(name)
            if tool_slot is not None:
                capability_label[tool_slot] = 1.0
            else:
                skill_slot = cap_map.get_skill_slot(name)
                if skill_slot is not None:
                    capability_label[trainer.model.max_tool_slots + skill_slot] = 1.0

        # 记录
        trainer.record_episode(
            task_emb=task_emb,
            decompose_label=decompose_label,
            complexity_label=complexity_label,
            subtask_count_label=subtask_count_label,
            capability_label=capability_label,
        )

        logger.debug(
            "[TCA] Recorded episode: decompose=%d, complexity=%d, subtasks=%d, tools=%s",
            decompose_label, complexity_label, subtask_count_label + 1, unique_tools,
        )

    except Exception as e:
        logger.debug("[TCA] record_tca_episode failed: %s", e)
