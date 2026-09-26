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
# frozen = packaged by PyInstaller (sys.frozen) OR compiled by Nuitka (__compiled__)
FROZEN = getattr(sys, "frozen", False) or ("__compiled__" in globals())

# PyInstaller extracts to sys._MEIPASS; Nuitka onefile extracts next to __file__,
# so HERE already points at the bundled resources there.
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
        if sys.platform == "darwin":
            # never write inside a .app bundle (breaks signing; Gatekeeper may run
            # it read-only from a translocated path) -> the standard mac location
            return os.path.join(os.path.expanduser("~"), "Library",
                                "Application Support", APP_NAME)
        # dir of the real .exe (works for both PyInstaller and Nuitka onefile,
        # where sys.executable can point at the temp unpack dir instead)
        near = os.path.dirname(os.path.abspath(sys.argv[0]))
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
    bundled = res("skills")
    if os.path.abspath(user_skills) == os.path.abspath(bundled):
        return                                   # dev run: same folder
    os.makedirs(user_skills, exist_ok=True)
    if os.path.isdir(bundled):
        # add bundled skills the user doesn't have yet (new app versions ship new
        # ones); never overwrite a skill the user already has or edited
        for name in os.listdir(bundled):
            src, dst = os.path.join(bundled, name), os.path.join(user_skills, name)
            if os.path.isdir(src) and not os.path.exists(dst):
                shutil.copytree(src, dst)
