"""
Meta Policy Network — 类型定义

定义元策略网络的核心数据结构，包括动作枚举、策略状态和策略建议。
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """元策略网络可输出的动作类型。

    Attributes:
        CALL_TOOL: 调用一个 Core Tool（read_file / terminal / python_repl 等）。
        CALL_SKILL: 调用一个 Skill（通过 SKILL.md 定义的技能）。
        THINK: 继续推理（不调用任何外部工具/技能）。
        FINISH: 结束当前轮次，输出最终回答。
    """

    CALL_TOOL = "call_tool"
    CALL_SKILL = "call_skill"
    THINK = "think"
    FINISH = "finish"


class PolicyState(BaseModel):
    """策略网络的输入状态向量。

    由 agent 主循环在每一轮拼装，传递给元策略网络进行决策。

    Attributes:
        state_vec: 语义状态向量（来自 LLM hidden state 或 embedding），长度由网络配置决定。
        latent_z: 潜在变量 z，用于编码用户意图或对话主题。
        tools_available: 当前可用工具名称列表。
        skills_available: 当前可用技能名称列表。
        round_count: 当前已执行的 agent 轮次计数。
        max_rounds: 本轮对话允许的最大轮次上限。
    """

    state_vec: List[float] = Field(
        default_factory=list,
        description="语义状态向量，由 embedding 或 hidden state 生成",
    )
    latent_z: List[float] = Field(
        default_factory=list,
        description="潜在变量 z，编码用户意图或对话主题",
    )
    tools_available: List[str] = Field(
        default_factory=list,
        description="当前可用工具名称列表",
    )
    skills_available: List[str] = Field(
        default_factory=list,
        description="当前可用技能名称列表",
    )
    round_count: int = Field(
        default=0,
        ge=0,
        description="当前已执行的 agent 轮次计数",
    )
    max_rounds: int = Field(
        default=50,
        gt=0,
        description="本轮对话允许的最大轮次上限",
    )


class MetaPolicyAdvice(BaseModel):
    """元策略网络输出的决策建议。

    由元策略网络（baseline 规则引擎或 NN 模型）生成，注入到 agent 的
    system prompt 或工具选择逻辑中，以非破坏性方式引导决策。

    Attributes:
        action_type: 建议的动作类型。
        tool: 建议调用的工具名称，仅在 action_type == CALL_TOOL 时有值。
        skill: 建议调用的技能名称，仅在 action_type == CALL_SKILL 时有值。
        confidence: 决策置信度，取值范围 [0.0, 1.0]。
        source: 决策来源，"baseline" 表示规则引擎，"nn" 表示神经网络模型。
        stage: 当前决策阶段标识（如 "pre_tool"、"post_tool"、"final" 等）。
        injection_text: 注入到 prompt 中的引导文本，用于以 hint/suggest/guide 强度影响 LLM。
    """

    action_type: ActionType = Field(
        description="建议的动作类型",
    )
    tool: Optional[str] = Field(
        default=None,
        description="建议调用的工具名称（仅 CALL_TOOL 时有值）",
    )
    skill: Optional[str] = Field(
        default=None,
        description="建议调用的技能名称（仅 CALL_SKILL 时有值）",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="决策置信度 [0.0, 1.0]",
    )
    source: str = Field(
        default="baseline",
        pattern="^(baseline|nn)$",
        description='决策来源: "baseline"（规则引擎）或 "nn"（神经网络）',
    )
    stage: str = Field(
        default="pre_tool",
        description="当前决策阶段标识",
    )
    injection_text: str = Field(
        default="",
        description="注入到 prompt 的引导文本",
    )
