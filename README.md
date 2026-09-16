# local-ai-with-claude-ui

Desktop app to manage a local **Ollama** AI — no terminal required. Claude-style
UI, warm dark theme with a clay accent, liquid-glass chrome, pill buttons, spring
motion. A top-right toggle flips between three views:

- **Chat** — streaming chat with tool-call chips inline.
- **Code** — file tree + viewer + a live activity feed. Watch it code.
- **VM** — a stream of the VM the AI runs in, plus the app it launches and
  tests, with Start / Launch / Stop controls.

> Built in an environment that can't run it. Ships the full UI + backend +
> Electron shell wired to Ollama. See `BUILD_PROMPT.md` for the complete spec
> to recreate it and install the AI + VM in another chat.

Our own native app — **no Electron**. A pure-Python launcher (`pywebview`) opens
a native window; everything is ours to brand.

## Install (pick one)

- **One command, from source** — `install.bat` (Windows) or `./install.sh`
  (mac/Linux). Sets up a venv, checks Ollama, pulls a default model, launches.
- **A real installer** — build once (`python build.py`) then make a Setup wizard:
  Windows `installer/AiHeaven.iss` (Inno Setup) → `AiHeaven-Setup.exe`; macOS
  `installer/build_dmg.sh` → `Ai Heaven.dmg`. See `installer/README.md`.

## Get the app (one double-click, no Python)

Build the standalone app once, then just run it:

```bash
pip install -r requirements.txt pyinstaller
python build.py            # or: build.bat (Windows) / ./build.sh (mac/Linux)
```

Result in `dist/`:

- **Windows** → `dist/Ai Heaven.exe`
- **macOS** → `dist/Ai Heaven.app`
- **Linux** → `dist/Ai Heaven`

Ship/keep that one item. It needs no Python install. It creates an
`AiHeaven-data/` folder next to itself for `workspace/`, `skills/`, and memory.
(A platform webview runtime is used: WebView2 on Windows — usually preinstalled;
WebKitGTK on Linux; WKWebView on macOS — built in.)

You still need **Ollama** installed and a model pulled:

```bash
ollama serve
ollama pull qwen2.5-coder:7b   # or any coding / uncensored tag
```

## Dev run (no packaging)

```bash
pip install -r requirements.txt
python desktop.py              # native window; backend runs in-process
# or backend only, in a browser at http://localhost:5173:
python app.py
```

## Make it yours

Everything is in **`branding.json`** — no code changes:

```json
{ "name": "Local AI", "tagline": "...", "accent": "#d9795b",
  "accent_soft": "#e39a80", "logo": "assets/logo.svg",
  "window": { "width": 1280, "height": 820 } }
```

Change the name, swap `assets/logo.svg`, set the accent color. The window title,
wordmark, logo, and theme all follow it live.

## Layout

```
desktop.py         app entry — native launcher (pywebview); PyInstaller target
build.py           builds the standalone app (build.bat / build.sh wrappers)
elysium.spec       PyInstaller spec (bundles Python, UI, skills, branding)
paths.py           bundled-resource vs writable-data path resolution
branding.json      name, logo, accent, window size — fully yours
assets/logo.svg    swappable logo
app.py             Flask: branding, models, chat SSE, tool loop, tree, VM, approval
tools.py           tool registry + sandbox jail
web.py             web_search / web_fetch (only on /web turns)
static/            index.html, style.css, app.js  (the UI)
skills/            <name>/SKILL.md  (seeded into AiHeaven-data on first run)
workspace/         dev sandbox (packaged app uses AiHeaven-data/workspace)
```

## VM stream

Set these env vars before launch (see `BUILD_PROMPT.md`):

- `VM_STREAM` — VNC/MJPEG/WebRTC URL embedded in the VM view
- `VM_APP_URL` — URL of the app the AI launches, for the preview pane
- `VM_HOOK_START` / `VM_HOOK_LAUNCH` / `VM_HOOK_STOP` — shell commands the VM
  controls run

Unset → the VM view shows a clear "not configured" state, never a faked stream.

## Notes

- Sandbox jail confines every file op to the work dir (`..`, absolute paths,
  symlink escapes blocked). Writes / edits / shell commands ask first.
- No content filter is added. Refusals come from the model weights — a system
  prompt can't remove them; pick an uncensored tag for fewer.
