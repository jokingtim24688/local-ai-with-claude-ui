"""Native desktop launcher — our own app window, no Electron, no browser chrome.

Starts the Flask backend in a background thread, then opens a native window
with pywebview. Everything (window title, logo, colors) comes from
branding.json, so it is fully yours to change.

    python desktop.py

If pywebview isn't installed it falls back to opening the default browser.
"""
from __future__ import annotations

import json
import os
import threading
import time

import app as backend

HERE = os.path.dirname(os.path.abspath(__file__))
HOST, PORT = "127.0.0.1", 5173


def load_branding() -> dict:
    try:
        with open(os.path.join(HERE, "branding.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"name": "Local AI", "window": {}}


def serve():
    backend.CFG["workdir"] = os.path.join(HERE, "workspace")
    backend.CFG["skills"] = os.path.join(HERE, "skills")
    backend.tools.set_sandbox(backend.CFG["workdir"])
    backend.tools.scan_skills(backend.CFG["skills"])
    backend.app.run(host=HOST, port=PORT, threaded=True, use_reloader=False)


def main():
    b = load_branding()
    w = b.get("window", {})
    threading.Thread(target=serve, daemon=True).start()
    time.sleep(1.2)  # let Flask bind

    url = f"http://{HOST}:{PORT}"
    try:
        import webview
        webview.create_window(
            b.get("name", "Local AI"), url,
            width=w.get("width", 1280), height=w.get("height", 820),
            min_size=(w.get("min_width", 900), w.get("min_height", 600)),
            background_color="#16130f",
        )
        webview.start()
    except ImportError:
        import webbrowser
        print("pywebview not installed — opening in browser.")
        print("install for the native app:  pip install pywebview")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
