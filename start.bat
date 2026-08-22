@echo off
title AuraMed AI + MEDRESOLVE AI Launcher
color 0B
echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║      AuraMed AI + MEDRESOLVE AI Local Stack Launcher       ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

:: Check Python executable
if exist "%BASE_DIR%\MEDRESOLVE AI\.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%BASE_DIR%\MEDRESOLVE AI\.venv\Scripts\python.exe"
) else (
    set "PYTHON_CMD=python"
)

:: ── Step 1: Start Backend (FastAPI on port 8000) ───────────────────────────
echo [1/2] Launching MEDRESOLVE AI Backend (Port 8000)...
start "MEDRESOLVE AI Backend (Port 8000)" cmd /k "cd /d "%BASE_DIR%\MEDRESOLVE AI" && "%PYTHON_CMD%" -m uvicorn medresolve.api.app:app --reload --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak > nul

:: ── Step 2: Start Frontend HTTP Server (Port 5500) ─────────────────────────
echo [2/2] Launching AuraMed AI Frontend Server (Port 5500)...
start "AuraMed AI Frontend (Port 5500)" cmd /k "cd /d "%BASE_DIR%\AI-Hackathon-Front-End--main" && "%PYTHON_CMD%" -m http.server 5500 --bind 127.0.0.1"

timeout /t 2 /nobreak > nul

:: ── Step 3: Open in Browser ────────────────────────────────────────────────
echo.
echo  ✅ Backend running at:  http://127.0.0.1:8000/docs
echo  ✅ Frontend running at: http://127.0.0.1:5500/assistant.html
echo.
echo Opening AuraMed AI in your browser...
start "" "http://127.0.0.1:5500/assistant.html"

echo.
echo  ══════════════════════════════════════════════════════════════
echo   Keep the two command windows open while testing!
echo  ══════════════════════════════════════════════════════════════
echo.
