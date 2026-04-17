---
name: arxiv-download-paper
description: Download academic papers from arXiv.org in PDF format. Use when user asks to download research papers, save academic papers locally, or get PDF versions of arXiv papers. Supports downloading by arXiv ID, title search, author search, or keyword query. Papers are saved with sanitized titles as filenames to the downloads directory. Optionally adds papers to knowledge base.
version: 1.0.0
author: miniClaw
tags: [arxiv, download, pdf, academic, research, papers]
dependencies:
  python:
    - "arxiv>=2.0.0"
---

# arXiv Paper Download

Download academic papers from arXiv.org in PDF format with proper filename sanitization.

## Overview

This skill enables downloading PDF versions of academic papers from arXiv.org. Papers are saved with sanitized titles as filenames to prevent filesystem issues. Supports multiple search methods and optional knowledge base integration.

## Quick Start

### Download by arXiv ID

Download a specific paper using its arXiv ID:

```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py --id "2307.09288" --output-dir downloads
```

### Download by Title Search

Search and download papers by title:

```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py --title "Attention Is All You Need" --output-dir downloads
```

### Download Multiple Papers

Download multiple papers by keyword query:

```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py --query "transformers" --max-results 5 --output-dir downloads
```

## Download Parameters

The download_paper script accepts the following parameters:

| Parameter | Short | Description | Example |
|-----------|-------|-------------|---------|
| `--id` | `-i` | Download specific paper by arXiv ID | `"2307.09288"` |
| `--title` | `-t` | Search by paper title | `"Attention Is All You Need"` |
| `--query` | `-q` | Search query (keywords, phrases) | `"large language models"` |
| `--author` | `-a` | Search by author name | `"Geoffrey Hinton"` |
| `--output-dir` | `-o` | Output directory for PDFs (default: `downloads`) | `"downloads"` |
| `--max-results` | `-m` | Maximum number of results (default: 10) | `20` |
| `--sort-by` | `-s` | Sort order: relevance, lastUpdatedDate, submittedDate | `relevance` |
| `--order` | `-o` | Sort direction: ascending, descending | `descending` |
| `--category` | `-c` | Filter by arXiv category | `cs.AI` |
| `--add-to-kb` | | Add downloaded papers to knowledge base | |

## Filename Sanitization

Papers are saved with filenames derived from their titles. Invalid characters are replaced with underscores:

- Invalid characters: `< > : " / \ | ? *`
- Control characters are removed
- Filenames are trimmed and limited to 200 characters
- Example: `"Attention Is All You Need"` → `Attention_Is_All_You_Need.pdf`

## Common Workflows

### Workflow 1: Download Single Paper

Download a specific paper by arXiv ID:

```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py \
  --id "2307.09288" \
  --output-dir downloads
```

### Workflow 2: Download Papers by Topic

Download recent papers on a specific topic:

```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py \
  --query "diffusion models" \
  --category cs.LG \
  --sort-by submittedDate \
  --order descending \
  --max-results 10 \
  --output-dir downloads
```

### Workflow 3: Download Papers by Author

Download papers from a specific researcher:

```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py \
  --author "Yann LeCun" \
  --max-results 5 \
  --output-dir downloads
```

### Workflow 4: Download and Add to Knowledge Base

Download papers and add them to the knowledge base for future reference:

```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py \
  --id "2307.09288" \
  --output-dir downloads \
  --add-to-kb
```

## Output Structure

Downloaded papers are saved to the specified output directory (default: `downloads/`):

```
downloads/
├── Attention_Is_All_You_Need.pdf
├── BERT_Pre-training_of_Deep_Bidirectional_Transformers.pdf
└── ...
```

If `--add-to-kb` is used, papers are also copied to `knowledge_base/papers/`.

## Error Handling

- **No results found**: The query may be too specific. Try broader terms.
- **Invalid arXiv ID**: Check the ID format (e.g., `2307.09288`).
- **Download failures**: Network issues or invalid PDF URLs. Check internet connection.
- **File already exists**: Script skips existing files to avoid overwrites.

## Tips for Effective Downloads

1. **Use specific IDs**: When you know the exact paper, use `--id` for fastest download.
2. **Limit results**: Use `--max-results` to control how many papers to download.
3. **Check categories**: Add `--category cs.AI` to narrow results to relevant fields.
4. **Sort by date**: Use `--sort-by submittedDate --order descending` for latest papers.
5. **Use knowledge base**: Add `--add-to-kb` to build a searchable paper collection.

## Example Interactions

### User: "Download the paper 'Attention Is All You Need'"

**Agent action:**
```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py \
  --title "Attention Is All You Need" \
  --output-dir downloads
```

### User: "Download arXiv paper 2307.09288"

**Agent action:**
```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py \
  --id "2307.09288" \
  --output-dir downloads
```

### User: "Download 5 recent papers about transformers and add to knowledge base"

**Agent action:**
```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py \
  --query "transformers" \
  --sort-by submittedDate \
  --order descending \
  --max-results 5 \
  --output-dir downloads \
  --add-to-kb
```

### User: "Download papers by Geoffrey Hinton"

**Agent action:**
```bash
python data/skills/arxiv-download-paper/scripts/download_paper.py \
  --author "Geoffrey Hinton" \
  --max-results 10 \
  --output-dir downloads
```

## Notes

- Requires the `arxiv` Python package. Install with: `pip install arxiv`
- Downloads use urllib for better compatibility across platforms
- Progress is shown during download with percentage and bytes transferred
- Existing files are not overwritten to prevent data loss
- Knowledge base integration copies papers to `knowledge_base/papers/` directory

## Resources

### scripts/download_paper.py

Python script that handles paper search and PDF download. Supports multiple search methods and filename sanitization.

**Usage examples:**

```bash
# Command line
python scripts/download_paper.py --id "2307.09288" --output-dir downloads

# With knowledge base
python scripts/download_paper.py --query "neural networks" --max-results 3 --add-to-kb
```