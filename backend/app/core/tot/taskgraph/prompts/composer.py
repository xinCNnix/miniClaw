"""
Prompt 4: ArtifactComposer — 从多个 task 的 artifact 组装最终答案。

复用现有 synthesis_node.py 的 synthesis prompt，增强多 task 组装能力。
"""

COMPOSER_SYSTEM_PROMPT = """你是一个报告组装器。根据多个子任务的执行结果，组装最终答案。

规则:
- 按任务执行顺序组织内容
- 如果有多个 task 产出相同类型的内容，合并去重
- 如果有 research report artifact，以其为主体
- 引用具体的 task 执行结果作为支撑
"""

COMPOSER_USER_TEMPLATE = """[Tasks Summary]
{tasks_summary_with_artifacts}

请生成最终答案。"""


def format_composer_prompt(tasks_summary: str) -> list:
    """格式化组装 prompt"""
    user = COMPOSER_USER_TEMPLATE.format(
        tasks_summary_with_artifacts=tasks_summary,
    )
    return [
        {"role": "system", "content": COMPOSER_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
