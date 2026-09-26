#!/usr/bin/env bash
# Ai Heaven — install from source and run (macOS / Linux)
set -e
cd "$(dirname "$0")"
echo "== Ai Heaven setup =="

command -v python3 >/dev/null || { echo "Install Python 3.10+ first (python.org / brew install python)"; exit 1; }

[ -d .venv ] || { echo "Creating venv..."; python3 -m venv .venv; }
source .venv/bin/activate
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if ! command -v ollama >/dev/null; then
  if [ "$(uname)" = "Linux" ]; then
    echo "Installing Ollama..."; curl -fsSL https://ollama.com/install.sh | sh
  else
    echo "Ollama not found. Install from https://ollama.com/download then re-run."; open https://ollama.com/download || true; exit 1
  fi
fi

echo "Starting Ollama..."; (ollama serve >/dev/null 2>&1 &) ; sleep 2
# the lead (debugs) + the low-power worker (writes first drafts)
ollama list | grep -q "hermes3:8b" || { echo "Pulling the lead model hermes3:8b..."; ollama pull hermes3:8b; }
ollama list | grep -q "qwen2.5-coder:3b" || { echo "Pulling the worker model qwen2.5-coder:3b..."; ollama pull qwen2.5-coder:3b; }

echo "Launching Ai Heaven..."; python3 desktop.py
