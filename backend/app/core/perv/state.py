"""
PERV (Planner-Executor-Replanner-Verifier) State Definitions

Defines the state schema for the LangGraph StateGraph used in the PERV loop.

PERV 循环流程:
    Plan -> Execute -> Verify -> [pass] -> Synthesize -> Final Answer
                       |
                       v
                     [fail] -> Replan -> Plan (retry)

PERV 模式支持两种计划执行策略:
    - 批量模式: 一次执行所有步骤后验证
    - 逐步模式: 逐步骤执行并验证, 支持 step_cursor 游标控制

节点间通过 PlannerState 传递状态，带 Annotated reducer 的字段
会在节点返回新值时自动追加而非覆盖。
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated


def _append_list(existing: list, new: list) -> list:
    """Reducer: 列表追加（LangGraph Annotated reducer）。

    LangGraph 节点返回带此 reducer 的字段时，返回值会被追加到
    现有列表而非替换，确保跨节点的执行记录和推理轨迹完整保留。

    Args:
        existing: 当前状态中的列表。
        new: 节点返回的新列表元素。

    Returns:
        合并后的列表。
    """
    return existing + new


class PlanStep(TypedDict):
    """单个执行步骤。

    由 Planner 节点生成，描述一步工具调用的全部信息。
    扩展字段支持 PERV 模式: depends_on 追踪步骤依赖,
    output_key 用于步骤间数据传递, on_fail 定义失败处理策略.
    """

    id: str  # "s1", "s2"
    name: str  # 简短步骤名称
    tool: str  # 工具名称
    purpose: str  # 该步骤要达成什么
    inputs: Dict[str, Any]  # 工具输入参数
    depends_on: List[str]  # 依赖的前置步骤 id 列表
    output_key: str  # 唯一输出键名, 用于步骤间数据传递
    on_fail: Dict[str, Any]  # 失败处理: {retry: int, fallback_tool: str|None, fallback_inputs: dict|None}
    # 兼容旧字段
    description: str  # 兼容: 同 purpose
    expected: str  # 兼容: 预期输出描述
    skill: Optional[str]  # 兼容: 参考的技能名称
    input: Dict[str, Any]  # 兼容: 同 inputs (旧字段名)
    skill_group: Optional[str]  # Skill group identifier for parallel scheduling


class Observation(TypedDict):
    """执行观察结果。

    由 Executor 节点在执行工具调用后生成，记录工具执行的
    输入、输出和状态，供 Verifier 判断步骤是否成功。
    """

    step_id: str
    tool: str
    input: Dict[str, Any]
    status: str  # "success" | "fail"
    result: Any
    evidence: List[str]


class VerifierReport(TypedDict):
    """验证报告。

    由 Verifier 节点生成，综合评估所有 Observations 是否满足
    原始任务要求。

    新格式使用 verdict/confidence/checks 体系,
    兼容旧格式的 passed/coverage/scores 字段.
    """

    # 新格式 (PERV 模式)
    verdict: str  # "pass" | "fail" | "needs_repair"
    confidence: float  # 0.0 - 1.0
    checks: List[Dict[str, str]]  # [{name, status, evidence, fix_suggestion}]
    risk_notes: List[str]

    # 兼容旧格式
    passed: bool
    reason: str
    missing: List[str]
    grounded: bool
    coverage: float  # 0.0 - 1.0
    scores: Dict[str, float]


class PlanUpdate(TypedDict):
    """计划更新指令。

    由 Replanner 节点生成, 支持两种模式:
    - repair_patch: 局部修补 (edit_step_inputs/replace_step_tool/insert_step_after)
    - full_replan: 完全重新规划
    兼容旧格式的 action/target_step/steps 字段.
    """

    # 新格式 (PERV patch 模式)
    mode: str  # "repair_patch" | "full_replan"
    reason: str
    patch: List[Dict[str, Any]]  # [{op, step_id, ...}]

    # 兼容旧格式
    action: str  # "append" | "replace" | "retry"
    target_step: Optional[str]
    steps: List[Dict[str, Any]]


class RouteDecision(TypedDict):
    """PERV 路由决策结果。

    由 PERV Router 生成，根据任务特征选择执行路径。
    source 字段标识决策来源: rule（规则匹配）或 llm（LLM 兜底）。
    """
    mode: str           # "direct_answer" | "plan_execute" | "plan_execute_verify"
    risk: str           # "low" | "medium" | "high"
    reason: str         # 路由原因描述
    max_steps: int      # 允许的最大步骤数
    allow_tools: bool   # 是否允许工具调用
    source: str         # "rule" | "llm"


class PlannerState(TypedDict):
    """PERV 闭环状态（LangGraph StateGraph 使用的状态）。

    所有字段说明:
        task:                原始用户任务描述
        session_context:     会话级上下文（用户偏好、环境信息等）
        system_prompt:       Agent 系统提示词
        messages:            原始消息列表（LangChain message dicts）
        plan:                当前执行计划（步骤列表）
        observations:        执行结果（带 reducer，节点返回新列表会自动追加）
        verifier_report:     最新验证报告
        retry_count:         当前已重试次数
        max_retries:         最大允许重试次数
        consecutive_failures: PERV 模式连续失败计数
        step_cursor:         PERV 逐步执行游标
        step_outputs:        PERV 步骤间数据传递字典
        route_decision:      PERV 路由决策结果（由 Router 生成）
        summarized_observations: 摘要后的观察列表（中风险压缩用）
        final_answer:        最终答案（仅在 Verify 通过后由 Synthesizer 填入）
        reasoning_trace:     SSE 追踪日志（带 reducer，自动追加）
    """

    # 输入
    task: str
    session_context: Dict[str, Any]
    system_prompt: str
    messages: List[Dict[str, str]]  # 原始消息列表

    # 计划
    plan: List[PlanStep]

    # 执行结果（带 reducer，节点返回新列表会自动追加）
    observations: Annotated[List[Observation], _append_list]

    # 验证
    verifier_report: Optional[VerifierReport]

    # 重试控制
    retry_count: int
    max_retries: int

    # PERV 模式扩展
    consecutive_failures: int  # 追踪连续失败次数 (用于控制 replan 行为)
    step_cursor: int  # 逐步模式执行游标
    step_outputs: Dict[str, Any]  # output_key → value (步骤间数据传递)
    execution_layers: Optional[List[Dict[str, Any]]]  # DAG 执行层级
    current_layer: int  # 当前执行层级索引

    # PERV 路由决策
    route_decision: Optional[RouteDecision]         # 路由决策结果
    summarized_observations: Optional[List[str]]     # 摘要后的观察（中风险用）

    # 最终输出
    final_answer: Optional[str]

    # SSE 追踪
    reasoning_trace: Annotated[List[Dict[str, Any]], _append_list]

    # SkillPolicy 编译报告
    skill_policy_report: Optional[Dict[str, Any]]

    # 学习集成（规划前准备的经验/策略/历史数据）
    enrichment: Dict[str, Any]
    # 执行后学习指标（reward、pattern_id 等）
    learning_metrics: Dict[str, Any]

    # 内部对象（不参与序列化，通过 orchestrator 注入闭包传递给节点）
    _pevr_log: Any  # PEVRLogger 实例，用于节点生命周期追踪
