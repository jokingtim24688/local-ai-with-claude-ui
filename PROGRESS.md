# PROGRESS / RESTORE FILE

If context lost, read this. Redo exactly what is here.

## Task
Build web UI for local Ollama coding agent (from prior CLI `ollama-agent`).
Cannot run/test in this env. Ship clean, coherent UI + backend.
Branch: `claude/amazing-keller-dvibe7`. Repo: jokingtim24688/local-ai-with-claude-ui.

## User rules
- Caveman replies. No articles, no filler. Short. Direct. Code speaks.
- Do NOT reply to self / acknowledge loops.
- Save progress every 5 min to this file with redo instructions.

## PIVOT 5: subagents + multi-VM + Claude org features
- Subagents: /api/subagents CRUD (subagents.json), spawn_subagent tool, nested
  run_subagent loop (autonomous, shared sandbox). Each can have own VM (vm.stream).
- Shared agent bus: /api/bus + send_agent_message/read_agent_messages tools.
  "different VMs, same storage, talk over bus." (real multi-VM provisioning = TODO)
- /api/vm now returns agents[] -> VM tab shows a screen per agent + bus feed.
- Sidebar decluttered: Projects (groups) + Recents + Archived toggle; per-chat ⋯
  menu (rename/archive/delete/move). Skills+Memory+Subagents+Instructions moved
  into a Customize modal. localStorage: aiheaven.convos/projects/instructions.
- Top-right view switch is now a DROPDOWN showing current view (Chat/IDE/VM).
- Images: preview_chat.png, preview_ide.png, preview_vm.png (dropped preview_code).

## PIVOT 4: Claude-desktop layout + rename "Ai Heaven"
- New shell: left sidebar (chat history via localStorage `aiheaven.convos`,
  New chat, search, collapsible Skills/Memory/status), centered home greeting,
  composer card with model pill + Tools/Web chips + round ↑ send. Views segmented
  top-right. index.html + style.css + app.js rewritten; heaven skin kept.
- App name = "Ai Heaven" (branding.json). paths APP_NAME=AiHeaven -> AiHeaven-data.
- spec builds "Ai Heaven.exe"/"Ai Heaven.app", auto-detects OS (win/mac only).
- HANDOFF.md written for the second chat (API contracts, structure, agreement).
- STANDING RULE: regenerate preview_chat.png + preview_code.png after any big
  visual change (or every 3rd change). Rendered via headless chromium at
  /opt/pw-browsers, previews built in scratchpad from real style.css.

## PIVOT 3: real standalone app (no running .py)
- PyInstaller: elysium.spec + build.py + build.bat/build.sh -> dist/Elysium(.exe/.app).
- paths.py: RES_DIR (sys._MEIPASS bundled static/assets/branding/skills) vs
  DATA_DIR (AiHeaven-data next to exe: workspace, skills seeded, MEMORY).
- app.py uses paths.res/paths.data; branding+assets allow user override next to app.
- desktop.py = entry, seeds data, picks free port, opens pywebview window.
- Needs Ollama installed + platform webview runtime. gitignore build/ dist/ data.

## PIVOT 2: no Electron -> our own native app
- Dropped electron/, package.json. Use pywebview native window `desktop.py`.
- Full branding via branding.json (name, logo, accent, window). /api/branding
  + /assets/<f>. Renderer applies name/logo/accent live. Swap assets/logo.svg.
- python desktop.py = start Flask in thread + native window. Browser fallback.

## PIVOT (latest direction)
NOT a web app. Electron **desktop app** cloning Claude UI.
- top-right segmented toggle: Chat / Code / VM (the "edit" toggle).
- Code view = file tree + viewer + live activity (watch it code).
- VM view = stream of AI's VM + app it launches/tests, Start/Launch/Stop.
- No cmd panel for user. Full working app to manage the AI.
- Design: liquid glass, pill buttons, spring animations, clay accent (NO purple),
  grain, load reveal. Human-made feel. (anti-vibe-polish skill applied.)
- Deliverable also: BUILD_PROMPT.md = full prompt to give another chat to
  recreate + install AI + VM. Ship skills.
Files added for pivot: package.json, electron/main.js, electron/preload.js,
BUILD_PROMPT.md, rebuilt static/*, extra skills. Backend gained /api/tree,
/api/file, /api/vm, /api/vm/action.

## Plan (original web version, now wrapped by electron)
1. Flask backend `app.py` -> wraps ollama python lib.
   - GET /api/models       list ollama tags
   - POST /api/chat        stream reply, run tool loop
   - GET /api/skills       scan skills/**/SKILL.md
   - POST /api/tool/approve gate writes/commands
   - sandbox jail on file ops (workdir confine)
2. Frontend static/ : index.html + style.css + app.js
   - chat window, streaming
   - model dropdown
   - mode toggle chat/tool
   - /web toggle
   - skills sidebar
   - tool-call log (-> write_file OK lines)
   - workdir + sandbox indicator
   - memory panel
   - approval modal for writes/commands
3. tools.py  -> tool registry + sandbox guard (reused by backend)
4. requirements.txt, README.md

## Build order (redo steps)
- [x] inspect repo (empty, README only)
- [x] tools.py
- [x] web.py
- [x] app.py
- [x] static/index.html
- [x] static/style.css
- [x] static/app.js
- [x] requirements.txt + .gitignore
- [x] README.md
- [x] sample skill + workspace/.gitkeep
- [x] py_compile + node --check pass
- [x] commit + push branch

## Notes
- Ollama REST at http://localhost:11434 (browser cannot import python lib; backend bridges).
- No content filter added; refusals come from model weights.
- Approval gate on write_file/edit_file/run_command unless yolo.

## PIVOT 6: roles + MCP connectors + per-tab settings + VM auto-shrink
- Main = BUILDER; seed default subagents designer/researcher/tester (seed_default_subagents).
- connectors.py = MCP client bridge (mcp SDK, fail-closed). connectors.json + CRUD
  endpoints. mcp__server__tool appended to main + subagent loops; gated by approval.
- Customize -> Connectors tab with catalog of Claude's connectors (one-click add,
  user auths own account; cannot export Claude's live servers/creds).
- Per-tab ⚙ in view dropdown (Chat->Instructions, IDE->Skills, VM->Connectors).
- VM grid cols = ceil(sqrt(n)) so cards shrink as agents added; uniform square cards.
- Images: preview_vm.png (updated), preview_connectors.png.

## PIVOT 7: full skill library + Auto mode
- 26 skills in skills/ (seeded to every agent): app-control, spotify-control,
  ollama-ops, desktop-automation, music-player-dev, mcp-builder, docx/pdf/pptx/xlsx,
  game-dev-3d, model-training, reverse-engineering, skill-creator, vm-orchestration,
  frontend-polish, data-viz, ui-design, claude-api, internal-comms, morning-brief,
  learn, code-review + existing game-programming/vscode-windows-dev/web-research.
- Composer "Auto" chip -> ask=false (run commands hands-free for home automation).
- Scenario "start spotify + ollama + build music player" now covered by skills;
  run_command launches apps (only file paths sandboxed, not process launch).

## PIVOT 8: parent+prompt-creator, dolphin pool, skill-creator, shared prompt, task board
- Main = PARENT + PROMPT CREATOR: writes prompt.md (injected into every agent's
  system prompt via read_prompt), breaks into add_task, helps subagents.
- Dolphin pool (dolphin3:8b) default subagents: skill-creator, buddy, designer,
  researcher, tester, reviewer. (only seeds on fresh subagents.json)
- skill-creator: create_skill(name,desc,body) writes skills/<name>/SKILL.md AND
  re-scans so it's live for all agents. Schemas in main + subagent loops.
- Task board (tasks.json): add_task/list_tasks/claim_task(≤2)/complete_task/
  review_task(approve|redo). /api/tasks. redo re-queues for another agent.
- Skills added: shared-prompt, task-orchestration, agent-comms (3P bus updates).
- UI: Task board panel in VM side (status dots) + theme polish (contrast, gold,
  focus rings). Image: preview_vm.png updated.

## PIVOT 9: parent=2-in-1 (prompt+skill), capacity-aware scaling
- Parent = two models one VM: prompt-maker + skill-maker. Removed skill-creator
  subagent (parent makes skills via create_skill). Pool: buddy/designer/researcher/
  tester/reviewer (dolphin3:8b).
- System load: system_load() (psutil CPU/RAM + nvidia-smi GPU). /api/system.
  Tool get_system_load for parent (check before spawning).
- Capacity control: disable_agent(name)/enable_agent(name) tools (parent only).
  Disabling re-queues that agent's 'doing' tasks (auto-reassign). spawn refuses
  disabled agents. subagent 'enabled' flag; /api/vm returns enabled + system.
- UI: System load meters (CPU/RAM/GPU, warm/hot) + disabled agent card (greyed)
  in VM tab. requirements += psutil. Image: preview_vm.png.

## PIVOT 10: per-agent prompt slices, idle-pause, affirmations, VM design
- prompt.md format = `name: task` lines + `all:` lines. read_prompt_for(who) feeds
  each subagent only its lines (+all); parent sees whole. Parent prompt updated.
- Runtime state per agent (from task board): active/paused/disabled. Idle=paused.
  sync_machines tool suspends idle agents' VMs (vm.suspend hook) + resumes working
  ones (vm.resume). /api/vm returns runtime + system load. UI shows paused (blue) vs
  disabled (red), running/paused counts.
- Auto-affirmation: reviewer approve -> parent posts "Great job ..." to the doer.
- VM_DESIGN.md: split thinking(host Ollama)/working(per-agent VM); Multipass Ubuntu
  24.04, shared mount, multipass exec for run_command, suspend/start to breathe;
  VirtualBox/Hyper-V/QEMU/WSL/Docker alternatives. Remaining bridge: route
  run_command through multipass exec for VM-backed agents.

## PIVOT 11: parent second-review + pool skill grant; smarter model
- Reviewer redo now counts task.redos; at >=2 it pings the parent on the bus.
- Parent does a SECOND review: if an agent keeps missing, create_skill once then
  grant_skill(name) -> appends the skill to EVERY subagent's preloaded skills
  (grant_skill_to_all), so the pool keeps it and nobody remakes it. Parent-only tool.
- Pool model swapped dolphin3:8b -> hermes3:8b (POOL_MODEL): smarter + best tool-
  calling, lightly aligned, ~same RAM. Per-agent model still overridable.

## PIVOT 12: Terminal mode + git changes + push targets
- 4th view in the top-right dropdown: Terminal (simple mono console; shares the
  conversation, renders plain lines). wireTerminal/termSend in app.js.
- File changes: /api/git/status + /api/git/diff; Changes panel shows live diff.
- Targets (targets.json): /api/targets CRUD; picker in terminal bar. Type repo
  (git url+branch) or file (path). /api/git/push does add/commit/push to the repo
  target (git init if needed; creds via user's git helper / token-in-url).
- Image: preview_terminal.png.

## PIVOT 13: polish pass (anti-vibe)
- New logo (halo + wings, no weird head); assets/icon.ico generated → real exe icon
  (spec already wires it). desktop.py auto-starts `ollama serve` if installed.
- Sharper: grain .5→.14, glass blur 22→10px, solid-ish panels; text crisp.
- View switcher: dropdown → animated segmented (Chat/IDE/VM/Terminal) with sliding
  indicator. moveInd/selectView/wireViews rewritten.
- Collapsed sidebar = mini rail (#rail-mini): logo, ☰ expand, + new chat, ✦ settings,
  green/red ollama dot. wireCollapse.
- Settings modal: click-off + Esc to close, scrollbar hidden, blur lowered, cream
  panes (not white).
- Model pill filtered to hermes/dolphin only. mini-dot mirrors ollama status.
- Images: preview_chat.png (repolished), preview_collapsed.png.

## PIVOT 14: Nuitka (real compiled exe)
- Added build_nuitka.py + build_nuitka.bat: Nuitka --standalone --onefile compiles
  desktop.py to a native binary (true machine code, not interpreter-bundled like
  PyInstaller). Icon baked in; static/assets/skills/branding.json included.
- paths.py: FROZEN now also true under Nuitka ("__compiled__" in globals()); DATA_DIR
  uses dirname(sys.argv[0]) so AiHeaven-data lands next to the real exe for both.

## PIVOT 15: custom exe icon + custom operation (title) bar
- assets/icon.ico regenerated as a real MULTI-SIZE ICO (16/24/32/48/64/128/256)
  from logo.svg → exe/taskbar/window show the angel-wing icon, not Python's.
- desktop.py: window is now frameless=True with a js_api (Api.minimize/
  toggle_maximize/close driving webview window).
- static/index.html: custom .titlebar (logo + "Ai Heaven" + min/max/close);
  .tb-brand has pywebview-drag-region for moving the frameless window.
- style.css: title bar theme + body flex column; .shell flex:1, .main height:100%
  so content sits below the 40px bar.
- app.js wireTitlebar(): buttons call window.pywebview.api.*; controls revealed on
  pywebviewready (hidden in plain browser). Image: preview_titlebar.png.
