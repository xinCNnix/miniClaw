# miniClaw E2E Test Runner
# Complete automation script for running E2E tests

$ErrorActionPreference = "Continue"

$PROJECT_DIR = "I:\code\miniclaw"
$BACKEND_DIR = "$PROJECT_DIR\backend"
$FRONTEND_DIR = "$PROJECT_DIR\frontend"
$LOG_DIR = "$PROJECT_DIR\temp"

Write-Host "=== miniClaw E2E Test Runner ===" -ForegroundColor Cyan
Write-Host ""

# Ensure log directory exists
if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR | Out-Null
}

# Function to cleanup processes
function Cleanup-Processes {
    Write-Host "Cleaning up background processes..." -ForegroundColor Yellow
    Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
}

# Cleanup on script exit
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    Cleanup-Processes
} | Out-Null

# Trap Ctrl+C
trap {
    Cleanup-Processes
    exit 1
}

# Step 1: Start Backend
Write-Host "[1/5] Setting up backend..." -ForegroundColor Green

$backendLog = "$LOG_DIR\backend-e2e.log"

# Remove old venv if exists and is broken
if (Test-Path "$BACKEND_DIR\venv") {
    try {
        Remove-Item -Recurse -Force "$BACKEND_DIR\venv" -ErrorAction Stop
        Write-Host "  Removed old venv" -ForegroundColor Gray
    } catch {
        Write-Host "  Warning: Could not remove old venv" -ForegroundColor Yellow
    }
}

# Create new venv
Write-Host "  Creating virtual environment..." -ForegroundColor Gray
& python -m venv "$BACKEND_DIR\venv"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Failed to create venv" -ForegroundColor Red
    exit 1
}

# Activate venv and install dependencies
Write-Host "  Installing dependencies..." -ForegroundColor Gray
$activateScript = "$BACKEND_DIR\venv\Scripts\Activate.ps1"
& $activateScript
& pip install -q -r "$BACKEND_DIR\requirements.txt"

# Start backend
Write-Host "  Starting backend server..." -ForegroundColor Gray
$backendProcess = Start-Process -FilePath "$BACKEND_DIR\venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8002","--reload" `
    -WorkingDirectory $BACKEND_DIR `
    -WindowStyle Minimized `
    -PassThru

Write-Host "  Backend PID: $($backendProcess.Id)" -ForegroundColor Gray

# Wait for backend to be ready
Write-Host "  Waiting for backend to be ready..." -ForegroundColor Gray
$maxWait = 60
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8002/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "  Backend is ready!" -ForegroundColor Green
            break
        }
    } catch {
        # Keep waiting
    }
    Start-Sleep -Seconds 2
    $waited += 2
    Write-Host "  Waiting... ($waited/$maxWait seconds)" -ForegroundColor Gray
}

if ($waited -ge $maxWait) {
    Write-Host "  ERROR: Backend failed to start within $maxWait seconds" -ForegroundColor Red
    Cleanup-Processes
    exit 1
}

# Step 2: Start Frontend
Write-Host "[2/5] Starting frontend..." -ForegroundColor Green

$frontendProcess = Start-Process -FilePath "npm" `
    -ArgumentList "run","dev" `
    -WorkingDirectory $FRONTEND_DIR `
    -WindowStyle Minimized `
    -PassThru

Write-Host "  Frontend PID: $($frontendProcess.Id)" -ForegroundColor Gray

# Wait for frontend to be ready
Write-Host "  Waiting for frontend to be ready..." -ForegroundColor Gray
$maxWait = 60
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "  Frontend is ready!" -ForegroundColor Green
            break
        }
    } catch {
        # Keep waiting
    }
    Start-Sleep -Seconds 2
    $waited += 2
    Write-Host "  Waiting... ($waited/$maxWait seconds)" -ForegroundColor Gray
}

if ($waited -ge $maxWait) {
    Write-Host "  ERROR: Frontend failed to start within $maxWait seconds" -ForegroundColor Red
    Cleanup-Processes
    exit 1
}

# Step 3: Run E2E Tests
Write-Host "[3/5] Running E2E tests..." -ForegroundColor Green
Write-Host ""

Push-Location $FRONTEND_DIR
try {
    & npm run test:e2e
    $testExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

# Step 4: Report Results
Write-Host ""
Write-Host "[4/5] Test Results:" -ForegroundColor Cyan
if ($testExitCode -eq 0) {
    Write-Host "  ✓ All E2E tests PASSED!" -ForegroundColor Green
} else {
    Write-Host "  ✗ Some E2E tests FAILED" -ForegroundColor Red
}

# Step 5: Cleanup
Write-Host "[5/5] Cleanup..." -ForegroundColor Cyan
Cleanup-Processes

Write-Host ""
Write-Host "=== E2E Test Run Complete ===" -ForegroundColor Cyan
Write-Host "Exit code: $testExitCode"
Write-Host ""

exit $testExitCode
