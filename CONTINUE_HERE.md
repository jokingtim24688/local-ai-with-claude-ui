# >>> ACTIVE: ENGINE BRIDGE (user prompt was cut off after Component 1) <<<
Goal: OpenSCAD + UE5 + UEFN/Verse + Roblox bridge for a 3B lead (qwen2.5-coder:3b),
dynamic skill loader, execution tags, JSON plans, CLI.
- [x] skill_router.py, exec_tags.py, engines.py, apps.py registration
- [ ] skills: openscad-cad, fortnite-map-maker, roblox-obby-builder, unreal-level-layout (+triggers on old ones)
- [ ] app.py: routed skills in lead + worker prompts, domain tool filtering, exec tags -> calls,
      auto-checks (.scad compile, .verse lint, plan validate), specialists openscad/fortnite
- [ ] nightcrew_cli.py, docs/ENGINE_BRIDGE.md, tests, commit/push

# >>> LATEST (2026-09-27) — resume here <<<
Last pushed: ef0fae3 "Make the lead act instead of printing JSON or instructions".
User reported the lead printing tool-call JSON / instructions (they were on a qwen
model; screenshots showed llama3.2:3b too). Fix shipped: toolcalls.py + lean lead +
app_control/open_url/unreal_quick_level/blender one-shot. NOT yet verified on the
user's PC. Next: read the user's queued prompt; if tool calls still fail, check which
qwen tag they use (qwen2.5-coder's Ollama template emits text calls; qwen3 / qwen2.5
instruct use real tool calls) and look at update.log + the chat output.
Open item: PR #1 README conflict — still waiting on the user's choice.

# >>> REWORK 2 (IDE + connectors + auto-setup) — DONE, see PROGRESS.md PIVOT 20 <<<
User asked: remove VM + Terminal tabs (agents keep running in the background);
IDE view looks like Google Antigravity (explorer | editor tabs | agent chat panel on
the right — the chat REPLACES "Live activity"); opening the IDE closes the sidebar
with a "going into the light" animation; connectors always on but only used when a
chat asks for one — asked once -> saved as per-chat temporary instructions; on start
the app checks Roblox Studio + Unreal Engine, installs if missing, launches them in
the background.
- [x] backend: per-chat connectors (/api/chat body.connectors), settings
      auto_setup/launch_on_start, apps auto-setup thread + /api/apps/setup
- [x] UI: drop VM/Terminal views, Antigravity IDE layout, sidebar light animation,
      chat moves into IDE agent panel, per-chat connector chips, setup banner
- [x] previews, docs, commit, push
Redo recipe: read this, `git log --oneline -10`, continue first unchecked item.

# >>> REWORK 2026-09-26 — DONE (see PROGRESS.md PIVOT 19) <<<
User asked: (1) Mac + Windows app, (2) agents manage Unreal Engine, Blender,
Roblox Studio + public docs for each, (3) theme: midnight app + Catppuccin
("cappuccino") code colors, (4) keep subagents but they run LOW-POWER coder models
that write code / 3D-model scripts; the parent (main) DEBUGS after each one finishes.
Checklist (tick in git log / PROGRESS.md PIVOT 19):
- [x] desktop.py: fix drag crash (js_api must not expose window -> Api._window),
      mac traffic-light controls, ollama discovery on mac/win
- [x] paths.py: mac data dir ~/Library/Application Support/AiHeaven when frozen
- [x] apps.py: detect Blender/Unreal/Roblox (win+mac), tools blender_run,
      unreal_run_python, unreal_uat, roblox_open, rojo, luau_check, app_launch,
      app_status, fetch_docs (whitelisted official docs + disk cache)
- [x] skills: blender-python, unreal-engine, roblox-studio (condensed public docs + links)
- [x] app.py: worker_model (default qwen2.5-coder:3b), specialists blender/unreal/roblox,
      post-run auto checks (compile/json/node/luau) + "PARENT: debug now" handoff,
      /api/apps endpoints, main-only app tools (gated)
- [x] UI: midnight theme rewrite of static/style.css, Catppuccin code blocks,
      static/hl.js highlighter, markdown code fences in chat, Apps tab in Customize
- [x] logo: crescent mark -> assets/logo.svg, icon.ico, icon.icns
- [x] build_mac.sh (+ nuitka mac flags), docs (CLAUDE.md, PROGRESS.md), previews
Redo recipe: read this list, `git log --oneline -15`, continue the first unchecked item.

# CONTINUE HERE — Ai Heaven handoff

Pick this up in a fresh chat. Branch: `claude/amazing-keller-dvibe7`.
Repo: `jokingtim24688/local-ai-with-claude-ui`. Dev in cloud sandbox (no PC access);
user pulls + runs/builds on their own Windows PC and pastes screenshots/console.

## What the app is
Native desktop app (pywebview frameless window + Flask backend, vanilla JS UI in
`static/`). Runs a local coding-agent pool on Ollama. Heaven theme, gold accent.
Parent = 2 models (prompt-maker + skill-maker) managing subagents (buddy, designer,
researcher, tester, reviewer, porter) via shared prompt.md, task board, agent bus.
See CLAUDE.md, HANDOFF.md, VM_DESIGN.md, PROGRESS.md.

## Done this session
- **Grok-bot avatars** (PIVOT 17). Each VM-tab agent = a tintable inline-SVG cloud
  face w/ two eyes, distinct color per pool slot. Working = eyes dart around; idle =
  eyes shut + greyed. Parent tool `set_avatar(name, pose)` (look/sleep/happy/think/
  alert/auto). Code: `grokAvatar()` + `screenCard()` in `static/app.js`; `.gbot`
  CSS + keyframes in `static/style.css`; backend `_avatar_color`/`_avatar_pose`/
  `set_avatar`/`AVATAR_POSE` in `app.py`, surfaced in `/api/vm` (`color`,`pose`).
  (The user's uploaded Grok PNGs are NOT reachable from the cloud sandbox — they
  live only in chat — so the face is drawn in code. Same look, animates + tints.)
- **Desktop window fixes**: force `gui="edgechromium"` in `desktop.py` (MSHTML
  fallback was freezing the window), whole top bar draggable (`pywebview-drag-region`
  on `.spacer` in `static/index.html`), set Windows AppUserModelID + pass icon to
  the window. Exe/folder icon flags already correct (`build_nuitka.py`
  `--windows-icon-from-ico`, `elysium.spec`); needs a rebuild + Windows icon-cache
  refresh to show.

## FIXED (PIVOT 19) — was: **Dragging the window from the top bar crashes with a Python `RecursionError`:**
console spams `Empty.Empty.Empty.…: maximum recursion depth exceeded`.

- Trigger: user grabbed the titlebar drag region and the window died.
- The `Empty.Empty.…` chain is pywebview's js_api bridge (pythonnet/.NET
  `Empty` objects) recursing — almost certainly the drag handling path on the
  edgechromium backend, likely interacting with our custom `Api` js_api object
  or the `pywebview-drag-region` + `easy_drag=False` combo.
- Files: `desktop.py` (`Api` class, `webview.create_window(..., frameless=True,
  easy_drag=False, js_api=api)`, the `webview.start(gui="edgechromium", ...)` call)
  and `static/index.html` (`.titlebar`, `.tb-brand`/`.spacer` drag regions).

### Things to try
1. Reproduce: `python desktop.py`, drag the top bar. Capture full traceback (the
   recursion likely originates in pywebview's `edgechromium`/`js_bridge` — run with
   `debug=True` in `webview.start` to see the real stack).
2. Suspect the **js_api serialization**: pywebview may try to JSON-serialize the
   `Api` object or a return value on drag and recurse. Ensure `Api` methods return
   `None`/plain values, never `self` or the window. They already return None —
   double check nothing implicitly returns the window.
3. Try **`easy_drag=True` + remove the `pywebview-drag-region` classes** (native
   easy_drag instead of CSS regions) and see if the crash goes away. If easy_drag
   drags from everywhere (incl. buttons/inputs), scope it or re-add regions.
4. Check pywebview version pin (`requirements.txt` has `pywebview>=5.0`); a known
   drag/recursion bug may be version-specific — pin a known-good version.
5. If edgechromium drag is the culprit, consider a **JS-driven move** via the
   js_api (`api.start_drag()` on `mousedown` calling `window.move`) instead of the
   built-in drag region.
6. Verify WebView2 Runtime is installed on the PC (Win11 usually has it).

## How the user runs it (their Windows PC)
```
cd /d "%USERPROFILE%\Desktop\local-ai-with-claude-ui"
git pull origin claude/amazing-keller-dvibe7
python desktop.py                          # quick test
call buildenv\Scripts\activate && python build_nuitka.py --desktop   # real exe
```
Every new CMD window: run the `cd /d` line first. Commit msg footer:
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: <session url>
```
User preference: reply caveman-brief. Save progress every 5 min to a file with
redo instructions.
