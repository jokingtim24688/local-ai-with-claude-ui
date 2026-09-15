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

## Run

```bash
pip install -r requirements.txt   # flask, ollama, pywebview
ollama serve                      # if not running
ollama pull qwen2.5-coder:7b      # or any coding / uncensored tag
python desktop.py                 # opens the native app window
```

`desktop.py` starts the Flask backend in-process and opens the window. No cmd
panel is shown to the user. Without `pywebview` it falls back to the browser.

Run the backend alone (browser at http://localhost:5173):

```bash
python app.py --workdir ./workspace --skills ./skills
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
desktop.py         native launcher (pywebview) — our own app window
branding.json      name, logo, accent, window size — fully yours
assets/logo.svg    swappable logo
app.py             Flask: branding, models, chat SSE, tool loop, tree, VM, approval
tools.py           tool registry + sandbox jail
web.py             web_search / web_fetch (only on /web turns)
static/            index.html, style.css, app.js  (the UI)
skills/            <name>/SKILL.md
workspace/         default sandbox (AI confined here)
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
