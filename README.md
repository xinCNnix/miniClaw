# miniClaw

> Lightweight, Highly Transparent AI Agent System

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16+-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Project Introduction

miniClaw is a lightweight, highly transparent AI Agent system featuring multi-mode reasoning (Normal / PERV / ToT), progressive auto-learning, and plugin-based extensibility. Unlike traditional black-box Agent systems, miniClaw maintains full visibility into Agent behavior through structured storage, traceable tool execution, and human-readable configuration files.

### Core Features

- **Three Execution Modes (User-Selected)**
  - **Normal Agent**: Default fast single-pass tool-augmented conversation
  - **PERV (Plan-Execute-Verify-Reflect)**: User-enabled Deep Planning mode for structured multi-step task execution with verification loops
  - **ToT (Tree of Thoughts)**: User-enabled Research mode for multi-branch deep reasoning with beam search and evidence synthesis

- **Progressive Auto-Learning System**
  - **Reflection Engine**: Post-execution quality assessment (micro + macro), self-correction with quality scores
  - **Pattern Learning**: Automatic extraction and reuse of successful strategies
  - **Neural Strategy**: Progressive NN policy integration with 5-stage scheduler (baseline → dominant)
  - **RL Training**: Transformer + MLP dual-head reward model with experience replay
  - **TCA (Task Complexity Analysis)**: 4-phase deployment (collection → shadow → mixed → dominant)
  - **Meta Policy**: Adaptive strategy injection with progressive stages

- **Online/Offline Distillation**
  - **Online Distill**: Real-time trajectory recording and skill distillation during execution
  - **Dream (Offline)**: Scheduled or manual offline trajectory replay, analysis, and skill synthesis
  - Trajectory store with weighted sampling (failure-heavy, low-score-heavy)

- **Dual-Storage Memory System**
  - **SQLite Database**: Structured storage for conversations, memories, and user profiles
  - **Vector Database**: ChromaDB for hybrid retrieval (BM25 + semantic, reciprocal rank fusion)
  - **Knowledge Graph**: Entity and relationship extraction with SQLite backend
  - **Wiki Engine**: Long-term knowledge accumulation and retrieval
  - **Human-Readable Files**: `MEMORY.md` and `USER.md` for manual inspection
  - LLM-powered automatic memory extraction with confidence scoring

- **Plugin-Based Skills System (23 Built-in)**
  - Follows Anthropic Agent Skills paradigm with `SKILL.md` documentation
  - **SkillPolicy Engine**: Unified compilation pipeline (Match → Gate → Compile → Guard)
  - Automatic dependency detection (Python packages + system tools)
  - Hot-pluggable — extend capabilities without code changes
  - Built-in skills: arxiv-search, chart-plotter, geometry-plotter, diagram-plotter, get_weather, github, research_report_writer, skill-creator, and more

- **Full Transparency & Observability**
  - System prompt assembled from 6 dynamically generated components
  - Execution trace recording with JSON persistence
  - Watchdog system for run monitoring and cancellation
  - Human-readable markdown files for debugging

- **Security-First Design**
  - Terminal tool sandboxed with cross-platform command blacklist
  - File reading restricted to project directory
  - API keys via environment variables, never hardcoded
  - Multi-round tool calling with context isolation

- **Multi-LLM Provider Support**
  - Qwen, OpenAI, DeepSeek, Ollama, Claude, Gemini, and custom OpenAI-compatible APIs
  - Environment variable-based switching

- **Multimodal Support**
  - Image, audio, and document file upload and processing
  - Images served via `/api/media/` (no base64 in LLM or session storage)
  - Full Markdown rendering: tables, code blocks, ASCII art with monospace font

---

## Development & Testing Platform

**Primary Development Environment: Windows 10/11**

This project is developed and tested primarily on Windows. While designed to be cross-platform compatible (Windows, Linux, macOS), some features may have been optimized or tested more extensively on Windows.

- **Windows 10/11** — Primary development and testing platform
- **Linux** — Compatible (tested on Ubuntu 20.04+)
- **macOS** — Compatible (tested on macOS 12+)

---

## Tech Stack

### Backend
- **Python 3.10+** — Core language
- **FastAPI** — High-performance web framework
- **LangChain 1.x** — Agent orchestration engine (`create_agent` API)
- **LangGraph** — Graph-based workflow (ToT, PERV, Dream)
- **LlamaIndex** — RAG hybrid retrieval engine
- **PyTorch** — Neural strategy and RL training
- **Pydantic** — Data validation

### Frontend
- **Next.js 16+** — React framework (App Router + Turbopack)
- **TypeScript** — Type safety
- **Shadcn/UI** — UI component library
- **Tailwind CSS** — Styling framework

### Storage & Deployment
- **SQLite** — Conversations, trajectories, knowledge graph
- **ChromaDB** — Vector storage (hybrid retrieval)
- **Docker** — Containerized deployment

---

## Quick Start

### One-Click Installation (Recommended)

**Windows Users:**
```bash
start.bat
```

**Linux/macOS Users:**
```bash
chmod +x start.sh
./start.sh
```

The startup scripts will:
- Verify Python and Node.js are installed
- Create virtual environments and install dependencies
- Prompt for API key configuration (first run only)
- Start backend (port 8002) and frontend (port 3000)
- Open browser automatically

Visit http://localhost:3000 to start using.

### First Run

On first run, configure your LLM API keys:
1. Choose an LLM provider (Qwen recommended, free tier available)
2. Enter your API key
3. Configuration is saved in `backend/.env`

For detailed setup instructions, see **[QUICKSTART.md](./QUICKSTART.md)**.

### Docker Deployment

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys
docker-compose up -d
```

Access:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8002
- API Docs: http://localhost:8002/docs

---

## Core Features

### 6 Core Tools

| Tool | Function | Security Features | Example |
|------|----------|-------------------|---------|
| **terminal** | Shell command execution | Sandboxed + command blacklist | `ls -la`, `git status` |
| **python_repl** | Python code interpreter | Timeout control + matplotlib Agg backend | Data analysis, computation |
| **fetch_url** | Web content fetching | HTML auto-cleaning | News, API calls |
| **read_file** | File reading | Restricted to project directory | Reading code, documentation |
| **write_file** | File writing | Path restriction + sensitive file protection | Creating, editing files |
| **search_kb** | RAG knowledge base retrieval | Hybrid search (BM25 + semantic) | Document queries, knowledge Q&A |

### 23 Built-in Skills

| Category | Skills |
|----------|--------|
| **Search & Research** | arxiv-search, arxiv-download-paper, baidu-search, agent-papers, conference-paper |
| **Visualization** | chart-plotter, geometry-plotter, diagram-plotter |
| **Research Pipeline** | deep_source_extractor, cluster_reduce_synthesis, research_report_writer |
| **Code Analysis** | scale_down_analyze_python, scale_down_fix_bug, scale_down_refactor_module, tool_restricted_analyze_python, tool_restricted_fix_bug |
| **Utilities** | get_weather, github, doc-creator, distill-persona, skill-creator, skill_validator, find-skill |

### System Prompt Composition

System Prompt is dynamically assembled from 6 components (in order):

1. **SKILLS_SNAPSHOT.md** — Dynamically generated capability list
2. **SOUL.md** — Agent core settings (personality, tone, values)
3. **IDENTITY.md** — Self-awareness (name, capability boundaries)
4. **USER.md** — User profile (preferences, common locations, terminology)
5. **AGENTS.md** — Behavioral guidelines and skill invocation protocols
6. **MEMORY.md** — Long-term memory (important information extraction)

### File-first Memory System

- **Conversation Records**: `backend/data/sessions/*.json`
- **System Prompts**: `backend/workspace/`
- **Knowledge Base**: `backend/data/knowledge_base/`
- **Vector Storage**: `backend/data/vector_store/`

---

## Project Structure

```
miniclaw/
├── backend/                        # Python backend service
│   ├── app/
│   │   ├── main.py                # FastAPI application entry
│   │   ├── config.py              # Configuration management
│   │   │
│   │   ├── core/                  # Core modules
│   │   │   ├── agent.py           # LangChain Agent wrapper (Normal mode)
│   │   │   ├── llm.py             # LLM model initialization
│   │   │   ├── rag_engine.py      # RAG hybrid retrieval engine
│   │   │   ├── embedding_manager.py # Embedding model lifecycle
│   │   │   ├── media/             # Image registry & HTTP serving
│   │   │   ├── streaming/         # SSE streaming + image embedding
│   │   │   ├── watchdog.py        # Run monitoring & cancellation
│   │   │   ├── trajectory/        # Execution trace recording
│   │   │   ├── skill_policy/      # SkillPolicy compilation pipeline
│   │   │   ├── reflection/        # Unified evaluation (micro + macro)
│   │   │   ├── meta_policy/       # TCA + Meta Policy injection
│   │   │   ├── online_distill/    # Online trajectory distillation
│   │   │   ├── tot/               # Tree of Thoughts reasoning
│   │   │   │   ├── nodes/         # Thought nodes (generate, evaluate, execute, synthesize)
│   │   │   │   ├── research/      # Research mode sub-graph
│   │   │   │   ├── router.py      # ToT orchestrator & routing
│   │   │   │   └── streaming.py   # SSE tree update streaming
│   │   │   ├── perv/              # PERV framework
│   │   │   │   ├── nodes/         # Plan, execute, verify, replan nodes
│   │   │   │   ├── orchestrator.py # PERV graph builder & runner
│   │   │   │   └── router.py      # PERV routing classifier
│   │   │   └── dream/             # Offline distillation (Dream)
│   │   │       ├── nodes/         # Trajectory store, analysis, synthesis
│   │   │       └── config.py      # Dream scheduling & config
│   │   │
│   │   ├── tools/                 # 6 core tools
│   │   ├── skills/                # Skills bootstrap & loader
│   │   ├── memory/                # Memory management
│   │   │   ├── auto_learning/     # Pattern NN, RL trainer, reflection
│   │   │   ├── kg/                # Knowledge graph store
│   │   │   ├── wiki/              # Wiki engine (long-term knowledge)
│   │   │   ├── pattern_memory/    # Learned pattern storage
│   │   │   └── engine.py          # Memory manager
│   │   ├── api/                   # API routes (16 endpoints)
│   │   └── models/                # Pydantic data models
│   │
│   ├── data/                      # Local data storage
│   │   ├── skills/                # 23 skill definitions
│   │   ├── sessions/              # Conversation records
│   │   ├── knowledge_base/        # Knowledge base files
│   │   └── vector_store/          # ChromaDB vector storage
│   │
│   ├── workspace/                 # System Prompt components
│   └── logs/                      # Runtime logs & traces
│
├── frontend/                      # Next.js frontend (v16+)
│   ├── app/                       # App Router
│   ├── components/                # React components
│   ├── hooks/                     # React Hooks
│   ├── lib/                       # Utility libraries
│   └── types/                     # TypeScript types
│
├── docs/                          # Documentation
├── QUICKSTART.md                  # Quick start guide
├── README.md                      # This file
├── start.bat                      # Windows startup script
├── start.sh                       # Linux/Mac startup script
└── docker-compose.yml             # Docker orchestration
```

---

## API Interfaces

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Chat with SSE streaming (Normal / PERV / ToT) |
| `/api/chat/cancel` | POST | Cancel running chat |
| `/api/sessions` | GET | List sessions |
| `/api/files` | GET/POST | Read/write workspace files |
| `/api/media/{id}` | GET | Serve registered media (images) |
| `/api/skills` | GET | List loaded skills |
| `/api/knowledge-base` | GET/POST | Knowledge base management |
| `/api/embedding` | POST | Embedding operations |
| `/api/dream/trigger` | POST | Trigger offline Dream session |
| `/api/memory` | GET | Memory retrieval |
| `/api/wiki` | GET | Wiki search |

Full API documentation: http://localhost:8002/docs (after starting backend)

### Chat SSE Example

```http
POST /api/chat
Content-Type: application/json

{
  "message": "Help me check the weather in Beijing",
  "session_id": "main_session",
  "context": {}
}
```

Returns SSE streaming events: `content_delta`, `tool_call`, `tool_result`, `tree_update`, `final_answer`.

---

## LLM Configuration

### Supported Providers

| Provider | Configuration | Description |
|----------|--------------|-------------|
| **Qwen** | `QWEN_API_KEY` | Alibaba Qwen, free tier available |
| **OpenAI** | `OPENAI_API_KEY` | OpenAI official API |
| **DeepSeek** | `DEEPSEEK_API_KEY` | Cost-effective |
| **Ollama** | No API Key required | Completely local |
| **Claude** | `CLAUDE_API_KEY` | Anthropic Claude |
| **Gemini** | `GEMINI_API_KEY` | Google Gemini |
| **Custom** | `CUSTOM_API_KEY` + `CUSTOM_BASE_URL` | OpenAI-compatible API |

### Configuration Example

Edit `backend/.env`:

```bash
LLM_PROVIDER=qwen
QWEN_API_KEY=sk-your-api-key
QWEN_MODEL=qwen-plus
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

## Testing

```bash
# Backend
cd backend
pytest tests/

# Frontend
cd frontend
npm test
npx playwright test
```

---

## Development Guide

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload

# Frontend
cd frontend
npm install
npm run dev
```

Code standards: [CLAUDE.md](./CLAUDE.md)

---

## Documentation

- **[QUICKSTART.md](./QUICKSTART.md)** — Quick start guide
- **[CLAUDE.md](./CLAUDE.md)** — Development standards and AI collaboration protocol
- **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** — System architecture design
- **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)** — Docker and production deployment

---

## Roadmap

### v1.0.0 (Current)

- [x] PERV framework (Plan-Execute-Verify-Reflect)
- [x] Tree of Thoughts reasoning with research mode
- [x] SkillPolicy unified skill compilation
- [x] Progressive auto-learning (reflection, pattern, neural strategy, RL)
- [x] Online/Offline distillation (Dream)
- [x] TCA & Meta Policy injection
- [x] 23 built-in skills
- [x] Multimodal support (image, audio, document upload)
- [x] Full Markdown rendering (tables, code blocks, ASCII art)
- [x] Knowledge graph memory
- [x] Wiki engine for long-term knowledge

### v0.4 (Planned)

- [ ] Multi-session management
- [ ] Skill marketplace integration
- [ ] Multi-Agent collaboration

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [LangChain](https://github.com/langchain-ai/langchain) — Agent framework
- [LangGraph](https://github.com/langchain-ai/langgraph) — Graph-based workflow
- [LlamaIndex](https://github.com/run-llama/llama_index) — RAG engine
- [Anthropic](https://www.anthropic.com) — Agent Skills paradigm
- [Shadcn/UI](https://ui.shadcn.com) — UI component library
