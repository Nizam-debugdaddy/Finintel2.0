@echo off
setlocal EnableDelayedExpansion
title FinIntel — Building Frontend

set "FININTEL_DIR=%~dp0"
set "FRONTEND_DIR=%FININTEL_DIR%frontend"
set "DIST_DIR=%FRONTEND_DIR%\dist"
set "BACKUP_DIR=%FININTEL_DIR%frontend_dist_backup"

echo.
echo  ┌─────────────────────────────────────────────────┐
echo  │         FinIntel — Build Frontend UI             │
echo  └─────────────────────────────────────────────────┘
echo.
echo  This rebuilds the React frontend from source.
echo  Run this after editing any file in frontend\src\
echo.

:: ── Check npm available ──────────────────────────────────────────────────────
npm --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: npm not found. Install Node.js from https://nodejs.org
    pause
    exit /b 1
)

:: ── Backup existing dist (safe rollback) ────────────────────────────────────
if exist "%DIST_DIR%\index.html" (
    echo  [1/3] Backing up existing build to frontend_dist_backup\...
    if exist "%BACKUP_DIR%" rd /s /q "%BACKUP_DIR%"
    xcopy "%DIST_DIR%" "%BACKUP_DIR%" /E /I /Q >nul
    echo        Backup complete. Run Rollback_UI.bat to restore.
) else (
    echo  [1/3] No existing build to backup.
)

:: ── Install/update packages if needed ───────────────────────────────────────
echo  [2/3] Checking Node packages...
cd /d "%FRONTEND_DIR%"
if not exist "%FRONTEND_DIR%\node_modules" (
    echo        Installing (first time — ~3 minutes)...
    npm install --legacy-peer-deps --silent
)

:: ── Build ────────────────────────────────────────────────────────────────────
echo  [3/3] Building frontend (takes ~60-90 seconds)...
echo.
call npm run build
if errorlevel 1 (
    echo.
    echo  ─────────────────────────────────────────────────
    echo  BUILD FAILED.
    echo  Restoring previous build...
    if exist "%BACKUP_DIR%\index.html" (
        if exist "%DIST_DIR%" rd /s /q "%DIST_DIR%"
        xcopy "%BACKUP_DIR%" "%DIST_DIR%" /E /I /Q >nul
        echo  Previous build restored. Platform still usable.
    )
    echo  ─────────────────────────────────────────────────
    pause
    exit /b 1
)

echo.
echo  ┌─────────────────────────────────────────────────┐
echo  │  Build successful!                               │
echo  │  Run Launch_FinIntel.bat to start the platform.  │
echo  └─────────────────────────────────────────────────┘
echo.
echo  Files in frontend\dist:
dir /b "%DIST_DIR%"
echo.
pause
