"""Elysium — native desktop launcher.

This is the whole app's entry point. Packaged with PyInstaller it becomes a
single double-clickable executable (Elysium.exe / Elysium.app / Elysium) — no
Python install, no running individual files. In dev, just `python desktop.py`.

It starts the Flask backend in a background thread, then opens a native window
(pywebview). All branding comes from branding.json.
"""
from __future__ import annotations

import json
import socket
import threading
import time

import paths
import app as backend


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
    backend.app.run(host=HOST, port=port, threaded=True, use_reloader=False)


def wait_up(url: str, tries: int = 60):
    import urllib.request
    for _ in range(tries):
        try:
            urllib.request.urlopen(url + "/api/config", timeout=1).read()
            return
        except Exception:
            time.sleep(0.25)


def main():
    paths.seed_user_data()
    b = load_branding()
    w = b.get("window", {})
    port = free_port()
    url = f"http://{HOST}:{port}"

    threading.Thread(target=serve, args=(port,), daemon=True).start()
    wait_up(url)

    try:
        import webview
        webview.create_window(
            b.get("name", "Elysium"), url,
            width=w.get("width", 1280), height=w.get("height", 820),
            min_size=(w.get("min_width", 900), w.get("min_height", 600)),
            background_color="#eaf3ff",
        )
        webview.start()
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
