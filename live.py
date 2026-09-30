"""Live bridges into running apps (all localhost-only, token/header guarded).

Blender       add-on `bridges/blender/nightcrew_bridge.py` = TCP JSON on 127.0.0.1:9876.
              Every request carries the token from ~/.nightcrew/bridge.token.
Roblox Studio plugin `bridges/roblox/NightCrewBridge.lua` long-polls OUR tiny HTTP queue on
              127.0.0.1:9877 (/poll, /result need header X-NC: 1 — browsers can't send that
              cross-site). Tools post to /enqueue with the token. Whoever starts first (the
              app, or a standalone MCP server) hosts the queue; others forward to it.
Unreal        Remote Control API (RemoteControl plugin) on 127.0.0.1:30010; editor Python runs
              through PythonScriptLibrary.ExecutePythonCommandEx and its log comes back.
"""
from __future__ import annotations

import http.server
import json
import os
import queue
import secrets
import shutil
import socket
import sys
import threading
import time
import uuid

BLENDER_PORT, ROBLOX_PORT, UE_PORT = 9876, 9877, 30010


def token() -> str:
    d = os.path.join(os.path.expanduser("~"), ".nightcrew")
    p = os.path.join(d, "bridge.token")
    try:
        with open(p, encoding="utf-8") as f:
            t = f.read().strip()
        if len(t) >= 32:
            return t
    except Exception:
        pass
    os.makedirs(d, exist_ok=True)
    t = secrets.token_hex(24)
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass
    return t


def res_path(*parts) -> str:
    import paths
    return paths.res(os.path.join("bridges", *parts))


# ---- Blender ------------------------------------------------------------------------
def blender_send(req: dict, timeout: float = 120) -> dict:
    req = dict(req, token=token(), timeout=timeout)
    with socket.create_connection(("127.0.0.1", BLENDER_PORT), timeout=2) as s:
        s.settimeout(timeout + 5)
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode() or "{}")


def blender_live() -> bool:
    try:
        return bool(blender_send({"op": "ping"}, timeout=2).get("ok"))
    except Exception:
        return False


def blender_exec(code: str, timeout: float = 300) -> tuple[bool, str]:
    r = blender_send({"op": "exec", "code": code}, timeout=timeout)
    return bool(r.get("ok")), r.get("output", "") or r.get("error", "")


def install_blender_addon() -> str:
    import apps
    src = res_path("blender", "nightcrew_bridge.py")
    token()                                                     # make sure the add-on can read it
    code = (
        "import bpy, addon_utils\n"
        f"bpy.ops.preferences.addon_install(filepath={src!r}, overwrite=True)\n"
        "addon_utils.enable('nightcrew_bridge', default_set=True, persistent=True)\n"
        "bpy.ops.wm.save_userpref()\n"
        "print('NC_ADDON_OK')\n")
    exe = apps._need("blender")
    rc, out = apps._run([exe, "-b", "--python-expr", code], 300)
    if "NC_ADDON_OK" in out:
        return "OK: Blender add-on 'Night Crew Bridge' installed + enabled. Restart Blender once."
    return f"error: add-on install failed (exit {rc}):\n" + apps._tail(out, 1500)


# ---- Roblox Studio --------------------------------------------------------------------
class _RobloxHost:
    def __init__(self):
        self.cmds: queue.Queue = queue.Queue()
        self.results: dict[str, dict] = {}
        self.events: dict[str, threading.Event] = {}
        self.last_poll = 0.0
        self.srv = None

    def connected(self) -> bool:
        return time.time() - self.last_poll < 30

    def call(self, op: str, args: dict, timeout: float) -> dict:
        cid = uuid.uuid4().hex
        ev = self.events[cid] = threading.Event()
        self.cmds.put({"id": cid, "op": op, "args": args or {}})
        ok = ev.wait(timeout)
        self.events.pop(cid, None)
        if not ok:
            return {"ok": False, "output": "timed out waiting for Roblox Studio (is the Night Crew plugin connected?)"}
        return self.results.pop(cid, {"ok": False, "output": "no result"})


_HOST: _RobloxHost | None = None


def _handler(host: _RobloxHost):
    tok = token()

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, code, obj=None):
            body = b"" if obj is None else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(min(n, 20_000_000)) or b"{}")

        def do_GET(self):
            if self.path == "/status" and self.headers.get("X-NC-Token") == tok:
                return self._send(200, {"connected": host.connected()})
            if self.path != "/poll" or self.headers.get("X-NC") != "1":
                return self._send(403)
            host.last_poll = time.time()
            try:
                cmd = host.cmds.get(timeout=15)
            except queue.Empty:
                return self._send(204)
            host.last_poll = time.time()
            self._send(200, cmd)

        def do_POST(self):
            if self.path == "/result" and self.headers.get("X-NC") == "1":
                r = self._body()
                cid = str(r.get("id", ""))
                if cid in host.events:
                    host.results[cid] = {"ok": bool(r.get("ok")), "output": r.get("output")}
                    host.events[cid].set()
                return self._send(200, {})
            if self.path == "/enqueue" and self.headers.get("X-NC-Token") == tok:
                r = self._body()
                return self._send(200, host.call(r.get("op", ""), r.get("args") or {},
                                                 float(r.get("timeout") or 60)))
            self._send(403)

        def log_message(self, *a):
            pass

    return H


def start_roblox_host() -> bool:
    """Host the plugin queue in THIS process if the port is free. True if we host it."""
    global _HOST
    if _HOST:
        return True
    host = _RobloxHost()
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", ROBLOX_PORT), _handler(host))
    except OSError:
        return False
    srv.daemon_threads = True
    host.srv = srv
    threading.Thread(target=srv.serve_forever, daemon=True, name="roblox-bridge").start()
    _HOST = host
    return True


def _remote(path: str, body: dict | None, timeout: float):
    import httpx
    h = {"X-NC-Token": token()}
    url = f"http://127.0.0.1:{ROBLOX_PORT}{path}"
    r = httpx.post(url, json=body, headers=h, timeout=timeout) if body is not None \
        else httpx.get(url, headers=h, timeout=timeout)
    return r.json()


def roblox_call(op: str, args: dict | None = None, timeout: float = 60) -> dict:
    if _HOST:
        return _HOST.call(op, args or {}, timeout)
    try:
        return _remote("/enqueue", {"op": op, "args": args or {}, "timeout": timeout}, timeout + 5)
    except Exception:
        pass
    if start_roblox_host():                                    # nobody hosts: we do
        return _HOST.call(op, args or {}, timeout)
    return {"ok": False, "output": "Roblox bridge port 9877 is busy with something else"}


def roblox_connected() -> bool:
    if _HOST:
        return _HOST.connected()
    try:
        return bool(_remote("/status", None, 3).get("connected"))
    except Exception:
        return False


def roblox_plugins_dir() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Roblox", "Plugins")
    return os.path.join(os.path.expanduser("~"), "Documents", "Roblox", "Plugins")


def install_roblox_plugin() -> str:
    d = roblox_plugins_dir()
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, "NightCrewBridge.lua")
    shutil.copyfile(res_path("roblox", "NightCrewBridge.lua"), dst)
    return (f"OK: plugin copied to {dst}. In Studio: restart it, allow the plugin's HTTP request to "
            "127.0.0.1 when asked, then the 'Night Crew' toolbar button shows Connected.")


# ---- Unreal ---------------------------------------------------------------------------
def unreal_live() -> bool:
    import httpx
    try:
        return httpx.get(f"http://127.0.0.1:{UE_PORT}/remote/info", timeout=1).status_code == 200
    except Exception:
        return False


def unreal_exec(code: str, timeout: float = 300) -> tuple[bool, str]:
    import httpx
    body = {"objectPath": "/Script/PythonScriptPlugin.Default__PythonScriptLibrary",
            "functionName": "ExecutePythonCommandEx",
            "parameters": {"PythonCommand": code, "ExecutionMode": "ExecuteFile",
                           "FileExecutionScope": "Private"},
            "generateTransaction": True}
    r = httpx.put(f"http://127.0.0.1:{UE_PORT}/remote/object/call", json=body, timeout=timeout)
    if r.status_code >= 400:
        return False, f"Remote Control HTTP {r.status_code}: {r.text[:400]}"
    d = r.json()
    logs = "\n".join(f"{x.get('Type', '')}: {x.get('Output', '')}".rstrip() for x in d.get("LogOutput") or [])
    ok = bool(d.get("ReturnValue"))
    return ok, (logs + ("\n" + d["CommandResult"] if d.get("CommandResult") else "")).strip()


def unreal_enable_live(project: str) -> str:
    """Enable Python + Remote Control plugins and auto-start its web server for a .uproject."""
    import apps
    up = apps.resolve(project)
    with open(up, encoding="utf-8") as f:
        data = json.load(f)
    plugins = data.setdefault("Plugins", [])
    for pl in ("PythonScriptPlugin", "EditorScriptingUtilities", "RemoteControl"):
        if not any(x.get("Name") == pl for x in plugins):
            plugins.append({"Name": pl, "Enabled": True})
        else:
            for x in plugins:
                if x.get("Name") == pl:
                    x["Enabled"] = True
    with open(up, "w", encoding="utf-8") as f:
        json.dump(data, f, indent="\t")
    cfg = os.path.join(os.path.dirname(up), "Config")
    os.makedirs(cfg, exist_ok=True)
    ini = os.path.join(cfg, "DefaultRemoteControl.ini")
    sect = "[/Script/RemoteControlCommon.RemoteControlSettings]"
    txt = open(ini, encoding="utf-8").read() if os.path.exists(ini) else ""
    if "bAutoStartWebServer" not in txt:
        txt = txt.rstrip() + ("\n\n" if txt.strip() else "") + f"{sect}\nbAutoStartWebServer=True\nRemoteControlHttpServerPort={UE_PORT}\n"
        with open(ini, "w", encoding="utf-8") as f:
            f.write(txt)
    return (f"OK: {os.path.basename(up)} now has Python + Remote Control enabled. Open it in the editor "
            "(first open rebuilds plugins); live tools connect on port 30010.")


def unreal_open_live(project: str = "") -> str:
    import apps
    exe = apps.find_unreal(gui=True) or apps._need("unreal")
    args = [exe] + ([apps.resolve(project)] if project else []) + ["-RCWebControlEnable"]
    apps._spawn(args)
    return "OK: Unreal Editor starting with Remote Control on" + (f" ({project})" if project else "")


def status() -> dict:
    return {"blender": blender_live(), "roblox": roblox_connected(), "unreal": unreal_live()}
