@echo off
REM Night Crew — install from source and run (Windows)
setlocal
cd /d "%~dp0"
echo == Night Crew setup ==

where python >nul 2>&1
if errorlevel 1 (
  echo Python not found. Install Python 3.10+ from https://python.org (check "Add to PATH"), then re-run.
  start https://www.python.org/downloads/
  pause & exit /b 1
)

if not exist .venv ( echo Creating venv... & python -m venv .venv )
call .venv\Scripts\activate.bat
echo Installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

set /p PW=Also install JS-page scraping (Playwright + Chromium, ~150 MB)? [y/N] 
if /i "%PW%"=="y" ( python -m pip install --quiet playwright & python -m playwright install chromium )

where ollama >nul 2>&1
if errorlevel 1 (
  echo Ollama not found. Opening the download page - install it, then re-run this script.
  start https://ollama.com/download
  pause & exit /b 1
)

echo Starting Ollama...
start "" /b ollama serve
timeout /t 2 >nul

rem the lead (debugs) + the low-power worker (writes first drafts)
ollama list | find "hermes3:8b" >nul || (echo Pulling the lead model hermes3:8b... & ollama pull hermes3:8b)
ollama list | find "qwen2.5-coder:3b" >nul || (echo Pulling the worker model qwen2.5-coder:3b... & ollama pull qwen2.5-coder:3b)

echo Launching Night Crew...
python desktop.py
