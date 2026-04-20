---
name: cluster_reduce_synthesis
description: |
  将多个源的结构化提取结果，进行聚类合并压缩。
  输出 cluster summaries + contradictions + consensus。
version: 1.0
dependencies: {}
inputs:
  - extracted_list: list   # List[dict]，来自 deep_source_extractor
  - user_query: str
  - max_clusters: int
outputs:
  - reduced_json: dict
---

# cluster_reduce_synthesis

## Purpose
将多个源 extracted_json 综合成主题聚类，输出结构化 cluster。
使用分步 synthesis 来可控，避免 token 爆炸。

## Output Schema (JSON)

```json
{
  "query": "",
  "clusters": [
    {
      "cluster_id": "C1",
      "topic": "",
      "summary": "",
      "merged_claims": [
        {
          "claim": "",
          "supporting_sources": ["S1", "S3"],
          "evidence": "",
          "confidence": 0.0
        }
      ],
      "key_results": [
        {
          "result": "",
          "metric": "",
          "value": "",
          "sources": ["S2"]
        }
      ]
    }
  ],
  "consensus_points": [
    {
      "point": "",
      "sources": ["S1", "S4"]
    }
  ],
  "contradictions": [
    {
      "issue": "",
      "side_a": {"claim": "", "sources": ["S1"]},
      "side_b": {"claim": "", "sources": ["S2"]},
      "notes": ""
    }
  ],
  "open_questions": [],
  "recommended_next_search": []
}
```

## Reduction Rules

- cluster 数量不超过 max_clusters
- 每个 cluster summary 必须综合多个源，而不是只改写某篇 summary
- contradictions 必须明确指出冲突双方来源
- supporting_sources 必须真实存在

## Prompt Style

- 输出严格为 JSON
- 禁止捏造不存在的来源
