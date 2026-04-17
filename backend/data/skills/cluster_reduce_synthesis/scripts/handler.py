import json
import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


async def run(inputs: dict, context: dict) -> dict:
    """
    将多个源的结构化提取结果聚类合并为 reduced_json。

    Args:
        inputs: 包含 extracted_list, user_query, max_clusters
        context: 包含 llm (LangChain LLM instance)

    Returns:
        包含 reduced_json 的字典
    """
    llm = context["llm"].bind(max_tokens=6000)

    extracted_list = inputs["extracted_list"]
    user_query = inputs["user_query"]
    max_clusters = inputs.get("max_clusters", 6)

    payload = json.dumps(extracted_list, ensure_ascii=False)

    prompt = f"""你是研究综合专家。请将多个源的 extracted_json 聚类合并为若干 clusters，输出 reduced_json。

研究课题：
{user_query}

max_clusters={max_clusters}

输入 extracted_list(JSON)：
{payload}

请输出详细的 JSON（不要 markdown，不要解释）：
{{
  "query": "{user_query}",
  "clusters": [
    {{
      "cluster_id": "C1",
      "topic": "",
      "summary": "",
      "merged_claims": [
        {{
          "claim": "",
          "supporting_sources": ["S1"],
          "evidence": "",
          "confidence": 0.0
        }}
      ],
      "key_results": [
        {{
          "result": "",
          "metric": "",
          "value": "",
          "sources": ["S1"]
        }}
      ]
    }}
  ],
  "consensus_points": [
    {{
      "point": "",
      "sources": ["S1", "S2"]
    }}
  ],
  "contradictions": [
    {{
      "issue": "",
      "side_a": {{"claim": "", "sources": ["S1"]}},
      "side_b": {{"claim": "", "sources": ["S2"]}},
      "notes": ""
    }}
  ],
  "open_questions": [],
  "recommended_next_search": []
}}

要求
- clusters 数量 <= max_clusters
- merged_claims 必须包含 supporting_sources
- contradictions 必须明确指出冲突双方来源
- 禁止捏造不存在的来源ID
"""

    resp = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        reduced = json.loads(resp.content)
    except json.JSONDecodeError:
        logger.warning("cluster_reduce_synthesis: LLM 输出非合法 JSON，降级返回原文")
        reduced = {
            "query": user_query,
            "raw_text": resp.content,
            "parse_error": True,
        }

    return {"reduced_json": reduced}
