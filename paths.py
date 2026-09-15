"""Path resolution for both dev runs and the packaged (frozen) app.

- RES_DIR : read-only bundled resources (static/, assets/, branding.json,
            default skills). When frozen by PyInstaller this is the temp
            extraction dir (sys._MEIPASS); in dev it's the source tree.
- DATA_DIR: writable user data (workspace/, skills/, MEMORY.md). Next to the
            executable when frozen, or the source tree in dev. Falls back to
            ~/<AppName> if the exe dir is not writable.
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)

RES_DIR = getattr(sys, "_MEIPASS", HERE)

APP_NAME = "AiHeaven"


def _writable(d: str) -> bool:
    try:
        os.makedirs(d, exist_ok=True)
        t = os.path.join(d, ".w")
        open(t, "w").close()
        os.remove(t)
        return True
    except Exception:
        return False


def data_dir() -> str:
    if FROZEN:
        near = os.path.dirname(sys.executable)
        cand = os.path.join(near, f"{APP_NAME}-data")
        if _writable(cand):
            return cand
        return os.path.join(os.path.expanduser("~"), APP_NAME)
    return HERE


DATA_DIR = data_dir()


def res(*parts: str) -> str:
    return os.path.join(RES_DIR, *parts)


def data(*parts: str) -> str:
    return os.path.join(DATA_DIR, *parts)


def seed_user_data() -> None:
    """Create workspace/ and seed skills/ from the bundle on first run."""
    os.makedirs(data("workspace"), exist_ok=True)
    user_skills = data("skills")
    if not os.path.isdir(user_skills):
        bundled = res("skills")
        if os.path.isdir(bundled):
            shutil.copytree(bundled, user_skills)
        else:
            os.makedirs(user_skills, exist_ok=True)
