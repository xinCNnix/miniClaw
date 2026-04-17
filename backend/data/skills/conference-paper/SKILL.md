---
name: conference-paper
description: "Search and retrieve papers from top AI conferences (ICLR, NeurIPS, ICML, IJCAI, CVPR, ICCV, ACL). Use when: (1) user asks about papers from specific AI conferences, (2) user wants to find papers presented at ICLR/NeurIPS/ICML etc., (3) user needs to browse conference proceedings by year/topic, (4) user wants to download PDFs of conference papers. NOT for: general arXiv search (use arxiv-search), AI Agent specific papers (use agent-papers)."
version: 1.0.0
author: miniClaw
tags: [conference, academic, research, papers, AI, ICLR, NeurIPS, ICML, CVPR, ACL]
dependencies:
  python:
    - "requests>=2.31.0"
---

# Conference Paper Search

Search and retrieve papers from top AI/ML conferences: ICLR, NeurIPS, ICML, IJCAI, CVPR, ICCV, ACL.

## Overview

This skill queries multiple academic APIs (OpenReview, Semantic Scholar, CVF OpenAccess, ACL Anthology, DBLP) to find papers from major AI conferences. It automatically routes queries to the best provider based on the target conference, deduplicates results, and supports PDF download.

## Supported Conferences

| Conference | Primary Provider | Coverage |
|------------|-----------------|----------|
| ICLR | OpenReview | Full |
| NeurIPS | Semantic Scholar | Full |
| ICML | Semantic Scholar | Full |
| IJCAI | Semantic Scholar | Full |
| CVPR | CVF + Semantic Scholar | Full |
| ICCV | CVF + Semantic Scholar | Full |
| ACL | ACL Anthology + Semantic Scholar | Full |

## Quick Start

### Search papers by conference and year

```bash
python data/skills/conference-paper/scripts/conference_search.py --conference ICLR --year 2024 --keywords "agent" "tool use" --max-results 10
```

### Search by title

```bash
python data/skills/conference-paper/scripts/conference_search.py --conference NeurIPS --year 2024 --title "attention is all you need"
```

### Search by author

```bash
python data/skills/conference-paper/scripts/conference_search.py --conference ICML --year 2023 --authors "Hinton" "LeCun"
```

### Resolve PDF URL

```bash
python data/skills/conference-paper/scripts/resolve_pdf.py --arxiv-id "2307.09288"
```

### Download paper PDF

```bash
python data/skills/conference-paper/scripts/download_pdf.py --pdf-url "https://arxiv.org/pdf/2307.09288.pdf"
```

## Search Parameters

| Parameter | Short | Description | Example |
|-----------|-------|-------------|---------|
| `--conference` | `-c` | Conference name (required) | `ICLR`, `NeurIPS`, `ICML`, `IJCAI`, `CVPR`, `ICCV`, `ACL` |
| `--year` | `-y` | Publication year (required) | `2024` |
| `--keywords` | `-k` | Search keywords (space-separated) | `"agent" "tool use"` |
| `--title` | `-t` | Search by title | `"attention mechanism"` |
| `--authors` | `-a` | Search by authors (space-separated) | `"Hinton" "LeCun"` |
| `--max-results` | `-m` | Maximum results (default: 10) | `20` |
| `--format` | `-f` | Output format: text, json (default: text) | `json` |

## Output Format

```json
{
  "conference": "ICLR",
  "year": 2024,
  "returned": 10,
  "provider_used": "openreview",
  "papers": [
    {
      "title": "...",
      "authors": ["..."],
      "conference": "ICLR",
      "year": 2024,
      "abstract": "...",
      "pdf_url": "...",
      "source_url": "...",
      "doi": "...",
      "arxiv_id": "..."
    }
  ]
}
```

## Other Commands

### Resolve PDF URL

Resolve a direct PDF link from DOI, arXiv ID, or source URL:

```bash
# From arXiv ID
python data/skills/conference-paper/scripts/resolve_pdf.py --arxiv-id "2307.09288"

# From DOI
python data/skills/conference-paper/scripts/resolve_pdf.py --doi "10.xxxx/..."

# From source URL
python data/skills/conference-paper/scripts/resolve_pdf.py --source-url "https://openreview.net/..."
```

### Download PDF

```bash
python data/skills/conference-paper/scripts/download_pdf.py \
  --pdf-url "https://arxiv.org/pdf/2307.09288.pdf"
```

Downloaded files are saved as `<sha256>.pdf` to `<project_root>/downloads/`.

## Common Workflows

### Workflow 1: Find papers at a specific conference

```bash
python data/skills/conference-paper/scripts/conference_search.py \
  --conference ICLR --year 2024 \
  --keywords "large language model" \
  --max-results 20
```

### Workflow 2: Search + resolve + download

```bash
# Step 1: Search
python data/skills/conference-paper/scripts/conference_search.py \
  --conference NeurIPS --year 2024 \
  --title "chain of thought" -f json

# Step 2: If pdf_url missing, resolve it
python data/skills/conference-paper/scripts/resolve_pdf.py \
  --arxiv-id "2201.xxxxx"

# Step 3: Download
python data/skills/conference-paper/scripts/download_pdf.py \
  --pdf-url "https://arxiv.org/pdf/2201.xxxxx.pdf"
```

### Workflow 3: Browse recent CVPR papers

```bash
python data/skills/conference-paper/scripts/conference_search.py \
  --conference CVPR --year 2024 \
  --keywords "diffusion" "generation" \
  --max-results 15
```

### Workflow 4: Find papers by author at a conference

```bash
python data/skills/conference-paper/scripts/conference_search.py \
  --conference ACL --year 2023 \
  --authors "Vaswani" \
  --max-results 10
```

## Error Handling

- **No results found**: Try broader keywords or a different year
- **API timeout**: Providers have 30s timeout, retry if needed
- **Invalid conference name**: Must be one of ICLR/NeurIPS/ICML/IJCAI/CVPR/ICCV/ACL
- **PDF download fails**: Verify URL is a direct PDF link, check network

## Notes

- Provider routing is automatic based on conference name
- Results are deduplicated by normalized title + year
- Semantic Scholar works as fallback for all conferences
- OpenReview is the primary source for ICLR (most accurate)
- CVF and ACL providers are currently stubs (returns from Semantic Scholar)
- PDF downloads are validated (Content-Type check, 50MB limit)

## Related Skills

- `arxiv-search`: For general arXiv paper search (not conference-specific)
- `arxiv-download-paper`: For downloading papers from arXiv
- `agent-papers`: For searching AI Agent specific papers
