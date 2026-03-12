#!/bin/bash
# E2E Test Runner for miniClaw

set -e

PROJECT_DIR="I:/code/miniclaw"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "=== miniClaw E2E Test Runner ==="
echo

# Function to cleanup on exit
cleanup() {
    echo "Cleaning up..."
    # Kill background processes
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

# Step 1: Start Backend
echo "[1/4] Starting backend..."
cd "$BACKEND_DIR"

# Create and activate venv
if [ ! -d "venv" ]; then
    python -m venv venv
fi

# Activate venv (Git Bash on Windows)
source venv/Scripts/activate

# Install dependencies
pip install -q -r requirements.txt

# Start backend in background
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload &
BACKEND_PID=$!

echo "Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo "Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8002/health > /dev/null 2>&1; then
        echo "Backend is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: Backend failed to start"
        exit 1
    fi
    sleep 2
    echo "Waiting... ($i/30)"
done

# Step 2: Start Frontend
echo "[2/4] Starting frontend..."
cd "$FRONTEND_DIR"

# Start frontend in background
npm run dev &
FRONTEND_PID=$!

echo "Frontend PID: $FRONTEND_PID"

# Wait for frontend to be ready
echo "Waiting for frontend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo "Frontend is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: Frontend failed to start"
        exit 1
    fi
    sleep 2
    echo "Waiting... ($i/30)"
done

# Step 3: Run E2E Tests
echo "[3/4] Running E2E tests..."
cd "$FRONTEND_DIR"

npm run test:e2e || {
    echo "E2E tests failed!"
    exit 1
}

# Step 4: Cleanup
echo "[4/4] Tests completed. Cleaning up..."

echo
echo "=== E2E Test Summary ==="
echo "All tests passed!"
echo "Backend PID: $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
