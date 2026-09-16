---
name: vscode-windows-dev
description: Build, run, debug, compile on Windows + version control.
---

# vscode-windows-dev

Run / build:
- Python: `python app.py`  | venv: `python -m venv .venv && .venv\Scripts\activate`
- Node: `npm install` then `npm start` / `npm run dev`
- .NET: `dotnet run` (needs SDK, not just runtime)
- C/C++: `cl main.c` (MSVC) or `g++ main.cpp -o main` (mingw)

Debug in VS Code:
- `.vscode/launch.json` defines configs; F5 starts, breakpoints in gutter.
- integrated terminal = Ctrl+` ; run task = Ctrl+Shift+B.

Version control (git):
- `git status` / `git add -A` / `git commit -m "..."` / `git push`
- branch: `git checkout -b feat` ; undo file: `git restore <f>`
- never force-push shared branches.

Note: check a tool exists before assuming (`where python`, `where node`,
`dotnet --version`). Report missing toolchains, do not fake commands.
