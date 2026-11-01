@echo off
title FinIntel — Stopping Server
echo.
echo  Stopping FinIntel server on port 8000...
echo.

:: Find the PID listening on port 8000 and kill it
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo  Stopping process %%p...
    taskkill /PID %%p /F >nul 2>&1
    echo  Done.
    goto :killed
)

:: Also try to kill by window title
taskkill /FI "WINDOWTITLE eq FinIntel Server" /F >nul 2>&1

:killed
:: Verify port is free
timeout /t 2 /nobreak >nul
netstat -an 2>nul | find ":8000 " | find "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo  FinIntel server stopped.
) else (
    echo  WARNING: Port 8000 still in use. May need manual cleanup.
)

echo.
pause
