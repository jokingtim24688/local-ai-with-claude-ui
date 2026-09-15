---
name: cross-platform-shell
description: Every Linux and Windows shell command, what works on both, and how to convert Linux-only commands to Windows so the app runs on Windows.
---

# cross-platform-shell

The agent VMs are Linux; the user's machine is Windows. This skill makes what the
pool builds run on Windows. Rule of thumb: **prefer portable tooling** (Python,
Node, git — identical on both) over shell built-ins; only translate when a raw
shell command is unavoidable.

## Works the same on BOTH (use these first, no translation needed)
`python` / `python3` · `node` / `npm` / `npx` · `git` · `curl` · `pip` ·
`ssh` · `ollama` · `docker` · most language runtimes. `&&` and `||` chain on both
(cmd + bash). In Python, use `pathlib.Path`, `os`, `shutil`, `subprocess` and it
runs unchanged on either OS.

## Linux → Windows command map
| Purpose | Linux (bash) | Windows (cmd) | Windows (PowerShell) |
|---|---|---|---|
| list dir | `ls -la` | `dir` | `Get-ChildItem` |
| print file | `cat f` | `type f` | `Get-Content f` |
| copy | `cp a b` | `copy a b` | `Copy-Item a b` |
| move/rename | `mv a b` | `move a b` | `Move-Item a b` |
| delete file | `rm f` | `del f` | `Remove-Item f` |
| delete dir | `rm -rf d` | `rmdir /s /q d` | `Remove-Item -Recurse -Force d` |
| make dir | `mkdir -p d` | `mkdir d` | `New-Item -Type Directory d` |
| find text | `grep x f` | `findstr x f` | `Select-String x f` |
| find file | `find . -name x` | `dir /s /b x` | `Get-ChildItem -Recurse -Filter x` |
| which | `which x` | `where x` | `Get-Command x` |
| env var (set) | `export V=1` | `set V=1` | `$env:V=1` |
| env var (use) | `$V` / `$HOME` | `%V%` / `%USERPROFILE%` | `$env:V` / `$env:USERPROFILE` |
| print | `echo hi` | `echo hi` | `Write-Output hi` |
| empty file | `touch f` | `type nul > f` | `New-Item f` |
| symlink | `ln -s t l` | `mklink l t` | `New-Item -ItemType SymbolicLink` |
| processes | `ps aux` | `tasklist` | `Get-Process` |
| kill | `kill -9 PID` | `taskkill /F /PID PID` | `Stop-Process -Id PID` |
| run in bg | `cmd &` | `start /b cmd` | `Start-Process cmd` |
| perms | `chmod +x f` | (n/a — use `icacls`) | `icacls` |
| sudo | `sudo x` | (run as Administrator) | (elevated shell) |
| download | `wget URL` | `curl -O URL` | `Invoke-WebRequest URL -OutFile` |
| package install | `apt install x` | `winget install x` / `choco install x` | same |
| path separator | `/` | `\` (cmd) — `/` mostly works in tools | `\` |
| source script | `source s.sh` | `call s.bat` | `. .\s.ps1` |
| open app/file | `xdg-open x` | `start x` | `Invoke-Item x` |
| line: shebang | `#!/usr/bin/env python3` | (ignored — call `python`) | — |

## Conversion recipe (Linux-only → Windows)
1. If the step can be Python/Node/git, rewrite it that way — done, portable.
2. Else map each command with the table above; swap `/`→`\` only for cmd built-ins.
3. Fix env vars (`$VAR`→`%VAR%`), paths (`~`→`%USERPROFILE%`), and script calls.
4. Provide BOTH: keep the `.sh` for the Linux VM and emit a `.bat`/`.ps1` for
   Windows (the install.bat / install.sh pair in this repo is the pattern).
5. Verify on the Windows host, not just in the Linux VM.

## Gotchas
- `rm -rf` has no safe cmd one-liner — use `rmdir /s /q` (dirs) / `del /q` (files).
- cmd has no `grep`; `findstr` regex is weaker — prefer `python -c` or PowerShell.
- Backslashes in cmd; forward slashes usually fine inside quoted args to real tools.
- PowerShell execution policy may block `.ps1`: `Set-ExecutionPolicy -Scope Process Bypass`.
- Prefer `subprocess.run([...])` lists over shell strings to avoid quoting hell.
