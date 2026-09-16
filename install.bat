@echo off
REM Ai Heaven — install from source and run (Windows)
setlocal
cd /d "%~dp0"
echo == Ai Heaven setup ==

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

where ollama >nul 2>&1
if errorlevel 1 (
  echo Ollama not found. Opening the download page - install it, then re-run this script.
  start https://ollama.com/download
  pause & exit /b 1
)

echo Starting Ollama...
start "" /b ollama serve
timeout /t 2 >nul

for /f %%i in ('ollama list ^| find /c /v ""') do set LINES=%%i
if "%LINES%"=="1" (
  echo No models yet - pulling a good default ^(qwen2.5-coder:7b^)...
  ollama pull qwen2.5-coder:7b
)

echo Launching Ai Heaven...
python desktop.py
