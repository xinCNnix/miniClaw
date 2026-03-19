# Available Skills
This document lists all available skills that the Agent can use.
**Total Skills**: 7
---

### arxiv-download-paper
**Description**: Download academic papers from arXiv.org in PDF format. Use when user asks to download research papers, save academic papers locally, or get PDF versions of arXiv papers. Supports downloading by arXiv ID, title search, author search, or keyword query. Papers are saved with sanitized titles as filenames to the downloads directory. Optionally adds papers to knowledge base.
**Location**: `data/skills/arxiv-download-paper`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: arxiv, download, pdf, academic, research, papers

### arxiv-search
**Description**: Search and retrieve academic papers from arXiv.org by query, author, or ID. Use when user asks to find research papers, search academic literature, or get paper information from arXiv.
**Location**: `data/skills/arxiv-search`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: arxiv, academic, research, papers, literature-search

### find-skill
**Description**: Search and install skills from external sources like GitHub, clawhub, and other skill repositories. Use when user asks to find, download, or install new skills from the internet.
**Location**: `data/skills/find-skill`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: skills, search, install, github, repository

### get_weather
**Description**: Get current weather and forecasts via wttr.in. Use when: user asks about weather, temperature, or forecasts for any location. Returns current conditions, temperature, humidity, wind, and forecasts. No API key needed.
**Location**: `data/skills/get_weather`
**Version**: 1.0.0

### github
**Description**: GitHub operations via `gh` CLI: issues, PRs, CI runs, code review, API queries. Use when: (1) checking PR status or CI, (2) creating/commenting on issues, (3) listing/filtering PRs or issues, (4) viewing run logs. NOT for: complex web UI interactions requiring manual browser flows (use browser tooling when available), bulk operations across many repos (script with gh api), or when gh auth is not configured.
**Location**: `data/skills/github`
**Version**: 1.0.0

### skill-creator
**Description**: Create or update skills. Use when designing, structuring, validating, or packaging skills with scripts, references, and assets.
**Location**: `data/skills/skill-creator`
**Version**: 1.0.0

### skill_validator
**Description**: Validate skill files before use. Use when: loading new skills, verifying skill integrity, checking skill metadata. Checks for: required fields, valid syntax, security issues.
**Location**: `data/skills/skill_validator`
**Version**: 1.0.0

