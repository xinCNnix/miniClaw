@echo off
setlocal enabledelayedexpansion

title miniClaw AI Agent System Launcher

echo ====================================
echo miniClaw AI Agent System
echo ====================================
echo/

cd /d "%~dp0"

rem --- Check Prerequisites ---
echo Step 0.0: Checking prerequisites...
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
    pause
    exit /b 1
)
echo [OK] Prerequisites found.
echo/

echo Step 0.1/4: Checking required tools...
where clawhub >nul 2>&1
if !errorlevel! neq 0 (
    echo ClawHub CLI not found. Installing...
    call npm i -g clawhub
    if !errorlevel! equ 0 (
        echo [OK] ClawHub CLI installed
    ) else (
        echo [ERROR] Failed to install ClawHub CLI. Please check npm logs.
        pause
        exit /b 1
    )
) else (
    echo [OK] ClawHub CLI already installed
)
echo/

echo Step 0.2/4: Checking ClawSec security suite...
set "CLAWSEC_DIR=backend\data\skills\clawsec-suite"
if not exist "%CLAWSEC_DIR%" (
    echo ClawSec not found. Installing to project skills directory...
    echo This may take a minute...
    rem Ensure we are in the right dir for npx if needed, though npx usually handles it
    call npx clawhub@latest install clawsec-suite
    if !errorlevel! equ 0 (
        echo [OK] ClawSec installed successfully
    ) else (
        echo [WARNING] ClawSec installation failed. You can install it later manually.
    )
) else (
    echo [OK] ClawSec already installed
)
echo/

rem --- Env Configuration ---
set "NEED_LLM_CONFIG=0"
if not exist "backend\.env" (
    if exist "backend\.env.example" (
        echo Creating backend\.env file from backend\.env.example...
        copy "backend\.env.example" "backend\.env" >nul
        set "NEED_LLM_CONFIG=1"
    ) else (
        echo [WARNING] backend\.env.example not found. Creating empty backend\.env
        type nul > "backend\.env"
        set "NEED_LLM_CONFIG=1"
    )
)

rem Check for placeholder key
findstr /C:"sk-your-" "backend\.env" >nul 2>&1
if !errorlevel! equ 0 (
    set "NEED_LLM_CONFIG=1"
)

if "!NEED_LLM_CONFIG!" equ "1" (
    echo/
    echo [WARNING] LLM provider not configured
    echo ========================================
    echo The backend will start but the agent will not be functional.
    echo Please configure your LLM provider in backend\.env file.
    echo/
    echo Option 1 - Ollama - Free, Local
    echo   1. Install Ollama from https://ollama.com
    echo   2. Run: ollama pull qwen2.5
    echo   3. In backend\.env, set:
    echo      LLM_PROVIDER=ollama
    echo      OLLAMA_MODEL=qwen2.5
    echo/
    echo Option 2 - Qwen - Alibaba Cloud
    echo   1. Get API key from https://dashscope.aliyun.com
    echo   2. In backend\.env, set:
    echo      QWEN_API_KEY=your-actual-api-key
    echo      QWEN_MODEL=qwen-plus
    echo/
    echo Option 3 - OpenAI
    echo   1. Get API key from https://platform.openai.com
    echo   2. In backend\.env, set:
    echo      OPENAI_API_KEY=your-actual-api-key
    echo      OPENAI_MODEL=gpt-4o-mini
    echo/
    echo After editing backend\.env, run this script again.
    echo ========================================
    echo/
    rem Changed: continue execution without pause
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

echo Step 1/3: Starting backend...
start "miniClaw Backend" cmd /k "cd /d "%~dp0backend" && echo Installing dependencies... && pip install -q -r requirements.txt && echo. && echo Starting Uvicorn server on port 8002... && uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload"

echo/
echo Step 2/3: Waiting for backend to be ready...
echo/

:wait_for_backend
rem Try curl first, if fails try PowerShell
set "BACKEND_READY=0"

where curl >nul 2>&1
if !errorlevel! equ 0 (
    curl -s http://localhost:8002/health >nul 2>&1
    if !errorlevel! equ 0 set "BACKEND_READY=1"
) else (
    rem Fallback to PowerShell
    powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8002/health' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if !errorlevel! equ 0 set "BACKEND_READY=1"
)

if "!BACKEND_READY!" equ "1" (
    echo [OK] Backend is ready!
    goto start_frontend
)

rem Wait 2 seconds and retry
timeout /t 2 /nobreak >nul
goto wait_for_backend

:start_frontend
echo/

echo/
echo Step 3/3: Starting frontend...
start "miniClaw Frontend" cmd /k "cd /d "%~dp0frontend" && echo Installing dependencies... && npm install && echo. && echo Starting Next.js dev server... && npm run dev"

echo/
echo Waiting for frontend to be ready...
echo/

:wait_for_frontend
rem Try curl first, if fails try PowerShell
set "FRONTEND_READY=0"
set "FRONTEND_PORT="

rem Check ports 3000, 3001, 3002 (Next.js will try these if default is busy)
for %%p in (3000 3001 3002) do (
    where curl >nul 2>&1
    if !errorlevel! equ 0 (
        curl -s http://localhost:%%p >nul 2>&1
        if !errorlevel! equ 0 (
            set "FRONTEND_READY=1"
            set "FRONTEND_PORT=%%p"
            goto frontend_found
        )
    ) else (
        rem Fallback to PowerShell
        powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:%%p' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set "FRONTEND_READY=1"
            set "FRONTEND_PORT=%%p"
            goto frontend_found
        )
    )
)

:frontend_found
if "!FRONTEND_READY!" equ "1" (
    echo [OK] Frontend is ready on port !FRONTEND_PORT!
    goto open_browser
)

rem Wait 2 seconds and retry
timeout /t 2 /nobreak >nul
goto wait_for_frontend

:open_browser
echo/
echo ====================================
echo System is starting...
echo ====================================
echo/
echo Frontend: http://localhost:3000
echo Backend API: http://localhost:8002
echo API Docs: http://localhost:8002/docs
echo/
echo Note: Press Ctrl+C in each opened window to stop the services.
echo/

echo Opening browser...
if "!FRONTEND_PORT!"=="" (
    start http://localhost:3000
) else (
    start http://localhost:!FRONTEND_PORT!
)

exit /b 0
