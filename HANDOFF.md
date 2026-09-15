# HANDOFF — read me before working on this repo

Two chats are building this together. This note says what exists, how it fits,
and the contracts to keep so we don't break each other. Branch:
`claude/amazing-keller-dvibe7`.

## What this is
**Ai Heaven** — a native desktop app (our own, not Electron) to run and manage a
local coding AI on **Ollama**. Claude-desktop-style UI with a heaven theme.
Packaged to one double-click app with PyInstaller. We can't test it in the build
env, so it's coded to be correct and shipped as UI + backend.

## Architecture (how the pieces talk)
```
desktop.py   ← app entry. Seeds user data, picks a free port, starts Flask in a
               background thread, opens a native pywebview window. PyInstaller
               target.
app.py       ← Flask backend. Serves the UI + JSON/SSE API. Ollama bridge +
               agent tool loop.
tools.py     ← tool registry + SANDBOX jail (all file ops confined to workdir).
web.py       ← web_search / web_fetch, only used on /web turns.
paths.py     ← resolves bundled resources (sys._MEIPASS) vs writable
               AiHeaven-data/ (workspace, skills, MEMORY.md) next to the exe.
static/      ← the UI: index.html, style.css, app.js (vanilla, no framework).
skills/      ← <name>/SKILL.md, seeded into AiHeaven-data/skills on first run.
branding.json← name/logo/accent/window. Currently name = "Ai Heaven".
elysium.spec ← PyInstaller build (auto-detects Windows→.exe / macOS→.app).
```

## Subagents + shared agent bus (multi-VM collaboration)
- Subagents are named helpers with their own system prompt / model / skills, and
  optionally their **own VM** (`sub.vm.stream`). Stored in
  `AiHeaven-data/subagents.json`. The main agent delegates with the
  `spawn_subagent(name, task)` tool (added to its schema only when subagents
  exist). `run_subagent()` runs a nested tool-loop autonomously (no approval
  modal) but **inside the same sandbox** = shared storage.
- Agents (main + subs) collaborate over a **shared bus** (`bus.json`) with tools
  `send_agent_message(to,text)` / `read_agent_messages()`. Model: "different PCs
  (VMs), same data (shared workspace), talk over the bus."
- Real multi-VM provisioning is the piece still to build: give each subagent its
  own VM (VirtualBox/QEMU/cloud), mount the SAME shared workspace into each, run
  a backend instance per VM, and point `sub.vm.stream` at each VM's feed. The VM
  tab already renders one screen per agent from `/api/vm`.

## Backend API contract (don't rename without updating app.js)
- `GET/POST /api/subagents`, `DELETE /api/subagents/<id>` — subagent CRUD.
- `GET/POST /api/bus` — shared agent message bus.
- `GET  /api/branding` → {name, tagline, accent, accent_soft, logo}
- `GET  /api/config`   → {workdir, skills_dir, ollama}
- `GET  /api/models`   → {models:[tag,...], error?}
- `GET  /api/skills`   → {skills:[{name,desc},...]}
- `GET  /api/memory`   → {memory}
- `GET  /api/tree`     → {tree:[{name,path,dir,children?}]}
- `GET  /api/file?path=` → {path, content, error?}
- `GET  /api/vm` / `POST /api/vm/action {action}` → {stream,status,app_url}
- `POST /api/chat` → **SSE**. Events: `token`(str), `tool_call`{name,args},
  `tool_result`{name,result}, `approval`{id,tool,args}, `error`(str), `done`.
  Request body: {model, messages:[{role,content}], web, tools, ask}.
- `POST /api/approve {id, allow}` → resolves a pending approval (threading.Event).

## UI notes
- Vanilla JS in `static/app.js`. Client state in `localStorage`:
  `aiheaven.convos` (chats: title, messages, projectId, archived),
  `aiheaven.projects` (groups), `aiheaven.instructions` (custom instructions
  prepended as a system msg). Chats support rename / archive / delete / move-to-
  project via a right-side ⋯ menu; a "Archived" toggle switches the Recents list.
- Views: Chat / IDE (code) / VM chosen from a **top-right dropdown** that shows
  the current view. Chat "home" (centered greeting) vs "chatting" via the `home`
  class on `#chat-view`.
- **Customize** modal (gear in the sidebar foot) holds tabs: Skills, Subagents
  (CRUD + own-VM stream field), Instructions, Memory, About. This is where the
  clutter moved out of the sidebar.
- Design: heaven skin — dawn-sky bg, gold (`--clay #c99a3a`) accent, frosted
  glass on chrome, pill/spring motion. NO purple. Keep it hand-built, not
  templated. See the anti-vibe-polish guidance.

## Known stubs / real edges
- **Ollama**: real. Backend uses the `ollama` python lib. UI stays usable if the
  lib/daemon is missing (models list shows an error, chat reports it).
- **VM view**: wiring is real but needs env vars — `VM_STREAM`, `VM_APP_URL`,
  `VM_HOOK_START/LAUNCH/STOP`. Unset → shows a clear "not configured" state.
- **Refusals**: no content filter is added; refusal behavior lives in the model
  weights. Pick an uncensored tag for fewer.

## Build / run
- Dev: `pip install -r requirements.txt` then `python desktop.py`
  (or `python app.py` for the backend in a browser at :5173).
- Ship: `python build.py` (or build.bat / build.sh) → `dist/Ai Heaven.exe` on
  Windows, `dist/Ai Heaven.app` on macOS. One file per OS (can't be one binary
  for both). Needs Ollama installed + a model pulled.

## Working agreement
- Keep the API event/field names above stable, or change both sides in one go.
- Keep everything brandable via `branding.json` — don't hardcode the name.
- Preview images live in the repo root (`preview_*.png`); regenerate them after
  a big visual change (or every third change).
- `PROGRESS.md` is the running restore log; append, don't rewrite.
