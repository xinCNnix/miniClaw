# miniClaw Launcher with Auto-Cleanup
# Closing this window will automatically stop all services

$ErrorActionPreference = "Continue"

# Script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Track process IDs
$BackendProcess = $null
$FrontendProcess = $null

# Cleanup function
function Cleanup {
    Write-Host "`n====================================" -ForegroundColor Yellow
    Write-Host "Stopping all services..." -ForegroundColor Yellow
    Write-Host "====================================`n"

    # Kill backend by port
    $BackendPort = 8002
    try {
        $BackendProc = Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -ErrorAction SilentlyContinue

        if ($BackendProc) {
            Write-Host "Stopping backend (PID: $BackendProc)..." -ForegroundColor Cyan
            Stop-Process -Id $BackendProc -Force -ErrorAction SilentlyContinue
        }
    } catch {
        # Ignore errors
    }

    # Kill frontend by port
    foreach ($Port in 3000, 3001, 3002) {
        try {
            $FrontendProc = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -ErrorAction SilentlyContinue

            if ($FrontendProc) {
                Write-Host "Stopping frontend (PID: $FrontendProc, Port: $Port)..." -ForegroundColor Cyan
                Stop-Process -Id $FrontendProc -Force -ErrorAction SilentlyContinue
            }
        } catch {
            # Ignore errors
        }
    }

    Write-Host "`n====================================" -ForegroundColor Green
    Write-Host "All services stopped!" -ForegroundColor Green
    Write-Host "====================================`n"

    Start-Sleep -Seconds 1
}

# Register cleanup on window close
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Cleanup }

# Ctrl+C handler
trap {
    Cleanup
    exit
}

Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  miniClaw AI Agent System" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: Closing this window will automatically stop all services." -ForegroundColor Yellow
Write-Host "      Press Ctrl+C to quit.`n" -ForegroundColor Yellow

# --- Check prerequisites ---
Write-Host "[1/3] Checking prerequisites..." -ForegroundColor Cyan

$NpmPath = Get-Command npm -ErrorAction SilentlyContinue
if (-not $NpmPath) {
    Write-Host "[ERROR] npm is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Node.js from https://nodejs.org" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

$PythonPath = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonPath) {
    Write-Host "[ERROR] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

$PyVersion = & python --version 2>&1
Write-Host "[OK] $PyVersion found" -ForegroundColor Green
Write-Host "[OK] Node.js $(node --version) found" -ForegroundColor Green

# Check .env file
$EnvFile = Join-Path $ScriptDir "backend\.env"
$NeedConfig = $false

if (-not (Test-Path $EnvFile)) {
    $EnvExample = Join-Path $ScriptDir "backend\.env.example"
    if (Test-Path $EnvExample) {
        Write-Host "Creating backend\.env from backend\.env.example..." -ForegroundColor Yellow
        Copy-Item $EnvExample $EnvFile
    } else {
        Write-Host "Creating empty backend\.env..." -ForegroundColor Yellow
        New-Item -Path $EnvFile -ItemType File -Force | Out-Null
    }
    $NeedConfig = $true
} else {
    $EnvContent = Get-Content $EnvFile -Raw
    if ($EnvContent -match "sk-your-") {
        $NeedConfig = $true
    }
}

if ($NeedConfig) {
    Write-Host ""
    Write-Host "[WARNING] LLM provider not configured" -ForegroundColor Yellow
    Write-Host "========================================="
    Write-Host "The backend will start but the agent will not be functional."
    Write-Host "Please configure your LLM provider in backend\.env file."
    Write-Host ""
    Write-Host "Option 1 - Ollama - Free, Local"
    Write-Host "  1. Install Ollama from https://ollama.com"
    Write-Host "  2. Run: ollama pull qwen2.5"
    Write-Host "  3. In backend\.env, set:"
    Write-Host "     LLM_PROVIDER=ollama"
    Write-Host "     OLLAMA_MODEL=qwen2.5"
    Write-Host ""
    Write-Host "Option 2 - Qwen - Alibaba Cloud"
    Write-Host "  1. Get API key from https://dashscope.aliyun.com"
    Write-Host "  2. In backend\.env, set:"
    Write-Host "     QWEN_API_KEY=your-actual-api-key"
    Write-Host "     QWEN_MODEL=qwen-plus"
    Write-Host ""
    Write-Host "Option 3 - OpenAI"
    Write-Host "  1. Get API key from https://platform.openai.com"
    Write-Host "  2. In backend\.env, set:"
    Write-Host "     OPENAI_API_KEY=your-actual-api-key"
    Write-Host "     OPENAI_MODEL=gpt-4o-mini"
    Write-Host ""
    Write-Host "After editing backend\.env, restart this script."
    Write-Host "=========================================`n"
}

# --- Start Backend ---
Write-Host "[2/3] Starting backend..." -ForegroundColor Cyan
$BackendDir = Join-Path $ScriptDir "backend"
$BackendCmd = "cd /d `"$BackendDir`" && echo Installing dependencies... && pip install -q -r requirements.txt && echo. && echo Starting Uvicorn server on port 8002... && uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload"
Start-Process cmd -ArgumentList "/k", $BackendCmd -WindowStyle Normal

Write-Host "Waiting for backend to be ready..." -ForegroundColor Gray

$BackendReady = $false
$maxRetries = 90  # 90 x 2s = 3 minutes
$retry = 0

while (-not $BackendReady -and $retry -lt $maxRetries) {
    Start-Sleep -Seconds 2
    $retry++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8002/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $BackendReady = $true
            Write-Host "[OK] Backend is ready! (attempt $retry/$maxRetries)" -ForegroundColor Green
        }
    } catch {
        if ($retry % 10 -eq 0) {
            Write-Host "Still waiting for backend... ($retry/$maxRetries)" -ForegroundColor Yellow
        }
    }
}

if (-not $BackendReady) {
    Write-Host ""
    Write-Host "[ERROR] Backend failed to start within 3 minutes." -ForegroundColor Red
    Write-Host "Please check the backend window for errors." -ForegroundColor Yellow
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host "  - Missing deps: cd backend && pip install -r requirements.txt"
    Write-Host "  - Port 8002 in use: netstat -ano | findstr :8002"
    Write-Host "  - Python < 3.10: python --version"
    Cleanup
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""

# --- Start Frontend ---
Write-Host "[3/3] Starting frontend..." -ForegroundColor Cyan
$FrontendDir = Join-Path $ScriptDir "frontend"

$nodeModulesExists = Test-Path (Join-Path $FrontendDir "node_modules")
if ($nodeModulesExists) {
    $FrontendCmd = "cd /d `"$FrontendDir`" && echo Checking dependencies... && npm install && echo. && echo Starting Next.js dev server... && npm run dev"
} else {
    $FrontendCmd = "cd /d `"$FrontendDir`" && echo Installing frontend dependencies... && npm install && echo. && echo Starting Next.js dev server... && npm run dev"
}
Start-Process cmd -ArgumentList "/k", $FrontendCmd -WindowStyle Normal

Write-Host "Waiting for frontend to be ready..." -ForegroundColor Gray

$FrontendReady = $false
$FrontendPort = $null
$maxRetries = 90  # 90 x 2s = 3 minutes
$retry = 0

while (-not $FrontendReady -and $retry -lt $maxRetries) {
    Start-Sleep -Seconds 2
    $retry++
    foreach ($Port in 3000, 3001, 3002) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$Port" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                $FrontendReady = $true
                $FrontendPort = $Port
                break
            }
        } catch {
            # Continue trying
        }
    }
    if (-not $FrontendReady -and $retry % 10 -eq 0) {
        Write-Host "Still waiting for frontend... ($retry/$maxRetries)" -ForegroundColor Yellow
    }
}

if (-not $FrontendReady) {
    Write-Host "[WARNING] Frontend did not respond within 3 minutes." -ForegroundColor Yellow
    Write-Host "It may still be starting. Check the frontend window." -ForegroundColor Yellow
    $FrontendPort = 3000
} else {
    Write-Host "[OK] Frontend is ready on port $FrontendPort!" -ForegroundColor Green
}

# Open browser
Write-Host ""
Start-Process "http://localhost:$FrontendPort"

Write-Host "====================================" -ForegroundColor Green
Write-Host "  miniClaw is ready!" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend: http://localhost:$FrontendPort" -ForegroundColor White
Write-Host "  Backend:  http://localhost:8002" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8002/docs" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Yellow
Write-Host "Closing this window will also stop all services." -ForegroundColor Yellow
Write-Host "====================================`n" -ForegroundColor Green

# Keep running until Ctrl+C
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Cleanup
}
