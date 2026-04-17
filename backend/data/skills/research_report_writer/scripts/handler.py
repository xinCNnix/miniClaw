import json
import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


async def run(inputs: dict, context: dict) -> dict:
    """
    基于 reduced_json 撰写研究报告，强制引用标注。

    Args:
        inputs: 包含 reduced_json, user_query, output_style, citation_style
        context: 包含 llm (LangChain LLM instance)

    Returns:
        包含 report_markdown 的字典
    """
    llm = context["llm"].bind(max_tokens=16000)

    reduced_json = inputs["reduced_json"]
    user_query = inputs["user_query"]
    output_style = inputs.get("output_style", "report")

    payload = json.dumps(reduced_json, ensure_ascii=False)

    prompt = f"""你是资深研究报告撰写师。请基于 reduced_json 写一篇高质量研究报告。

研究课题：
{user_query}

输出格式：
{output_style}

reduced_json：
{payload}

输出要求：
- 输出 markdown，不要 JSON
- 包含以下章节
  1. Executive Summary
  2. Key Themes / Findings
  3. Method Comparison
  4. Contradictions & Uncertainty
  5. Limitations
  6. Future Directions
  7. References
- 每个关键论点必须标注来源，例如 [S1][S4]
- 不要编造不存在的来源ID
- 进行多源对比，而不是简单复述

开始撰写：
"""

    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    return {"report_markdown": resp.content}
