---
name: app-control
description: Launch and control desktop apps from the shell — Spotify, Ollama, Steam, Blender, Office, Chrome.
---

# app-control

Use `run_command` to launch/control apps. On Windows `start` / `os.startfile`,
on macOS `open`, on Linux `xdg-open`.

## Spotify
- Launch desktop app: Windows `start spotify:` · macOS `open -a Spotify` · Linux `spotify &`
- Play something specific / skip / pause without touching the app → use the
  **spotify-control** skill (Spotify Web API via spotipy).

## Ollama (this app's engine)
- Start server: `ollama serve` (run in background)
- Pull a model: `ollama pull qwen2.5-coder:7b`
- List / running: `ollama list` · `ollama ps`
- One-off run: `ollama run <model> "prompt"`

## Steam
- Launch a game: open URI `steam://rungameid/<appid>` (Windows `start steam://rungameid/<appid>`)
- Store page `steam://store/<appid>` · install `steam://install/<appid>`

## Chrome
- `chrome --new-window <url>` · `--incognito` · kiosk `--kiosk <url>`

## Blender (headless)
- Render frame: `blender -b scene.blend -o //out -f 1`
- Run a bpy script: `blender -b scene.blend --python script.py`

## Microsoft / Windows
- Word `winword /n` · Excel `excel /e` · Outlook `outlook /c ipm.note`
- Install anything: `winget install <pkg>` · `winget list` · `winget upgrade`
- Process control (PowerShell): `Start-Process`, `Stop-Process -Name x`, `Get-Process`

## Launch + manage from Python
```python
import os, subprocess, psutil
os.startfile("spotify")                 # Windows launch by protocol/name
subprocess.Popen(["ollama", "serve"])   # background process
running = any(p.name()=="Spotify.exe" for p in psutil.process_iter(["name"]))
```

Rule: an app is only launched if the command returns OK. Report the real result.
