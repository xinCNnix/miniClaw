---
name: research_report_writer
description: |
  基于综合后的 reduced_json 撰写研究报告，
  强制使用引用标注 [S1][S2]。
version: 1.0
dependencies: {}
inputs:
  - reduced_json: dict
  - user_query: str
  - output_style: str   # report/slide/blog
  - citation_style: str # bracket or footnote
outputs:
  - report_markdown: str
---

# research_report_writer

## Purpose
综合并分析研究结果，写成高质量研究报告，保证结构化、引用数据出处、可追溯。

## Output Requirements

- 默认输出 markdown
- 包含以下章节结构：
  - Executive Summary
  - Key Themes / Findings
  - Method Comparison
  - Evidence Table（可选）
  - Contradictions & Uncertainty
  - Limitations
  - Future Directions
  - References（source_id 列表）

## Citation Rules

- 每个关键论点必须标注来源，例如：
  - ...结论... [S1][S3]
- contradictions 必须并列给出双源对比

## Quality Rules

- 不能只有摘要，要有分析和比较
- 不能简单复述，要指出创新点、不足之处、可改进方向
