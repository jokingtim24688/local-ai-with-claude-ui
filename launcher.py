"""Night Crew launcher — updates itself from GitHub, then opens the app.

The Desktop / Start-menu shortcut (make_shortcut.py) points here. Every launch:
  1. git fetch the branch this folder is on (skipped quietly when offline)
  2. fast-forward to it. Local edits are stashed first and only put back if they
     still apply cleanly — never leaves conflict markers in your files
  3. pip install -r requirements.txt if the update changed it
  4. start desktop.py (no console window) and tell it what changed

    python launcher.py              update + launch
    python launcher.py --no-update  just launch
Log: update.log next to this file.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "update.log")
WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if WIN else 0           # CREATE_NO_WINDOW for git/pip


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def git(*args, timeout: int = 60, ok: tuple = (0,)) -> str | None:
    """Run git in this folder. Returns stdout, or None on failure."""
    try:
        r = subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True,
                           timeout=timeout, creationflags=NO_WINDOW)
    except Exception as e:
        log(f"git {' '.join(args)}: {e}")
        return None
    if r.returncode not in ok:
        log(f"git {' '.join(args)} -> {r.returncode}: {(r.stderr or r.stdout).strip()[:300]}")
        return None
    return r.stdout.strip()


def update(status) -> str:
    """Returns a one-line note for the app ('' when nothing changed)."""
    if not os.path.isdir(os.path.join(HERE, ".git")):
        return ""
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or ""
    if not branch or branch == "HEAD":
        return ""
    status("Checking for updates…")
    if git("fetch", "--quiet", "origin", branch, timeout=25) is None:
        return ""                                            # offline: just launch
    old = git("rev-parse", "HEAD")
    new = git("rev-parse", f"origin/{branch}")
    if not old or not new or old == new:
        return ""
    if subprocess.run(["git", "merge-base", "--is-ancestor", old, new], cwd=HERE,
                      creationflags=NO_WINDOW).returncode != 0:
        log("local commits differ from GitHub — not auto-updating")
        return "Update skipped: this folder has its own commits (see update.log)"
    count = git("rev-list", "--count", f"{old}..{new}") or "?"
    status(f"Updating Night Crew ({count} new changes)…")

    stashed = False
    if git("status", "--porcelain", "--untracked-files=no"):     # local edits to tracked files
        if git("stash", "push", "-m", f"night-crew autoupdate {time.strftime('%Y-%m-%d %H:%M')}") is not None:
            stashed = True
    if git("merge", "--ff-only", "--quiet", new) is None:
        if stashed:
            git("stash", "pop")
        return "Update failed — opened the current version (see update.log)"

    note = f"Updated: {count} new changes"
    if stashed:
        # raw patch (git() strips output, which would corrupt the patch's last line)
        patch = subprocess.run(["git", "stash", "show", "-p", "stash@{0}"], cwd=HERE, capture_output=True,
                               text=True, creationflags=NO_WINDOW).stdout
        clean = bool(patch) and subprocess.run(
            ["git", "apply", "--check"], cwd=HERE, input=patch, text=True,
            capture_output=True, creationflags=NO_WINDOW).returncode == 0
        if clean and git("stash", "pop") is not None:
            note += " (your local edits were kept)"
        else:
            note += " (your local edits clashed — saved in git stash)"
            log("local edits kept in `git stash list`; restore with `git stash pop` after reviewing")

    changed = git("diff", "--name-only", old, new) or ""
    if "requirements.txt" in changed.split():
        status("Installing new packages…")
        py = sys.executable.replace("pythonw.exe", "python.exe")
        r = subprocess.run([py, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=HERE,
                           capture_output=True, text=True, creationflags=NO_WINDOW)
        log(f"pip install -> {r.returncode} {(r.stderr or '')[-300:]}")
    log(f"updated {old[:7]} -> {new[:7]} ({count} changes)")
    return note


def close_running(log_to=lambda s: None) -> int:
    """Close any Night Crew already running, so an update never leaves two windows (and two
    apps fighting over the same port and chats.json). Asks politely first, then forces it."""
    try:
        import psutil
    except Exception:
        return 0
    me = os.getpid()
    try:
        mine = {me} | {p.pid for p in psutil.Process(me).parents()}
    except Exception:
        mine = {me}
    doomed = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
        if p.info["pid"] in mine:
            continue
        try:
            name = (p.info["name"] or "").lower()
            cmd = " ".join(p.info["cmdline"] or []).lower()
            ours = ("night crew" in name or "nightcrew" in name
                    or ("desktop.py" in cmd and HERE.lower() in cmd.lower()))
            if ours:
                doomed.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not doomed:
        return 0
    log_to(f"closing {len(doomed)} running copy…")
    for p in doomed:
        try:
            p.terminate()
        except Exception:
            pass
    gone, alive = psutil.wait_procs(doomed, timeout=6)
    for p in alive:                      # still there: stop pretending
        try:
            p.kill()
        except Exception:
            pass
    log(f"closed {len(doomed)} running instance(s)")
    return len(doomed)


def launch(note: str) -> None:
    close_running()
    py = sys.executable
    if WIN and py.lower().endswith("python.exe"):              # no console window
        w = py[:-10] + "pythonw.exe"
        py = w if os.path.isfile(w) else py
    env = dict(os.environ, NIGHTCREW_UPDATE_NOTE=note)
    subprocess.Popen([py, os.path.join(HERE, "desktop.py")], cwd=HERE, env=env,
                     creationflags=NO_WINDOW if WIN else 0)


def main() -> None:
    if "--no-update" in sys.argv:
        return launch("")
    # a small "Updating…" window while git/pip run (skipped if tkinter is missing)
    try:
        import tkinter as tk
    except Exception:
        return launch(update(lambda s: None))
    root = tk.Tk()
    root.title("Night Crew")
    root.configure(bg="#0b1020")
    root.overrideredirect(True)
    w, h = 340, 90
    root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")
    tk.Label(root, text="Night Crew", fg="#e8b98a", bg="#0b1020", font=("Segoe UI", 13, "bold")).pack(pady=(16, 2))
    msg = tk.Label(root, text="Starting…", fg="#aab3ca", bg="#0b1020", font=("Segoe UI", 10))
    msg.pack()
    shared = {"status": "Starting…", "done": False, "note": ""}

    def work():                         # never touch tk from here — the UI polls `shared`
        try:
            shared["note"] = update(lambda s: shared.__setitem__("status", s))
        except Exception as e:
            log(f"update crashed: {e}")
        shared["done"] = True

    def poll():
        msg.config(text=shared["status"])
        root.destroy() if shared["done"] else root.after(120, poll)

    threading.Thread(target=work, daemon=True).start()
    root.after(120, poll)
    root.mainloop()
    result = shared
    launch(result.get("note", ""))


if __name__ == "__main__":
    main()
