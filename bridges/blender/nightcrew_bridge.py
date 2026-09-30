"""Night Crew Bridge — lets the Night Crew agents drive THIS Blender session.

Listens on 127.0.0.1:9876 only. Every request must carry the token stored in
~/.nightcrew/bridge.token (written by the Night Crew app), so other programs and web pages
can't use it. Code runs on Blender's main thread (bpy.app.timers) and each run is one undo
step, so Ctrl+Z reverts what the agent did.
"""
bl_info = {
    "name": "Night Crew Bridge",
    "author": "Night Crew",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "runs in the background",
    "description": "Lets the local Night Crew agents edit this Blender session (localhost only)",
    "category": "System",
}

import contextlib
import io
import json
import os
import queue
import socket
import threading
import traceback

import bpy

PORT = 9876
_jobs: "queue.Queue" = queue.Queue()
_stop = threading.Event()
_thread = None


def _token() -> str:
    try:
        with open(os.path.join(os.path.expanduser("~"), ".nightcrew", "bridge.token"), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _reply(conn, obj) -> None:
    try:
        conn.sendall((json.dumps(obj, default=str) + "\n").encode())
    except Exception:
        pass


def _client(conn) -> None:
    with conn:
        conn.settimeout(30)
        buf = b""
        try:
            while not buf.endswith(b"\n") and len(buf) < 20_000_000:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
            req = json.loads(buf.decode("utf-8"))
        except Exception:
            return                                              # not our protocol: drop
        tok = _token()
        if not tok or req.get("token") != tok:
            return _reply(conn, {"ok": False, "error": "bad token"})
        if req.get("op") == "ping":
            return _reply(conn, {"ok": True, "version": bpy.app.version_string})
        box, done = {}, threading.Event()
        _jobs.put((req, box, done))
        wait = float(req.get("timeout") or 120)
        conn.settimeout(wait + 10)
        if not done.wait(wait):
            return _reply(conn, {"ok": False, "error": "timed out on Blender's main thread"})
        _reply(conn, box)


def _serve() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", PORT))
    except OSError as e:
        print(f"[Night Crew Bridge] port {PORT} busy: {e}")
        return
    s.listen(4)
    s.settimeout(1.0)
    print(f"[Night Crew Bridge] listening on 127.0.0.1:{PORT}")
    while not _stop.is_set():
        try:
            conn, _ = s.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=_client, args=(conn,), daemon=True).start()
    s.close()


def _run(req) -> dict:
    if req.get("op") != "exec":
        return {"ok": False, "error": f"unknown op {req.get('op')}"}
    out = io.StringIO()
    ns = {"bpy": bpy, "__name__": "__nightcrew__"}
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(compile(req.get("code", ""), "<nightcrew>", "exec"), ns)
        ok = True
    except Exception:
        out.write(traceback.format_exc())
        ok = False
    try:
        bpy.ops.ed.undo_push(message="Night Crew")
    except Exception:
        pass
    return {"ok": ok, "output": out.getvalue()[-60000:]}


def _tick():
    while True:
        try:
            req, box, done = _jobs.get_nowait()
        except queue.Empty:
            break
        box.update(_run(req))
        done.set()
    return None if _stop.is_set() else 0.1


def register():
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_serve, daemon=True, name="nightcrew-bridge")
    _thread.start()
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.5, persistent=True)


def unregister():
    _stop.set()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
