@echo off
title FinIntel — Rollback UI

set "FININTEL_DIR=%~dp0"
set "DIST_DIR=%FININTEL_DIR%frontend\dist"
set "BACKUP_DIR=%FININTEL_DIR%frontend_dist_backup"

echo.
echo  FinIntel — Restore previous frontend build
echo.

if not exist "%BACKUP_DIR%\index.html" (
    echo  No backup found at frontend_dist_backup\
    echo  Nothing to restore.
    pause
    exit /b 1
)

echo  Restoring from backup...
if exist "%DIST_DIR%" rd /s /q "%DIST_DIR%"
xcopy "%BACKUP_DIR%" "%DIST_DIR%" /E /I /Q >nul
echo  Restored. Restart the server for changes to take effect.
echo.
pause
