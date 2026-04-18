#!/bin/bash
# E2E Test Runner - Waits for services and runs tests

set -e

PROJECT_DIR="I:/code/miniclaw"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "=== miniClaw E2E Test Runner ==="
echo ""
echo "This script will wait for services to be ready before running tests."
echo ""

# Function to check if service is ready
check_service() {
    local url=$1
    local name=$2
    local max_wait=120
    local waited=0

    echo "Checking $name at $url..."

    while [ $waited -lt $max_wait ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "✓ $name is ready!"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
        echo "  Waiting... ($waited/$max_wait seconds)"
    done

    echo "✗ $name failed to become ready within $max_wait seconds"
    echo ""
    echo "Please ensure services are running:"
    echo "  - Backend:  cd backend && python -m uvicorn app.main:app --port 8002"
    echo "  - Frontend: cd frontend && npm run dev"
    echo ""
    return 1
}

# Check services
echo "[1/3] Checking backend service..."
if ! check_service "http://localhost:8002/health" "Backend"; then
    exit 1
fi

echo ""
echo "[2/3] Checking frontend service..."
if ! check_service "http://localhost:3000" "Frontend"; then
    exit 1
fi

# Run tests
echo ""
echo "[3/3] Running E2E tests..."
echo ""
cd "$FRONTEND_DIR"

# Set environment variables for tests
export BASE_URL=http://localhost:3000
export BACKEND_URL=http://localhost:8002

# Run Playwright tests
npx playwright test ../tests/e2e/smoke.spec.ts

TEST_RESULT=$?

echo ""
echo "=== Test Results ==="
if [ $TEST_RESULT -eq 0 ]; then
    echo "✓ All tests PASSED!"
else
    echo "✗ Some tests FAILED"
fi
echo ""

exit $TEST_RESULT
