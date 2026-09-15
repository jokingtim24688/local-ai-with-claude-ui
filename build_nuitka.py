"""build_nuitka.py — compile Ai Heaven into a REAL native .exe with Nuitka.

Nuitka translates the Python to C and compiles it to a true machine-code binary
(faster start, harder to decompile) — unlike PyInstaller, which bundles the
interpreter. This is the "actual compiled exe".

    pip install nuitka
    python build_nuitka.py                 -> build_nuitka/Ai Heaven.exe
    python build_nuitka.py --desktop       -> builds straight onto your Desktop

First run downloads a C compiler (MinGW) automatically. Build takes a few minutes.
Do it in a CLEAN venv (flask ollama pywebview psutil nuitka) so it stays small.
"""
import os
import subprocess
import sys

OUT = os.path.join(os.path.expanduser("~"), "Desktop") if "--desktop" in sys.argv else "build_nuitka"

CMD = [
    sys.executable, "-m", "nuitka",
    "--standalone", "--onefile",
    "--assume-yes-for-downloads",          # auto-fetch MinGW if no compiler
    "--windows-console-mode=disable",       # no console window
    "--windows-icon-from-ico=assets/icon.ico",
    "--company-name=Ai Heaven", "--product-name=Ai Heaven",
    "--file-version=0.1.0", "--product-version=0.1.0",
    "--include-data-dir=static=static",
    "--include-data-dir=assets=assets",
    "--include-data-dir=skills=skills",
    "--include-data-files=branding.json=branding.json",
    f"--output-dir={OUT}",
    "--output-filename=Ai Heaven.exe",
    "desktop.py",
]


def main():
    try:
        import nuitka  # noqa: F401
    except ImportError:
        print("Nuitka missing. Run:  pip install nuitka")
        sys.exit(1)
    print(" ".join(CMD))
    subprocess.check_call(CMD)
    print(f"\nDone. Your compiled app: {os.path.join(OUT, 'Ai Heaven.exe')}")


if __name__ == "__main__":
    main()
