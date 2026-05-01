"""
Tree of Thoughts State Management

Defines the state schema for LangGraph-based Tree of Thoughts reasoning.
"""

from typing import TypedDict, List, Optional, Dict, Any, NotRequired
from typing_extensions import Annotated
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.messages import BaseMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool


def add_thoughts(left: List["Thought"], right: List["Thought"]) -> List["Thought"]:
    """
    Reducer function for adding thoughts to state.
    Merges new thoughts, deduplicates by id, and prunes stale entries.
    """
    merged = left + right
    if len(merged) <= 50:
        return merged

    # Deduplicate by id (keep latest), drop pruned thoughts
    seen: set = set()
    result: list = []
    for t in reversed(merged):
        if t.id not in seen:
            seen.add(t.id)
            if t.status != "pruned":
                result.append(t)
    result.reverse()
    return result


class Thought(BaseModel):
    """A single thought in the reasoning tree."""

    id: str = Field(description="Unique thought identifier")
    parent_id: Optional[str] = Field(
        default=None, description="Parent thought ID for tree structure"
    )
    content: str = Field(description="Thought description/reasoning")
    tool_calls: List[Dict[str, Any]] = Field(
        default_factory=list, description="Tools to execute for this thought"
    )
    tool_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Results from executed tools"
    )
    evaluation_score: Optional[float] = Field(
        default=None, description="Thought quality score (0-10)"
    )
    criteria_scores: Optional[Dict[str, float]] = Field(
        default=None, description="Individual criteria scores"
    )
    status: str = Field(
        default="pending",
        description="Thought status: pending/evaluated/pruned/selected/executing/done"
    )

    # --- 局部循环字段 (Phase 4 执行节点使用) ---
    scratchpad: str = Field(
        default="", description="局部推理过程中的思考记录"
    )
    tool_trace: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="局部循环中的工具调用历史（包含每步的 observation）"
    )
    artifacts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="工具产生的中间产物（检索内容、代码运行输出等）"
    )
    local_done: bool = Field(
        default=False,
        description="该 thought 下的局部执行是否已完成"
    )
    local_step_count: int = Field(
        default=0,
        description="局部循环已执行的步骤数"
    )
    local_error_count: int = Field(
        default=0,
        description="局部循环中的错误次数"
    )
    # --- Post-execution re-evaluation fields ---
    post_execution_score: Optional[float] = Field(
        default=None,
        description="Post-execution quality score based on actual results"
    )
    post_execution_criteria: Optional[Dict[str, float]] = Field(
        default=None,
        description="Post-execution criteria: result_quality, query_satisfaction, output_completeness"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="扩展元数据（缓存 depth 等，不参与 JSON 序列化）"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "thought_1",
                "parent_id": None,
                "content": "Search for information about quantum computing",
                "tool_calls": [],
                "tool_results": [],
                "evaluation_score": 8.5,
                "criteria_scores": {"relevance": 9.0, "feasibility": 8.0, "novelty": 8.5},
                "status": "evaluated"
            }
        }
    )


class ToTState(TypedDict):
    """
    State for Tree of Thoughts reasoning in LangGraph.

    This state is passed between nodes in the reasoning graph and
    maintains all information about the current reasoning process.
    """

    # Input
    user_query: str
    session_context: Dict[str, Any]
    messages: List[BaseMessage]  # LangChain message history

    # Reasoning Tree
    thoughts: Annotated[List[Thought], add_thoughts]
    current_depth: int
    max_depth: int
    branching_factor: int  # Branching factor for thought generation

    # Best Path Tracking
    best_path: List[str]  # List of thought IDs forming best path
    best_score: float

    # Execution Context
    tools: List[BaseTool]
    llm: BaseChatModel  # Base LLM for thought generation
    llm_with_tools: BaseChatModel  # LLM with tools bound for tool calling
    system_prompt: str

    # Research-specific (optional)
    research_sources: Optional[List[Dict[str, Any]]]
    research_stage: Optional[str]

    # Task classification (set by router)
    task_mode: NotRequired[str]              # "standard" | "research"
    task_type: NotRequired[str]              # profile name or "research"
    domain_profile: NotRequired[Optional[Dict]]  # DomainProfile.model_dump()
    tot_logger: NotRequired[Optional[Any]]   # ToTExecutionLogger
    session_id: NotRequired[Optional[str]]

    # Research fields
    evidence_store: NotRequired[List[Dict]]
    coverage_map: NotRequired[Optional[Dict]]
    contradictions: NotRequired[List[Dict]]
    draft: NotRequired[Optional[str]]
    raw_sources: NotRequired[List[Dict]]
    research_round: NotRequired[int]
    citation_chase_rounds: NotRequired[int]
    citation_chase_max: NotRequired[int]
    token_used: NotRequired[int]
    token_budget: NotRequired[int]
    prev_coverage_score: NotRequired[float]
    writer_min_delta: NotRequired[float]

    # Results
    final_answer: Optional[str]

    # Metadata
    reasoning_trace: List[Dict[str, Any]]  # For streaming to frontend
    fallback_to_simple: bool  # Flag to fall back to simple agent
    tca_injection_text: str  # TCA decomposition guidance (empty if disabled)
    meta_policy_injection_text: str  # Meta policy tool/skill guidance (empty if disabled)

    # --- Global Beam Search 字段 (Phase 1 新增) ---
    active_beams: NotRequired[List[List[str]]]      # 活跃束列表（每条束 = thought ID 路径）
    beam_scores: NotRequired[List[float]]            # 每个束的分数（路径加权平均）
    beam_width: NotRequired[int]                     # Global Beam 的 B（恒定）
    backtrack_count: NotRequired[int]                # 回溯总次数（regenerate + beam_switch）
    regenerate_count: NotRequired[int]               # 低分重生成次数（子树回溯）
    beam_switch_count: NotRequired[int]              # 束切换次数（最高分束变化）
    backtrack_score_threshold: NotRequired[float]     # 低分回溯阈值（默认 4.0）
    deferred_image_paths: NotRequired[List[str]]     # 延迟嵌入的图片路径
    needs_regeneration: NotRequired[List[int]]       # 需要回溯重新生成的 beam index 列表
    regeneration_context: NotRequired[List[Dict]]    # 回溯上下文（旧分支摘要 + 反思提示）

    # --- 局部循环配置 (Phase 1 新增) ---
    max_tool_steps_per_node: NotRequired[int]        # 每个节点最大工具调用步数（默认 5）
    max_time_per_node: NotRequired[float]            # 每个节点最大执行时间（秒，默认 30s）

    # --- SkillPolicy 门控结果 (Phase: SkillPolicyNode) ---
    skill_policy_decisions: NotRequired[Dict[str, Dict]]
    # key = skill_name, value = {"allowed": bool, "reason": str, "compiled_tool": {...}}

    # --- Enrichment data (pattern retrieval + semantic history) ---
    retrieved_patterns: NotRequired[List[Dict]]      # Retrieved learned patterns
    semantic_history: NotRequired[str]               # Unified KG + vector context


def get_depth_of_thought(thought: Thought, all_thoughts: List[Thought]) -> int:
    """
    Calculate the depth of a thought in the reasoning tree.

    Args:
        thought: The thought to calculate depth for
        all_thoughts: List of all thoughts for reference

    Returns:
        Depth level (0 for root thoughts)
    """
    depth = 0
    current_id = thought.parent_id

    while current_id:
        # Find parent thought
        parent = next((t for t in all_thoughts if t.id == current_id), None)
        if parent:
            depth += 1
            current_id = parent.parent_id
        else:
            break

    return depth


def get_thoughts_at_depth(
    all_thoughts: List[Thought], target_depth: int
) -> List[Thought]:
    """
    Get all thoughts at a specific depth level.

    Args:
        all_thoughts: List of all thoughts
        target_depth: Target depth level

    Returns:
        List of thoughts at the target depth
    """
    return [
        t for t in all_thoughts
        if get_depth_of_thought(t, all_thoughts) == target_depth
    ]


def compute_beam_schedule(branching_factor: int, max_depth: int) -> Dict[int, int]:
    """Global Beam: beam_width B 恒定 = branching_factor。

    每层逻辑:
      - frontier 有 B 个节点
      - 每个扩展 k 个子节点
      - 全局从 B*k 候选中选 top-B
      - B 保持不变

    Args:
        branching_factor: 即 B，也是 k
        max_depth: 最大搜索深度

    Returns:
        Dict[depth, beam_width] — 每层的 beam_width 均为 branching_factor
    """
    return {d: branching_factor for d in range(max_depth + 1)}


def compute_max_nodes(beam_width: int, branching_factor: int, max_depth: int) -> int:
    """计算最大节点数 = B + D * B * k

    - Depth 0: 生成 B 个 root thoughts
    - Depth 1~D: 每层生成 B*k 候选（frontier B * 各扩展 k 个）
    - 实际运行中剪枝会减少数量，这是理论上限
    """
    return beam_width + max_depth * beam_width * branching_factor


# ---------------------------------------------------------------------------
# 性能优化：thought_map + depth 缓存
# ---------------------------------------------------------------------------

def get_thought_map(thoughts: List["Thought"]) -> Dict[str, "Thought"]:
    """构建 thought_id → Thought 索引字典。

    在节点函数入口调用一次，后续通过 dict.get() O(1) 查找。
    不持久化到 state，每次调用时新建（thoughts 数量 ≤ max_nodes）。
    """
    return {t.id: t for t in thoughts}


def get_depth_cached(thought: "Thought", thought_map: Dict[str, "Thought"]) -> int:
    """带缓存的 depth 计算。

    优先使用 thought.metadata 中的缓存值，否则沿父链计算。
    性能: O(D) dict.get() 查找（而非 O(D*N) 线性扫描）。
    """
    meta = thought.metadata
    if "_cached_depth" in meta:
        return meta["_cached_depth"]

    depth = 0
    current = thought
    while current.parent_id:
        parent = thought_map.get(current.parent_id)
        if not parent:
            break
        # 检查父节点是否有缓存
        parent_meta = parent.metadata
        if "_cached_depth" in parent_meta:
            depth = parent_meta["_cached_depth"] + 1
            break
        depth += 1
        current = parent

    # 缓存到 metadata 中（下次 O(1)）
    meta["_cached_depth"] = depth
    return depth
