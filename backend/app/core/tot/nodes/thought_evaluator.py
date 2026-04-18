"""
Thought Evaluator Node

Evaluates the quality of thoughts using multi-criteria scoring.
Phase 2: Global Beam Selection with pruning pipeline, batch evaluation,
         subtree diversity, and backtracking detection.
"""

import logging
import json
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.tot.state import ToTState, Thought, get_depth_of_thought, get_thought_map, get_depth_cached
from app.core.tot.utils import content_similarity as _content_similarity, tool_calls_signature as _tool_calls_signature

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 2: 辅助函数 — 内容相似度 & 工具签名
# [已迁移到 app.core.tot.utils，此处通过 import 引入]
# ---------------------------------------------------------------------------

# def _content_similarity(content1: str, content2: str) -> float:
#     """[已迁移到 app.core.tot.utils.content_similarity]"""
#     words1 = set(content1.split())
#     words2 = set(content2.split())
#     if not words1 or not words2:
#         return 0.0
#     intersection = words1.intersection(words2)
#     union = words1.union(words2)
#     return len(intersection) / len(union) if union else 0.0


# def _tool_calls_signature(tool_calls: Optional[List[Dict[str, Any]]]) -> tuple:
#     """[已迁移到 app.core.tot.utils.tool_calls_signature]"""
#     if not tool_calls:
#         return ()
#     parts = []
#     for tc in sorted(tool_calls, key=lambda x: x.get("name", "")):
#         name = tc.get("name", "")
#         args = tc.get("args", {})
#         path_val = args.get("path", "")
#         query_val = args.get("query", "")
#         parts.append((name, path_val, query_val))
#     return tuple(parts)


# ---------------------------------------------------------------------------
# Phase 2: 剪枝管道 — 冗余剪枝 + 支配剪枝
# ---------------------------------------------------------------------------

def _redundancy_prune(candidates: List[Dict], threshold: float = 0.75) -> List[Dict]:
    """剔除与更高分候选高度相似的节点。

    条件: 工具调用签名相同 AND 内容相似度 > threshold。
    """
    sorted_candidates = sorted(candidates, key=lambda c: c["path_score"], reverse=True)
    surviving = []

    for cand in sorted_candidates:
        thought = cand["thought"]
        is_duplicate = False
        for kept in surviving:
            kept_thought = kept["thought"]
            # 不同工具调用签名 → 不算冗余
            if _tool_calls_signature(thought.tool_calls) != _tool_calls_signature(kept_thought.tool_calls):
                continue
            # 相同签名 + 内容高度相似 → 冗余
            if _content_similarity(thought.content.lower(), kept_thought.content.lower()) > threshold:
                is_duplicate = True
                thought.status = "pruned"
                break
        if not is_duplicate:
            surviving.append(cand)

    pruned_count = len(sorted_candidates) - len(surviving)
    if pruned_count:
        logger.info(f"[Prune-Redundancy] Pruned {pruned_count} redundant candidates (threshold={threshold})")
    return surviving


def _dominance_prune(candidates: List[Dict]) -> List[Dict]:
    """同父节点下，被完全支配的候选直接淘汰。"""
    by_parent = defaultdict(list)
    for c in candidates:
        by_parent[c["parent_id"]].append(c)

    pruned_ids = set()
    for parent_id, group in by_parent.items():
        if len(group) < 2:
            continue
        for i, c1 in enumerate(group):
            if c1["thought"].id in pruned_ids:
                continue
            s1 = c1["thought"].criteria_scores or {}
            for j, c2 in enumerate(group):
                if i == j or c2["thought"].id in pruned_ids:
                    continue
                s2 = c2["thought"].criteria_scores or {}
                dims = set(s1.keys()) | set(s2.keys())
                if not dims:
                    continue
                all_better = all(
                    s1.get(d, 0.0) > s2.get(d, 0.0) for d in dims
                )
                if all_better:
                    pruned_ids.add(c2["thought"].id)
                    c2["thought"].status = "pruned"

    surviving = [c for c in candidates if c["thought"].id not in pruned_ids]
    if pruned_ids:
        logger.info(f"[Prune-Dominance] Pruned {len(pruned_ids)} dominated candidates")
    return surviving


# ---------------------------------------------------------------------------
# Phase 2: 束路径分数计算
# ---------------------------------------------------------------------------

def _compute_beam_path_score(
    beam: List[str],
    beam_base_score: float,
    new_thought: Thought,
    all_thoughts: List[Thought],
    thought_map: Optional[Dict[str, Thought]] = None,
) -> float:
    """计算束的路径加权分数。越近的节点权重越高。

    weight(d) = 0.5 + 0.1 * d  (depth 0: 0.5, depth 5: 1.0)
    """
    thought_score = new_thought.evaluation_score or 0.0
    path_length = len(beam)

    if path_length == 0:
        return thought_score

    total_weight = 0.0
    weighted_sum = 0.0

    for i, tid in enumerate(beam):
        if thought_map:
            t = thought_map.get(tid)
        else:
            t = next((x for x in all_thoughts if x.id == tid), None)
        if t and t.evaluation_score is not None:
            w = 0.5 + 0.1 * i
            weighted_sum += t.evaluation_score * w
            total_weight += w

    w_new = 0.5 + 0.1 * path_length
    weighted_sum += thought_score * w_new
    total_weight += w_new

    return weighted_sum / total_weight if total_weight > 0 else 0.0


# ---------------------------------------------------------------------------
# Phase 2: 子树多样性选择算法
# ---------------------------------------------------------------------------

def _select_with_subtree_diversity(
    candidates: List[Dict],
    beam_width: int,
    is_last_layer: bool,
) -> List[Dict]:
    """从候选中选择 top-B，确保子树多样性（最后一层除外）。"""
    if is_last_layer:
        # 最后一层：纯粹按分数
        return candidates[:beam_width]

    # 防御性排序：确保高分候选优先处理
    sorted_candidates = sorted(candidates, key=lambda c: c["path_score"], reverse=True)

    unique_parents = len(set(c["parent_id"] for c in sorted_candidates))
    max_per_parent = max(1, beam_width // max(1, unique_parents))
    parent_count: Dict[str, int] = {}
    selected = []

    for cand in sorted_candidates:
        pid = cand["parent_id"]
        current_count = parent_count.get(pid, 0)
        if current_count < max_per_parent:
            selected.append(cand)
            parent_count[pid] = current_count + 1
            if len(selected) >= beam_width:
                break

    # 如果因多样性约束导致不足，从剩余候选中补充
    if len(selected) < beam_width:
        selected_ids = {id(s["thought"]) for s in selected}
        remaining = [c for c in sorted_candidates if id(c["thought"]) not in selected_ids]
        for cand in remaining:
            selected.append(cand)
            if len(selected) >= beam_width:
                break

    return selected[:beam_width]


# ---------------------------------------------------------------------------
# Phase 2: Global Beam Selection（核心）
# ---------------------------------------------------------------------------

async def _update_beam_selection(state: ToTState) -> None:
    """Global Beam 选择：从所有候选中选 top-B，带子树多样性约束。"""
    all_thoughts = state["thoughts"]
    beam_width = state.get("beam_width", state.get("branching_factor", 3))
    current_depth = state["current_depth"]
    max_depth = state["max_depth"]
    active_beams = state.get("active_beams", [])
    beam_scores = state.get("beam_scores", [])

    # 按需构建 thought_map 索引
    thought_map = {t.id: t for t in all_thoughts}

    if current_depth == 0:
        # Depth 0: 所有 root thought 按分数排序，取 top-B
        root_thoughts = [t for t in all_thoughts if t.parent_id is None and t.status == "evaluated"]
        root_thoughts.sort(key=lambda t: t.evaluation_score or 0.0, reverse=True)
        selected = root_thoughts[:beam_width]

        state["active_beams"] = [[t.id] for t in selected]
        state["beam_scores"] = [t.evaluation_score or 0.0 for t in selected]
    else:
        # Depth > 0: 收集所有活跃束尖端的新子节点 → B*k 候选
        candidates = []
        for beam_idx, beam in enumerate(active_beams):
            parent_id = beam[-1]
            children = [
                t for t in all_thoughts
                if t.parent_id == parent_id and t.status == "evaluated"
            ]
            beam_base_score = beam_scores[beam_idx] if beam_idx < len(beam_scores) else 0.0
            for child in children:
                path_score = _compute_beam_path_score(
                    beam, beam_base_score, child, all_thoughts, thought_map
                )
                candidates.append({
                    "thought": child,
                    "parent_beam_idx": beam_idx,
                    "parent_id": parent_id,
                    "path_score": path_score,
                })

        if not candidates:
            return

        # --- 二级剪枝管道（评估阶段） ---
        total_before = len(candidates)
        candidates = _redundancy_prune(candidates, threshold=0.75)
        candidates = _dominance_prune(candidates)
        logger.info(
            f"[Prune Pipeline] depth={current_depth}: "
            f"{total_before} -> {len(candidates)} candidates"
        )

        if not candidates:
            return

        # --- 低分阈值回溯检测 ---
        threshold = state.get("backtrack_score_threshold", 4.0)
        beams_to_regenerate: List[int] = []

        for beam_idx, beam in enumerate(active_beams):
            parent_score = beam_scores[beam_idx] if beam_idx < len(beam_scores) else 0.0
            actual_threshold = max(threshold, parent_score - 3.0)
            beam_children = [c for c in candidates if c["parent_beam_idx"] == beam_idx]
            if beam_children:
                best_child_score = max(c["path_score"] for c in beam_children)
                if best_child_score < actual_threshold:
                    beams_to_regenerate.append(beam_idx)
                    for c in beam_children:
                        c["thought"].status = "pruned"
                    logger.info(
                        f"[Backtrack-Detect] Beam {beam_idx} children all below "
                        f"threshold: best={best_child_score:.2f} < {actual_threshold:.2f}"
                    )

        # 将回溯信息写入 state
        if beams_to_regenerate:
            state["needs_regeneration"] = beams_to_regenerate
            state["regenerate_count"] = state.get("regenerate_count", 0) + len(beams_to_regenerate)
            state["backtrack_count"] = state.get("backtrack_count", 0) + len(beams_to_regenerate)
            candidates = [c for c in candidates if c["parent_beam_idx"] not in beams_to_regenerate]
            for beam_idx in beams_to_regenerate:
                state["reasoning_trace"].append({
                    "type": "backtrack",
                    "reason": "low_score_regenerate",
                    "beam_idx": beam_idx,
                    "depth": current_depth,
                })

        # 全局排序
        candidates.sort(key=lambda c: c["path_score"], reverse=True)

        # 子树多样性选择
        is_last_layer = (current_depth >= max_depth)
        selected = _select_with_subtree_diversity(
            candidates, beam_width, is_last_layer
        )

        # 更新 active_beams 和 beam_scores
        new_beams = []
        new_scores = []
        old_best_beam = active_beams[0] if active_beams else []
        new_best_beam = None

        for sel in selected:
            beam_idx = sel["parent_beam_idx"]
            old_beam = list(active_beams[beam_idx])
            new_beam = old_beam + [sel["thought"].id]
            new_beams.append(new_beam)
            new_scores.append(sel["path_score"])
            if new_best_beam is None:
                new_best_beam = new_beam

        # 回溯检测: 最高分束是否变化（beam_switch 事件）
        if old_best_beam and new_best_beam:
            old_root = old_best_beam[0] if old_best_beam else None
            new_root = new_best_beam[0] if new_best_beam else None
            if old_root != new_root:
                state["beam_switch_count"] = state.get("beam_switch_count", 0) + 1
                state["backtrack_count"] = state.get("backtrack_count", 0) + 1
                state["reasoning_trace"].append({
                    "type": "backtrack",
                    "reason": "beam_switch",
                    "from_root": old_root,
                    "to_root": new_root,
                    "depth": current_depth,
                })

        state["active_beams"] = new_beams
        state["beam_scores"] = new_scores

    # 同步更新 best_path（向后兼容）
    if state.get("active_beams"):
        state["best_path"] = state["active_beams"][0]
        state["best_score"] = state["beam_scores"][0] if state.get("beam_scores") else 0.0


# ---------------------------------------------------------------------------
# Phase 2: 批量评估
# ---------------------------------------------------------------------------

def _build_batch_evaluation_prompt(thoughts: List[Thought], state: ToTState) -> str:
    """构建批量评估 prompt，每个 thought 带 ID 以确保结果匹配。"""
    user_query = state["user_query"]
    all_thoughts = state["thoughts"]
    thought_map = get_thought_map(all_thoughts)

    items = []
    for t in thoughts:
        depth = get_depth_cached(t, thought_map)
        items.append(f"""[THOUGHT_{t.id}]
Depth: {depth}
Parent: {t.parent_id or "root"}
Content: {t.content}
Tool calls: {len(t.tool_calls)} calls
---""")

    thoughts_text = "\n".join(items)

    return f"""Evaluate {len(thoughts)} thoughts on 3 criteria (score 0-10 each).

User Query: {user_query}

{thoughts_text}

Return a JSON array with EXACTLY {len(thoughts)} elements. Each element MUST include the thought_id:
```json
[
  {{"thought_id": "<id>", "relevance": X, "feasibility": X, "novelty": X}},
  ...
]
```

IMPORTANT:
- Each thought_id MUST match the [THOUGHT_<id>] header above
- Be objective and critical
- Score each thought independently (branch isolation)"""


def _parse_batch_scores(content: str, thoughts: List[Thought]) -> Dict[str, Dict]:
    """解析批量评估结果，用 thought_id 匹配。失败时回退到逐个评估。"""
    try:
        text = content.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        results = json.loads(text)
        if not isinstance(results, list):
            results = [results]

        scores_map = {}
        for item in results:
            tid = item.get("thought_id", "")
            scores_map[tid] = {
                "criteria": {
                    "relevance": float(item.get("relevance", 5.0)),
                    "feasibility": float(item.get("feasibility", 5.0)),
                    "novelty": float(item.get("novelty", 5.0)),
                },
                "weighted": (
                    float(item.get("relevance", 5.0)) * 0.4 +
                    float(item.get("feasibility", 5.0)) * 0.4 +
                    float(item.get("novelty", 5.0)) * 0.2
                ),
            }
        return scores_map

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Batch score parsing failed: {e}, returning empty map")
        return {}


async def _batch_evaluate_thoughts(thoughts: List[Thought], state: ToTState) -> List[Dict]:
    """一次 LLM 调用评估所有同深度 thoughts。返回 eval_scores 列表。"""
    if not thoughts:
        return []

    llm = state["llm"]
    eval_scores = []

    prompt = _build_batch_evaluation_prompt(thoughts, state)

    from app.core.tot.prompt_composer import compose_system_prompt
    eval_system = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="evaluator",
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="analysis",  # 评估器用精简 prompt
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=eval_system),
            HumanMessage(content=prompt)
        ])

        scores_map = _parse_batch_scores(response.content, thoughts)

        for thought in thoughts:
            score_data = scores_map.get(thought.id)
            if score_data:
                thought.evaluation_score = score_data["weighted"]
                thought.criteria_scores = score_data["criteria"]
            else:
                # 回退：该 thought 未被正确评分，赋予默认分数
                thought.evaluation_score = 5.0
                thought.criteria_scores = {"relevance": 5.0, "feasibility": 5.0, "novelty": 5.0}
            thought.status = "evaluated"

            eval_scores.append({
                "thought_id": thought.id,
                "score": thought.evaluation_score,
                "criteria": thought.criteria_scores,
                "fatal_flaw": None,
            })

            logger.info(
                f"[BatchEval] Thought {thought.id}: "
                f"relevance={thought.criteria_scores.get('relevance', 0):.1f}, "
                f"feasibility={thought.criteria_scores.get('feasibility', 0):.1f}, "
                f"novelty={thought.criteria_scores.get('novelty', 0):.1f}, "
                f"final={thought.evaluation_score:.2f}"
            )

        return eval_scores

    except Exception as e:
        logger.error(f"Batch evaluation failed: {e}, falling back to individual evaluation")
        return await _individual_evaluate_thoughts(thoughts, state)


# ---------------------------------------------------------------------------
# Phase 2: 逐个评估（fallback）
# ---------------------------------------------------------------------------

async def _individual_evaluate_thoughts(thoughts: List[Thought], state: ToTState) -> List[Dict]:
    """逐个评估 thoughts（原有逻辑，作为 batch 评估的 fallback）。"""
    llm = state["llm"]
    user_query = state["user_query"]
    all_thoughts = state["thoughts"]
    eval_scores = []

    from app.core.tot.prompt_composer import compose_system_prompt
    eval_system = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="evaluator",
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="full",
    )

    response = None
    for thought in thoughts:
        try:
            prompt = _build_evaluation_prompt(thought, user_query, all_thoughts)

            response = await llm.ainvoke([
                SystemMessage(content=eval_system),
                HumanMessage(content=prompt)
            ])

            scores = _parse_evaluation_scores(response.content)

            weighted_score = (
                scores.get("relevance", 5.0) * 0.4 +
                scores.get("feasibility", 5.0) * 0.4 +
                scores.get("novelty", 5.0) * 0.2
            )

            thought.evaluation_score = weighted_score
            thought.criteria_scores = scores
            thought.status = "evaluated"

            eval_scores.append({
                "thought_id": thought.id,
                "score": weighted_score,
                "criteria": scores,
                "fatal_flaw": None,
            })

            logger.info(
                f"Thought {thought.id}: relevance={scores.get('relevance', 0):.1f}, "
                f"feasibility={scores.get('feasibility', 0):.1f}, "
                f"novelty={scores.get('novelty', 0):.1f}, "
                f"final={weighted_score:.2f}"
            )

        except Exception as e:
            logger.error(f"Error evaluating thought {thought.id}: {e}")
            thought.evaluation_score = 5.0
            thought.status = "evaluated"

    return eval_scores


# ---------------------------------------------------------------------------
# Main evaluator node
# ---------------------------------------------------------------------------

async def thought_evaluator_node(state: ToTState) -> ToTState:
    """
    Evaluate thoughts using multi-criteria scoring.

    Phase 2 增强功能:
    - beam_width 在 state 中时使用 Global Beam Selection
    - 批量评估优化（一次 LLM 调用评估所有 thoughts）
    - 二级剪枝管道（冗余 + 支配）
    - 低分阈值回溯检测
    - 子树多样性约束

    当 beam_width 未设置时，退化为原有贪心模式（向后兼容）。
    """
    user_query = state["user_query"]
    all_thoughts = state["thoughts"]
    beam_width = state.get("beam_width")

    # Find thoughts that need evaluation (status == "pending")
    pending_thoughts = [t for t in all_thoughts if t.status == "pending"]

    if not pending_thoughts:
        logger.info("No pending thoughts to evaluate")
        return state

    logger.info(f"Evaluating {len(pending_thoughts)} thoughts (beam_mode={'on' if beam_width else 'off'})")

    eval_start = time.time()

    # ---- 评估阶段 ----
    if beam_width:
        # Phase 2: 批量评估
        eval_scores = await _batch_evaluate_thoughts(pending_thoughts, state)
    else:
        # 原有逐个评估
        eval_scores = await _individual_evaluate_thoughts(pending_thoughts, state)

    # ---- 路径选择阶段 ----
    if beam_width:
        # Phase 2: Global Beam Selection
        await _update_beam_selection(state)
    else:
        # 原有贪心 best_path
        _update_best_path(state)

    # ---- 日志 & trace ----
    if "tot_logger" in state:
        elapsed = time.time() - eval_start
        state["tot_logger"].log_evaluation(
            depth=state.get("current_depth", 0),
            scores=eval_scores,
            best_path_changed=True,
            beam_pruned=sum(1 for t in pending_thoughts if t.status == "pruned"),
            token_usage=None,  # batch eval doesn't expose response directly
        )

    state["reasoning_trace"].append({
        "type": "thoughts_evaluated",
        "best_path": state.get("best_path", []),
        "best_score": state.get("best_score", 0.0),
        "active_beams": state.get("active_beams", []),
        "beam_scores": state.get("beam_scores", []),
    })

    return state


# ---------------------------------------------------------------------------
# 旧代码保留（注释掉）— 向后兼容，beam_width 未设置时使用
# ---------------------------------------------------------------------------

def _build_evaluation_prompt(
    thought: Thought,
    user_query: str,
    all_thoughts: List[Thought]
) -> str:
    """Build prompt for evaluating a single thought."""
    return f"""Evaluate this thought on 3 criteria (score 0-10 each):

**User Query:** {user_query}

**Thought to Evaluate:**
{thought.content}

**Evaluation Criteria:**

1. **Relevance (0-10)**: How well does this thought directly address the user's query?
   - 10: Directly addresses the core question
   - 5: Somewhat related but tangential
   - 0: Irrelevant to the query

2. **Feasibility (0-10)**: Can this be executed with available tools?
   Available tools: terminal, python_repl, search_kb, fetch_url, read_file, write_file
   - 10: Straightforward to execute with available tools
   - 5: Possible but may require creative tool use
   - 0: Not feasible with current toolset

3. **Novelty (0-10)**: Is this a new angle or redundant?
   - 10: Completely new, unique approach
   - 5: Some new elements but similar to previous thoughts
   - 0: Redundant with existing thoughts

Return your evaluation as JSON only:
{{"relevance": X, "feasibility": X, "novelty": X}}

Be objective and critical in your scoring."""


def _parse_evaluation_scores(content: str) -> Dict[str, float]:
    """Parse LLM response to extract evaluation scores."""
    try:
        content = content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        scores = json.loads(content)

        return {
            "relevance": float(scores.get("relevance", 5.0)),
            "feasibility": float(scores.get("feasibility", 5.0)),
            "novelty": float(scores.get("novelty", 5.0))
        }

    except json.JSONDecodeError:
        import re
        numbers = re.findall(r'\d+\.?\d*', content)
        if len(numbers) >= 3:
            return {
                "relevance": float(numbers[0]),
                "feasibility": float(numbers[1]),
                "novelty": float(numbers[2])
            }

    return {"relevance": 5.0, "feasibility": 5.0, "novelty": 5.0}


# OLD: 贪心 best_path 选择（beam_width 未设置时仍使用）
def _update_best_path(state: ToTState):
    """
    Update best_path based on highest-scoring thoughts at each depth level.

    [旧代码保留] 贪心模式: beam_width 未设置时使用此函数。
    当 beam_width 设置后，使用 _update_beam_selection() 代替。
    """
    all_thoughts = state["thoughts"]

    if not all_thoughts:
        state["best_path"] = []
        state["best_score"] = 0.0
        return

    # 使用 thought_map 优化查找
    thought_map = get_thought_map(all_thoughts)

    # Group thoughts by depth
    depth_groups: Dict[int, List[Thought]] = {}
    for thought in all_thoughts:
        depth = get_depth_cached(thought, thought_map)
        if depth not in depth_groups:
            depth_groups[depth] = []
        depth_groups[depth].append(thought)

    # Select best thought at each depth
    best_path = []
    previous_best = None

    for depth in sorted(depth_groups.keys()):
        thoughts_at_depth = depth_groups[depth]

        if depth == 0:
            # Root: prioritize thoughts with tool calls
            thoughts_with_tools = [t for t in thoughts_at_depth if t.tool_calls]
            thoughts_without_tools = [t for t in thoughts_at_depth if not t.tool_calls]

            if thoughts_with_tools:
                best = max(thoughts_with_tools, key=lambda t: t.evaluation_score or 0.0)
                logger.info(f"Root depth: Selected thought WITH tools ({best.id}), score={best.evaluation_score:.2f}")
            elif thoughts_without_tools:
                best = max(thoughts_without_tools, key=lambda t: t.evaluation_score or 0.0)
                logger.warning(f"Root depth: No thoughts with tools! Selected thought WITHOUT tools ({best.id})")
            else:
                break

            best_path.append(best.id)
            previous_best = best
        else:
            children = [
                t for t in thoughts_at_depth
                if t.parent_id == previous_best.id
            ]

            if not children:
                break

            children_with_tools = [t for t in children if t.tool_calls]
            children_without_tools = [t for t in children if not t.tool_calls]

            if children_with_tools:
                best = max(children_with_tools, key=lambda t: t.evaluation_score or 0.0)
                logger.info(f"Depth {depth}: Selected child WITH tools ({best.id}), score={best.evaluation_score:.2f}")
            else:
                best = max(children_without_tools, key=lambda t: t.evaluation_score or 0.0)
                logger.warning(f"Depth {depth}: No children with tools! Selected child WITHOUT tools ({best.id})")

            best_path.append(best.id)
            previous_best = best

    state["best_path"] = best_path

    if best_path:
        path_scores = []
        for thought_id in best_path:
            t = thought_map.get(thought_id)
            if t and t.evaluation_score is not None:
                path_scores.append(t.evaluation_score)
        state["best_score"] = sum(path_scores) / len(path_scores) if path_scores else 0.0
    else:
        state["best_score"] = 0.0

    logger.info(
        f"Updated best path: {best_path} with average score {state['best_score']:.2f}"
    )
