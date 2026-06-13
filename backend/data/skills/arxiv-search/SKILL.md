---
name: arxiv-search
description: Search academic papers from arXiv, OpenAlex, and Semantic Scholar. Use when user asks to find research papers, search academic literature, get paper information, or verify citations.
version: 2.0.0
author: miniClaw
tags: [arxiv, openalex, semantic-scholar, academic, research, papers, literature-search]
dependencies:
  python:
    - "arxiv>=2.0.0"
---

# Academic Paper Search (arXiv + OpenAlex + Semantic Scholar)

Search and retrieve academic papers from three complementary sources:

| Source | API Key | Rate Limit | Strengths |
|--------|---------|------------|-----------|
| **arXiv** | 不需要 | ~3s/请求 | 预印本、最新研究、cs/physics/math 领域 |
| **OpenAlex** | 不需要 | 200ms/请求 (10K/天) | 全学科覆盖、引用数、DOI 查找、元数据最全 |
| **Semantic Scholar** | 可选 (`S2_API_KEY`) | 1.5s/请求 (有key: 0.3s) | 引用数、语义搜索、论文关联、批量查询 |

## Quick Start

### arXiv — 搜索预印本

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py --query "large language models" --sort-by submittedDate --order descending --max-results 10
```

### OpenAlex — 全学科搜索 (推荐首选)

```bash
python data/skills/arxiv-search/scripts/openalex_search.py --query "neural networks" --sort-by cited --year-min 2023 --max-results 10
```

### Semantic Scholar — 语义搜索 + 引用分析

```bash
python data/skills/arxiv-search/scripts/semantic_scholar_search.py --query "transformer attention mechanism" --max-results 10
```

## Mandatory Rules for Agent

When using this skill for research or literature review tasks, the agent MUST follow these rules:

1. **多源搜索策略**: 每次文献检索任务必须使用至少 2 个数据源，交叉验证结果。
2. **首选 OpenAlex**: 对于一般性学术搜索，优先使用 OpenAlex（速率最快、覆盖最广、无需 key）。
3. **arXiv 用于最新预印本**: 搜索尚未正式发表的最新研究时使用 arXiv，按提交日期降序排列。
4. **S2 用于引用分析**: 需要论文引用数、引用关系、或论文 ID 查找时使用 Semantic Scholar。
5. **时间排序**: 除非用户明确要求相关性排序，否则始终包含时间排序（最新优先）。
6. **去重**: 多源搜索结果需要按 DOI / arXiv ID / 标题去重，保留信息最完整的记录。
7. **年份过滤**: 研究任务默认使用 `--year-min` 限制在近 3 年，除非用户指定其他范围。

## Source 1: arXiv

### 搜索参数

| 参数 | 短选项 | 说明 | 示例 |
|------|--------|------|------|
| `--query` | `-q` | 搜索查询（支持布尔运算符） | `"neural networks AND deep learning"` |
| `--author` | `-a` | 按作者搜索 | `"Yann LeCun"` |
| `--id` | `-i` | 按 arXiv ID 查找 | `"2307.09288"` |
| `--max-results` | `-m` | 最大结果数 (默认 10) | `20` |
| `--sort-by` | `-s` | 排序: relevance, lastUpdatedDate, submittedDate | `submittedDate` |
| `--order` | `-o` | 方向: ascending, descending | `descending` |
| `--category` | `-c` | 按类别过滤 | `cs.AI` |

### 查询语法

```bash
# 布尔运算符
"neural networks AND attention"
"(transformers OR GPT) NOT supervised"

# 字段搜索
"ti:quantum computing"       # 标题
"au:Hinton"                   # 作者
"abs:attention mechanism"     # 摘要
"cat:cs.AI AND deep learning" # 类别

# 常用类别
cs.AI  cs.LG  cs.CL  cs.CV  cs.CR  stat.ML  math.OC  physics.comp-ph
```

## Source 2: OpenAlex

### 搜索参数

| 参数 | 短选项 | 说明 | 示例 |
|------|--------|------|------|
| `--query` | `-q` | 搜索查询 | `"neural networks"` |
| `--author` | `-a` | 按作者搜索 | `"Geoffrey Hinton"` |
| `--doi` | `-d` | 按 DOI 查找 | `"10.1038/s41586-020-2649-2"` |
| `--max-results` | `-m` | 最大结果数 (默认 10, 上限 50) | `20` |
| `--year-min` | | 最早发表年份 | `2020` |
| `--year-max` | | 最晚发表年份 | `2024` |
| `--sort-by` | | relevance / cited / date | `cited` |
| `--format` | `-f` | text / json | `json` |

### 使用场景

- **查找高引用论文**: `--sort-by cited`
- **DOI 反查**: `--doi "10.1234/..."` 直接定位论文
- **年份范围**: `--year-min 2023 --year-max 2025`
- **无需 key**: 默认使用礼貌池 (10K/天)

## Source 3: Semantic Scholar

### 搜索参数

| 参数 | 短选项 | 说明 | 示例 |
|------|--------|------|------|
| `--query` | `-q` | 语义搜索查询 | `"attention mechanism"` |
| `--author` | `-a` | 按作者搜索 | `"Geoffrey Hinton"` |
| `--id` | `-i` | 按论文 ID 查找 (S2 ID / DOI:xxx / ARXIV:xxx) | `"ARXIV:2307.09288"` |
| `--batch` | `-b` | 批量获取多个 ID | `"id1" "id2" "id3"` |
| `--max-results` | `-m` | 最大结果数 (默认 10, 上限 100) | `20` |
| `--year-min` | | 最早发表年份 | `2020` |
| `--year-max` | | 最晚发表年份 | `2024` |
| `--format` | `-f` | text / json | `json` |

### 使用场景

- **语义搜索**: 比 arXiv 关键词搜索更智能，能理解查询意图
- **论文 ID 查找**: 支持多种 ID 格式 (S2 ID, `DOI:10.xxx`, `ARXIV:2307.09288`)
- **批量查询**: `--batch id1 id2 id3` 一次获取多篇论文
- **引用分析**: 返回精确的引用数和论文关联

### API Key (可选)

设置 `S2_API_KEY` 环境变量可将速率限制从 1.5s/请求 提升至 0.3s/请求。

## Common Workflows

### Workflow 1: 全面的文献综述

同时搜索三个源，交叉验证：

```bash
# Step 1: OpenAlex 快速概览 (最快)
python data/skills/arxiv-search/scripts/openalex_search.py \
  --query "graph neural networks" --sort-by cited --year-min 2023 --max-results 20 --format json

# Step 2: arXiv 查找最新预印本
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --query "graph neural networks" --sort-by submittedDate --order descending --max-results 15 --format json

# Step 3: S2 补充引用数据
python data/skills/arxiv-search/scripts/semantic_scholar_search.py \
  --query "graph neural networks" --year-min 2023 --max-results 15 --format json
```

### Workflow 2: 查找特定论文

```bash
# 通过 DOI
python data/skills/arxiv-search/scripts/openalex_search.py --doi "10.1038/s41586-020-2649-2"

# 通过 arXiv ID
python data/skills/arxiv-search/scripts/arxiv_search.py --id "2307.09288"

# 通过 S2 关联搜索
python data/skills/arxiv-search/scripts/semantic_scholar_search.py --id "ARXIV:2307.09288"
```

### Workflow 3: 追踪研究者

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --author "Yann LeCun" --sort-by submittedDate --order descending --max-results 15

python data/skills/arxiv-search/scripts/openalex_search.py \
  --author "Yann LeCun" --sort-by date --year-min 2023

python data/skills/arxiv-search/scripts/semantic_scholar_search.py \
  --author "Yann LeCun" --year-min 2023 --max-results 20
```

### Workflow 4: 高被引论文

```bash
# OpenAlex 按引用数排序 (最直接)
python data/skills/arxiv-search/scripts/openalex_search.py \
  --query "transformer architecture" --sort-by cited --max-results 10

# S2 也提供精确引用数
python data/skills/arxiv-search/scripts/semantic_scholar_search.py \
  --query "transformer architecture" --max-results 10 --format json
```

## 去重策略

多源搜索后需要去重，优先级：

1. **DOI 匹配**: 最可靠，不区分大小写
2. **arXiv ID 匹配**: 提取 `XXXX.XXXXX` 格式
3. **标题模糊匹配**: 归一化后比较（去除标点、转小写）
4. **保留策略**: 信息更完整的记录优先（有 DOI + 引用数 + 摘要 的优先）

## 输出格式

三个脚本返回统一的结构化格式：

```json
{
  "source": "openalex",
  "total_results": 1523,
  "returned": 10,
  "papers": [
    {
      "title": "Attention Is All You Need",
      "authors": ["Vaswani, Ashish", "Shazeer, Noam"],
      "summary": "The dominant sequence transduction models...",
      "published": "2017-06-12",
      "year": 2017,
      "venue": "NeurIPS",
      "doi": "10.48550/arXiv.1706.03762",
      "arxiv_id": "1706.03762",
      "cited_by_count": 95000,
      "url": "https://..."
    }
  ]
}
```

## Error Handling

| 问题 | 处理方式 |
|------|---------|
| 无结果 | 查询可能过于具体，尝试更宽泛的关键词或换一个数据源 |
| 速率限制 | 脚本内置退避重试，无需手动处理 |
| 网络错误 | 自动重试 3 次，每次指数退避 |
| S2 429 | 等待后重试，最多 3 次 |
| OpenAlex 空结果 | 可能是查询语法问题，尝试简化查询 |

## Tips for Effective Searches

1. **先用 OpenAlex**: 速度最快、无需 key、覆盖全学科
2. **arXiv 查最新**: 尚未正式发表的预印本只在 arXiv
3. **S2 查引用**: 需要精确引用数和论文关联关系时使用
4. **交叉验证**: 重要论文用 DOI/arXiv ID 在多个源验证
5. **年份过滤**: 限定 `--year-min` 避免过时结果
6. **引用排序**: `openalex_search.py --sort-by cited` 找高影响力论文
7. **S2 ID 格式**: 支持 `ARXIV:2307.09288` 或 `DOI:10.xxx` 直接查找

## Resources

### scripts/arxiv_search.py
arXiv API 封装。依赖 `arxiv` pip 包。支持查询、作者、ID 搜索。

### scripts/openalex_search.py
OpenAlex API 封装。纯标准库，无需额外依赖。10K/天免费额度。

### scripts/semantic_scholar_search.py
Semantic Scholar API 封装。纯标准库，无需额外依赖。可选 `S2_API_KEY` 加速。

## Example Interactions

### User: "帮我搜一下最新的 diffusion model 论文"

**Agent action:**
```bash
# OpenAlex 先搜
python data/skills/arxiv-search/scripts/openalex_search.py \
  --query "diffusion models" --sort-by date --year-min 2024 --max-results 10 --format json

# arXiv 补充最新预印本
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --query "diffusion models" --sort-by submittedDate --order descending --max-results 10 --format json
```

### User: "这篇论文被引用了多少次？DOI: 10.1038/s41586-020-2649-2"

**Agent action:**
```bash
python data/skills/arxiv-search/scripts/openalex_search.py \
  --doi "10.1038/s41586-020-2649-2" --format json
```

### User: "找找 Geoffrey Hinton 近三年的论文"

**Agent action:**
```bash
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --author "Geoffrey Hinton" --sort-by submittedDate --order descending --max-results 15

python data/skills/arxiv-search/scripts/semantic_scholar_search.py \
  --author "Geoffrey Hinton" --year-min 2023 --max-results 20
```
