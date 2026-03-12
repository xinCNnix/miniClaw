@echo off
echo Starting services for E2E tests...

REM Start backend
start "miniClaw Backend Test" cmd /k "cd /d I:\code\miniclaw\backend && python -m venv venv 2>nul && venv\Scripts\activate && pip install -q -r requirements.txt && python -m uvicorn app.main:app --host 0.0.0.0 --port 8002"

REM Wait for backend
timeout /t 15 /nobreak >nul

REM Start frontend
start "miniClaw Frontend Test" cmd /k "cd /d I:\code\miniclaw\frontend && npm run dev"

REM Wait for frontend
timeout /t 10 /nobreak >nul

echo Services should be starting...
echo Backend: http://localhost:8002
echo Frontend: http://localhost:3000
