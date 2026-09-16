# Installing Ai Heaven

Two ways. Both still need **Ollama** + at least one model pulled.

## A) One-command (from source) — fastest to try

No building. Installs deps into a local venv, checks Ollama, pulls a default
model, launches the app.

- **Windows:** double-click `install.bat`
- **macOS / Linux:** `./install.sh`

Re-run the same script any time to launch again.

## B) A real installer (wizard, shortcuts, uninstaller)

This is the "not one loose file" path — a proper Setup that installs the app,
adds Start-Menu / desktop shortcuts, and registers an uninstaller.

### Windows → `AiHeaven-Setup.exe`
1. `python build.py` → makes `dist\Ai Heaven.exe`
2. Install **Inno Setup** (https://jrsoftware.org/isdl.php)
3. Compile `installer/AiHeaven.iss` (open + Compile, or `iscc installer\AiHeaven.iss`)
4. Share `installer/Output/AiHeaven-Setup.exe`

The wizard offers to install Ollama (via winget) if it's missing, and launches
the app at the end.

### macOS → `Ai Heaven.dmg`
1. `python build.py` → makes `dist/Ai Heaven.app`
2. `./installer/build_dmg.sh` → `installer/Ai Heaven.dmg`
3. Share the .dmg. User drags **Ai Heaven** into Applications.
   (Unsigned: first launch = right-click → Open.)

## What still has to be there
- **Ollama** — the installer can pull it on Windows; otherwise
  https://ollama.com/download.
- **A model** — e.g. `ollama pull qwen2.5-coder:7b` (the from-source scripts do
  this automatically on first run). See `bench.py` to pick the best one.
