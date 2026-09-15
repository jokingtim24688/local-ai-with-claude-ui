# BUILD PROMPT — give this to a fresh chat to recreate + install the AI

Copy everything below the line into a new coding chat. It fully specifies the
app, the local AI engine, the skills, and the VM stream. It builds a **native
desktop app** (pywebview, no Electron) that manages a local Ollama AI — no
terminal panel for the user.

---

## What to build

A Windows + macOS **native desktop app** (our own, **not Electron**) called
**Ai Heaven**. Use a pure-Python launcher (`pywebview`) that opens a native
window and hosts the Flask UI in-process — no Node, no browser chrome. Every
brand detail (name, logo, accent color, window size) lives in `branding.json`
and is applied live; nothing brand-related is hardcoded. It manages a local
coding agent that runs on **Ollama** (any pulled model). The app must look
hand-built, not AI-generated: a heaven theme — luminous dawn-sky background, gold accent (NOT
purple), **liquid-glass** chrome (`backdrop-filter` blur + translucent fill +
thin light border + soft shadow), **pill-shaped** buttons, spring-eased
micro-interactions, one orchestrated load reveal, and a subtle grain overlay.

### Three views, switched by a segmented control in the top-right

1. **Chat** — Claude-style centered chat. Streaming replies. Tool calls render
   as animated pill "chips" inline with their results. Glass composer pinned
   at the bottom. Prefix a message with `/web` to allow web tools that turn.
2. **Code** — three columns: a **file tree** of the sandbox, a **file viewer**,
   and a **live activity** feed that mirrors every tool call as the AI works.
   This is the "watch it code" view.
3. **VM** — a big glass **stream stage** showing the VM the AI runs in (VNC /
   MJPEG / WebRTC feed), plus controls (Start VM, Launch app, Stop) and an
   **app preview** pane that shows the app the AI launches and tests inside the
   VM. The user watches the AI build and test a real app here.

The segmented control (Chat / Code / VM) with a sliding glass "thumb" is the
top-right toggle — flip between normal chat and watching it code / run.

## Architecture

```
desktop.py           native launcher (pywebview): runs Flask in-thread, opens window
branding.json        name, logo, accent, window size — fully editable, no code
assets/logo.svg      swappable logo (also window icon)
app.py               Flask backend: Ollama bridge + tool loop + endpoints
tools.py             tool registry + sandbox jail (confine every file op)
web.py               web_search / web_fetch (only on /web turns)
static/              index.html, style.css, app.js  (the renderer / UI)
skills/<name>/SKILL.md   loadable skills (name+desc in prompt, body on demand)
workspace/           default sandbox — the AI is confined here
```

`desktop.py` (pywebview) loads `http://127.0.0.1:5173` (the Flask app) inside a
native window, so it presents as a real app. The Python backend bridges the
browser to the Ollama Python lib (the browser can't import it). There is also a
Claude-desktop-style **left sidebar** (chat history + New chat + search +
collapsible Skills/Memory/status) and a centered **home greeting** that gives
way to the thread once a conversation starts. Conversations persist in
`localStorage` (`aiheaven.convos`).

### Backend endpoints (Flask, `app.py`)

- `GET  /api/config`  → `{workdir, skills_dir, ollama}`
- `GET  /api/models`  → local Ollama tags via `ollama.Client().list()`
- `GET  /api/skills`  → scan `skills/**/SKILL.md`, return name+desc
- `GET  /api/memory`  → contents of `MEMORY.md`
- `GET  /api/tree`    → recursive file tree of the sandbox
- `GET  /api/file?path=` → read one sandboxed file
- `GET  /api/vm` / `POST /api/vm/action` → VM stream URL + start/launch/stop
- `POST /api/chat`    → **SSE stream**: events `token`, `tool_call`,
  `tool_result`, `approval`, `error`, `done`. Runs a native-tool-calling loop
  (cap ~12 iterations). Web tools appended only when the turn is `/web`.
- `POST /api/approve` → resolves a pending `approval` (threading.Event keyed by
  id) so gated tools wait for the user's Allow/Deny in the UI.

### Tools (`tools.py`) — all confined to the sandbox

`read_file`, `write_file`, `edit_file`, `list_dir`, `glob`, `grep`,
`run_command`, `load_skill`, `remember`. Every path resolves inside the work
dir; block `..`, absolute paths, and symlink escapes (resolve then
`Path.relative_to(sandbox)` and reject on `ValueError`). Gate
`write_file` / `edit_file` / `run_command` behind the approval modal unless a
yolo flag is set.

### System prompt (blunt, honest)

> You are a local coding agent on the user's machine. Be blunt and terse; no
> filler, no lecturing, no "as an AI". You have real tools — an action counts
> as done ONLY when a tool returns OK. Never claim you saved/ran/edited/found
> anything unless a tool result says so. All paths are relative to the work
> directory; you cannot escape it. Web tools exist only on `/web` turns.

No content filter is added by the app. Refusal behavior comes from the model
weights — use an uncensored tag (e.g. a Dolphin fine-tune) for fewer refusals;
a system prompt cannot remove training baked into weights.

## Design spec (make it look human-made)

- Heaven palette (light): text `--ink #33384a`, accent `--clay #c99a3a` /
  `--clay-soft #eac86f`, sky-white ground. NO purple/violet anywhere. Background
  is a luminous dawn gradient with drifting clouds + faint god-rays.
- Glass recipe on floating chrome only (sidebar, composer, panes, modal, VM
  stage): `backdrop-filter:blur(22px) saturate(150%)`,
  `background:rgba(255,255,255,.52)`, `border:1px solid rgba(255,255,255,.85)`,
  soft `box-shadow`. Body-text surfaces stay solid white for contrast. Provide a
  `@supports not (backdrop-filter)` fallback.
- Pills: gradient clay fill, inset top highlight, `:active{scale(.95)}`, spring
  easing `cubic-bezier(.2,.9,.25,1.15)`.
- Motion: staggered load reveal (topbar → rail → stage); messages fade-up;
  tool chips have a pulsing dot; view switch cross-fades + slides; blinking
  caret while streaming. One grain overlay via inline `feTurbulence`.
- Serif wordmark + serif home greeting (time-based, e.g. "Good evening. What
  shall we create?"), sans body. Composer is a rounded card with inline controls
  (model pill + Tools / Web toggle chips + a round ↑ send button). Real copy, not
  "No items yet".

## Skills (ship these; the app loads any `skills/<name>/SKILL.md`)

Include at minimum:
- **game-programming** — engines→languages, defensive anticheat, Lua/Python
  scripting.
- **vscode-windows-dev** — build/run/debug/compile commands on Windows + VCS.
- **web-research** — how to use `/web` search+fetch well.
- **blender-bpy**, **anticheat** as the user provides them.

A skill file is Markdown with optional `name:` / `description:` lines; the app
puts only name+description in the prompt and loads the full body on demand via
`load_skill`.

## The VM (where the AI actually runs)

Provision a VM (VirtualBox / QEMU-KVM / Vagrant / cloud). Install Ollama and
this app's backend inside it. Expose the VM's screen as a stream and set:

- `VM_STREAM`  → the VNC/MJPEG/WebRTC stream URL the VM view embeds
- `VM_APP_URL` → URL of the app the AI launches, for the preview pane
- `VM_HOOK_START` / `VM_HOOK_LAUNCH` / `VM_HOOK_STOP` → shell commands the VM
  controls run (start the machine, launch the app under test, stop it)

With none set, the VM view shows a clear "not configured" state instead of
faking a stream.

## Install / run

Ship it as a real standalone app, not loose scripts. Package `desktop.py` with
**PyInstaller** so it becomes one double-clickable file — no Python install:

```bash
pip install -r requirements.txt pyinstaller
python build.py            # runs: pyinstaller --noconfirm elysium.spec
# dist/Ai Heaven.exe  (Windows) | dist/Ai Heaven.app (macOS)
```

The spec bundles `static/`, `assets/`, `branding.json`, and default `skills/`
as read-only resources (served from `sys._MEIPASS`). Use a `paths.py` that
resolves bundled resources vs. a writable `AiHeaven-data/` folder created next
to the executable for `workspace/`, `skills/` (seeded from the bundle on first
run), and `MEMORY.md`. `desktop.py` starts Flask in a background thread on a
free port and opens a native `pywebview` window titled from `branding.json`;
no terminal is shown. Dev: `python desktop.py`. Requires Ollama installed +
a model pulled.

## Acceptance

- App opens as a native window, Ollama status dot goes green.
- Chat streams; a build request makes the AI call `write_file` / `run_command`
  (each gated by the Allow modal); files appear in the Code tree live.
- Code view shows the tree, file contents, and the live activity feed.
- VM view embeds the stream when `VM_STREAM` is set and the controls fire the
  `VM_HOOK_*` commands.
- No purple, real glass, pill buttons, spring motion — reads as hand-built.
