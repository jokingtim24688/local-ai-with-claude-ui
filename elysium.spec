# PyInstaller spec — builds "Night Crew" into one standalone app.
# The build auto-detects the OS it runs on:
#   run it on Windows -> dist/Night Crew.exe
#   run it on macOS   -> dist/Night Crew.app
# (A single file can't run on both OSes — different binary formats — so build
#  once per OS. Each build produces the right app automatically.)
#   pip install pyinstaller
#   pyinstaller elysium.spec
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

APP = "Night Crew"

block_cipher = None

# bundled read-only resources (served from sys._MEIPASS at runtime)
datas = [
    ("static", "static"),
    ("assets", "assets"),
    ("branding.json", "."),
    ("skills", "skills"),          # default skills, seeded to user data on first run
    ("bridges", "bridges"),        # Blender add-on + Roblox Studio plugin (copied into the apps)
]
for _pkg in ("trafilatura", "courlan", "htmldate", "justext", "tld", "certifi"):   # scraper data files
    try:
        datas += collect_data_files(_pkg)
    except Exception:
        pass

hiddenimports = (
    collect_submodules("webview")
    + collect_submodules("flask")
    + ["ollama", "httpx", "trafilatura", "scraper", "integrations", "telegram_bridge",
       "gmail_listener", "vision", "context", "vault", "google_auth", "keyring", "live", "mcp_servers", "mcp_servers.core",
       "mcp_servers.blender", "mcp_servers.unreal", "mcp_servers.roblox", "mcp_servers.openscad",
       "mcp_servers.fortnite"]
    + collect_submodules("keyring")
    + collect_submodules("trafilatura")
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

MAC = sys.platform == "darwin"
VERSION = "0.2.0"

if not MAC:
    # Windows / Linux: one self-contained file
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
else:
    # macOS: a proper .app bundle (onedir inside; onefile .app is deprecated)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP, debug=False,
              strip=False, upx=False, console=False)
    coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name=APP)
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon="assets/icon.icns" if os.path.exists("assets/icon.icns") else None,
        bundle_identifier="app.nightcrew.desktop",
        version=VERSION,
        info_plist={
            "CFBundleName": APP,
            "CFBundleDisplayName": APP,
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
