"""
Prompt 2: Verifier LLM 层 — 语义评估。

输入: task (title, description, dod), tool_results, artifacts
输出: 结构化 VerifierVerdict JSON
"""

SYSTEM_PROMPT = """你是一个任务验证器。判断任务执行结果是否满足完成标准。

评估维度:
1. result_quality (0-10): 工具结果的质量
2. query_satisfaction (0-10): 是否满足任务目标
3. output_completeness (0-10): 输出的完整性

规则:
- 严格按完成标准评估，不要宽松放行
- 如果失败，必须给出具体的修复建议（patch_suggestions）
- patch_suggestions 应该是下一步应该执行的具体操作
- confidence 反映你的确定程度
"""

USER_PROMPT_TEMPLATE = """[Task]
任务: {task_title}
描述: {task_description}
完成标准: {dod_checks}

[Results]
工具执行结果: {tool_results_summary}
产物: {artifacts_summary}

请输出 JSON:
{{
  "passed": true或false,
  "confidence": 0.0到1.0,
  "scores": {{
    "result_quality": 0到10,
    "query_satisfaction": 0到10,
    "output_completeness": 0到10
  }},
  "failed_reasons": ["..."],
  "patch_suggestions": ["具体修复步骤1", "具体修复步骤2"],
  "evidence": "判断依据"
}}
"""


def format_verifier_prompt(
    task_title: str,
    task_description: str,
    dod_checks: str,
    tool_results_summary: str,
    artifacts_summary: str,
) -> list:
    """格式化验证 prompt"""
    user = USER_PROMPT_TEMPLATE.format(
        task_title=task_title,
        task_description=task_description,
        dod_checks=dod_checks,
        tool_results_summary=tool_results_summary,
        artifacts_summary=artifacts_summary,
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
