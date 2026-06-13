"""
TaskVerifier — 三层验证 Rule → Code → LLM。

Layer 1 (Rule): 确定性检查，~0ms
Layer 2 (Code): 文件/数据验证，~1-5s
Layer 3 (LLM): 语义评估，~2-10s（后续 Task 中集成 LLM）

短路机制: HARD 检查失败立即返回，不进入下一层。
"""
from __future__ import annotations

import logging
import os
from typing import List

from app.core.tot.taskgraph.models import (
    CheckResult,
    DoDCheck,
    TaskNode,
    VerifierVerdict,
)
from app.core.tot.taskgraph.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


class TaskVerifier:
    """三层任务验证器"""

    def verify(self, task: TaskNode, store: ArtifactStore) -> VerifierVerdict:
        """执行三层验证，返回裁决结果"""
        # Layer 1: Rule checks
        rule_results = self._rule_checks(task)
        if self._has_hard_fail(rule_results):
            return self._build_verdict(rule_results, layer="RULE")

        # Layer 2: Code checks
        code_results = self._code_checks(task, store)
        all_results = rule_results + code_results
        if self._has_hard_fail(code_results):
            return self._build_verdict(all_results, layer="CODE")

        # Layer 3: LLM judge — 初始版本用 rule+code 结果综合评分
        return self._build_verdict(all_results, layer="CODE")

    def _rule_checks(self, task: TaskNode) -> List[CheckResult]:
        """确定性规则检查"""
        results: List[CheckResult] = []

        for check in task.dod:
            if check.check_type == "NON_EMPTY":
                passed = len(task.tool_results) > 0
                evidence = f"tool_results 数量: {len(task.tool_results)}"
                results.append(CheckResult(
                    check_type=check.check_type,
                    passed=passed,
                    evidence=evidence,
                    severity=check.severity,
                ))

            elif check.check_type == "TOOL_SUCCESS":
                errors = [r for r in task.tool_results if not r.get("success", True)]
                passed = len(errors) == 0
                evidence = f"失败工具数: {len(errors)}" if errors else "全部成功"
                results.append(CheckResult(
                    check_type=check.check_type,
                    passed=passed,
                    evidence=evidence,
                    severity=check.severity,
                ))

            elif check.check_type == "FILE_EXISTS":
                pass

            elif check.check_type == "SOURCE_COUNT":
                min_sources = check.params.get("min_sources", 3)
                source_count = len(task.tool_results)
                passed = source_count >= min_sources
                results.append(CheckResult(
                    check_type=check.check_type,
                    passed=passed,
                    evidence=f"来源数: {source_count}, 要求: {min_sources}",
                    severity=check.severity,
                ))

            elif check.check_type == "CODE_EXECUTABLE":
                has_traceback = any(
                    "traceback" in str(r.get("output", "")).lower()
                    or "error" in str(r.get("output", "")).lower()
                    for r in task.tool_results
                )
                results.append(CheckResult(
                    check_type=check.check_type,
                    passed=not has_traceback,
                    evidence="检查执行错误" if has_traceback else "无执行错误",
                    severity=check.severity,
                ))

        return results

    def _code_checks(self, task: TaskNode, store: ArtifactStore) -> List[CheckResult]:
        """代码/文件系统验证"""
        results: List[CheckResult] = []

        for check in task.dod:
            if check.check_type == "FILE_EXISTS":
                path = check.params.get("path", "")
                exists = os.path.exists(path) if path else False
                results.append(CheckResult(
                    check_type=check.check_type,
                    passed=exists,
                    evidence=f"文件 {path} {'存在' if exists else '不存在'}",
                    severity=check.severity,
                ))

        return results

    def _has_hard_fail(self, results: List[CheckResult]) -> bool:
        """是否有 HARD 严重级别的检查失败"""
        return any(r.severity == "HARD" and not r.passed for r in results)

    def _build_verdict(self, results: List[CheckResult], layer: str) -> VerifierVerdict:
        """从检查结果构建裁决"""
        all_pass = all(r.passed for r in results if r.severity == "HARD")
        hard_results = [r for r in results if r.severity == "HARD"]
        confidence = (
            sum(1 for r in hard_results if r.passed) / len(hard_results)
            if hard_results
            else 1.0
        )
        failed_reasons = [
            f"{r.check_type}: {r.evidence}"
            for r in results if not r.passed
        ]

        return VerifierVerdict(
            passed=all_pass,
            confidence=round(confidence, 2),
            failed_reasons=failed_reasons,
            patch_suggestions=[],
            check_results=results,
            verification_layer=layer,
        )
