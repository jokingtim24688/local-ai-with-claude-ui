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
