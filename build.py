"""Cross-platform build script — makes the standalone Elysium app.

    pip install -r requirements.txt pyinstaller
    python build.py

Result:
    Windows : dist/Elysium.exe
    macOS   : dist/Elysium.app
    Linux   : dist/Elysium
Ship that one item. It needs no Python install. A platform webview runtime is
required at runtime (WebView2 on Windows 10/11 — usually preinstalled; WebKitGTK
on Linux; WKWebView on macOS — built in).
"""
import subprocess
import sys


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller missing. Run:  pip install pyinstaller")
        sys.exit(1)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "elysium.spec"]
    print(" ".join(cmd))
    subprocess.check_call(cmd)
    print("\nBuilt. See the dist/ folder — that is your app.")


if __name__ == "__main__":
    main()
