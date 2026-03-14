# miniClaw Quick Start Guide

> Lightweight, highly transparent AI Agent System - One-Click Setup 🚀

## 🚀 Super Easy Setup (Recommended)

### Windows Users

1. **Download or clone the project**
   ```bash
   git clone <repository-url>
   cd miniclaw
   ```

2. **Double-click `start.bat`**
   - That's it! Wait for automatic installation to complete
   - Browser will open automatically when ready

### Linux/macOS Users

1. **Download or clone the project**
   ```bash
   git clone <repository-url>
   cd miniclaw
   ```

2. **Run the startup script**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

3. **Done!** Wait for installation, browser will open automatically

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
   - Qwen (通义千问) - **Recommended**, has free tier
   - OpenAI GPT - Production quality
   - DeepSeek - Cost-effective
   - Ollama - Completely local, free

2. **Enter your API key**
   - Get your key from the provider's website
   - Paste it when prompted
   - Configuration is saved automatically

**That's it!** You're ready to use miniClaw.

## 🎯 Start Using

1. Browser opens to http://localhost:3000
2. Type your message in the chat box
3. Examples:
   - "帮我分析一下当前目录的文件结构"
   - "Query the weather in Beijing"
   - "Search arxiv for latest papers on LLM"
4. Wait for the Agent response

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

**Terminal 1 - Backend:**
```bash
cd backend
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start backend
uvicorn app.main:app --port 8002 --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## 📚 Core Features Preview

### 5 Core Tools

| Tool | Function | Example |
|------|----------|---------|
| **terminal** | Execute Shell commands | "List files in current directory" |
| **python_repl** | Run Python code | "Calculate Fibonacci sequence" |
| **fetch_url** | Fetch web content | "Get GitHub trending page" |
| **read_file** | Read local files | "Read README.md" |
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

**A:** First run downloads dependencies (~500MB for backend, ~200MB for frontend). Future starts are instant.

### Q: Script fails with "command not found"

**A:** Install Git first:
- Windows: https://git-scm.com/download/win
- Linux: `sudo apt install git`
- macOS: `xcode-select --install`

### Q: How to get API key?

**A:** Visit provider's website:
- **Qwen**: https://dashscope.aliyun.com/ (Free tier available)
- **OpenAI**: https://platform.openai.com/
- **Ollama**: https://ollama.com/ (Local, free)

### Q: Can I use my own Python/Node.js?

**A:** Yes! The scripts work with existing installations. They check if tools are present and only install what's missing.

### Q: How to switch LLM provider later?

**A:** Edit `backend/.env` file and change `LLM_PROVIDER` variable, then restart.

### Q: Port already in use

**A:** Change ports in `backend/.env`:
```bash
BACKEND_PORT=8003  # Change backend port
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
