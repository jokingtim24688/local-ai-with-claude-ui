"""make_shortcut.py — run ONCE to get a Night Crew icon that auto-updates.

    python make_shortcut.py

Windows: "Night Crew" shortcut on your Desktop (OneDrive Desktop too) and in the
         Start menu, with the moon icon, running launcher.py with no console.
macOS:   ~/Applications/Night Crew.app (drag it to the Dock), which runs
         launcher.py with this same Python.
Double-click it any time: it pulls the latest version, then opens the app.
Run it with the SAME python that has the app's packages (the one you pip-installed into).
"""
from __future__ import annotations

import os
import plistlib
import shutil
import stat
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCHER = os.path.join(HERE, "launcher.py")
NAME = "Night Crew"


def windows() -> None:
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    target = pyw if os.path.isfile(pyw) else py
    icon = os.path.join(HERE, "assets", "icon.ico")

    def q(s: str) -> str:                     # PowerShell single-quoted string
        return "'" + s.replace("'", "''") + "'"

    ps = f"""
$sh = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'),
                   (Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs'))) {{
  $lnk = $sh.CreateShortcut((Join-Path $dir {q(NAME + '.lnk')}))
  $lnk.TargetPath = {q(target)}
  $lnk.Arguments = '"' + {q(LAUNCHER)} + '"'
  $lnk.WorkingDirectory = {q(HERE)}
  $lnk.IconLocation = {q(icon + ',0')}
  $lnk.Description = 'Night Crew - updates itself, then opens'
  $lnk.Save()
  Write-Output (Join-Path $dir {q(NAME + '.lnk')})
}}
"""
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("Couldn't create the shortcut:\n" + (r.stderr or r.stdout))
        sys.exit(1)
    print("Created:\n  " + "\n  ".join(l for l in r.stdout.splitlines() if l.strip()))


def mac() -> None:
    app = os.path.join(os.path.expanduser("~/Applications"), NAME + ".app")
    shutil.rmtree(app, ignore_errors=True)
    macos, res = os.path.join(app, "Contents", "MacOS"), os.path.join(app, "Contents", "Resources")
    os.makedirs(macos)
    os.makedirs(res)
    exe = os.path.join(macos, "NightCrew")
    with open(exe, "w") as f:
        f.write(f'#!/bin/sh\ncd "{HERE}"\nexec "{sys.executable}" "{LAUNCHER}"\n')
    os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    shutil.copy(os.path.join(HERE, "assets", "icon.icns"), os.path.join(res, "icon.icns"))
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump({"CFBundleName": NAME, "CFBundleDisplayName": NAME,
                       "CFBundleExecutable": "NightCrew", "CFBundleIconFile": "icon.icns",
                       "CFBundleIdentifier": "app.nightcrew.launcher", "CFBundlePackageType": "APPL",
                       "CFBundleShortVersionString": "1.0", "LSUIElement": False}, f)
    print(f"Created: {app}\nOpen it from Finder > Applications (yours) or drag it to the Dock.")


if __name__ == "__main__":
    if sys.platform == "win32":
        windows()
    elif sys.platform == "darwin":
        mac()
    else:
        print("Linux: run  python3 launcher.py  (or point a .desktop file at it).")
