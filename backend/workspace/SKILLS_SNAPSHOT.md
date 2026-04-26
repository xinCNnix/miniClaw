# Available Skills
This document lists all available skills that the Agent can use.
**Total Skills**: 22
---

### agent-papers
**Description**: 搜索和浏览 AI Agent 研究论文库 (基于 Awesome-AI-Agents-Live 数据集，8800+ 篇论文)。Use when: (1) user asks about AI agent research papers, (2) user wants to find papers on specific agent topics (memory, planning, tools, collaboration, etc.), (3) user asks about trends or state-of-the-art in AI agents, (4) user needs paper recommendations by category/difficulty/score. NOT for: general academic search outside AI agents (use arxiv-search), non-research questions.
**Location**: `data/skills/agent-papers`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: ai-agents, research, papers, literature-search, knowledge-base

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

### baidu-search
**Description**: Search the web using Baidu AI Search Engine (BDSE). Use for live information, documentation, or research topics.
**Location**: `data/skills/baidu-search`
**Version**: 1.0.0

### chart-plotter
**Description**: Create, customize, and export publication-ready charts (line, bar, scatter, pie, histogram) from CSV/Excel data with full Chinese font support, responsive layout, and Windows-compatible rendering. Use when user asks to: (1) 画图表、绘图、数据可视化; (2) 折线图、柱状图、散点图、饼图、直方图; (3) CSV/Excel 数据绘制; (4) mention chart type ('line chart', 'bar plot'); (5) 中文标签、标题、字体.
**Location**: `data/skills/chart-plotter`
**Version**: 1.0.0

### cluster_reduce_synthesis
**Description**: 将多个源的结构化提取结果，进行聚类合并压缩。
输出 cluster summaries + contradictions + consensus。

**Location**: `data/skills/cluster_reduce_synthesis`
**Version**: 1.0

### conference-paper
**Description**: Search and retrieve papers from top AI conferences (ICLR, NeurIPS, ICML, IJCAI, CVPR, ICCV, ACL). Use when: (1) user asks about papers from specific AI conferences, (2) user wants to find papers presented at ICLR/NeurIPS/ICML etc., (3) user needs to browse conference proceedings by year/topic, (4) user wants to download PDFs of conference papers. NOT for: general arXiv search (use arxiv-search), AI Agent specific papers (use agent-papers).
**Location**: `data/skills/conference-paper`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: conference, academic, research, papers, AI, ICLR, NeurIPS, ICML, CVPR, ACL

### deep_source_extractor
**Description**: 对单个来源全文进行深层结构化信息提取，输出详细结构化 JSON。
适用于论文、网页、PDF 转文本等长文档的研究信息提取。

**Location**: `data/skills/deep_source_extractor`
**Version**: 1.0

### diagram-plotter
**Description**: Create architecture diagrams, flowcharts, mind maps, UML diagrams, and network topology graphs from text descriptions. Use when user asks to: (1) 画架构图、画流程图、绘制拓扑图; (2) 思维导图、脑图; (3) UML类图、时序图; (4) 系统架构、微服务架构、网络拓扑; (5) specify nodes and edges relationships.
**Location**: `data/skills/diagram-plotter`
**Version**: 1.0.0

### distill-persona
**Description**: 从人物样本中蒸馏可复用的 Agent 技能 profile。当需要：(1) 从一组问答样本提取某人的决策风格和表达习惯， (2) 生成可执行的 skill profile (profile.json + skill.md + skill.py)，(3) 自动评判和修复 profile 质量， (4) 批量蒸馏多个 persona 为独立 skill 时使用。输入为人物名称 + 样本列表，输出为完整 skill 包。

**Location**: `data/skills/distill-persona`
**Version**: 1.0.0

### doc-creator
**Description**: Create professional DOCX/XLSX/PPTX documents with embedded images, tables, and formatted text. Use when user asks to: (1) 'create a Word/Excel/PowerPoint document'; (2) 'generate a report with charts'; (3) 'export data to Office format'; (4) 'make a presentation with slides'; (5) insert charts/images into documents.
**Location**: `data/skills/doc-creator`
**Version**: 1.0.0

### find-skill
**Description**: Search and install skills from external sources like GitHub, clawhub, and other skill repositories. Use when user asks to find, download, or install new skills from the internet.
**Location**: `data/skills/find-skill`
**Version**: 1.0.0
**Author**: miniClaw
**Tags**: skills, search, install, github, repository

### geometry-plotter
**Description**: 绘制2D/3D数学图形：函数图像、几何证明示意图、3D曲面等。输出 SVG 矢量图。Use when user asks to: (1) 画图、绘图、绘制图形; (2) 函数图像 (sin, cos, relu, sigmoid 等); (3) 几何证明示意图; (4) 数学定理可视化; (5) 坐标系、函数曲线、3D曲面.
**Location**: `data/skills/geometry-plotter`
**Version**: 1.0.0

### get_weather
**Description**: Get current weather and forecasts via wttr.in. Use when: user asks about weather, temperature, or forecasts for any location. Returns current conditions, temperature, humidity, wind, and forecasts. No API key needed.
**Location**: `data/skills/get_weather`
**Version**: 1.0.0

### github
**Description**: GitHub operations via `gh` CLI: issues, PRs, CI runs, code review, API queries. Use when: (1) checking PR status or CI, (2) creating/commenting on issues, (3) listing/filtering PRs or issues, (4) viewing run logs. NOT for: complex web UI interactions requiring manual browser flows (use browser tooling when available), bulk operations across many repos (script with gh api), or when gh auth is not configured.
**Location**: `data/skills/github`
**Version**: 1.0.0

### research_report_writer
**Description**: 基于综合后的 reduced_json 撰写研究报告，
强制使用引用标注 [S1][S2]。

**Location**: `data/skills/research_report_writer`
**Version**: 1.0

### scale_down_fix_bug
**Description**: No description
**Location**: `data/skills/scale_down_fix_bug`
**Version**: 1.0.0

### scale_down_refactor_module
**Description**: No description
**Location**: `data/skills/scale_down_refactor_module`
**Version**: 1.0.0

### skill-creator
**Description**: Create or update skills. Use when designing, structuring, validating, or packaging skills with scripts, references, and assets.
**Location**: `data/skills/skill-creator`
**Version**: 1.0.0

### skill_validator
**Description**: Validate skill files before use. Use when: loading new skills, verifying skill integrity, checking skill metadata. Checks for: required fields, valid syntax, security issues.
**Location**: `data/skills/skill_validator`
**Version**: 1.0.0

### tool_restricted_analyze_python
**Description**: No description
**Location**: `data/skills/tool_restricted_analyze_python`
**Version**: 1.0.0

### tool_restricted_fix_bug
**Description**: No description
**Location**: `data/skills/tool_restricted_fix_bug`
**Version**: 1.0.0

