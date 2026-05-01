"""
Synthesis Node

Generates the final answer based on task_mode / task_type:
- task_mode == "research": evidence-based report with verifier + repair.
- task_type == "research_writing": full pipeline
  (deep_source_extractor -> cluster_reduce_synthesis)
  -> research_report_writer + visual_base (parallel)
  -> doc-creator (assemble final document).
- other task_types: simple LLM synthesis (migrated from old _generate_final_answer).
"""

import asyncio
import base64
import hashlib
import importlib.util
import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.tot.state import ToTState, Thought, get_thought_map
from app.core.tot.prompt_composer import compose_system_prompt
from app.core.tot.research.prompts import (
    get_synthesis_prompt,
    get_verifier_prompt,
    get_repair_prompt,
    parse_json_output,
)
from app.core.tot.research.evidence_utils import format_evidence_for_prompt

logger = logging.getLogger(__name__)

_skills_dir = Path("data/skills")
_outputs_dir = Path("outputs")


def _save_report_to_disk(title: str, content: str) -> Optional[str]:
    """Save report markdown to outputs/ directory. Returns the file path or None."""
    try:
        _outputs_dir.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '_')
        if not safe_title:
            safe_title = "report"
        filename = f"{safe_title}.md"
        filepath = _outputs_dir / filename
        filepath.write_text(content, encoding="utf-8")
        logger.info("[Synthesis] Report saved to %s", filepath)
        return str(filepath)
    except Exception as e:
        logger.warning("[Synthesis] Failed to save report to disk: %s", e)
        return None


async def _call_skill_handler(skill_name: str, inputs: dict, context: dict):
    """Load a skill's handler.py via importlib and call its run() function."""
    handler_path = (_skills_dir / skill_name / "scripts" / "handler.py").resolve()
    if not handler_path.exists():
        raise FileNotFoundError(f"handler.py not found for skill '{skill_name}' at {handler_path}")
    spec = importlib.util.spec_from_file_location(skill_name, handler_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return await mod.run(inputs=inputs, context=context)

# MediaRegistry integration (optional — graceful fallback if unavailable)
try:
    from app.core.media import resolve_media
except ImportError:
    resolve_media = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Image embedding helper
# ---------------------------------------------------------------------------

def _resolve_image_refs(text: str, state: ToTState) -> str:
    """Post-process final answer: replace file paths with API URLs.

    [IMAGE_UNIFY] Uses MediaRegistry to convert local file paths to
    ``/api/media/{media_id}`` URLs (NOT base64 data-URIs) so that
    ReactMarkdown renders inline images via the media API endpoint.
    """
    session_id = state.get("session_id", "")

    # Only harvest images from winning path thoughts
    active_beams = state.get("active_beams", [])
    if active_beams and active_beams[0]:
        winning_path_ids = set(active_beams[0])
    else:
        winning_path_ids = set(state.get("best_path", []))

    all_thoughts: List[Thought] = state.get("thoughts", [])
    thought_map = get_thought_map(all_thoughts)
    winning_thoughts = [thought_map[tid] for tid in winning_path_ids if tid in thought_map]

    logger.info(
        "[RESOLVE] Winning path: %s (%d thoughts), deferred_paths=%s",
        winning_path_ids, len(winning_thoughts),
        state.get("deferred_image_paths", []),
    )

    output_dir = Path("data/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    for thought in winning_thoughts:
        for tr in (thought.tool_results or []):
            raw = ""
            if isinstance(tr, dict):
                raw = str(tr.get("result", "") or tr.get("output", "") or "")
            elif isinstance(tr, str):
                raw = tr

            # Extract image_path from tool results (e.g. geometry-plotter)
            if isinstance(tr, dict):
                raw_result = tr.get("result", "")
                if isinstance(raw_result, dict):
                    image_path = raw_result.get("image_path")
                    if image_path and image_path not in text:
                        img_file = Path(image_path)
                        if img_file.exists():
                            file_ref = f"![{img_file.name}]({image_path})"
                            if file_ref not in text:
                                text += f"\n\n{file_ref}"

    # [IMAGE_UNIFY] Replace file paths with /api/media/{media_id} URLs
    # Do NOT use resolve_media() — it embeds base64 data-URIs for images < 10MB.
    try:
        from app.core.media import get_registry
        from app.core.media.resolver import scan_text_for_paths, file_to_api_url
        registry = get_registry()
        paths = scan_text_for_paths(text)
        for raw_path in paths:
            entry = registry.lookup_by_path(raw_path)
            if entry is None:
                from app.core.media.resolver import find_file_in_roots
                found = find_file_in_roots(raw_path)
                if found is not None:
                    try:
                        entry = registry.register(found, source="resolve_refs", session_id=session_id or None)
                    except Exception:
                        continue
            if entry is not None:
                api_url = file_to_api_url(entry.media_id)
                text = text.replace(raw_path, api_url)
                logger.info("[RESOLVE] %s → %s", raw_path, api_url)
    except Exception as exc:
        logger.warning("[RESOLVE] API URL resolution failed: %s", exc)

    return text


async def synthesis_node(state: ToTState) -> ToTState:
    """Generate final answer based on task_mode and task_type.

    Dispatch priority:
      1. task_mode == "research": evidence-based synthesis with verifier+repair.
      2. task_type == "research_writing": full research-writing pipeline.
      3. Default: generic LLM synthesis.
    """
    task_mode = state.get("task_mode", "standard")
    task_type = state.get("task_type", "generic")
    logger.info(
        f"Synthesis node: task_mode={task_mode}, task_type={task_type}"
    )

    try:
        if task_mode == "research":
            logger.info("Starting research-mode synthesis...")
            state["final_answer"] = await _research_mode_synthesis(state)
        elif task_type == "research_writing":
            logger.info("Starting research-writing pipeline...")
            state["final_answer"] = await _research_writing_synthesis(state)
        else:
            logger.info("Starting generic synthesis...")
            state["final_answer"] = await _generic_synthesis(state)

        # Post-process: resolve image references (file paths → API URLs,
        # embed base64 images from tool results)
        state["final_answer"] = _resolve_image_refs(state["final_answer"], state)

        logger.info(
            f"Synthesis done, answer length={len(state['final_answer'])}"
        )

        # Log final answer via ToTExecutionLogger
        tot_logger = state.get("tot_logger")
        if tot_logger:
            tot_logger.log_final_answer(
                answer=state["final_answer"],
                best_path=state.get("best_path", []),
                total_iterations=len(state.get("thoughts", [])),
            )
    except Exception as e:
        logger.error(f"Synthesis error: {e}", exc_info=True)
        state["final_answer"] = _fallback_synthesis(state)

    return state


# ---------------------------------------------------------------------------
# Research-mode synthesis — evidence-based report with verifier + repair
# ---------------------------------------------------------------------------

async def _research_mode_synthesis(state: ToTState) -> str:
    """Evidence-based report synthesis for task_mode == "research".

    Pipeline:
      1. Format evidence from evidence_store, serialize coverage_map and
         contradictions.
      2. Generate a full report using the synthesis prompt (prompt_level=
         "writing").
      3. Run a verifier (prompt_level="analysis") to audit the report.
      4. If overall_quality_score < 0.8, run a single repair pass
         (prompt_level="writing").
      5. Return the (possibly repaired) final report.

    Critical constraint: the repair step MUST NOT fabricate new facts not
    present in the evidence_store. The repair prompt is instructed to only
    correct issues identified by the verifier using existing evidence.

    Args:
        state: Current ToT state with research fields populated.

    Returns:
        The final synthesized report as a Markdown string.
    """
    llm = state.get("llm")
    if llm is None:
        logger.warning("No LLM available for research-mode synthesis")
        return _fallback_synthesis(state)

    user_query = state["user_query"]
    evidence_store = state.get("evidence_store") or []

    # Step 1: Format evidence and serialize metadata
    evidence_summary = format_evidence_for_prompt(evidence_store)

    coverage_map = state.get("coverage_map") or {}
    coverage_map_str = json.dumps(coverage_map, ensure_ascii=False, indent=2)

    contradictions = state.get("contradictions") or []
    contradictions_str = json.dumps(
        contradictions, ensure_ascii=False, indent=2
    )

    draft = state.get("draft") or ""

    # Step 2: Generate the full report
    synthesis_user_prompt = get_synthesis_prompt(
        user_query=user_query,
        evidence_summary=evidence_summary,
        coverage_map=coverage_map_str,
        contradictions=contradictions_str,
        draft=draft,
    )

    synthesis_system = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="termination",
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="writing",
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=synthesis_system),
            HumanMessage(content=synthesis_user_prompt),
        ])

        # Extract token usage from synthesis LLM call
        from app.core.execution_trace.token_utils import extract_token_usage
        synthesis_token_usage = extract_token_usage(response)

        final_report = response.content
        logger.info(
            f"Research synthesis report generated: "
            f"{len(final_report)} chars"
        )
    except Exception as exc:
        logger.error(f"Research synthesis report generation failed: {exc}")
        return _fallback_synthesis(state)

    # Step 3: Verifier — audit the report
    final_report = await _verify_and_repair(
        state=state,
        llm=llm,
        user_query=user_query,
        evidence_summary=evidence_summary,
        final_report=final_report,
    )

    return final_report


async def _verify_and_repair(
    state: ToTState,
    llm,
    user_query: str,
    evidence_summary: str,
    final_report: str,
) -> str:
    """Run verifier + single repair round on the synthesized report.

    The verifier audits the report for factual accuracy, completeness,
    and logical consistency against the evidence. If the quality score
    falls below 0.8, a single repair pass is attempted.

    Args:
        state: Current ToT state (used for system prompt composition).
        llm: The chat model instance.
        user_query: Original user research query.
        evidence_summary: Formatted evidence text.
        final_report: The draft final report to verify.

    Returns:
        The final (possibly repaired) report. Returns the original report
        if verification fails entirely.
    """
    # ── Verifier pass ──
    verifier_prompt = get_verifier_prompt(
        user_query=user_query,
        evidence_summary=evidence_summary,
        final_report=final_report,
    )

    verifier_system = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="termination",
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="analysis",
    )

    try:
        verifier_response = await llm.ainvoke([
            SystemMessage(content=verifier_system),
            HumanMessage(content=verifier_prompt),
        ])

        # Extract token usage from verifier LLM call
        from app.core.execution_trace.token_utils import extract_token_usage as _etu
        verifier_token_usage = _etu(verifier_response)

        audit_result = parse_json_output(verifier_response.content)
        overall_quality = audit_result.get("overall_quality_score", 1.0)

        logger.info(
            f"Verifier result: quality={overall_quality:.2f}, "
            f"keys={list(audit_result.keys())}"
        )
    except Exception as exc:
        logger.warning(
            f"Verifier failed, using original report: {exc}"
        )
        return final_report

    # ── Repair pass (only if quality is below threshold) ──
    if overall_quality >= 0.8:
        logger.info("Report quality sufficient, skipping repair")
        return final_report

    logger.info(
        f"Report quality ({overall_quality:.2f}) below 0.8, "
        f"attempting repair"
    )

    audit_result_str = json.dumps(
        audit_result, ensure_ascii=False, indent=2
    )

    repair_prompt = get_repair_prompt(
        user_query=user_query,
        evidence_summary=evidence_summary,
        audit_result=audit_result_str,
        final_report=final_report,
    )

    repair_system = compose_system_prompt(
        base_system_prompt=state.get("system_prompt", ""),
        node_role="termination",
        domain_profile=state.get("domain_profile"),
        tools=state.get("tools"),
        prompt_level="writing",
    )

    try:
        repair_response = await llm.ainvoke([
            SystemMessage(content=repair_system),
            HumanMessage(content=repair_prompt),
        ])

        # Extract token usage from repair LLM call
        from app.core.execution_trace.token_utils import extract_token_usage as _etu2
        repair_token_usage = _etu2(repair_response)

        repaired_report = repair_response.content
        logger.info(
            f"Report repaired: {len(repaired_report)} chars"
        )
        return repaired_report
    except Exception as exc:
        logger.warning(
            f"Repair failed, using original report: {exc}"
        )
        return final_report


# ---------------------------------------------------------------------------
# Research-writing synthesis — four-stage pipeline
# ---------------------------------------------------------------------------

async def _research_writing_synthesis(state: ToTState) -> str:
    """
    研究报告完整 pipeline:
    Stage A:  deep_source_extractor (并发提取)
    Stage A2: cluster_reduce_synthesis (聚类归并)
    Stage B:  research_report_writer + visual_base (并行)
    Stage C:  doc-creator (组装最终文档)
    """
    from app.core.tot.nodes.visual_base import generate_visuals

    llm = state["llm"]
    user_query = state["user_query"]
    findings = _collect_tool_results(state)

    if not findings:
        return "未收集到任何研究资料。"

    # Wrap as sources
    sources = [
        {"source_id": f"S{i+1}", "source_text": txt, "source_type": "unknown"}
        for i, txt in enumerate(findings)
    ]

    # Stage A: deep extraction (concurrent)
    extracted_list = await _extract_all_sources(sources, user_query, llm)

    # Stage A2: cluster reduce
    reduced = await _call_skill_handler(
        "cluster_reduce_synthesis",
        inputs={
            "extracted_list": extracted_list,
            "user_query": user_query,
            "max_clusters": 6
        },
        context={"llm": llm}
    )
    reduced_json = reduced["reduced_json"]

    # Stage B: 并行生成文字报告 + 视觉内容
    report_task = _call_skill_handler(
        "research_report_writer",
        inputs={
            "reduced_json": reduced_json,
            "user_query": user_query,
            "output_style": "academic_paper"
        },
        context={"llm": llm}
    )
    visual_task = generate_visuals(reduced_json, user_query, llm)

    report_result, image_paths = await asyncio.gather(report_task, visual_task)
    report_text = report_result["report_markdown"]

    # Always save the paper to disk
    saved_path = _save_report_to_disk(user_query, report_text)
    save_msg = f"\n\n> 论文已保存至: `{saved_path}`" if saved_path else ""

    # Stage C: doc-creator 组装最终文档 (only if visuals available)
    if image_paths:
        file_path = await _assemble_document(
            title=user_query,
            content=report_text,
            image_paths=image_paths,
            output_format=state.get("output_format", "docx"),
        )
        return f"研究报告已生成: {file_path}\n\n{report_text}"

    return report_text + save_msg


# ---------------------------------------------------------------------------
# Generic synthesis — simple LLM summary
# ---------------------------------------------------------------------------

async def _generic_synthesis(state: ToTState) -> str:
    """Simple LLM synthesis for non-research tasks."""
    llm = state["llm"]
    user_query = state["user_query"]
    all_thoughts = state["thoughts"]
    domain_profile = state.get("domain_profile", {})

    # 获取获胜束路径（优先使用 active_beams，向后兼容 best_path）
    active_beams = state.get("active_beams", [])
    if active_beams and active_beams[0]:
        winning_path_ids = set(active_beams[0])
    else:
        winning_path_ids = set(state.get("best_path", []))

    # 使用 thought_map 优化查找
    thought_map = get_thought_map(all_thoughts)
    best_thoughts = [thought_map[tid] for tid in winning_path_ids if tid in thought_map]

    # 延迟图片嵌入（仅对获胜束路径上的 thoughts）
    _embed_deferred_images_for_path(best_thoughts, state)

    if not best_thoughts:
        return f"I've analyzed your query about: {user_query}"

    # ── Collect reasoning text and tool results ──
    reasoning_text = _build_reasoning_summary(best_thoughts)

    # ── Build system prompt: only synthesis instruction, no tool descriptions ──
    synthesis_instruction = domain_profile.get("synthesis_instruction", "")
    if not synthesis_instruction:
        # fallback: generic instruction with formatting rules
        synthesis_instruction = (
            "You are composing the final answer from completed reasoning steps.\n"
            "Provide a clear, comprehensive answer based on the reasoning process.\n\n"
            "=== 排版规则（必须遵守）===\n"
            "1. 使用 Markdown 排版，结构清晰\n"
            "2. 标题层级：# 主标题 → ## 子标题 → ### 小节\n"
            "3. 关键结论用 **加粗**，重要公式用 $$LaTeX$$ 行间公式\n"
            "4. 列表用 - 或 1. 2. 3.，不要用纯文本堆叠\n"
            "5. 图片必须用 ![描述](路径) 插入，放在相关文字之后\n"
            "6. 代码用 ```语言 包裹\n"
            "7. 每个章节之间用空行分隔，不要挤在一起\n"
            "8. 数学公式用 $inline$ 或 $$display$$ 格式\n\n"
            "IMPORTANT: If the tool results contain file paths (e.g., images, documents), "
            "you MUST include them in the final answer using markdown image syntax ![...](path) "
            "or markdown link syntax [file](path) so the user can see the output.\n"
            "CRITICAL: NEVER generate or embed base64 data, data: URIs, SVG/XML code, "
            "or raw image data in your output. Only reference images by their file paths or URLs. "
            "Violating this rule will corrupt the output.\n"
            "Output in the same language as the user query."
        )

    # ── Build messages ──
    # Inject chat history context if available
    chat_history = state.get("messages", [])
    history_section = ""
    if chat_history:
        history_lines = []
        for msg in chat_history:
            role = "用户" if msg.type == "human" else "助手"
            content = msg.content[:200] if msg.content else ""
            history_lines.append(f"{role}: {content}")
        history_section = f"**Conversation History:**\n" + "\n".join(history_lines) + "\n\n"

    prompt = (
        f"**User Query:** {user_query}\n\n"
        f"{history_section}"
        f"**Reasoning Process & Tool Results:**\n{reasoning_text}\n\n"
        f"Compose the final answer based on the above."
    )

    messages = [
        SystemMessage(content=synthesis_instruction),
        HumanMessage(content=prompt),
    ]

    response = await llm.bind(max_tokens=16384).ainvoke(messages)

    # Extract token usage
    from app.core.execution_trace.token_utils import extract_token_usage
    generic_token_usage = extract_token_usage(response)

    result = response.content
    if _is_truncated(result):
        logger.warning("Synthesis result appears truncated, appending notice")
        result += "\n\n[注: 因长度限制，部分内容被截断]"
    return result


# ---------------------------------------------------------------------------
# Concurrent extraction + Hash Cache
# ---------------------------------------------------------------------------

async def _extract_all_sources(
    sources: List[Dict],
    user_query: str,
    llm,
    max_concurrent: int = 3,
) -> List[Dict]:
    """Concurrent extraction with hash-based dedup."""
    sem = asyncio.Semaphore(max_concurrent)
    cache: Dict[str, Dict] = {}

    async def extract_one(src: Dict) -> Dict:
        content_hash = _content_hash(src["source_text"])

        # Cache hit: skip extraction
        if content_hash in cache:
            logger.info(f"Cache hit for {src['source_id']}")
            return cache[content_hash]

        async with sem:
            result = await _call_skill_handler(
                "deep_source_extractor",
                inputs={**src, "user_query": user_query},
                context={"llm": llm}
            )
            extracted = result["extracted_json"]
            cache[content_hash] = extracted
            return extracted

    results = await asyncio.gather(*[extract_one(s) for s in sources])
    return list(results)


def _content_hash(source_text: str) -> str:
    """Fast hash: first 2KB + length for dedup."""
    head = source_text[:2048]
    raw = f"{len(source_text)}:{head}".encode()
    return hashlib.sha1(raw).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------

async def _assemble_document(
    title: str,
    content: str,
    image_paths: List[str],
    output_format: str = "docx",
) -> str:
    """调用 doc-creator skill 组装最终文档。"""
    result = await _call_skill_handler(
        "doc-creator",
        inputs={
            "doc_type": output_format,
            "title": title,
            "content": content,
            "image_paths": image_paths,
        },
        context={}
    )
    return result["file_path"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _is_truncated(text: str) -> bool:
    """检测文本是否被截断。

    Checks for common signals of incomplete LLM output:
    - Unclosed fenced code blocks (odd number of ``` delimiters).
    - Text ending mid-sentence (not a typical terminator or structural char).
    """
    if text.count("```") % 2 != 0:
        return True
    text_stripped = text.rstrip()
    if not text_stripped:
        return False
    last = text_stripped[-1]
    # Broad set of valid terminators: punctuation, math symbols, brackets, etc.
    valid_endings = set(".!?。！？\n`)$:：■□▪▫★☆—–-…>}|]{")
    if last in valid_endings or last.isdigit():
        return False
    return True


def _collect_tool_results(state: ToTState) -> List[str]:
    """Collect all tool result content strings from winning beam thoughts."""
    # 优先使用 active_beams[0]，向后兼容 best_path
    active_beams = state.get("active_beams", [])
    if active_beams and active_beams[0]:
        winning_path_ids = set(active_beams[0])
    else:
        winning_path_ids = set(state.get("best_path", []))
    all_thoughts = state["thoughts"]
    thought_map = get_thought_map(all_thoughts)
    findings = []
    for tid in winning_path_ids:
        thought = thought_map.get(tid)
        if thought and thought.tool_results:
            for result in thought.tool_results:
                if isinstance(result, dict):
                    content = result.get("result") or result.get("output") or str(result)
                    findings.append(content)
                elif isinstance(result, str):
                    findings.append(result)
    return findings


def _summarize_tool_result(r: dict) -> str:
    """Convert a tool result dict into a compact summary for LLM synthesis.

    For image-bearing results (geometry-plotter, chart-plotter, etc.):
    emits a markdown image placeholder only — never sends raw SVG/base64.
    For other results: truncates to keep prompt small.
    """
    if r.get("status") == "error":
        return f"[{r.get('tool','?')} ERROR] {r.get('error','')}"

    raw = r.get("result") or r.get("output") or ""

    # ---- Image-bearing result (dict with image_path) ----
    if isinstance(raw, dict):
        image_path = raw.get("image_path")
        image_format = raw.get("image_format", "")
        if image_path:
            fname = Path(image_path).name
            desc = raw.get("description", f"Generated {image_format or 'image'}")
            return (
                f"[{r.get('tool','?')}] Image generated successfully.\n"
                f"![{desc}]({image_path})"
            )
        # Non-image dict result
        text = str(raw)
    elif isinstance(raw, str):
        text = raw
    else:
        text = str(raw)

    # ---- Check if text contains embedded base64 images ----
    if "data:image/" in text:
        # Strip base64 data, keep file paths only
        import re as _re
        # Extract file paths
        paths = _re.findall(
            r'(?:data/outputs/|outputs?/|downloads/)[\w./\-]+\.(?:png|jpg|jpeg|gif|svg|webp)',
            text, _re.IGNORECASE,
        )
        # Strip base64 blobs
        text = _re.sub(r'\n*!\[[^\]]*\]\(data:image/[^)]+\)', '', text).strip()
        if paths:
            for p in paths:
                text += f"\n![Generated image]({p})"
        return f"[{r.get('tool','?')}] {text[:2000]}"

    # ---- Truncate very long text ----
    if len(text) > 5000:
        text = text[:5000] + "...[truncated]"

    return f"[{r.get('tool','?')}] {text}"


def _build_reasoning_summary(thoughts: List[Thought]) -> str:
    """Build compact summary for LLM synthesis — image data stays as placeholders."""
    parts = []
    for i, thought in enumerate(thoughts):
        part = f"**Step {i+1}:** {thought.content}"
        if thought.tool_results:
            result_summaries = []
            for r in thought.tool_results:
                if isinstance(r, dict):
                    result_summaries.append(_summarize_tool_result(r))
                elif isinstance(r, str):
                    text = r[:3000] if len(r) > 3000 else r
                    result_summaries.append(text)
            if result_summaries:
                part += f"\n   Tool Results:\n   " + "\n   ".join(result_summaries)
            else:
                part += f"\n   Results: {len(thought.tool_results)} tool results"
        if thought.evaluation_score is not None:
            part += f" (Score: {thought.evaluation_score:.2f})"
        parts.append(part)
    return "\n\n".join(parts)


def _fallback_synthesis(state: ToTState) -> str:
    """Minimal fallback when synthesis fails."""
    user_query = state["user_query"]
    thoughts = state.get("thoughts", [])
    best_score = state.get("best_score", 0)
    return (
        f"Based on my analysis of: {user_query}\n\n"
        f"I explored {len(thoughts)} thoughts. "
        f"The best path scored {best_score:.2f}. "
        f"Please try rephrasing your query for a more detailed answer."
    )


# ---------------------------------------------------------------------------
# 延迟图片嵌入（Beam Search 配套）
# ---------------------------------------------------------------------------

def _embed_deferred_images_for_path(
    thoughts: List[Thought],
    state: ToTState,
) -> None:
    """对获胜束路径上的 thoughts 处理延迟图片。

    探索阶段（executor）跳过了 embed_output_images_v2，
    只提取了文件路径到 deferred_image_paths。
    此处在最终路径确认后，重新扫描并注册图片到 MediaRegistry。
    """
    deferred_paths = state.get("deferred_image_paths", [])
    if not deferred_paths:
        logger.info("[Synthesis-Image] No deferred_image_paths in state, skipping")
        return

    logger.info(
        "[Synthesis-Image] Processing %d deferred paths for %d winning thoughts: %s",
        len(deferred_paths), len(thoughts), deferred_paths,
    )

    try:
        from app.core.streaming.image_embedder import embed_output_images_v2
    except ImportError:
        logger.warning("[Synthesis-Image] image_embedder not available, skipping deferred images")
        return

    for thought in thoughts:
        for r in (thought.tool_results or []):
            result_text = str(r.get("result", ""))
            if not result_text:
                continue

            # 检查此结果是否包含延迟的图片路径
            has_deferred = any(p in result_text for p in deferred_paths)
            if has_deferred:
                # 重新注册图片到 MediaRegistry
                clean_text, img_meta = embed_output_images_v2(
                    result_text,
                    max_age_seconds=300,
                )
                if img_meta:
                    r["result"] = clean_text
                    if "generated_images" not in r:
                        r["generated_images"] = []
                    r["generated_images"].extend(img_meta)

    logger.info(
        f"[Synthesis-Image] Processed {len(deferred_paths)} deferred image paths"
    )
