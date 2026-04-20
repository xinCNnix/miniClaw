---
name: agent-papers
description: "搜索和浏览 AI Agent 研究论文库 (基于 Awesome-AI-Agents-Live 数据集，8800+ 篇论文)。Use when: (1) user asks about AI agent research papers, (2) user wants to find papers on specific agent topics (memory, planning, tools, collaboration, etc.), (3) user asks about trends or state-of-the-art in AI agents, (4) user needs paper recommendations by category/difficulty/score. NOT for: general academic search outside AI agents (use arxiv-search), non-research questions."
version: 1.0.0
author: miniClaw
tags: [ai-agents, research, papers, literature-search, knowledge-base]
---

# AI Agent 论文搜索

基于 [Awesome-AI-Agents-Live](https://github.com/Saifs-AIHub/Awesome-AI-Agents-Live) 数据集的 AI Agent 研究论文搜索工具。收录 8800+ 篇论文，每篇包含 AI 生成的摘要分析、关键洞察、优缺点和评分。

## When to Use

USE this skill when:
- 用户想了解 AI Agent 相关研究论文
- 用户想按主题搜索 Agent 论文 (记忆机制、规划能力、工具使用、多 Agent 协作等)
- 用户想了解某个 Agent 子领域的最新进展
- 用户想按评分/难度筛选论文推荐
- 用户需要为某个 Agent 技术方案寻找学术参考

DON'T use this skill when:
- 非 AI Agent 领域的论文搜索 → 用 `arxiv-search`
- 一般性知识问答 → 直接回答
- 需要获取论文全文 → 用 `arxiv-download-paper`

## Categories

数据集涵盖以下分类:

| 分类 | 说明 |
|------|------|
| Profile Definition | Agent 角色定义与身份建模 |
| Memory Mechanism | 记忆机制 (短期/长期/工作记忆) |
| Planning Capability | 规划能力 (任务分解、推理链) |
| Action Execution | 动作执行 (工具调用、API 交互) |
| Agent Collaboration | 多 Agent 协作 |
| Agent Evolution | Agent 进化与自主学习 |
| Tools | Agent 工具系统 |
| Applications | 应用场景 |
| Benchmarks and Datasets | 基准测试与数据集 |
| Security | 安全性 |
| Ethics | 伦理问题 |
| Social Simulation | 社会模拟 |
| Survey | 综述论文 |

## Quick Start

### 按关键词搜索

```bash
python data/skills/agent-papers/scripts/search_papers.py search -q "multi-agent collaboration"
```

### 按分类浏览

```bash
python data/skills/agent-papers/scripts/search_papers.py search -c "Memory Mechanism" -m 5
```

### 高评分论文推荐

```bash
python data/skills/agent-papers/scripts/search_papers.py search --min-score 8 -m 10
```

## Search Parameters

| 参数 | 缩写 | 说明 | 示例 |
|------|------|------|------|
| `--query` | `-q` | 关键词 (AND 逻辑，全部匹配) | `"RAG" "retrieval"` |
| `--category` | `-c` | 按分类筛选 | `"Tools"` |
| `--label` | `-l` | 按标签筛选 (OR 逻辑) | `"CS & SE" "Research Assistant"` |
| `--min-score` | | 最低评分 (1-10) | `8` |
| `--max-score` | | 最高评分 (1-10) | `10` |
| `--difficulty` | `-d` | 难度: Beginner / Intermediate / Advanced | `Intermediate` |
| `--author` | `-a` | 作者关键词 | `"Hinton"` |
| `--sort-by` | `-s` | 排序: score / date / title / composite | `score` |
| `--asc` | | 升序 (默认降序) | |
| `--max-results` | `-m` | 返回数量 (默认 10) | `20` |
| `--offset` | | 跳过前 N 条 (翻页) | `10` |
| `--brief` | | 简要输出 (不含 insights/pros/cons) | |

## Other Commands

### 列出所有分类

```bash
python data/skills/agent-papers/scripts/search_papers.py categories
```

### 列出所有标签

```bash
python data/skills/agent-papers/scripts/search_papers.py labels
```

### 数据集统计

```bash
python data/skills/agent-papers/scripts/search_papers.py stats
```

### 更新数据

从 GitHub 下载最新的 papers.json 和 analyses.json，替换本地数据。

```bash
python data/skills/agent-papers/scripts/search_papers.py update
```

指定下载超时 (秒):

```bash
python data/skills/agent-papers/scripts/search_papers.py update --timeout 180
```

**容错机制**: 更新失败时 (网络不可用、数据损坏等)，本地数据保持不变，skill 继续正常工作。更新过程:
1. 下载到临时目录
2. 验证 JSON 格式和基本结构
3. 备份当前文件
4. 验证通过后才替换本地文件
5. 任何步骤失败都会回退，不影响已有数据

## Common Workflows

### Workflow 1: 了解某个子领域

用户想了解 Agent 记忆机制的研究现状:

```bash
python data/skills/agent-papers/scripts/search_papers.py search -c "Memory Mechanism" -s score -m 10
```

### Workflow 2: 按主题深度搜索

用户想找关于 RAG + Agent 结合的论文:

```bash
python data/skills/agent-papers/scripts/search_papers.py search -q "RAG" "retrieval augmented" -m 15
```

### Workflow 3: 入门推荐

用户刚开始学习 AI Agent，需要入门级论文:

```bash
python data/skills/agent-papers/scripts/search_papers.py search -d "Beginner" --min-score 7 -s score -m 10
```

### Workflow 4: 查找综述论文

用户想要某个方向的综述:

```bash
python data/skills/agent-papers/scripts/search_papers.py search -c "Survey" -m 5
```

### Workflow 5: 按作者搜索

```bash
python data/skills/agent-papers/scripts/search_papers.py search -a "Bommasani"
```

### Workflow 6: 翻页浏览

```bash
# 第一页
python data/skills/agent-papers/scripts/search_papers.py search -c "Tools" -m 5 --offset 0
# 第二页
python data/skills/agent-papers/scripts/search_papers.py search -c "Tools" -m 5 --offset 5
```

## Output Format

每篇论文返回以下信息:

- **title**: 论文标题
- **authors**: 作者列表
- **category**: 分类 (如 Memory Mechanism, Tools, ...)
- **labels**: 标签 (如 CS & SE, Research Assistant, ...)
- **score**: AI 评分 (1-10)
- **difficulty_level**: 难度等级
- **summary**: AI 生成的摘要分析
- **key_insights**: 关键洞察列表
- **pros**: 优点列表
- **cons**: 缺点列表
- **published_date**: 发布日期
- **arxiv_id**: arXiv ID (如有)
- **url**: 论文链接

## Notes

- 数据来源于 Awesome-AI-Agents-Live 项目，定期更新
- 论文摘要和分析为 AI 生成，可能存在不准确，建议对照原文
- 评分为 AI 生成的主观评分，仅供参考
- 如需下载论文全文，结合 `arxiv-download-paper` skill 使用
