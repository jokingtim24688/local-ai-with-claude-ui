# Night Crew — project brief for Claude

Native desktop app (**Windows + macOS**) that runs a **local game-dev agent team on
Ollama**: a lead model with memory plus low-power worker models, driving **Blender,
Unreal Engine and Roblox Studio**. "Midnight" UI (crescent logo, crema accent) with
**Catppuccin Mocha** code colors. Fully local & free once set up.
This file is the front door — deeper detail lives in `HANDOFF.md`, `VM_DESIGN.md`,
and `PROGRESS.md`.

## Run it
```
pip install -r requirements.txt          # flask, ollama, pywebview, psutil, (mcp)
python desktop.py                         # native window; auto-starts `ollama serve`
python app.py                             # backend only, browser at :5173
```
**Auto-updating shortcut:** `python make_shortcut.py` once -> Desktop + Start-menu
"Night Crew" (Windows) / `~/Applications/Night Crew.app` (macOS). It runs
`launcher.py`: git fetch + fast-forward (local edits stashed, re-applied only if clean,
never conflict markers), pip install when requirements.txt changed, then desktop.py;
the app shows an "Updated: N changes" toast (`NIGHTCREW_UPDATE_NOTE`). Log: update.log.
Needs Ollama + two models: `ollama pull hermes3:8b` (lead) and
`ollama pull qwen2.5-coder:3b` (worker). `install.sh` / `install.bat` do all of it.

## Build the app (build on each OS for that OS)
- Windows: `build_nuitka.bat` / `python build_nuitka.py [--desktop]` → `Night Crew.exe`
  (compiled), or `python build.py` → `dist/Night Crew.exe` (PyInstaller)
- macOS: `python3 build_nuitka.py` → `build_nuitka/Night Crew.app` (needs
  `xcode-select --install`), or `./build.sh` → `dist/Night Crew.app` (PyInstaller,
  onedir + BUNDLE). Unsigned: first launch = right-click → Open.
Build in a clean venv (flask ollama pywebview psutil + the build tool) so it stays
small — a global env drags in torch/pandas and bloats it to GBs.

## File map
```
launcher.py    auto-update (git ff + safe stash) then start desktop.py
make_shortcut.py  one-time: Desktop/Start-menu shortcut (Win) or Night Crew.app (mac)
desktop.py     app entry: ensure_ollama(), free port, Flask thread, pywebview window
app.py         Flask backend: chat SSE + agent tool-loop, all /api/* routes
toolcalls.py   recovers tool calls small models TYPE as JSON text; hides that JSON
tools.py       tool registry + SANDBOX jail (file ops confined to the workdir)
apps.py        Blender / Unreal / Roblox Studio / Rojo / luau: detection (win+mac),
               tools (blender_run, unreal_run_python, unreal_uat, roblox_open, rojo,
               luau_check, fetch_docs, docs_index, app_control, open_url,
               unreal_quick_level; blender_run takes inline code + save_as/open_after)
web.py         web_search / web_fetch (only on /web turns)
connectors.py  MCP client bridge (mcp SDK, fail-closed)
paths.py       bundled-resource (RES_DIR) vs writable NightCrew-data (DATA_DIR);
               detects PyInstaller AND Nuitka
branding.json  name / logo / accent / default_model — everything brandable, no code
assets/        logo.svg (UI mark), icon.svg -> icon.ico (Windows) + icon.icns (macOS)
static/        index.html, style.css, app.js, hl.js (offline highlighter + chat
               markdown), fonts/ (IBM Plex Sans, Fraunces, JetBrains Mono — OFL)
skills/        <name>/SKILL.md — new ones are copied into NightCrew-data on each start
               (never overwriting the user's). blender-python / unreal-engine /
               roblox-studio = condensed official docs
elysium.spec + build*.{py,bat,sh}   packaging/installers
```

## Agent model (see HANDOFF.md for the contract)
- **MAIN** = ONE resident model (the composer pick, `keep_alive=-1`) with
  **persistent memory**: `MEMORY.md` as terse `key: value` lines, injected into its
  system prompt every turn. `remember` is auto-approved, squeezes filler, and a
  same-key note overwrites the old one. Over 2000 chars → auto-compacted after the turn
  by the same resident model (fallback: drop oldest lines). No approval needed.
- **Workers WRITE, MAIN DEBUGS.** Subagents (buddy, designer, researcher, tester,
  reviewer, porter + specialists **blender**, **unreal**, **roblox**) boot **FRESH** per
  `spawn_subagent` on the low-power **worker model** (settings `worker_model`, default
  `qwen2.5-coder:3b`; falls back to MAIN's model if not pulled; unloads after with
  `keep_alive=0`). They see role + assigned skills + MAIN's brief only, one at a time
  (`SUB_LOCK`). Their result comes back with FILES + offline AUTO-CHECKS (py compile,
  JSON, node --check, luau lint) and a "debug now" handoff; MAIN runs and fixes.
- Small leads (llama3.2:3b etc.) often write tool calls as text: the chat loop holds
  back text that starts like a call (or a mid-answer `{"name":`), runs it via
  toolcalls.extract_calls, and nudges the model when it invents a tool. The lead's tool
  menu is deliberately lean (no bus/task/avatar tools) and its prompt short.
- App tools (Blender/Unreal/Roblox) are **MAIN-only**; the ones that run code or launch
  programs need approval unless Auto is on. Paths: sandbox + user-registered project
  folders (`apps.json`) only. `num_ctx` 8192 for MAIN and workers.
- When the app starts Ollama itself, it sets `OLLAMA_MAX_LOADED_MODELS=1`,
  `NUM_PARALLEL=1`, `FLASH_ATTENTION=1`, `KV_CACHE_TYPE=q8_0` (the user's env wins).
- Agents run in the background (no VM/Terminal tabs any more; `/api/vm` etc. remain
  for tooling). **Connectors** are always configured but a chat only gets a connector's
  MCP tools after the user mentions it there; the UI stores it per chat
  (`convo.connectors`) and sends it as a chat-only system instruction +
  `/api/chat` `connectors` (workers inherit the same set).
- **Startup** (`startup_apps` -> `apps.start_setup`): Roblox Studio + Unreal Engine are
  checked; missing -> winget/Homebrew install (Roblox Studio directly; Unreal via the
  Epic Games Launcher, which needs the user's Epic sign-in once), then both start
  minimized/hidden unless RAM >= 85%. Settings `auto_setup`, `launch_on_start`;
  log at `/api/apps/setup`.
- Low-RAM pick: `ollama pull hermes3:3b` (~2 GB).
- **Views**: Chat / IDE; the switcher lives in the composer, before the model pill.
  The IDE is Antigravity-style (explorer | tabbed editor | Agent panel); opening it
  moves the one chat DOM into the Agent panel and the sidebar exits "into the light"
  (Web Animations API in app.js — it must not depend on CSS animations, because
  Windows "animation effects: off" = prefers-reduced-motion).
- **Explorer**: Workspace (the agents' folder; lazy tree) | PC (drives -> folders,
  read-only file view). "Use" on a PC folder makes it the workspace (settings
  `workdir`, `POST /api/workspace` needs header `X-NC: 1`). MEMORY.md lives in the
  data dir (`tools.MEMORY_PATH`), not the workspace, so switching folders keeps it.

## Backend API (keep event/field names stable, or change both sides at once)
`/api/branding /config /settings /models /skills /memory /tree /file /vm /system /tasks
/bus /subagents /connectors /targets /apps(+/launch,/docs/prefetch,/setup) /open-url
/fs/list /fs/read /workspace
/git/{status,diff,push} /chat(SSE) /approve`
SSE events: `token, tool_call, tool_result, approval, error, done`.

## Conventions
- Brandable only via `branding.json` — never hardcode the name/colors. Theme tokens
  live at the top of `style.css` (`--sky-*`, `--accent*`, `--ctp-*`).
- pywebview `js_api`: never keep the window (or any native object) in a PUBLIC
  attribute — pywebview walks public attributes recursively (the drag crash). Use `_window`.
- Runtime json (subagents/tasks/bus/connectors/targets/settings/apps, MEMORY.md, prompt.md) is
  gitignored; it's user data, written to `NightCrew-data/` next to the exe (Windows),
  `~/Library/Application Support/NightCrew` (macOS app), or the repo root (dev).
- No content filter is added; refusals come from model weights.
- Regenerate `preview_*.png` after a big visual change (rendered from the real CSS).
- Vanilla JS + Flask, no build step for the UI.
