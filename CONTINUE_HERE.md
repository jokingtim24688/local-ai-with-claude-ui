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

## OPEN BUG — fix this next
**Dragging the window from the top bar crashes with a Python `RecursionError`:**
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
