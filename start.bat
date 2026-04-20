@echo off
setlocal enabledelayedexpansion

title miniClaw AI Agent System Launcher

echo ====================================
echo miniClaw AI Agent System
echo ====================================
echo.

cd /d "%~dp0"

rem --- Check Prerequisites ---
echo [1/3] Checking prerequisites...

where npm >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] npm is not installed or not in PATH.
    echo Please install Node.js from https://nodejs.org
    pause
    exit /b 1
)

where python >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] !PY_VER! found

rem --- Env Configuration ---
set "NEED_LLM_CONFIG=0"
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        echo Creating backend\.env from .env.example...
        copy "backend\.env.example" "backend\.env" >nul
        set "NEED_LLM_CONFIG=1"
    ) else (
        echo [WARNING] backend\.env.example not found. Creating empty backend\.env
        type nul > "backend\.env"
        set "NEED_LLM_CONFIG=1"
    )
)

findstr /C:"sk-your-" "backend\.env" >nul 2>&1
if !errorlevel! equ 0 (
    set "NEED_LLM_CONFIG=1"
)

if "!NEED_LLM_CONFIG!" equ "1" (
    echo.
    echo [WARNING] LLM provider not configured
    echo ========================================
    echo The backend will start but the agent will not be functional.
    echo Please configure your LLM provider in backend\.env file.
    echo.
    echo Option 1 - Ollama (Free, Local^):
    echo   1. Install Ollama from https://ollama.com
    echo   2. Run: ollama pull qwen2.5
    echo   3. In backend\.env, set:
    echo      LLM_PROVIDER=ollama
    echo      OLLAMA_MODEL=qwen2.5
    echo.
    echo Option 2 - Qwen (Alibaba Cloud^):
    echo   1. Get API key from https://dashscope.aliyun.com
    echo   2. In backend\.env, set:
    echo      QWEN_API_KEY=your-actual-api-key
    echo      QWEN_MODEL=qwen-plus
    echo.
    echo Option 3 - OpenAI:
    echo   1. Get API key from https://platform.openai.com
    echo   2. In backend\.env, set:
    echo      OPENAI_API_KEY=your-actual-api-key
    echo      OPENAI_MODEL=gpt-4o-mini
    echo.
    echo After editing backend\.env, run this script again.
    echo ========================================
    echo.
)

rem --- Directory Checks ---
if not exist "backend" (
    echo [ERROR] backend directory not found.
    echo Please run this script from the project root directory.
    pause
    exit /b 1
)

if not exist "frontend" (
    echo [ERROR] frontend directory not found.
    echo Please run this script from the project root directory.
    pause
    exit /b 1
)

rem --- Start Backend ---
echo [2/3] Starting backend...
echo Installing Python dependencies...
cd /d "%~dp0backend"
pip install -q -r requirements.txt
if !errorlevel! neq 0 (
    echo [WARNING] pip install had errors, attempting to continue...
)
echo Starting Uvicorn server on port 8002...
start "miniClaw Backend" cmd /k "cd /d "%~dp0backend" && uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload"
cd /d "%~dp0"

echo.
echo Waiting for backend to be ready...

set "BACKEND_ATTEMPTS=0"
set "BACKEND_MAX=90"

:wait_for_backend
set /a "BACKEND_ATTEMPTS+=1"

where curl >nul 2>&1
if !errorlevel! equ 0 (
    curl -s http://localhost:8002/health >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Backend is ready! ^(attempt !BACKEND_ATTEMPTS!/!BACKEND_MAX!^)
        goto start_frontend
    )
) else (
    powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8002/health' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Backend is ready! ^(attempt !BACKEND_ATTEMPTS!/!BACKEND_MAX!^)
        goto start_frontend
    )
)

if !BACKEND_ATTEMPTS! geq !BACKEND_MAX! (
    echo.
    echo [ERROR] Backend failed to start within 3 minutes.
    echo Please check the backend window for errors.
    echo Common issues:
    echo   - Missing dependencies: cd backend ^&^& pip install -r requirements.txt
    echo   - Port 8002 in use: netstat -ano ^| findstr :8002
    echo   - Python version ^< 3.10: python --version
    pause
    exit /b 1
)

echo Waiting... [!BACKEND_ATTEMPTS!/!BACKEND_MAX!]
timeout /t 2 /nobreak >nul
goto wait_for_backend

:start_frontend
echo.

rem --- Start Frontend ---
echo [3/3] Starting frontend...
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo Installing frontend dependencies...
) else (
    echo Checking frontend dependencies...
)
start "miniClaw Frontend" cmd /k "cd /d "%~dp0frontend" && npm install && npm run dev"
cd /d "%~dp0"

echo.
echo Waiting for frontend to be ready...

set "FE_ATTEMPTS=0"
set "FE_MAX=90"
set "FE_PORT="

:wait_for_frontend
set /a "FE_ATTEMPTS+=1"

for %%p in (3000 3001 3002) do (
    where curl >nul 2>&1
    if !errorlevel! equ 0 (
        curl -s http://localhost:%%p >nul 2>&1
        if !errorlevel! equ 0 (
            set "FE_PORT=%%p"
            goto frontend_found
        )
    ) else (
        powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:%%p' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set "FE_PORT=%%p"
            goto frontend_found
        )
    )
)

if !FE_ATTEMPTS! geq !FE_MAX! (
    echo.
    echo [WARNING] Frontend did not respond within 3 minutes.
    echo It may still be starting. Check the frontend window.
    echo.
    set "FE_PORT=3000"
    goto open_browser
)

echo Waiting... [!FE_ATTEMPTS!/!FE_MAX!]
timeout /t 2 /nobreak >nul
goto wait_for_frontend

:frontend_found
echo [OK] Frontend is ready on port !FE_PORT!

:open_browser
echo.
echo ====================================
echo miniClaw is ready!
echo ====================================
echo.
echo Frontend:  http://localhost:!FE_PORT!
echo Backend:   http://localhost:8002
echo API Docs:  http://localhost:8002/docs
echo.
echo Press Ctrl+C in each window to stop.
echo.

start http://localhost:!FE_PORT!

exit /b 0
