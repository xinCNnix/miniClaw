# miniClaw Quick Start Guide

> Lightweight, highly transparent AI Agent System - Get started in 5 minutes

## Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: 18 or higher
- **npm**: Usually comes with Node.js

---

## Step 1: Get API Key

miniClaw requires an LLM service configuration to run. Choose one of the following options:

### Option A: Qwen (Free Tier Available)

1. Visit [Alibaba Cloud Dashscope Platform](https://dashscope.aliyun.com/)
2. Register/Login
3. Create API Key
4. Save API Key (format: `sk-xxxxxxxx`)

### Option B: OpenAI GPT

1. Visit [OpenAI Platform](https://platform.openai.com/)
2. Register/Login
3. Create API Key
4. Ensure account has balance

### Option C: Ollama (Completely Local, Free)

1. Download and install from [Ollama Website](https://ollama.com/)
2. After installation, run: `ollama pull qwen2.5`
3. No API Key required

---

## Step 2: Configure Environment Variables

```bash
# Copy configuration template
cp backend/.env.example backend/.env
```

Edit `backend/.env` file and configure based on your chosen LLM provider:

### Qwen Configuration

```bash
LLM_PROVIDER=qwen
QWEN_API_KEY=sk-your-actual-qwen-api-key-here
QWEN_MODEL=qwen-plus
```

### OpenAI Configuration

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-actual-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

### Ollama Configuration

```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5
```

> 💡 **Tip**: Ensure no spaces or quotes in API Key

---

## Step 3: Start the System

### Windows Users (Easiest)

Double-click `start.bat`, the script will:
- Automatically check and install dependencies
- Start backend service (port 8002)
- Start frontend service (port 3000)
- Open browser automatically

### Linux/macOS Users

```bash
chmod +x start.sh
./start.sh
```

### Manual Start (For Debugging)

**Terminal 1 - Start Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload
```

**Terminal 2 - Start Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## Step 4: Start Using

1. Open browser at: **http://localhost:3000**
2. Type a message in the chat box, such as:
   - "Help me analyze the current directory structure"
   - "Query the weather in Beijing"
   - "Search arxiv for latest papers on LLM"
3. Wait for Agent response

---

## Core Features Preview

### 5 Core Tools

| Tool | Function | Example Usage |
|------|----------|---------------|
| **terminal** | Execute Shell commands | "List files in current directory" |
| **python_repl** | Run Python code | "Calculate Fibonacci sequence with Python" |
| **fetch_url** | Fetch web content | "Get GitHub trending page" |
| **read_file** | Read local files | "Read README.md content" |
| **search_kb** | Knowledge base search | "Search knowledge base for relevant content" |

### Built-in Skills

- **get_weather** - Weather query
- **arxiv-search** - Academic paper search
- **github** - GitHub operations (requires gh CLI)
- **find-skill** - Find and install new Skills
- **skill-creator** - Create custom Skills
- **skill_validator** - Validate Skills integrity

---

## FAQ

### Q1: Startup shows "LLM provider not configured"

**Cause**: `.env` file not configured or misconfigured

**Solutions**:
1. Check if `backend/.env` exists
2. Confirm `LLM_PROVIDER` is set
3. Verify API Key is correct (no extra spaces)
4. Ensure selected LLM account has balance

### Q2: Backend fails to start, missing dependencies

**Solution**:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Q3: Frontend cannot connect to backend

**Checklist**:
1. Is backend running normally (visit http://localhost:8002/docs)
2. Is frontend API address correct
3. Is firewall blocking ports

### Q4: Agent response is slow

**Optimization Suggestions**:
- Use local Ollama model (fastest, but requires better hardware)
- Switch to faster models
- Reduce conversation history length

### Q5: Knowledge base feature is slow on first use

**Cause**: First use requires downloading Embedding model (~8GB)

**Solutions**:
- Wait for download to complete (HF-Mirror acceleration for China users)
- Or use LLM provider's Embedding API (no download required)

---

## Next Steps

- 📖 Read full documentation: [README.md](./README.md)
- 🏗️ Learn architecture: [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)
- 🔌 View API docs: [docs/API.md](./docs/API.md)
- 🚀 Learn deployment: [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)

---

## Get Help

- **Issues**: Submit issues on GitHub
- **Documentation**: Check `docs/` directory
- **Examples**: See Skill examples in `backend/data/skills/`

---

**Happy Using! 🎉**
