@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: Dev_Mode.bat — Starts both servers for development (hot reload, TypeScript errors, etc.)
:: Uses Vite dev server on :3000 and FastAPI on :8000
:: ─────────────────────────────────────────────────────────────────────────────
title FinIntel — Dev Mode

set "FININTEL_DIR=%~dp0"
set "BACKEND_DIR=%FININTEL_DIR%backend"
set "FRONTEND_DIR=%FININTEL_DIR%frontend"

echo.
echo  FinIntel Dev Mode
echo  Backend: http://localhost:8000
echo  Frontend: http://localhost:3000  (hot reload)
echo.

:: Start backend in separate window with dev flag
start "FinIntel Backend [Dev]" cmd /k "cd /d "%BACKEND_DIR%" && set PYTHONPATH=%BACKEND_DIR%\src && set FININTEL_DEV=1 && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

:: Small wait for backend
timeout /t 3 /nobreak >nul

:: Start Vite dev server in separate window
start "FinIntel Frontend [Dev]" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

timeout /t 4 /nobreak >nul
start "" "http://localhost:3000"

echo  Both servers started. Close the two server windows to stop.
pause
