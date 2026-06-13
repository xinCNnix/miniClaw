"""
Prompt 3: MicroToT — 失败修补方案生成。

输入: task, failure history, tool_list, skill_hints
输出: 3 个 MicroCandidate
"""

SYSTEM_PROMPT = """你是一个任务修补规划器。某个任务执行多次失败，请生成替代方案。

规则:
- 生成 3 个不同的方案
- 每个方案必须包含完整的 tool_plan（从第一步到最后一步）
- 方案之间必须有明显差异（不同的工具、不同的参数策略、不同的顺序）
- 基于失败原因和之前的修补历史来设计
- 如果之前没有使用技能，检查是否有匹配的技能可以作为替代方案
- 调用技能方式: read_file(path="data/skills/{{SkillName}}/SKILL.md")

可用工具: {tool_list}

【可用技能】:
{skill_hints}
"""

USER_PROMPT_TEMPLATE = """[Task]
任务: {task_title}
描述: {task_description}
当前工具计划: {current_tool_plan}
完成标准: {dod_checks}

[Failure History]
失败次数: {attempt_count}
失败原因:
{patch_history_summary}

请输出 JSON:
{{
  "candidates": [
    {{
      "tool_plan": [{{"tool_name": "...", "args_template": {{...}}}}],
      "description": "方案说明",
      "variant_type": "ARG_VARIANT|TOOL_VARIANT|COMBINED"
    }}
  ]
}}
"""


def format_micro_tot_prompt(
    task_title: str,
    task_description: str,
    current_tool_plan: str,
    dod_checks: str,
    attempt_count: int,
    patch_history_summary: str,
    tool_list: str,
    skill_hints: str,
) -> list:
    """格式化 MicroToT prompt"""
    system = SYSTEM_PROMPT.format(tool_list=tool_list, skill_hints=skill_hints)
    user = USER_PROMPT_TEMPLATE.format(
        task_title=task_title,
        task_description=task_description,
        current_tool_plan=current_tool_plan,
        dod_checks=dod_checks,
        attempt_count=attempt_count,
        patch_history_summary=patch_history_summary,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
