"""
LLMVerifier — Verifier Layer 3: LLM 语义评估。

在 Rule + Code 检查通过后，调用 LLM 判断语义质量，
生成 patch_suggestions 用于后续修复。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from app.core.tot.taskgraph.models import (
    CheckResult,
    TaskNode,
    VerifierVerdict,
)

logger = logging.getLogger(__name__)

_EXTERNAL_ERROR_PATTERNS = [
    "429", "rate limit", "too many requests", "timeout", "503", "502",
    "service unavailable", "connection refused", "api key", "quota",
]

_QUALITY_ISSUE_PATTERNS = [
    "相关性", "覆盖度", "权威来源", "不相关",
    "relevance", "coverage", "quality",
    "不全面", "不够全面",
    "来源数量不足", "缺乏多样性",
]


def is_external_error_issue(issue_text: str) -> bool:
    """判断 issue 是否为外部 API 错误（非任务自身问题）"""
    text_lower = issue_text.lower()
    return any(p in text_lower for p in _EXTERNAL_ERROR_PATTERNS)


def is_quality_issue(issue_text: str) -> bool:
    """判断 issue 是否为数据质量问题（不影响任务执行成功）"""
    text_lower = issue_text.lower()
    return any(p in text_lower for p in _QUALITY_ISSUE_PATTERNS)


class LLMVerifier:
    """Verifier Layer 3: LLM 语义评估"""

    def __init__(self, llm: Any = None, trajectory: Optional[Any] = None):
        self.llm = llm
        self.trajectory = trajectory

    async def verify(
        self,
        task: TaskNode,
        rule_code_results: List[CheckResult],
    ) -> Optional[VerifierVerdict]:
        """LLM 评估输出质量，生成 patch_suggestions"""
        if not self.llm:
            return None

        # 收集 tool 输出摘要
        outputs_summary = "\n".join(
            f"- {tr.get('tool', '?')}: {tr.get('output', '')[:500]}"
            for tr in task.tool_results
        )

        # 构建 DoD 描述
        dod_desc = json.dumps(
            [{"type": d.check_type, "desc": d.description} for d in task.dod],
            ensure_ascii=False,
        )

        prompt = (
            f"评估以下任务执行结果的质量。\n"
            f"任务: {task.title}\n"
            f"描述: {task.description}\n"
            f"完成标准: {dod_desc}\n\n"
            f"执行结果:\n{outputs_summary}\n\n"
            f"请以 JSON 格式回答:\n"
            f'{{"passed": true/false, "quality_score": 0.0-1.0, '
            f'"issues": ["问题1", ...], "suggestions": ["建议1", ...]}}'
        )

        llm_start = time.time()
        try:
            response = await self.llm.ainvoke([{"role": "user", "content": prompt}])
            llm_ms = (time.time() - llm_start) * 1000
            raw = response.content if hasattr(response, "content") else str(response)
            parsed = self._parse_llm_response(raw)

            # 提取 token 用量
            prompt_tokens = 0
            completion_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                prompt_tokens = response.usage_metadata.get("prompt_tokens", 0)
                completion_tokens = response.usage_metadata.get("completion_tokens", 0)

            # 记录 LLM 调用轨迹
            if self.trajectory:
                self.trajectory.log_llm_call(
                    caller=f"llm_verifier:{task.id}",
                    prompt_preview=f"verify task={task.title} dod={len(task.dod)} checks",
                    response_preview=raw[:300],
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    duration_ms=llm_ms,
                )

            # 降级逻辑：外部 API 错误和数据质量问题不阻止任务通过
            issues = parsed.get("issues", [])
            critical_issues = [
                i for i in issues
                if not is_external_error_issue(i) and not is_quality_issue(i)
            ]
            # 如果只剩外部错误和质量问题，视为通过
            passed = parsed.get("passed", False) or len(critical_issues) == 0

            return VerifierVerdict(
                passed=passed,
                confidence=parsed.get("quality_score", 0.5),
                failed_reasons=critical_issues,
                patch_suggestions=parsed.get("suggestions", []),
                check_results=rule_code_results,
                verification_layer="LLM",
            )
        except Exception as e:
            llm_ms = (time.time() - llm_start) * 1000
            logger.warning("[TG:llm_verifier] LLM verification failed: %s", e)
            if self.trajectory:
                self.trajectory.log_llm_call(
                    caller=f"llm_verifier:{task.id}",
                    duration_ms=llm_ms,
                    error=str(e),
                )
            return None

    def _parse_llm_response(self, raw: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON，提取评估结果"""
        # 尝试直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown code block 中提取
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个 { ... } 块
        brace_match = re.search(r'\{[\s\S]*\}', raw)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("[TG:llm_verifier] Failed to parse LLM response: %s", raw[:200])
        return {"passed": False, "quality_score": 0.0, "issues": ["解析失败"], "suggestions": []}
