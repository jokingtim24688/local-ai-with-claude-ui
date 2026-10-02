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
**Auto-updating shortcut** (closes any Night Crew already running first, via
`launcher.close_running()` — two copies would fight over the port and chats.json):
`python make_shortcut.py` once -> Desktop + Start-menu
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
skill_router.py dynamic skill loader: frontmatter `domain`/`triggers` -> routed skills
exec_tags.py   ```<lang> file=<path> run``` blocks -> write_file + engine step
scraper.py     web_scrape tool (trafilatura -> markdown, SSRF-guarded)
mcp_servers/   OUR MCP server per app (blender/unreal/roblox/openscad/fortnite, 60 tools):
               `--mcp <name>`, registered as built-in connectors (docs/MCP_SERVERS.md)
live.py        live bridges: Blender add-on :9876, Roblox plugin queue :9877, UE Remote Control :30010
bridges/       the in-app halves: Blender add-on (.py), Roblox Studio plugin (.lua)
integrations.py + telegram_bridge.py + gmail_listener.py + google_auth.py + vault.py: owner-locked Telegram bot, read-only Gmail watcher (Sign in with Google), secrets in OS keychain (docs/INTEGRATIONS.md)
vision.py      image attachments: save to workspace/attachments, native or described-by-vision-model
context.py     collapse old tool output, trim old turns
engines.py     OpenSCAD, UEFN/Verse (lint, islands), terrain heightmaps + scatter,
               Roblox .rbxlx/obby, UE5 templates + layout plans, run_plan
nightcrew_cli.py  every engine step as a terminal command (--workspace for VMs)
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
- **Engine bridge** (docs/ENGINE_BRIDGE.md): 3B models answer with execution tags or JSON
  plans (kinds ue_layout/obby/island/terrain) instead of big API code; the lead's prompt
  gets the routed `# ACTIVE SKILL` and a tool menu filtered to that domain
  (`lead_app_tools`). Skill templates are verified (OpenSCAD compiles, Verse lints clean).
- App tools (Blender/Unreal/Roblox) are **MAIN-only**; the ones that run code or launch
  programs need approval unless Auto is on. Paths: sandbox + user-registered project
  folders (`apps.json`) only. `num_ctx` 16384 default (setting `num_ctx`) for MAIN and workers; old tool output is collapsed and old turns trimmed (`context.py`).
- When the app starts Ollama itself, it sets `OLLAMA_MAX_LOADED_MODELS=1`,
  `NUM_PARALLEL=1`, `FLASH_ATTENTION=1`, `KV_CACHE_TYPE=q4_0` (the user's env wins).
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
- **Commands and deletes never leave the workspace.** `run_command(command, cwd, timeout)`
  and `gradle(task, project)` both resolve through `tools._jail`, and gradle's walk-up for
  gradlew stops at the workspace root; `delete_file(path, recursive)` refuses the workspace
  itself. To build a real project the user points the workspace at it (IDE -> PC -> Use).
  Reading (read_file/list_dir/glob/grep) may still reach registered project folders. All gated.
- **Unverified "I built it" is flagged mechanically.** The prompt rule alone did not hold
  (an 8B lead kept claiming it finished a Minecraft mod). The loop tracks `ran_ok` (any tool
  result not starting error/FAILED/blocked); if nothing succeeded and
  `toolcalls.claims_work_done(reply)` matches a completion claim ("I have created…",
  "has been built", "your mod is ready"), the loop FORCES one more round ("You called NO tool
  … call the tool now") and only then gives up with a ⚠. Both messages report how many tools
  were offered and whether native or text tool calling was used, so it is obvious whether the
  app or the model is at fault. Claims are judged per sentence; plans never match.
- **Repeated tool calls**: small leads get stuck calling one tool with identical arguments
  (classically `remember`). The same (tool, args) is executed ONCE per turn; a repeat returns
  "already called, nothing changed — answer now", and a second repeat ends the turn with a
  note. Workers have the same guard. Nothing is ever run twice.
- **Thinking models** (Qwen3 and friends): `think` is sent ONLY to models whose Ollama
  capabilities list `thinking` (sending it to others makes Ollama reject the request), and
  it defaults to OFF (setting `think`, toggle in Customize -> Apps) because a thinking model
  can burn a whole turn reasoning and return empty content. `message.thinking` is collected
  separately; a turn NEVER ends with an empty bubble — the loop says what happened instead.
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
/fs/list /fs/read /workspace /chats /integrations /google/{signin,signout} /bridges
/git/{status,diff,push} /chat(SSE) /approve`
SSE events: `token, tool_call, tool_result, approval, image_note, error, done`.
Images: composer paste/attach/drop -> `/api/chat` message `images`; `vision.py` gives them natively to a vision lead or has the `vision_model` describe them for a text-only lead.

## Conventions
- Brandable only via `branding.json` — never hardcode the name/colors. Theme tokens
  live at the top of `style.css` (`--sky-*`, `--accent*`, `--ctp-*`).
- pywebview `js_api`: never keep the window (or any native object) in a PUBLIC
  attribute — pywebview walks public attributes recursively (the drag crash). Use `_window`.
- Window dragging is OURS, not pywebview's: `pywebview-drag-region` does nothing on the
  WebView2 backend, so `#titlebar` pointer events call `Api.drag_start/drag_move`, which
  `window.move()`s from the start position (rAF-throttled, pointer capture, dblclick =
  maximize). Keep every drag attribute underscore-private.
- Runtime json (subagents/tasks/bus/connectors/targets/settings/apps/chats, MEMORY.md, prompt.md) is
  gitignored; it's user data, written to `NightCrew-data/` next to the exe (Windows),
  `~/Library/Application Support/NightCrew` (macOS app), or the repo root (dev).
- No content filter is added; refusals come from model weights.
- Regenerate `preview_*.png` after a big visual change (rendered from the real CSS).
- Chats/projects/instructions live in `chats.json` in the data dir, NOT in browser
  storage: the window's port can change between launches and localStorage is keyed by
  origin, so browser-stored chats disappeared. `GET/POST /api/chats` (POST needs `X-NC: 1`).
- Vanilla JS + Flask, no build step for the UI.
