import json
import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


async def run(inputs: dict, context: dict) -> dict:
    """
    对单个来源全文进行深层结构化信息提取。

    Args:
        inputs: 包含 source_id, source_text, user_query, source_type
        context: 包含 llm (LangChain LLM instance)

    Returns:
        包含 extracted_json 的字典
    """
    llm = context["llm"].bind(max_tokens=4000)

    source_id = inputs["source_id"]
    source_text = inputs["source_text"]
    user_query = inputs["user_query"]
    source_type = inputs.get("source_type", "unknown")

    prompt = f"""你是研究信息提取专家。请对以下来源全文进行深层结构化提取。

研究课题：
{user_query}

来源ID：{source_id}
来源类型：{source_type}

来源全文：
{source_text}

请输出详细的 JSON（不要 markdown，不要解释）：
{{
  "source_id": "{source_id}",
  "source_type": "{source_type}",
  "title": "",
  "authors": [],
  "year": "",
  "venue": "",
  "summary": "",
  "key_claims": [
    {{
      "claim": "",
      "evidence": "",
      "quote": "",
      "confidence": 0.0
    }}
  ],
  "methodology": {{
    "approach": "",
    "model_or_algorithm": "",
    "dataset": "",
    "experimental_setup": ""
  }},
  "key_results": [
    {{
      "result": "",
      "metric": "",
      "value": "",
      "comparison": "",
      "context": ""
    }}
  ],
  "limitations": [],
  "novelty_contribution": [],
  "relevance_to_query": "",
  "open_questions": [],
  "keywords": []
}}

要求
- key_claims 至少 5 条（如果信息充分）
- 尽量提取事实、指标、实验数据
- evidence/quote 必须引用原文的句子（可截断）
"""

    resp = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        extracted = json.loads(resp.content)
    except json.JSONDecodeError:
        logger.warning("deep_source_extractor: LLM 输出非合法 JSON，降级返回原文")
        extracted = {
            "source_id": source_id,
            "source_type": source_type,
            "summary": resp.content,
            "parse_error": True,
        }

    return {"extracted_json": extracted}
