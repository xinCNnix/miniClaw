---
name: deep_source_extractor
description: |
  对单个来源全文进行深层结构化信息提取，输出详细结构化 JSON。
  适用于论文、网页、PDF 转文本等长文档的研究信息提取。
version: 1.0
dependencies: {}
inputs:
  - source_id: str
  - source_text: str
  - user_query: str
  - source_type: str   # paper/web/pdf/markdown/unknown
outputs:
  - extracted_json: dict
---

# deep_source_extractor

## Purpose
对单个来源全文进行深层信息提取，产出可靠的、可供下游分析的结构化结果。

## Output Schema (JSON)

输出合法 JSON，字段缺失用空值/空字符串填充。

```json
{
  "source_id": "S1",
  "source_type": "paper",
  "title": "",
  "authors": [],
  "year": "",
  "venue": "",
  "summary": "",
  "key_claims": [
    {
      "claim": "",
      "evidence": "",
      "quote": "",
      "confidence": 0.0
    }
  ],
  "methodology": {
    "approach": "",
    "model_or_algorithm": "",
    "dataset": "",
    "experimental_setup": ""
  },
  "key_results": [
    {
      "result": "",
      "metric": "",
      "value": "",
      "comparison": "",
      "context": ""
    }
  ],
  "limitations": [],
  "novelty_contribution": [],
  "relevance_to_query": "",
  "open_questions": [],
  "keywords": []
}
```

## Extraction Rules

- 尽量保留原文的精确句子、事实引用、指标
- 宁可只写确定的，不要列出无法验证的 claim
- 不确定的信息，confidence 打低（0~1）
- quote 字段必须引用原文句子（可截断，不要太长原文）

## Prompt Style

- 输出严格为 JSON，不要加 markdown 包装
- 即使长篇文本也尽量提取事实、数据、方法、结论
