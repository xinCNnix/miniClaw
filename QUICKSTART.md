# miniClaw Quick Start Guide

> Lightweight, highly transparent AI Agent System - One-Click Setup 🚀

## 📋 Prerequisites

### Required Software

**Before you begin**, ensure you have the following installed:

#### 1. Python 3.10 or higher
```bash
# Check your Python version
python --version

# If not installed or version < 3.10:
# Windows: Download from https://www.python.org/downloads/
# Linux: sudo apt install python3.10
# macOS: brew install python@3.10
```

#### 2. Node.js 18 or higher
```bash
# Check your Node.js version
node --version

# If not installed:
# Windows: Download from https://nodejs.org/
# Linux: sudo apt install nodejs npm
# macOS: brew install node
```

#### 3. Git (for cloning the repository)
```bash
# Check if Git is installed
git --version

# If not installed:
# Windows: https://git-scm.com/download/win
# Linux: sudo apt install git
# macOS: xcode-select --install
```

**Note**: The startup scripts will verify these tools and guide you if any are missing.

---

## 🚀 Super Easy Setup (Recommended)

### Windows Users

1. **Clone or download the project**
   ```bash
   git clone https://github.com/yourusername/miniclaw.git
   cd miniclaw
   ```

2. **Double-click `start.bat`**
   - That's it! The script will:
     - Verify Python and Node.js are installed
     - Create Python virtual environment
     - Install all dependencies automatically
     - Prompt for API key configuration (first run only)
     - Start both backend and frontend services
   - Browser will open automatically to http://localhost:3000

### Linux/macOS Users

1. **Clone the project**
   ```bash
   git clone https://github.com/yourusername/miniclaw.git
   cd miniclaw
   ```

2. **Run the startup script**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

3. **Done!** The script will handle everything automatically

## ✨ What the Startup Script Does

The `start.bat` (Windows) and `start.sh` (Linux/Mac) scripts automatically:

- ✅ Check for required tools (Python, Node.js, conda)
- ✅ Install missing dependencies automatically
- ✅ Set up virtual environments
- ✅ Install all Python and Node.js packages
- ✅ Prompt you to configure API keys (first run only)
- ✅ Start backend service (port 8002)
- ✅ Start frontend service (port 3000)
- ✅ Open your browser to http://localhost:3000

**No manual installation required!**

## 🔑 First Run Configuration

On first run, the script will ask you to:

1. **Choose an LLM provider**
   - **Qwen (通义千问)** - Recommended, has free tier
   - **OpenAI GPT** - Production quality
   - **DeepSeek** - Cost-effective
   - **Ollama** - Completely local, free
   - **Custom OpenRouter-compatible** - Use any OpenRouter model

2. **Enter your API key**
   - Get your key from the provider's website (see links below)
   - Paste it when prompted
   - Configuration is saved automatically in `backend/.env`

**API Key Sources:**
- **Qwen**: https://dashscope.aliyun.com/ (Free tier available)
- **OpenAI**: https://platform.openai.com/api-keys
- **DeepSeek**: https://platform.deepseek.com/
- **Ollama**: https://ollama.com/ (No API key needed, just install Ollama)

**That's it!** You're ready to use miniClaw.

## 🎯 Start Using

1. Browser opens to http://localhost:3000
2. Type your message in the chat box
3. Examples:
   - "帮我分析一下当前目录的文件结构"
   - "Query the weather in Beijing"
   - "Search arxiv for latest papers on LLM"
4. Wait for the Agent response

### 💡 Advanced Features

#### Research Mode (Tree of Thoughts)

For complex queries requiring deep analysis, enable **Research Mode**:

**How to Use:**

1. **Click the Research Mode toggle** in the chat interface
2. **Select a thinking mode**:
   - ⚡ **Heuristic** (Quick): 2-depth × 3-branching, best for time-sensitive queries
   - 🔬 **Analytical** (Balanced): 4-depth × 4-branching, for complex problems
   - 🌌 **Exhaustive** (Deep): 7-depth × 6-branching, for thorough research

3. **Optionally adjust branching factor** (number of thought branches per level)

4. **Send your query**

**Example Research Queries:**
```
"深度研究量子计算的最新进展及其在密码学中的应用"
"Deep research on GPT-4 technical architecture and training methods"
"Compare different approaches to memory management in operating systems"
```

**What Happens in Research Mode:**
- System explores multiple reasoning branches
- Each branch is evaluated for relevance, novelty, and feasibility
- Best branches are expanded further
- Results from all branches are synthesized
- Final answer includes evidence and cross-references

**Visual Feedback:**
- Real-time thought tree visualization
- Research stage indicators (gathering → analysis → synthesis)
- Evaluation scores for each thought
- Tool execution tracking

**Note:** Research mode takes longer but produces higher-quality, well-researched answers.

## 🔧 Advanced Setup (Optional)

If you prefer manual setup or need troubleshooting, see below.

### Manual API Key Configuration

Edit `backend/.env` file manually:

```bash
# Copy the example file
cp backend/.env.example backend/.env

# Edit the file
# Windows: notepad backend/.env
# Linux/macOS: nano backend/.env
```

Choose your provider:

**Qwen (Recommended - Free Tier):**
```bash
LLM_PROVIDER=qwen
QWEN_API_KEY=sk-your-qwen-api-key
QWEN_MODEL=qwen-plus
```

**OpenAI:**
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL=gpt-4o-mini
```

**Ollama (Local, Free):**
```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5
```

### Manual Startup (If Scripts Fail)

**Prerequisites:**
- Python 3.10+ installed and in PATH
- Node.js 18+ installed and in PATH

**Terminal 1 - Backend:**
```bash
cd backend

# Create virtual environment (if not exists)
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
# Windows: notepad .env
# Linux/macOS: nano .env

# Start backend
uvicorn app.main:app --port 8002 --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend

# Install dependencies (first time only)
npm install

# Start frontend development server
npm run dev
```

**Access the application:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8002

## 📚 Core Features Preview

### 6 Core Tools

| Tool | Function | Example |
|------|----------|---------|
| **terminal** | Execute Shell commands | "List files in current directory" |
| **python_repl** | Run Python code | "Calculate Fibonacci sequence" |
| **fetch_url** | Fetch web content | "Get GitHub trending page" |
| **read_file** | Read local files | "Read README.md" |
| **write_file** | Write local files | "Generate a report" |
| **search_kb** | Knowledge base search | "Search for relevant info" |

### Built-in Skills

- **get_weather** - Weather query
- **arxiv-search** - Academic paper search
- **github** - GitHub operations
- **find-skill** - Find and install skills
- **skill-creator** - Create custom skills
- **skill_validator** - Validate skills

## ❓ FAQ

### Q: Installation takes too long

**A:** First run downloads dependencies (~500MB for backend, ~200MB for frontend). Future starts are instant (a few seconds).

### Q: Script fails with "command not found: python"

**A:** Install Python 3.10 or higher:
- Windows: https://www.python.org/downloads/ (Check "Add to PATH" during installation)
- Linux: `sudo apt install python3.10 python3.10-venv`
- macOS: `brew install python@3.10`

### Q: Script fails with "command not found: node"

**A:** Install Node.js 18 or higher:
- Windows: https://nodejs.org/ (Download LTS version)
- Linux: `sudo apt install nodejs npm`
- macOS: `brew install node`

### Q: Virtual environment creation fails

**A:** Ensure you have `venv` module installed:
```bash
# Linux/macOS
sudo apt install python3.10-venv  # Debian/Ubuntu
# or
sudo dnf install python3.10-venv  # Fedora

# Windows: venv is included with Python
```

### Q: How to get API key?

**A:** Visit provider's website:
- **Qwen**: https://dashscope.aliyun.com/ (Free tier available, recommended)
- **OpenAI**: https://platform.openai.com/api-keys
- **DeepSeek**: https://platform.deepseek.com/
- **Ollama**: No API key needed, just install from https://ollama.com/

### Q: Can I use my own Python/Node.js?

**A:** Yes! The scripts work with existing installations. They check if tools are present and only install what's missing.

### Q: How to switch LLM provider later?

**A:** Edit `backend/.env` file:
1. Find `LLM_PROVIDER=qwen` (or your current provider)
2. Change to your desired provider (openai, deepseek, ollama, etc.)
3. Update the corresponding API key
4. Restart the services

### Q: Port already in use

**A:** Change ports in `backend/.env`:
```bash
# Edit backend/.env
BACKEND_PORT=8003  # Change to available port
```
Or stop the service using the port:
```bash
# Windows: Find and kill the process
netstat -ano | findstr :8002
taskkill /PID <PID> /F

# Linux/macOS:
lsof -ti:8002 | xargs kill -9
```

### Q: How to update dependencies?

**A:**
```bash
# Backend
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install --upgrade -r requirements.txt

# Frontend
cd frontend
npm update
```

## 📖 Next Steps

- 📖 Read full documentation: [README.md](./README.md)
- 🏗️ Learn architecture: [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)
- 🔧 Advanced setup: [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)

## 💡 Tips

- **First run** takes 5-10 minutes (downloading dependencies)
- **Subsequent starts** are instant
- Use **Ctrl+C** in terminal to stop services
- Configuration files are preserved between runs
- All data is stored locally in your project directory

---

**Happy Using! 🎉**
