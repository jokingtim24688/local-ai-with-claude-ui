# Ai Heaven — project brief for Claude

Native desktop app that runs and manages a **local coding-agent pool on Ollama**.
Heaven-themed UI (angel-wing logo, gold accent). Fully local & free once set up.
This file is the front door — deeper detail lives in `HANDOFF.md`, `VM_DESIGN.md`,
and `PROGRESS.md`.

## Run it
```
pip install -r requirements.txt          # flask, ollama, pywebview, psutil, (mcp)
python desktop.py                         # native window; auto-starts `ollama serve`
python app.py                             # backend only, browser at :5173
```
Needs Ollama installed + a model pulled (`ollama pull hermes3:8b`).

## Build a standalone exe
- Bundled (PyInstaller): `python build.py` → `dist/Ai Heaven.exe`
- **Compiled (Nuitka, real native binary)**: `python build_nuitka.py [--desktop]`
  or `build_nuitka.bat`
Build in a clean venv (flask ollama pywebview psutil + the build tool) so it stays
small — a global env drags in torch/pandas and bloats it to GBs.

## File map
```
desktop.py     app entry: ensure_ollama(), free port, Flask thread, pywebview window
app.py         Flask backend: chat SSE + agent tool-loop, all /api/* routes
tools.py       tool registry + SANDBOX jail (file ops confined to the workdir)
web.py         web_search / web_fetch (only on /web turns)
connectors.py  MCP client bridge (mcp SDK, fail-closed)
paths.py       bundled-resource (RES_DIR) vs writable AiHeaven-data (DATA_DIR);
               detects PyInstaller AND Nuitka
branding.json  name / logo / accent / default_model — everything brandable, no code
assets/        logo.svg + icon.ico (exe icon)
static/        index.html, style.css, app.js  (vanilla JS UI, no framework)
skills/        <name>/SKILL.md — seeded into AiHeaven-data on first run
elysium.spec + build*.{py,bat,sh}   packaging/installers
```

## Agent model (see HANDOFF.md for the contract)
- **MAIN** = ONE resident model (the composer pick, `keep_alive=-1`) with
  **persistent memory**: `MEMORY.md` as terse `key: value` lines, injected into its
  system prompt every turn. `remember` is auto-approved, squeezes filler, and a
  same-key note overwrites the old one. Over 2000 chars → auto-compacted after the turn
  by the same resident model (fallback: drop oldest lines). No approval needed.
- **Subagents** (buddy, designer, researcher, tester, reviewer, porter) boot **FRESH**
  per `spawn_subagent`: role + assigned skills + MAIN's brief only (no memory, chat,
  prompt.md, bus or board). They run **one at a time** (`SUB_LOCK`) and reuse MAIN's
  model (`model: ""`), so only one set of weights sits in RAM. A subagent with a
  different model unloads right after (`keep_alive=0`).
- When the app starts Ollama itself, it sets `OLLAMA_MAX_LOADED_MODELS=1`,
  `NUM_PARALLEL=1`, `FLASH_ATTENTION=1`, `KV_CACHE_TYPE=q8_0` (the user's env wins).
- The VM tab avatar looks around only on the subagent running now (`RUNNING_SUB`).
- Low-RAM pick: `ollama pull hermes3:3b` (~2 GB).
- **Views**: Chat / IDE / VM / Terminal (segmented switcher, top-right).

## Backend API (keep event/field names stable, or change both sides at once)
`/api/branding /config /models /skills /memory /tree /file /vm /system /tasks
/bus /subagents /connectors /targets /git/{status,diff,push} /chat(SSE) /approve`
SSE events: `token, tool_call, tool_result, approval, error, done`.

## Conventions
- Brandable only via `branding.json` — never hardcode the name/colors.
- Runtime json (subagents/tasks/bus/connectors/targets, MEMORY.md, prompt.md) is
  gitignored; it's user data, written to `AiHeaven-data/` (frozen) or repo root (dev).
- No content filter is added; refusals come from model weights.
- Regenerate `preview_*.png` after a big visual change (rendered from the real CSS).
- Vanilla JS + Flask, no build step for the UI.
