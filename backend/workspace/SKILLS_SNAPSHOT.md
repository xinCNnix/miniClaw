# Available Skills
This document lists all available skills that the Agent can use.
**Total Skills**: 8
---

### arxiv-search
**Description**: Search and retrieve academic papers from arXiv.org by query, author, or ID. Use when user asks to find research papers, search academic literature, or get paper information from arXiv.
**Location**: `data/skills/arxiv-search/SKILL.md`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: arxiv, academic, research, papers, literature-search

### canvas
**Description**: No description
**Location**: `data/skills/canvas/SKILL.md`
**Version**: 1.0.0

### clawhub
**Description**: Use the ClawHub CLI to search, install, update, and publish agent skills from clawhub.com. Use when you need to fetch new skills on the fly, sync installed skills to latest or a specific version, or publish new/updated skill folders with the npm-installed clawhub CLI.
**Location**: `data/skills/clawhub/SKILL.md`
**Version**: 1.0.0

### clawsec-suite
**Description**: ClawSec suite manager with embedded advisory-feed monitoring, cryptographic signature verification, approval-gated malicious-skill response, and guided setup for additional security skills.
**Location**: `data/skills/clawsec-suite/SKILL.md`
**Version**: 0.1.4

### find-skill
**Description**: Search and install skills from external sources like GitHub, clawhub, and other skill repositories. Use when user asks to find, download, or install new skills from the internet.
**Location**: `data/skills/find-skill/SKILL.md`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: skills, search, install, github, repository

### get_weather
**Description**: 获取指定城市的实时天气信息
**Location**: `data/skills/get_weather/SKILL.md`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: weather, api, utility

### github
**Description**: GitHub operations via `gh` CLI: issues, PRs, CI runs, code review, API queries. Use when: (1) checking PR status or CI, (2) creating/commenting on issues, (3) listing/filtering PRs or issues, (4) viewing run logs. NOT for: complex web UI interactions requiring manual browser flows (use browser tooling when available), bulk operations across many repos (script with gh api), or when gh auth is not configured.
**Location**: `data/skills/github/SKILL.md`
**Version**: 1.0.0

### skill-creator
**Description**: Create or update skills. Use when designing, structuring, validating, or packaging skills with scripts, references, and assets.
**Location**: `data/skills/skill-creator/SKILL.md`
**Version**: 1.0.0

