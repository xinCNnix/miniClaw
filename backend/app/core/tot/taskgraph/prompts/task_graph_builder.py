"""
Prompt 1: TaskGraphBuilder — 一次 LLM 调用生成任务 DAG。

输入: user_query, session_context, domain_profile, tool_list, enrichment, skill_hints
输出: 结构化 JSON（tasks 数组）
"""

SYSTEM_PROMPT = """你是一个任务规划引擎。根据用户请求，生成一个任务执行图（DAG）。

规则:
1. 每个任务必须有明确的目标和可验证的完成条件
2. 任务之间通过 dependencies 字段表示执行顺序
3. 每个任务指定需要的工具和备选工具
4. 根据任务性质选择执行模式:
   - direct: 简单工具调用（如搜索、读取文件）
   - beam_search: 需要多方案比较（如决策、分析）
   - research: 需要深度研究（如资料调研、论文综述）
5. 每个 task 的 priority: 数字越大越优先（0-100）

可用工具: {tool_list}
领域建议: {domain_methods}

【重要】可用技能列表:
{skill_hints}

工具选择规则:
- 有脚本的技能(技能列表中带 terminal 命令的): 使用 terminal 工具直接运行脚本
  示例: terminal(command="python data/skills/arxiv-search/scripts/openalex_search.py --query \\"...\\" --max-results 10")
  备选: search_kb (本地知识库搜索，仅在 terminal 不可用时使用)
- 没有脚本的技能(如写作/报告类): 使用 read_file 读取技能说明，然后用 python_repl 执行
- 保存文档类任务: 使用 write_file
- 图表/绘图类任务: 必须优先使用 visual 相关技能的脚本
- 每个 tool_plan 的 args_template 必须包含完整的参数，不能省略
"""

USER_PROMPT_TEMPLATE = """用户请求: {user_query}
会话上下文: {session_context}

{enrichment_section}

请输出 JSON:
{{
  "tasks": [
    {{
      "id": "t1",
      "title": "...",
      "description": "...",
      "dependencies": [],
      "execution_mode": "direct|beam_search|research",
      "task_type": "research|decision|coding|writing|generic",
      "tool_plan": [
        {{"tool_name": "...", "args_template": {{...}}, "fallback": "..."}}
      ],
      "priority": 70,
      "max_attempts": 3
    }}
  ]
}}
"""


def format_graph_prompt(
    user_query: str,
    session_context: str,
    tool_list: str,
    domain_methods: str,
    skill_hints: str,
    enrichment_texts: dict = None,
) -> list:
    """格式化 DAG 生成 prompt，返回 messages 列表"""
    enrichment_section = ""
    if enrichment_texts:
        parts = []
        if enrichment_texts.get("tca"):
            parts.append(f"[TCA 指引]\n{enrichment_texts['tca']}")
        if enrichment_texts.get("meta_policy"):
            parts.append(f"[Meta Policy 指引]\n{enrichment_texts['meta_policy']}")
        if enrichment_texts.get("patterns"):
            parts.append(f"[历史模式]\n{enrichment_texts['patterns']}")
        if enrichment_texts.get("semantic_history"):
            parts.append(f"[语义记忆]\n{enrichment_texts['semantic_history']}")
        if parts:
            enrichment_section = "\n".join(parts)

    system = SYSTEM_PROMPT.format(
        tool_list=tool_list,
        domain_methods=domain_methods,
        skill_hints=skill_hints,
    )
    user = USER_PROMPT_TEMPLATE.format(
        user_query=user_query,
        session_context=session_context,
        enrichment_section=enrichment_section,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
