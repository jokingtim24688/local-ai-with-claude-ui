# PyInstaller spec — builds "Ai Heaven" into one standalone app.
# The build auto-detects the OS it runs on:
#   run it on Windows -> dist/Ai Heaven.exe
#   run it on macOS   -> dist/Ai Heaven.app
# (A single file can't run on both OSes — different binary formats — so build
#  once per OS. Each build produces the right app automatically.)
#   pip install pyinstaller
#   pyinstaller elysium.spec
import sys
from PyInstaller.utils.hooks import collect_submodules

APP = "Ai Heaven"

block_cipher = None

# bundled read-only resources (served from sys._MEIPASS at runtime)
datas = [
    ("static", "static"),
    ("assets", "assets"),
    ("branding.json", "."),
    ("skills", "skills"),          # default skills, seeded to user data on first run
]

hiddenimports = (
    collect_submodules("webview")
    + collect_submodules("flask")
    + ["ollama"]
)

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

import os
_ico = "assets/icon.ico" if sys.platform == "win32" else None
if _ico and not os.path.exists(_ico):
    _ico = None

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name=APP,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,               # no terminal window
    icon=_ico,
)

# macOS: wrap into a proper .app bundle
if sys.platform == "darwin":
    _icns = "assets/icon.icns" if os.path.exists("assets/icon.icns") else None
    app = BUNDLE(
        exe,
        name=f"{APP}.app",
        icon=_icns,
        bundle_identifier="ai.heaven.app",
        info_plist={"NSHighResolutionCapable": True},
    )
