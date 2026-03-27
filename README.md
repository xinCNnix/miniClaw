# miniClaw

> Lightweight, Highly Transparent AI Agent System

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14+-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Project Introduction

miniClaw is a lightweight, highly transparent AI Agent system that combines database-backed memory management with plugin-based extensibility. Unlike traditional black-box Agent systems, miniClaw maintains full visibility into Agent behavior through structured storage, traceable tool execution, and human-readable configuration files.

### Core Features

- **Dual-Storage Memory System**
  - **SQLite Database**: Structured storage for conversations, memories, and user profiles
  - **Vector Database**: ChromaDB for semantic retrieval and similarity search
  - **Human-Readable Files**: `MEMORY.md` and `USER.md` for manual inspection and editing
  - LLM-powered automatic memory extraction with confidence scoring
  - Memory categorization: preferences, facts, context, and patterns
  - Automatic pruning and deduplication to prevent memory bloat
  - Seamless synchronization between database and markdown files

- **Plugin-Based Skills System**
  - Follows Anthropic Agent Skills paradigm
  - Each skill is a folder containing a `SKILL.md` documentation file
  - Automatic dependency detection and installation (Python packages, system tools)
  - Hot-pluggable design - extend capabilities without code changes
  - Agent learns skills through natural language documentation

- **Full Transparency & Observability**
  - System prompt assembly from 6 dynamically generated components
  - Traceable tool invocation process
  - Auditable Agent decision-making
  - Human-readable markdown files for debugging and inspection

- **Security-First Design**
  - Terminal tool sandboxed with cross-platform command blacklist
  - File reading restricted to project directory
  - API keys encrypted and stored securely
  - Multi-round tool calling with context isolation

- **Multi-LLM Provider Support**
  - Support for Qwen, OpenAI, DeepSeek, Ollama, Claude, Gemini, and more
  - Environment variable-based switching
  - Mix local and cloud models seamlessly

- **Tree of Thoughts (ToT) Reasoning System**
  - Advanced reasoning with multiple thought branches exploration
  - Three thinking modes: Heuristic (⚡), Analytical (🔬), Exhaustive (🌌)
  - Automatic complexity detection and mode switching
  - Real-time reasoning visualization
  - Smart stopping to balance quality and speed

- **Research Mode**
  - Deep research capabilities with structured multi-stage investigation
  - Knowledge base + arXiv + web sources integration
  - Evidence synthesis and cross-reference analysis
  - Streamed research progress with stage indicators

---

## Development & Testing Platform

**Primary Development Environment: Windows 11**

This project is developed and tested primarily on Windows 11. While designed to be cross-platform compatible (Windows, Linux, macOS), some features may have been optimized or tested more extensively on Windows.

**Platform Compatibility:**
- ✅ **Windows 10/11** - Primary development and testing platform
- ✅ **Linux** - Compatible (tested on Ubuntu 20.04+)
- ✅ **macOS** - Compatible (tested on macOS 12+)

**Platform-Specific Notes:**
- Windows: Use `start.bat` for quick start
- Linux/macOS: Use `./start.sh` for quick start
- Docker: Recommended for consistent behavior across platforms

---

## Tech Stack

### Backend

- **Python 3.10+** - Core language
- **FastAPI** - High-performance web framework
- **LangChain 1.x** - Agent orchestration engine (using `create_agent` API)
- **LlamaIndex** - RAG hybrid retrieval engine
- **Pydantic** - Data validation

### Frontend

- **Next.js 14+** - React framework (App Router)
- **TypeScript** - Type safety
- **Shadcn/UI** - High-quality UI component library
- **Monaco Editor** - Code editor
- **Tailwind CSS** - Styling framework (Frosty Glass theme)

### Storage & Deployment

- **File System** - Local data storage
- **Docker** - Containerized deployment
- **SQLite** - Vector storage (Chroma)

---

## Quick Start

### 🚀 One-Click Installation (Recommended)

**Windows Users:**
```bash
# Double-click start.bat
# Or run from command line
start.bat
```

**Linux/macOS Users:**
```bash
chmod +x start.sh
./start.sh
```

**That's it!** The startup scripts will:
- ✅ Automatically check and install dependencies (Python, Node.js, conda)
- ✅ Create virtual environments if needed
- ✅ Install all required packages
- ✅ Start backend (port 8002) and frontend (port 3000)
- ✅ Open browser automatically

Visit http://localhost:3000 to start using.

### 📋 Prerequisites

The startup scripts require:
- **Windows:** Command Prompt or PowerShell
- **Linux/macOS:** Bash shell
- **Git** (for cloning the repository)
- **Internet connection** (for downloading dependencies)

### 🔑 First Run

On the first run, you'll need to configure your LLM API keys. The script will prompt you to:
1. Choose an LLM provider (Qwen recommended, free tier available)
2. Enter your API key
3. The configuration will be saved automatically

For manual configuration, see **[QUICKSTART.md](./QUICKSTART.md)**.

### Docker Deployment

```bash
# Clone and start with Docker
git clone <repository-url>
cd miniclaw
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys

docker-compose up -d
```

Access:
- Frontend: http://localhost:3000
- Backend: http://localhost:8002
- API Docs: http://localhost:8002/docs

---

## Core Features

### 5 Core Tools

miniClaw includes 6 carefully designed core tools covering the most common AI Agent scenarios:

| Tool | Function | Security Features | Example |
|------|----------|-------------------|---------|
| **terminal** | Shell command execution | Sandboxed + command blacklist | `ls -la`, `git status` |
| **python_repl** | Python code interpreter | Timeout control + 3 execution modes | Data analysis, computation |
| **fetch_url** | Web scraping | HTML auto-cleaning | News fetching, API calls |
| **read_file** | File reading | Restricted to project directory | Reading code, documentation |
| **write_file** | File writing | Sensitive file protection | Writing code, generating reports |
| **search_kb** | RAG knowledge base retrieval | Hybrid search (semantic + keyword) | Document queries, knowledge Q&A |

> 💡 All tools can be automatically invoked by Agent through instructions in System Prompt.

### Agent Skills System

Adopts **Instruction-following** paradigm, allowing Agent to learn new capabilities by reading natural language documentation:

**Skill Structure:**
```
skill-name/
├── SKILL.md          # Skill documentation (YAML frontmatter + Markdown)
├── scripts/          # Optional: executable scripts
├── references/       # Optional: reference documentation
└── assets/           # Optional: resource files
```

**Built-in Skills:**

- **get_weather** - Weather query (using wttr.in)
- **arxiv-search** - Academic paper search (arXiv API)
- **github** - GitHub operations (gh CLI)
- **find-skill** - Find and install new Skills
- **skill-creator** - Create custom Skills
- **skill_validator** - Validate Skills integrity

**Creating Custom Skills:**

Simply create a folder and `SKILL.md` file:

```markdown
---
name: my-skill
description: Description of this skill's functionality
dependencies:
  python:
    - "requests>=2.31.0"
---

# Skill Name

## Usage Steps
1. First step
2. Second step

## Examples
Provide usage examples
```

Agent will automatically load and learn how to use this skill.

### System Prompt Composition

System Prompt is dynamically assembled from 6 components (in order):

1. **SKILLS_SNAPSHOT.md** - Dynamically generated capability list
2. **SOUL.md** - Agent core settings (personality, tone, values)
3. **IDENTITY.md** - Self-awareness (name, capability boundaries)
4. **USER.md** - User profile (preferences, common locations, terminology)
5. **AGENTS.md** - Behavioral guidelines & skill invocation protocols
6. **MEMORY.md** - Long-term memory (important information extraction)

All components can be customized by editing corresponding files.

### File-first Memory System

- **Conversation Records**: `backend/data/sessions/*.json`
- **System Prompts**: `backend/workspace/`
- **Knowledge Base**: `backend/data/knowledge_base/`
- **Vector Storage**: `backend/data/vector_store/`

---

## Project Structure

```
miniclaw/
├── backend/                      # Python backend service
│   ├── app/
│   │   ├── main.py              # FastAPI application entry
│   │   ├── config.py            # Configuration management
│   │   │
│   │   ├── core/                # Core modules
│   │   │   ├── agent.py         # LangChain Agent wrapper
│   │   │   ├── agent_components/ # Modular agent components (v0.2.0)
│   │   │   ├── llm.py           # LLM model initialization
│   │   │   ├── rag_engine.py    # RAG retrieval engine
│   │   │   ├── obfuscation.py   # API key obfuscation
│   │   │   ├── container.py     # Dependency injection container (v0.2.0)
│   │   │   ├── interfaces.py    # Protocol interfaces (v0.2.0)
│   │   │   ├── exceptions.py    # Structured exceptions (v0.2.0)
│   │   │   ├── callback_handler.py  # Trajectory callbacks (v0.2.0)
│   │   │   ├── streaming/       # Event-driven streaming (v0.2.0)
│   │   │   ├── reflection/      # Unified evaluation framework (v0.2.0)
│   │   │   └── tot/             # Tree of Thoughts system
│   │   │       ├── nodes/       # ToT node implementations
│   │   │       ├── cache.py     # Tool result cache
│   │   │       └── ...          # state, router, graph_builder
│   │   │
│   │   ├── tools/               # 6 core tools
│   │   │   ├── terminal.py      # Shell command execution
│   │   │   ├── python_repl.py   # Python code interpreter
│   │   │   ├── fetch_url.py     # Web scraping
│   │   │   ├── read_file.py     # File reading
│   │   │   ├── write_file.py    # File writing
│   │   │   └── search_kb.py     # Knowledge base search
│   │   │
│   │   ├── skills/              # Skills system
│   │   │   ├── bootstrap.py     # SKILLS_SNAPSHOT generation
│   │   │   ├── loader.py        # Skill loader
│   │   │   └── dependencies.py  # Dependency management
│   │   │
│   │   ├── memory/              # Conversation memory management
│   │   │   ├── session.py       # Session management
│   │   │   ├── prompts.py       # System Prompt components
│   │   │   ├── auto_learning/   # Pattern learning system (v0.2.0)
│   │   │   └── models.py        # Memory Pydantic models
│   │   │
│   │   ├── api/                 # API routes
│   │   │   ├── chat.py          # Chat interface (SSE streaming)
│   │   │   ├── config.py        # Configuration interface
│   │   │   └── files.py         # File management interface
│   │   │
│   │   └── models/              # Pydantic data models
│   │       ├── sessions.py      # Session models
│   │       └── messages.py      # Message models
│   │
│   ├── data/                    # Local data storage
│   │   ├── skills/              # Skills definitions
│   │   ├── sessions/            # Conversation records
│   │   ├── knowledge_base/      # Knowledge base files
│   │   ├── vector_store/        # Vector storage
│   │   └── credentials.encrypted # Encrypted API keys
│   │
│   ├── workspace/               # System Prompt components
│   │   ├── SKILLS_SNAPSHOT.md   # Dynamically generated
│   │   ├── SOUL.md
│   │   ├── IDENTITY.md
│   │   ├── USER.md
│   │   ├── AGENTS.md
│   │   └── MEMORY.md
│   │
│   ├── tests/                   # Backend tests
│   └── requirements.txt         # Python dependencies
│
├── frontend/                    # Next.js frontend
│   ├── app/                     # App Router
│   │   ├── chat/                # Chat page
│   │   └── layout.tsx           # Root layout
│   │
│   ├── components/              # React components
│   │   ├── ui/                  # Shadcn/UI components
│   │   ├── chat/                # Chat components
│   │   ├── common/              # Shared components (v0.2.0)
│   │   └── editor/              # Code editor
│   │
│   ├── lib/                     # Utility libraries
│   │   └── api.ts               # API client
│   │
│   ├── hooks/                   # React Hooks
│   │   ├── useChat.ts           # Chat Hook
│   │   ├── useToast.tsx         # Toast notifications (v0.2.0)
│   │   └── useSSE.ts            # SSE event handling
│   │
│   └── types/                   # TypeScript types
│       └── chat.ts              # Chat type definitions
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md          # Architecture documentation
│   ├── API.md                   # API documentation
│   └── DEPLOYMENT.md            # Deployment guide
│
├── .env.example                 # Environment variable template
├── QUICKSTART.md                # Quick start guide
├── README.md                    # This file
├── DEVELOPMENT_PLAN.md          # Development plan
├── start.bat                    # Windows startup script
├── start.sh                     # Linux/Mac startup script
└── docker-compose.yml           # Docker orchestration
```

---

## API Interfaces

### Core Chat Interface

```http
POST /api/chat
Content-Type: application/json

{
  "message": "Help me check the weather in Beijing",
  "session_id": "main_session",
  "stream": true
}
```

Returns SSE streaming data:

```
event: message
data: {"content": "Checking weather..."}

event: tool_call
data: {"tool": "terminal", "input": "curl wttr.in/Beijing"}

event: message
data: {"content": "Beijing current weather: Sunny, 15°C"}
```

### File Management Interface

```http
# Read file
GET /api/files?path=workspace/SOUL.md

# Write file
POST /api/files
Content-Type: application/json

{
  "path": "workspace/SOUL.md",
  "content": "# New content\n..."
}
```

For complete API documentation, visit: http://localhost:8002/docs (after starting backend)

---

## LLM Configuration

### Supported LLM Providers

miniClaw supports multiple LLM providers, switchable via `LLM_PROVIDER` environment variable:

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
# Select provider
LLM_PROVIDER=qwen  # or openai, deepseek, ollama, claude, gemini

# Qwen configuration
QWEN_API_KEY=sk-your-api-key
QWEN_MODEL=qwen-plus

# OpenAI configuration
# OPENAI_API_KEY=sk-your-api-key
# OPENAI_MODEL=gpt-4o-mini

# Ollama configuration (local)
# OLLAMA_BASE_URL=http://localhost:11434/v1
# OLLAMA_MODEL=qwen2.5
```

### Embedding Model Configuration

Knowledge base functionality requires Embedding model for semantic retrieval. System supports three configuration methods:

#### Method 1: Use LLM Provider's API Embedding (Recommended)

No model download required, direct API calls:

| LLM Provider | Embedding Model | Configuration |
|--------------|----------------|--------------|
| OpenAI | `text-embedding-3-large` | Auto-used |
| Qwen | `text-embedding-v3` | Auto-used |
| DeepSeek | `deepseek-embedding` | Auto-used |

#### Method 2: Use Local HuggingFace Model

When LLM doesn't support embedding, system automatically downloads local model:

- **Default Model**: `RamManavalan/Qwen3-VL-Embedding-8B-FP8`
- **Size**: ~8GB
- **Download**: HF-Mirror acceleration for China users

#### Method 3: Manually Specify Model

Edit `backend/app/core/rag_engine.py`:

```python
model_name = "BAAI/bge-large-zh-v1.5"  # Chinese embedding model
```

---

## Testing

**Testing Platform:** All tests are developed and validated on Windows 11. Tests should pass on Linux and macOS as well, but Windows is the primary testing environment.

### Backend Testing

```bash
cd backend

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_tools.py

# View coverage
pytest --cov=app tests/
```

### Frontend Testing

```bash
cd frontend

# Unit tests
npm test

# E2E tests
npx playwright test

# View E2E test report
npx playwright show-report
```

---

## Development Guide

### Backend Development

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start development server (hot reload)
uvicorn app.main:app --port 8002 --reload
```

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Build production version
npm run build
```

### Code Standards

Please refer to [CLAUDE.md](./CLAUDE.md) for complete development standards:

- **Python**: Follow PEP8, use Type Hints
- **TypeScript**: Strict mode, no `any`
- **LangChain**: Must use `create_agent` API, legacy `AgentExecutor` prohibited

---

## Documentation

- **[QUICKSTART.md](./QUICKSTART.md)** - 5-minute quick start guide
- **[CLAUDE.md](./CLAUDE.md)** - Development standards and AI collaboration protocol
- **[DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md)** - Complete development plan
- **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** - System architecture design
- **[docs/API.md](./docs/API.md)** - API interface documentation
- **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)** - Docker and production deployment

---

## Security Considerations

⚠️ **Before deploying to production, please note:**

1. **API Key Security**
   - Don't hard-code API keys in code
   - Use environment variables or key management services
   - Rotate API keys regularly

2. **File Access Restrictions**
   - Terminal tool configured with command blacklist
   - read_file tool restricted to project directory
   - Container isolation recommended for production

3. **Network Security**
   - Configure CORS whitelist
   - Enable HTTPS
   - Rate limit API access

4. **Log Auditing**
   - Log all tool invocations
   - Regularly audit System Prompt changes
   - Monitor anomalous behavior

---

## FAQ

### Q: How to add custom Skills?

A: Create a new folder under `backend/data/skills/`, add `SKILL.md` file. Agent will load automatically.

Example:
```bash
mkdir backend/data/skills/my-skill
cat > backend/data/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: My custom skill
---

# Skill Description

Detailed description of how to use this skill.
EOF
```

### Q: How to modify Agent personality?

A: Edit `backend/workspace/SOUL.md` file to define Agent's core settings.

### Q: Where are conversation histories saved?

A: Saved in `backend/data/sessions/*.json` files, can be viewed or edited directly.

### Q: How to disable certain tools?

A: Edit `backend/app/core/tools.py`, comment out unwanted tool registrations.

### Q: Knowledge base slow on first use?

A: First use requires downloading Embedding model (~8GB). Wait for download to complete or use LLM provider's Embedding API.

---

## Contributing

Contributions are welcome! Please follow this process:

1. Fork this project
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Follow code standards in [CLAUDE.md](./CLAUDE.md)
4. Commit changes (`git commit -m 'Add some AmazingFeature'`)
5. Push to branch (`git push origin feature/AmazingFeature`)
6. Open Pull Request

### Contribution Areas

- New Skills (tool integrations, domain knowledge)
- Core tool optimization
- UI/UX improvements
- Documentation enhancements
- Bug fixes

---

## Roadmap

### v0.3 (Planned)

- [ ] Multi-session management
- [ ] Skill marketplace integration
- [ ] WebRTC voice chat
- [ ] Multimodal support (images, files)
- [ ] Production deployment optimization

### v0.4 (Future)

- [ ] Multi-Agent collaboration
- [ ] Knowledge graph memory
- [ ] Plugin system
- [ ] Mobile support

---

## License

This project is licensed under the **MIT License** - see [LICENSE](LICENSE) file for details

---

## Acknowledgments

- [OpenClaw](https://github.com/openclaw) - Prototype project
- [LangChain](https://github.com/langchain-ai/langchain) - Powerful Agent framework
- [LlamaIndex](https://github.com/run-llama/llama_index) - Excellent RAG engine
- [Anthropic](https://www.anthropic.com) - Agent Skills paradigm
- [Shadcn/UI](https://ui.shadcn.com) - Beautiful UI component library

---

## Contact

- **Issues**: Submit issues on GitHub
- **Discussions**: Welcome discussions and feedback
- **Email**: [Maintainer email]

---

**Happy Coding! 🚀**

Making AI Agent capabilities transparent and controllable, enabling everyone to create their own intelligent assistants.
