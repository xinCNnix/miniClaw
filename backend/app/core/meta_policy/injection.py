"""PolicyInjector — 根据元策略建议和注入强度生成注入文本。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Dict
import logging

from app.core.meta_policy.types import ActionType

if TYPE_CHECKING:
    from app.core.meta_policy.task_complexity import DecompositionDecision

logger = logging.getLogger(__name__)


# 阶段到注入模板的映射
_INJECTION_TEMPLATES = {
    "baseline": {
        # baseline 阶段不注入任何内容
    },
    "conservative": {
        ActionType.CALL_TOOL: "可以考虑使用工具 {tool} 来辅助处理。",
        ActionType.CALL_SKILL: "可以考虑使用技能 {skill} 来处理这类问题。建议先 read_file 读取 SKILL.md。",
        ActionType.THINK: "这个问题可以尝试直接思考和推理。",
        ActionType.FINISH: "当前信息可能已经足够，可以考虑整理回复。",
    },
    "nn_dominant": {
        ActionType.CALL_TOOL: "建议使用工具 {tool} 来处理当前任务。置信度: {confidence:.0%}",
        ActionType.CALL_SKILL: "建议使用技能 {skill}。请先 read_file 读取 SKILL.md 了解使用方法。置信度: {confidence:.0%}",
        ActionType.THINK: "当前任务适合通过思考推理来解决，无需额外工具调用。置信度: {confidence:.0%}",
        ActionType.FINISH: "当前已收集足够信息，建议整理并给出最终回复。置信度: {confidence:.0%}",
    },
    "transition": {
        ActionType.CALL_TOOL: "请优先使用工具 {tool} 处理此任务。这是基于历史模式的推荐。置信度: {confidence:.0%}",
        ActionType.CALL_SKILL: "请优先使用技能 {skill}。请先 read_file 读取 SKILL.md，然后按照指令执行。置信度: {confidence:.0%}",
        ActionType.THINK: "根据分析，当前无需工具调用，请直接推理回答。置信度: {confidence:.0%}",
        ActionType.FINISH: "根据分析，当前已具备足够信息，请整理回复。置信度: {confidence:.0%}",
    },
    "active": {
        ActionType.CALL_TOOL: "请优先使用工具 {tool} 处理此任务。这是基于历史模式的推荐。置信度: {confidence:.0%}",
        ActionType.CALL_SKILL: "请优先使用技能 {skill}。请先 read_file 读取 SKILL.md，然后按照指令执行。置信度: {confidence:.0%}",
        ActionType.THINK: "根据分析，当前无需工具调用，请直接推理回答。置信度: {confidence:.0%}",
        ActionType.FINISH: "根据分析，当前已具备足够信息，请整理回复。置信度: {confidence:.0%}",
    },
}

# 注入强度到阶段的映射
_STRENGTH_STAGE_MAP = {
    "hint": "conservative",
    "suggest": "nn_dominant",
    "guide": "transition",
}


class PolicyInjector:
    """根据元策略建议和注入强度生成注入文本。

    注入文本随阶段渐进增强：
    - baseline: 空字符串（不注入）
    - conservative: 轻微提示
    - nn_dominant: 明确建议
    - transition/active: 强指导
    """

    def build_injection_text(
        self,
        action_type: ActionType,
        tool: Optional[str],
        skill: Optional[str],
        confidence: float,
        strength: str,
        stage: str,
        skill_descriptions: Optional[Dict[str, str]] = None,
    ) -> str:
        """生成注入文本。

        Args:
            action_type: 建议的动作类型
            tool: 推荐的工具名称（仅 CALL_TOOL 时有值）
            skill: 推荐的技能名称（仅 CALL_SKILL 时有值）
            confidence: 置信度 [0, 1]
            strength: 注入强度 ("hint" | "suggest" | "guide")
            stage: 当前阶段名称
            skill_descriptions: 技能名称到描述的映射（可选，用于增强注入文本）

        Returns:
            注入文本字符串，baseline 阶段返回空字符串
        """
        # baseline 阶段不注入
        if stage == "baseline":
            return ""

        # 获取该阶段的模板
        templates = _INJECTION_TEMPLATES.get(stage, {})
        template = templates.get(action_type, "")
        if not template:
            return ""

        # 格式化模板
        try:
            text = template.format(
                tool=tool or "",
                skill=skill or "",
                confidence=confidence,
            )
        except (KeyError, IndexError):
            logger.warning("Failed to format injection template: %s", template)
            return ""

        # 如果是技能推荐且有描述，追加技能描述
        if (
            action_type == ActionType.CALL_SKILL
            and skill
            and skill_descriptions
            and skill in skill_descriptions
        ):
            desc = skill_descriptions[skill]
            text += f"\n技能描述: {desc}"

        return text

    def get_stage_for_strength(self, strength: str) -> str:
        """将注入强度映射到阶段名称。

        Args:
            strength: "hint" | "suggest" | "guide"

        Returns:
            对应的阶段名称
        """
        return _STRENGTH_STAGE_MAP.get(strength, "conservative")

    # --- TCA 注入 ---

    def build_tca_injection_text(
        self,
        decision: "DecompositionDecision",
        phase: str,
    ) -> str:
        """根据 TCA 决策和部署阶段生成分解指导注入文本。

        Args:
            decision: TCA 分解决策
            phase: 部署阶段 ("collection" | "shadow" | "mixed" | "dominant")

        Returns:
            注入文本，collection/shadow 阶段返回空字符串
        """
        if phase in ("collection", "shadow"):
            return ""

        if not decision.should_decompose:
            # 简单任务提示
            if phase == "dominant" and decision.confidence > 0.7:
                return "此任务复杂度较低，建议直接回答，无需分解或使用复杂工具链。"
            return ""

        # 需要分解的任务
        parts = []
        if phase == "mixed":
            parts.append(f"此任务可能需要分解为 {decision.suggested_subtask_count} 个子任务。")
            if decision.complexity == "high":
                parts.append("任务复杂度较高，建议仔细规划执行步骤。")
        elif phase == "dominant":
            parts.append(
                f"建议将此任务分解为 {decision.suggested_subtask_count} 个子任务。"
                f"复杂度: {decision.complexity}。置信度: {decision.confidence:.0%}"
            )
            if decision.capability_hints:
                hints_str = "、".join(decision.capability_hints[:5])
                parts.append(f"可能需要的能力: {hints_str}")

        return "\n".join(parts)
