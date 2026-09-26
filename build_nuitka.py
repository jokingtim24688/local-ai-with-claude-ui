"""build_nuitka.py — compile Night Crew into a REAL native .exe with Nuitka.

Nuitka translates the Python to C and compiles it to a true machine-code binary
(faster start, harder to decompile) — unlike PyInstaller, which bundles the
interpreter. This is the "actual compiled exe".

    pip install nuitka
    python build_nuitka.py                 -> Windows: build_nuitka/Night Crew.exe
                                              macOS:   build_nuitka/Night Crew.app
    python build_nuitka.py --desktop       -> builds straight onto your Desktop

Windows: the first run downloads a C compiler (MinGW) automatically.
macOS: needs Xcode command line tools once:  xcode-select --install
Build on each OS for that OS (a Windows build can't run on a Mac and vice versa).
Do it in a CLEAN venv (flask ollama pywebview psutil nuitka) so it stays small.
"""
import os
import subprocess
import sys

OUT = os.path.join(os.path.expanduser("~"), "Desktop") if "--desktop" in sys.argv else "build_nuitka"
APP, VERSION = "Night Crew", "0.2.0"
MAC, WIN = sys.platform == "darwin", sys.platform == "win32"

DATA = [
    "--include-data-dir=static=static",          # UI + bundled fonts
    "--include-data-dir=assets=assets",
    "--include-data-dir=skills=skills",
    "--include-data-files=branding.json=branding.json",
]
if WIN:
    PLATFORM = [
        "--standalone", "--onefile",
        "--windows-console-mode=disable",        # no console window
        "--windows-icon-from-ico=assets/icon.ico",
        f"--company-name={APP}", f"--product-name={APP}",
        f"--file-version={VERSION}", f"--product-version={VERSION}",
        f"--output-filename={APP}.exe",
    ]
    RESULT = f"{APP}.exe"
elif MAC:
    PLATFORM = [
        "--standalone", "--macos-create-app-bundle",   # -> Night Crew.app
        "--macos-app-icon=assets/icon.icns",
        f"--macos-app-name={APP}", f"--macos-app-version={VERSION}",
        f"--output-filename={APP}",
    ]
    RESULT = f"{APP}.app"
else:
    PLATFORM = ["--standalone", "--onefile", f"--output-filename={APP.replace(' ', '')}"]
    RESULT = APP.replace(" ", "")

CMD = [sys.executable, "-m", "nuitka", "--assume-yes-for-downloads", *PLATFORM, *DATA,
       f"--output-dir={OUT}", "desktop.py"]


def main():
    try:
        import nuitka  # noqa: F401
    except ImportError:
        print("Nuitka missing. Run:  pip install nuitka")
        sys.exit(1)
    print(" ".join(CMD))
    subprocess.check_call(CMD)
    if MAC:   # Nuitka names the bundle after the script; give it the real app name
        import shutil
        src, dst = os.path.join(OUT, "desktop.app"), os.path.join(OUT, f"{APP}.app")
        if os.path.isdir(src):
            shutil.rmtree(dst, ignore_errors=True)
            shutil.move(src, dst)
    print(f"\nDone. Your compiled app: {os.path.join(OUT, RESULT)}")


if __name__ == "__main__":
    main()
