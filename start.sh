#!/bin/bash
# miniClaw Startup Script (Linux/Mac)
# Improved with health check, timeout protection, and better error handling

set -e

echo "===================================="
echo "miniClaw AI Agent System"
echo "===================================="
echo ""

cd "$(dirname "$0")"

# --- Check Prerequisites ---
echo "[1/3] Checking prerequisites..."

# Find Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python 3.10+ not found. Install from https://www.python.org"
    exit 1
fi

PY_VER=$($PYTHON --version 2>&1)
echo "[OK] $PY_VER found"

if ! command -v npm &>/dev/null; then
    echo "[ERROR] npm not found. Install Node.js from https://nodejs.org"
    exit 1
fi

echo "[OK] Node.js $(node --version) found"
echo ""

# --- Env Configuration ---
NEED_LLM_CONFIG=0
if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        echo "Creating backend/.env from .env.example..."
        cp backend/.env.example backend/.env
    else
        echo "[WARNING] backend/.env.example not found. Creating empty backend/.env"
        touch backend/.env
    fi
    NEED_LLM_CONFIG=1
fi

if grep -q "sk-your-" backend/.env 2>/dev/null; then
    NEED_LLM_CONFIG=1
fi

if [ $NEED_LLM_CONFIG -eq 1 ]; then
    echo ""
    echo "[WARNING] LLM provider not configured!"
    echo "========================================"
    echo "The backend will start but the agent will not be functional."
    echo "Please configure your LLM provider in backend/.env file."
    echo ""
    echo "Option 1 - Ollama (Free, Local):"
    echo "  1. Install Ollama from https://ollama.com"
    echo "  2. Run: ollama pull qwen2.5"
    echo "  3. In backend/.env, set:"
    echo "     LLM_PROVIDER=ollama"
    echo "     OLLAMA_MODEL=qwen2.5"
    echo ""
    echo "Option 2 - Qwen (Alibaba Cloud):"
    echo "  1. Get API key from https://dashscope.aliyun.com"
    echo "  2. In backend/.env, set:"
    echo "     QWEN_API_KEY=your-actual-api-key"
    echo "     QWEN_MODEL=qwen-plus"
    echo ""
    echo "Option 3 - OpenAI:"
    echo "  1. Get API key from https://platform.openai.com"
    echo "  2. In backend/.env, set:"
    echo "     OPENAI_API_KEY=your-actual-api-key"
    echo "     OPENAI_MODEL=gpt-4o-mini"
    echo ""
    echo "After editing backend/.env, run this script again."
    echo "========================================"
    echo ""
    read -p "Press Enter to continue anyway..."
fi

# --- Start Backend ---
echo "[2/3] Starting backend..."

cd backend

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

source venv/bin/activate
echo "Installing Python dependencies..."
pip install -q -r requirements.txt 2>/dev/null || echo "[WARNING] pip install had warnings"

echo "Starting Uvicorn server on port 8002..."
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload &
BACKEND_PID=$!

cd ..

# --- Wait for Backend ---
echo ""
echo "Waiting for backend to be ready..."

count=0
max_attempts=90

while [ $count -lt $max_attempts ]; do
    count=$((count + 1))

    if curl -sf http://localhost:8002/health >/dev/null 2>&1; then
        echo "[OK] Backend is ready! (attempt $count/$max_attempts)"
        break
    fi

    if [ $count -eq $max_attempts ]; then
        echo ""
        echo "[ERROR] Backend failed to start within 3 minutes."
        echo "Please check the backend output for errors."
        echo "Common issues:"
        echo "  - Missing deps: cd backend && pip install -r requirements.txt"
        echo "  - Port in use:  lsof -ti:8002 | xargs kill -9"
        echo "  - Python < 3.10: python3 --version"
        kill $BACKEND_PID 2>/dev/null
        exit 1
    fi

    echo "Waiting... [$count/$max_attempts]"
    sleep 2
done

echo ""

# --- Start Frontend ---
echo "[3/3] Starting frontend..."

cd frontend
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
else
    echo "Checking frontend dependencies..."
fi
npm install --silent 2>/dev/null
npm run dev &
FRONTEND_PID=$!

cd ..

echo ""
echo "Waiting for frontend to be ready..."

count=0
max_attempts=90
FE_PORT=""

while [ $count -lt $max_attempts ]; do
    count=$((count + 1))

    for port in 3000 3001 3002; do
        if curl -sf http://localhost:$port >/dev/null 2>&1; then
            FE_PORT=$port
            break 2
        fi
    done

    if [ $count -eq $max_attempts ]; then
        echo ""
        echo "[WARNING] Frontend did not respond within 3 minutes."
        echo "It may still be starting. Check the frontend output."
        FE_PORT="3000"
        break
    fi

    echo "Waiting... [$count/$max_attempts]"
    sleep 2
done

if [ -n "$FE_PORT" ]; then
    echo "[OK] Frontend is ready on port $FE_PORT"
fi

echo ""
echo "===================================="
echo "miniClaw is ready!"
echo "===================================="
echo ""
echo "Frontend:  http://localhost:${FE_PORT:-3000}"
echo "Backend:   http://localhost:8002"
echo "API Docs:  http://localhost:8002/docs"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Handle cleanup on exit
cleanup() {
    echo ""
    echo "Stopping services..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "Stopped."
    exit 0
}

trap cleanup INT TERM

# Keep script running
wait
