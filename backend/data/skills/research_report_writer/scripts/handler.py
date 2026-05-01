import json
import logging
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


async def run(inputs: dict, context: dict) -> dict:
    """
    基于 reduced_json 撰写研究论文，标准学术格式，强制引用标注。

    Args:
        inputs: 包含 reduced_json, user_query, output_style, citation_style
        context: 包含 llm (LangChain LLM instance)

    Returns:
        包含 report_markdown 的字典
    """
    llm = context["llm"].bind(max_tokens=16000)

    reduced_json = inputs["reduced_json"]
    user_query = inputs["user_query"]
    output_style = inputs.get("output_style", "academic_paper")

    payload = json.dumps(reduced_json, ensure_ascii=False)

    system_prompt = """You are a senior academic researcher writing a scholarly paper.
Follow standard academic conventions strictly:
- Use IMRaD structure (Introduction, Methods, Results, Discussion) or survey/review structure
- Include: Title, Abstract (with keywords), numbered sections, Conclusion, References
- Citations MUST use IEEE numeric style: [1], [2], etc. with full bibliographic entries
- Each reference entry MUST include: authors, title, venue/journal, year, DOI (if available)
- DO NOT fabricate references. Only cite sources provided in the data.
- Write in formal academic tone, third person, passive voice where appropriate
- Include quantitative evidence with specific numbers/metrics when available
- Compare and contrast findings across sources rather than listing them sequentially"""

    prompt = f"""Write a comprehensive academic survey paper based on the following clustered research data.

Topic: {user_query}
Format: {output_style}

Clustered Research Data (reduced_json):
{payload}

Structure Requirements:
1. **Title** — concise, descriptive
2. **Abstract** (150-300 words, with 4-6 keywords)
3. **1. Introduction** — background, motivation, scope, paper organization
4. **2. Literature Overview** — thematic analysis grouped by clusters
5. **3. Comparative Analysis** — cross-source comparison of methods, findings, metrics
6. **4. Discussion** — contradictions, gaps, open questions
7. **5. Conclusion & Future Directions**
8. **References** — IEEE numeric format [1], [2], ... with full bibliographic details

Citation Rules:
- Use numeric citations [1], [2], etc. mapping to the References section
- Every factual claim MUST have a citation
- Do NOT invent sources. Only cite what exists in the provided data.
- Map S1, S2, ... source IDs from the data to [1], [2], ... in references

Quality Rules:
- Minimum 3000 words of substantive content
- Include specific numbers, metrics, and experimental results from sources
- Compare at least 2 sources for each major claim
- Identify consensus and contradictions explicitly

Write the paper now:"""

    resp = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt),
    ])
    return {"report_markdown": resp.content}
