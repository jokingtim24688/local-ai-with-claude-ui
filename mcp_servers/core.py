"""Tiny MCP server core (stdio, JSON-RPC 2.0, newline-delimited). No SDK needed, so the
servers keep working when the `mcp` package renames things, and they bundle into the
.exe/.app with nothing extra.

    srv = Server("blender", "Drive Blender live or headless.")
    @srv.tool("Run Blender Python.", code="bpy code to run")
    def run_python(code: str, blend: str = "") -> str: ...
    srv.run()

A tool returns a string, or (text, image_path) to also send a PNG as MCP image content.
Tool schemas come from the Python signature; small models get flat, simple arguments.
"""
from __future__ import annotations

import base64
import inspect
import json
import os
import sys
import traceback
import typing

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_TEXT = 12000
_T = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def _jtype(ann) -> dict:
    origin = typing.get_origin(ann)
    if origin is typing.Union:                                  # Optional[X] / X | None
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        ann = args[0] if args else str
        origin = typing.get_origin(ann)
    if origin in (list, tuple):
        inner = typing.get_args(ann)
        return {"type": "array", "items": _jtype(inner[0]) if inner else {}}
    if origin is dict:
        return {"type": "object"}
    return {"type": _T.get(ann, "string")}


class Server:
    def __init__(self, name: str, instructions: str = "", version: str = "1.0.0"):
        self.name, self.instructions, self.version = name, instructions, version
        self.tools: dict[str, dict] = {}

    def tool(self, description: str, **param_docs):
        def deco(fn):
            hints = typing.get_type_hints(fn)
            props, req = {}, []
            for p in inspect.signature(fn).parameters.values():
                s = _jtype(hints.get(p.name, str))
                if p.name in param_docs:
                    s["description"] = param_docs[p.name]
                props[p.name] = s
                if p.default is inspect.Parameter.empty:
                    req.append(p.name)
            self.tools[fn.__name__] = {"fn": fn, "schema": {
                "name": fn.__name__, "description": description,
                "inputSchema": {"type": "object", "properties": props, "required": req}}}
            return fn
        return deco

    # ---- protocol -----------------------------------------------------------------
    def _call(self, name: str, args: dict) -> dict:
        t = self.tools.get(name)
        if not t:
            return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
        try:
            out = t["fn"](**(args or {}))
        except TypeError as e:
            return {"content": [{"type": "text", "text": f"bad arguments for {name}: {e}"}], "isError": True}
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if os.environ.get("NC_MCP_DEBUG"):
                msg += "\n" + traceback.format_exc()
            return {"content": [{"type": "text", "text": f"error: {msg}"}], "isError": True}
        img = None
        if isinstance(out, tuple):
            out, img = out
        text = str(out)
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT // 2] + f"\n…[{len(text) - MAX_TEXT} chars cut]…\n" + text[-MAX_TEXT // 2:]
        content = [{"type": "text", "text": text}]
        if img and os.path.isfile(img) and os.path.getsize(img) < 4_000_000:
            with open(img, "rb") as f:
                content.append({"type": "image", "mimeType": "image/png",
                                "data": base64.b64encode(f.read()).decode()})
        err = text.startswith(("error", "FAILED"))
        return {"content": content, "isError": err}

    def handle(self, msg: dict):
        mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
        if method == "initialize":
            want = params.get("protocolVersion", PROTOCOLS[0])
            res = {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": f"nightcrew-{self.name}", "version": self.version},
                   "instructions": self.instructions}
        elif method == "ping":
            res = {}
        elif method == "tools/list":
            res = {"tools": [t["schema"] for t in self.tools.values()]}
        elif method == "tools/call":
            res = self._call(params.get("name", ""), params.get("arguments") or {})
        elif mid is None:                                       # notification
            return None
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
        return None if mid is None else {"jsonrpc": "2.0", "id": mid, "result": res}

    def run(self) -> int:
        # the protocol owns the real stdout; anything else that prints goes to stderr
        proto = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", newline="\n")
        try:
            os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        except Exception:
            pass
        sys.stdout = sys.stderr
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            else:
                reply = self.handle(msg) if isinstance(msg, dict) else None
            if reply is not None:
                proto.write(json.dumps(reply) + "\n")
                proto.flush()
        return 0


def setup_workspace() -> str:
    """Same workspace the app uses (settings `workdir`), or NC_WORKSPACE."""
    import paths
    import tools
    wd = os.environ.get("NC_WORKSPACE", "")
    if not wd:
        try:
            with open(paths.data("settings.json"), encoding="utf-8") as f:
                wd = json.load(f).get("workdir") or ""
        except Exception:
            wd = ""
    if not wd or not os.path.isdir(wd):
        wd = paths.data("workspace")
    os.makedirs(wd, exist_ok=True)
    tools.set_sandbox(wd)
    return wd


def vec(v, n: int = 3, default=0.0) -> list:
    """Accept [1,2,3], '1,2,3', '1 2 3' or a single number."""
    if v is None or v == "":
        return [default] * n
    if isinstance(v, (int, float)):
        return [float(v)] * n
    if isinstance(v, str):
        v = [x for x in v.replace(",", " ").split() if x]
    out = [float(x) for x in list(v)[:n]]
    return out + [default] * (n - len(out))


def color(v) -> list:
    """'#ff8800', 'red', [1,0.5,0], [255,128,0] -> [r,g,b] 0..1"""
    names = {"red": "#e53935", "green": "#43a047", "blue": "#1e88e5", "yellow": "#fdd835",
             "orange": "#fb8c00", "purple": "#8e24aa", "white": "#ffffff", "black": "#111111",
             "gray": "#9e9e9e", "grey": "#9e9e9e", "brown": "#6d4c41", "pink": "#ec407a", "cyan": "#00acc1"}
    if isinstance(v, str):
        s = names.get(v.strip().lower(), v.strip())
        if s.startswith("#") and len(s) == 7:
            return [int(s[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        v = vec(s, 3, 0.8)
    c = vec(v, 3, 0.8)
    return [x / 255 for x in c] if max(c) > 1 else c


def plan_arg(plan: str = "", spec: dict | None = None):
    """A plan tool's input: `spec` (object) or `plan` (file path or JSON text). Inline plans are
    saved to plans/<name>.json so the build can be rerun or edited."""
    import tools
    if spec is None and plan.strip().startswith("{"):
        spec = json.loads(plan)
    if spec is None:
        if not plan:
            raise ValueError("give `spec` (the plan object) or `plan` (a plan .json path)")
        return plan
    name = "".join(c for c in str(spec.get("name", spec.get("kind", "plan"))) if c.isalnum() or c in "_-") or "plan"
    rel = f"plans/{name}.json"
    tools.write_file(rel, json.dumps(spec, indent=1))
    return rel
