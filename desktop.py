"""Elysium — native desktop launcher.

This is the whole app's entry point. Packaged with PyInstaller it becomes a
single double-clickable executable (Elysium.exe / Elysium.app / Elysium) — no
Python install, no running individual files. In dev, just `python desktop.py`.

It starts the Flask backend in a background thread, then opens a native window
(pywebview). All branding comes from branding.json.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time

import paths
import app as backend


def _win_icon():
    """The app icon for the taskbar/window (Windows), if present."""
    for p in (paths.res("assets/icon.ico"), paths.data("assets/icon.ico")):
        try:
            if os.path.exists(p):
                return p
        except Exception:
            pass
    return None


def load_branding() -> dict:
    for p in (paths.data("branding.json"), paths.res("branding.json")):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {"name": "Elysium", "window": {}}


def free_port(preferred: int = 5173) -> int:
    for port in (preferred, 5174, 5175, 0):
        try:
            s = socket.socket()
            s.bind(("127.0.0.1", port))
            p = s.getsockname()[1]
            s.close()
            return p
        except OSError:
            continue
    return preferred


HOST = "127.0.0.1"


def serve(port: int):
    backend.CFG["workdir"] = paths.data("workspace")
    backend.CFG["skills"] = paths.data("skills")
    backend.tools.set_sandbox(backend.CFG["workdir"])
    backend.tools.scan_skills(backend.CFG["skills"])
    backend.seed_default_subagents()
    backend.app.run(host=HOST, port=port, threaded=True, use_reloader=False)


def wait_up(url: str, tries: int = 60):
    import urllib.request
    for _ in range(tries):
        try:
            urllib.request.urlopen(url + "/api/config", timeout=1).read()
            return
        except Exception:
            time.sleep(0.25)


def ensure_ollama():
    """Best-effort: start `ollama serve` if Ollama is installed but not running."""
    import shutil
    import subprocess
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=1).read()
        return  # already up
    except Exception:
        pass
    exe = shutil.which("ollama")
    if not exe:
        return
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        subprocess.Popen([exe, "serve"], creationflags=flags) if sys.platform == "win32" \
            else subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
    except Exception:
        pass


def main():
    ensure_ollama()
    paths.seed_user_data()
    b = load_branding()
    w = b.get("window", {})
    port = free_port()
    url = f"http://{HOST}:{port}"

    # Windows: give the process our own taskbar identity + icon (not python's).
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "AiHeaven.Desktop.1")
        except Exception:
            pass

    threading.Thread(target=serve, args=(port,), daemon=True).start()
    wait_up(url)

    try:
        import webview

        class Api:
            window = None
            _max = False

            def minimize(self):
                if self.window:
                    self.window.minimize()

            def toggle_maximize(self):
                if not self.window:
                    return
                self._max = not self._max
                self.window.maximize() if self._max else self.window.restore()

            def close(self):
                if self.window:
                    self.window.destroy()

        api = Api()
        window = webview.create_window(
            b.get("name", "Ai Heaven"), url,
            width=w.get("width", 1280), height=w.get("height", 820),
            min_size=(w.get("min_width", 900), w.get("min_height", 600)),
            background_color="#eaf3ff",
            frameless=True, easy_drag=False, js_api=api,
        )
        api.window = window

        # Force the modern WebView2 engine on Windows. If pywebview falls back to
        # the ancient MSHTML/IE engine, the app's CSS/JS breaks and the window
        # hangs ("not responding") — so pin edgechromium, with graceful fallbacks.
        start_kwargs = {}
        ico = _win_icon()
        if ico:
            start_kwargs["icon"] = ico
        if sys.platform == "win32":
            start_kwargs["gui"] = "edgechromium"
        try:
            webview.start(**start_kwargs)
        except TypeError:
            start_kwargs.pop("icon", None)           # older pywebview: no icon kwarg
            try:
                webview.start(**start_kwargs)
            except Exception:
                webview.start()
        except Exception:
            webview.start()                          # WebView2 missing → default engine
    except ImportError:
        import webbrowser
        print("pywebview not installed — opening in browser.")
        print("for the native window:  pip install pywebview")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
