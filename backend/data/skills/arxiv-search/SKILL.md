---
name: arxiv-search
description: Search and retrieve academic papers from arXiv.org by query, author, or ID. Use when user asks to find research papers, search academic literature, or get paper information from arXiv.
version: 1.0.0
author: miniClaw
tags: [arxiv, academic, research, papers, literature-search]
dependencies:
  python:
    - "arxiv>=2.0.0"
---

# arXiv Paper Search

Search and retrieve academic papers from arXiv.org, the premier repository for scientific papers in physics, mathematics, computer science, and related fields.

## Overview

This skill enables searching arXiv's extensive database of academic papers using queries, author names, or paper IDs. It retrieves paper metadata including titles, authors, abstracts, publication dates, and PDF links.

## Quick Start

### Basic Search by Query

Search papers by keywords or topics:

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py --query "large language models" --max-results 10
```

### Search by Author

Find papers by a specific author:

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py --author "Geoffrey Hinton" --max-results 20
```

### Get Paper by ID

Retrieve specific paper using arXiv ID:

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py --id "2307.09288"
```

## Search Parameters

The arxiv_search script accepts the following parameters:

| Parameter | Short | Description | Example |
|-----------|-------|-------------|---------|
| `--query` | `-q` | Search query (keywords, phrases, boolean operators) | `"neural networks AND deep learning"` |
| `--author` | `-a` | Author name to search for | `"Yann LeCun"` |
| `--id` | `-i` | Specific arXiv paper ID | `"cs.AI/1234567"` or `"2307.09288"` |
| `--max-results` | `-m` | Maximum number of results (default: 10) | `20` |
| `--sort-by` | `-s` | Sort order: relevance, lastUpdatedDate, submittedDate | `relevance` |
| `--order` | `-o` | Sort direction: ascending, descending | `descending` |
| `--category` | `-c` | Filter by arXiv category (e.g., cs.AI, cs.LG) | `cs.AI` |

## Query Syntax

arXiv search supports powerful query syntax:

### Boolean Operators

```bash
# AND - both terms must appear
"neural networks AND attention"

# OR - either term can appear
"(transformers OR GPT)"

# NOT - exclude term
"deep learning NOT supervised"

# Grouping with parentheses
"(reinforcement learning OR RL) AND (games OR game theory)"
```

### Field-Specific Searches

```bash
# Search in title
"ti:quantum computing"

# Search in author
"au:Hinton"

# Search in abstract
"abs:attention mechanism"

# Combine fields
"ti:transformers AND au:Vaswani"

# Filter by category
"cat:cs.AI AND deep learning"
```

### Common Categories

- **cs.AI**: Artificial Intelligence
- **cs.LG**: Machine Learning
- **cs.CL**: Computation and Language (NLP)
- **cs.CV**: Computer Vision
- **cs.CR**: Cryptography and Security
- **stat.ML**: Statistics - Machine Learning
- **math.OC**: Optimization and Control
- **physics.comp-ph**: Computational Physics

## Output Format

Results are returned in a structured format:

```json
{
  "total_results": 1523,
  "returned": 10,
  "papers": [
    {
      "title": "Attention Is All You Need",
      "authors": ["Vaswani, Ashish", "Shazeer, Noam", ...],
      "summary": "The dominant sequence transduction models...",
      "published": "2017-06-12",
      "updated": "2017-06-12",
      "categories": ["cs.CL", "cs.LG"],
      "arxiv_id": "1706.03762",
      "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
      "abs_url": "https://arxiv.org/abs/1706.03762"
    },
    ...
  ]
}
```

## Common Workflows

### Workflow 1: Literature Review

Find recent papers on a specific topic:

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --query "graph neural networks" \
  --category cs.LG \
  --sort-by submittedDate \
  --order descending \
  --max-results 20
```

### Workflow 2: Find Seminal Papers

Find highly-cited or influential papers:

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --query "ti:convolutional neural networks" \
  --sort-by relevance \
  --max-results 10
```

### Workflow 3: Track Recent Work by Researcher

Monitor new publications from specific authors:

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --author "Yann LeCun" \
  --sort-by submittedDate \
  --order descending \
  --max-results 15
```

### Workflow 4: Get Paper Details

Retrieve full information for a known paper ID:

```bash
python data/skills/arxiv-search/scripts/arxiv_search.py --id "2307.09288"
```

## Error Handling

- **No results found**: The query may be too specific or the category might be wrong. Try broader terms or remove category filter.
- **Invalid arXiv ID**: Check the ID format. Old format: `cs.AI/1234567`, new format: `2307.09288`
- **API rate limiting**: arXiv allows 3 requests per second. If you hit rate limits, wait before retrying.

## Tips for Effective Searches

1. **Use specific keywords**: "transformer architecture" instead of just "transformer"
2. **Combine with categories**: Add `--category cs.AI` to narrow results to relevant fields
3. **Sort by date**: Use `--sort-by submittedDate --order descending` for latest papers
4. **Use quotes for phrases**: `"large language models"` finds the exact phrase
5. **Leverage boolean operators**: `(transformers OR attention) AND vision`

## Resources

### scripts/arxiv_search.py

Python script that wraps the arXiv API. Handles query construction, result parsing, and output formatting. Can be executed directly or imported as a module.

**Usage examples:**

```python
# Command line
python scripts/arxiv_search.py --query "quantum computing" --max-results 5

# As a module
from scripts.arxiv_search import search_arxiv
results = search_arxiv(query="neural networks", max_results=10)
```

## Example Interactions

### User: "Find recent papers about diffusion models"

**Agent action:**
```bash
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --query "diffusion models" \
  --sort-by submittedDate \
  --order descending \
  --max-results 10
```

### User: "Show me papers by Geoffrey Hinton"

**Agent action:**
```bash
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --author "Geoffrey Hinton" \
  --sort-by submittedDate \
  --order descending \
  --max-results 15
```

### User: "Get details for arXiv paper 2307.09288"

**Agent action:**
```bash
python data/skills/arxiv-search/scripts/arxiv_search.py --id "2307.09288"
```

### User: "Find papers about LLMs in computer vision"

**Agent action:**
```bash
python data/skills/arxiv-search/scripts/arxiv_search.py \
  --query "(large language models OR LLM OR GPT) AND vision" \
  --category "cs.CV" \
  --max-results 10
```

## Notes

- Results are limited to a maximum of 2000 results per query (arXiv API limit)
- Default maximum is 10 results. Adjust with `--max-results` for comprehensive searches
- The script requires the `arxiv` Python package. Install with: `pip install arxiv`
- For complex queries, consider using arXiv's advanced search interface online to construct the query, then use it here
