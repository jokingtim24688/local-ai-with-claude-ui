# PyInstaller spec — builds Elysium into one standalone app.
#   pip install pyinstaller
#   pyinstaller elysium.spec
# Output: dist/Elysium  (double-click; no Python needed)
import sys
from PyInstaller.utils.hooks import collect_submodules

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

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="Elysium",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,               # no terminal window
    icon="assets/icon.ico" if sys.platform == "win32" else None,
)

# macOS: wrap into a proper .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Elysium.app",
        icon="assets/icon.icns",
        bundle_identifier="ai.local.elysium",
        info_plist={"NSHighResolutionCapable": True},
    )
