#!/bin/bash
# miniClaw Startup Script (Linux/Mac)
# Improved with health check to ensure backend is ready before starting frontend

echo "===================================="
echo "miniClaw AI Agent System"
echo "===================================="
echo ""

# Step 0/4: Check and install required tools
echo "Step 0.1/4: Checking required tools..."

# Check for clawhub CLI
if ! command -v clawhub &> /dev/null; then
    echo "ClawHub CLI not found. Installing..."
    npm i -g clawhub
    if [ $? -eq 0 ]; then
        echo "[OK] ClawHub CLI installed"
    else
        echo "[WARNING] Failed to install ClawHub CLI"
    fi
else
    echo "[OK] ClawHub CLI already installed"
fi

# Check for ClawSec security suite
echo ""
echo "Step 0.2/4: Checking ClawSec security suite..."
CLAWSEC_DIR="./backend/data/skills/clawsec-suite"
if [ ! -d "$CLAWSEC_DIR" ]; then
    echo "ClawSec not found. Installing to project skills directory..."
    echo "This may take a minute..."
    if INSTALL_ROOT="./backend/data/skills" npx clawhub@latest install clawsec-suite; then
        echo "[OK] ClawSec installed successfully to: $CLAWSEC_DIR"
    else
        echo "[WARNING] ClawSec installation failed. Continuing without security monitoring."
        echo "You can install it later manually."
    fi
else
    echo "[OK] ClawSec already installed. Skipping installation."
fi
echo ""

# Check if backend/.env exists
NEED_LLM_CONFIG=0
if [ ! -f "backend/.env" ]; then
    echo "Creating backend/.env file from backend/.env.example..."
    cp backend/.env.example backend/.env
    NEED_LLM_CONFIG=1
fi

# Check if LLM is properly configured
if grep -q "sk-your-" backend/.env 2>/dev/null; then
    NEED_LLM_CONFIG=1
fi

if [ $NEED_LLM_CONFIG -eq 1 ]; then
    echo ""
    echo "[WARNING] LLM provider not configured!"
    echo "========================================"
    echo "The backend will start but the agent will not be functional."
    echo "Please configure your LLM provider in backend/.env file:"
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

# Step 1/3: Start backend
echo "Step 1/3: Starting backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt
uvicorn app.main:app --port 8002 --reload &
BACKEND_PID=$!

cd ..

# Step 2/3: Wait for backend to be healthy
echo ""
echo "Step 2/3: Waiting for backend to be ready..."
echo ""

count=0
max_attempts=30

while [ $count -lt $max_attempts ]; do
    if curl -s http://localhost:8002/health > /dev/null 2>&1; then
        echo "[OK] Backend is ready! (attempts: $((count + 1)))"
        break
    fi

    count=$((count + 1))
    echo -n "Waiting... [$count/$max_attempts] "

    if [ $((count % 5)) -eq 0 ]; then
        echo ""
    fi

    sleep 2
done

echo ""

# Check if backend started successfully
if [ $count -eq $max_attempts ]; then
    echo "[ERROR] Backend failed to start within 60 seconds."
    echo "Please check the backend output for errors."
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# Step 3/3: Start frontend
echo "Step 3/3: Starting frontend..."
cd frontend
npm install
npm run dev &
FRONTEND_PID=$!

cd ..

echo ""
echo "===================================="
echo "System started successfully!"
echo "===================================="
echo ""
echo "Frontend:  http://localhost:3000"
echo "Backend:   http://localhost:8002"
echo "API Docs:  http://localhost:8002/docs"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Handle cleanup on exit
trap "echo ''; echo 'Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

# Wait for processes
wait
