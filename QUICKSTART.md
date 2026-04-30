# miniClaw Quick Start Guide

> One-Click Setup for the AI Agent System

## Prerequisites

### Required Software

**Python 3.10+**
```bash
python --version
# Windows: https://www.python.org/downloads/
# Linux: sudo apt install python3.10
# macOS: brew install python@3.10
```

**Node.js 18+**
```bash
node --version
# Windows: https://nodejs.org/
# Linux: sudo apt install nodejs npm
# macOS: brew install node
```

### Optional: System Dependencies

Some skills require system-level tools:

```bash
# Graphviz (diagram-plotter)
winget install Graphviz.Graphviz

# GitHub CLI (github skill)
winget install GitHub.cli

# LaTeX (geometry-plotter advanced rendering)
winget install MiKTeX.MiKTeX
```

---

## One-Click Setup (Recommended)

### Windows Users

1. **Clone or download the project**
   ```bash
   cd miniclaw
   ```

2. **Double-click `start.bat`** or run from command line
   - Verifies Python and Node.js are installed
   - Creates virtual environment and installs dependencies
   - Prompts for API key configuration (first run only)
   - Starts backend (port 8002) and frontend (port 3000)
   - Browser opens to http://localhost:3000

### Linux/macOS Users

```bash
chmod +x start.sh
./start.sh
```

---

## First Run Configuration

On first run, configure your LLM API keys:

1. **Choose an LLM provider**
   - **Qwen** — Recommended, has free tier
   - **OpenAI GPT** — Production quality
   - **DeepSeek** — Cost-effective
   - **Ollama** — Completely local, free

2. **Enter your API key**
   - **Qwen**: https://dashscope.aliyun.com/ (Free tier available)
   - **OpenAI**: https://platform.openai.com/api-keys
   - **DeepSeek**: https://platform.deepseek.com/
   - **Ollama**: https://ollama.com/ (No API key needed)

3. Configuration is saved in `backend/.env`

---

## Start Using

1. Browser opens to http://localhost:3000
2. Type your message in the chat box
3. Examples:
   - "帮我分析一下当前目录的文件结构"
   - "Query the weather in Beijing"
   - "Search arxiv for latest papers on LLM"

### Research Mode (Tree of Thoughts)

For complex queries requiring deep analysis:

1. Click the **Research Mode** toggle in the chat interface
2. Select a thinking mode:
   - **Heuristic** (Quick): 2-depth x 3-branching
   - **Analytical** (Balanced): 4-depth x 4-branching
   - **Exhaustive** (Deep): 7-depth x 6-branching
3. Send your query

The system explores multiple reasoning branches, evaluates each, and synthesizes the best results into a comprehensive answer with evidence and cross-references.

### Deep Planning Mode (PERV)

For structured multi-step tasks:

1. Enable **Deep Planning** toggle in the chat interface
2. The system will create a step-by-step execution plan
3. Each step is executed, verified, and replanned if needed

---

## Manual Setup (If Scripts Fail)

**Terminal 1 — Backend:**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn app.main:app --port 8002 --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Access:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8002

---

## Features Overview

### 6 Core Tools

| Tool | Function | Example |
|------|----------|---------|
| **terminal** | Execute Shell commands | "List files in current directory" |
| **python_repl** | Run Python code | "Calculate Fibonacci sequence" |
| **fetch_url** | Fetch web content | "Get GitHub trending page" |
| **read_file** | Read local files | "Read README.md" |
| **write_file** | Write files | "Create a new file" |
| **search_kb** | Knowledge base search | "Search for relevant info" |

### 23 Built-in Skills

Search & Research: arxiv-search, arxiv-download-paper, baidu-search, agent-papers, conference-paper

Visualization: chart-plotter, geometry-plotter, diagram-plotter

Research Pipeline: deep_source_extractor, cluster_reduce_synthesis, research_report_writer

Code Analysis: scale_down_analyze_python, scale_down_fix_bug, scale_down_refactor_module, tool_restricted_analyze_python, tool_restricted_fix_bug

Utilities: get_weather, github, doc-creator, distill-persona, skill-creator, skill_validator, find-skill

---

## FAQ

### Q: Installation takes too long

First run downloads dependencies (~500MB backend, ~200MB frontend). Future starts are instant.

### Q: "command not found: python"

Install Python 3.10+: https://www.python.org/downloads/ (Check "Add to PATH" on Windows)

### Q: Port already in use

```bash
# Windows
netstat -ano | findstr :8002
taskkill /PID <PID> /F

# Linux/macOS
lsof -ti:8002 | xargs kill -9
```

### Q: How to switch LLM provider?

Edit `backend/.env`:
```bash
LLM_PROVIDER=qwen  # or openai, deepseek, ollama, claude, gemini
QWEN_API_KEY=sk-your-key
```

Then restart the services.

### Q: Knowledge base slow on first use?

First use requires downloading Embedding model (~8GB). Wait for download or use your LLM provider's Embedding API.

---

## Next Steps

- Full documentation: [README.md](./README.md)
- Architecture: [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)
- Deployment: [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)
- Development standards: [CLAUDE.md](./CLAUDE.md)
