@echo off
setlocal EnableDelayedExpansion
title FinIntel Financial Analytics Platform

set "FININTEL_DIR=%~dp0"
set "BACKEND_DIR=%FININTEL_DIR%backend"
set "FRONTEND_DIR=%FININTEL_DIR%frontend"
set "DIST_DIR=%FRONTEND_DIR%\dist"
set "PORT=8000"
set "URL=http://localhost:%PORT%"
set "LOG_FILE=%FININTEL_DIR%finintel_server.log"

cls
echo.
echo  ================================================
echo    FinIntel  Financial Analytics Platform
echo    v2.0  --  Starting...
echo  ================================================
echo.

:: ── Step 1: Check Python ──────────────────────────────────────────
echo  [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found.
    echo  Install Python 3.11+ from https://python.org
    echo  Make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo         Python %PYVER% found.

:: ── Step 2: Install packages if missing ──────────────────────────
echo  [2/4] Checking Python packages...
python -c "import fastapi, uvicorn, duckdb, pandas, pyarrow, reportlab" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Installing required packages - please wait 2-3 minutes...
    echo.
    cd /d "%BACKEND_DIR%"
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  ERROR: pip install failed.
        echo  Try running this command manually:
        echo    pip install -r "%BACKEND_DIR%\requirements.txt"
        echo.
        pause
        exit /b 1
    )
    echo.
    echo  Packages installed successfully.
)
echo         All packages ready.

:: ── Step 3: Check frontend build ─────────────────────────────────
echo  [3/4] Checking frontend build...
if not exist "%DIST_DIR%\index.html" (
    echo.
    echo  Frontend not built yet - building now...
    echo  This takes about 2 minutes on first run.
    echo.
    cd /d "%FRONTEND_DIR%"

    npm --version >nul 2>&1
    if errorlevel 1 (
        echo  ERROR: npm not found.
        echo  Install Node.js from https://nodejs.org
        echo.
        pause
        exit /b 1
    )

    if not exist "%FRONTEND_DIR%\node_modules" (
        echo  Installing Node packages - please wait 3-4 minutes...
        npm install --legacy-peer-deps
        if errorlevel 1 (
            echo  ERROR: npm install failed.
            echo.
            pause
            exit /b 1
        )
    )

    echo  Building frontend...
    call npm run build
    if errorlevel 1 (
        echo.
        echo  ERROR: Frontend build failed. Check the output above.
        echo.
        pause
        exit /b 1
    )
    echo  Frontend built successfully.
)
echo         Frontend ready.

:: ── Check if already running on port 8000 ────────────────────────
netstat -an 2>nul | find ":%PORT% " | find "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo  Port %PORT% already in use - FinIntel may already be running.
    echo  Opening browser...
    timeout /t 1 /nobreak >nul
    start "" "%URL%"
    echo.
    pause
    exit /b 0
)

:: ── Step 4: Start backend server ─────────────────────────────────
echo  [4/4] Starting server on %URL% ...
cd /d "%BACKEND_DIR%"
set "PYTHONPATH=%BACKEND_DIR%\src"

start "FinIntel Server" /min cmd /c "cd /d "%BACKEND_DIR%" && set PYTHONPATH=%BACKEND_DIR%\src && python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --no-access-log >> "%LOG_FILE%" 2>&1"

:: ── Wait for server to be ready ───────────────────────────────────
echo.
echo  Waiting for server...
set /a TRIES=0
:WAIT_LOOP
set /a TRIES+=1
if %TRIES% gtr 40 (
    echo.
    echo  ERROR: Server did not start after 40 seconds.
    echo  Check the file: %LOG_FILE%
    echo  for error details.
    echo.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
python -c "import urllib.request; urllib.request.urlopen('http://localhost:%PORT%/health', timeout=1)" >nul 2>&1
if errorlevel 1 goto :WAIT_LOOP

:: ── Open browser ──────────────────────────────────────────────────
echo  Server is ready!
echo.
echo  ================================================
echo   FinIntel is running at %URL%
echo   Close the "FinIntel Server" window to stop.
echo   Or run Stop_FinIntel.bat
echo  ================================================
echo.
timeout /t 1 /nobreak >nul
start "" "%URL%"
echo  Browser opened. Press any key to close this window.
echo  (The platform keeps running in the background)
pause >nul
exit /b 0
