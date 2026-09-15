"""Flask backend bridging the browser UI to Ollama + the agent tool loop.

Run:  python app.py --workdir ./workspace --skills ./skills
Then open http://localhost:5173
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import uuid

from flask import Flask, Response, jsonify, request, send_from_directory

import tools
import web

try:
    import ollama
except ImportError:  # keep UI usable even if lib missing
    ollama = None

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="")


def load_branding() -> dict:
    try:
        with open(os.path.join(HERE, "branding.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"name": "Local AI", "accent": "#d9795b", "accent_soft": "#e39a80"}

# runtime config (set in main)
CFG = {"workdir": os.path.join(HERE, "workspace"), "skills": os.path.join(HERE, "skills")}

# pending tool approvals: id -> {"event": Event, "allow": bool}
PENDING: dict[str, dict] = {}

SYSTEM_PROMPT = """You are a local coding agent running on the user's machine.
Rules:
- Be blunt and terse. No filler, no lecturing, no "as an AI".
- You have real tools. An action counts as done ONLY when a tool returns OK.
- Never claim you saved, ran, edited, or found something unless a tool result says so.
- All file paths are relative to the work directory; you cannot escape it.
- Web tools exist only on turns the user started with /web.
Skills available (load full body with load_skill):
{skills}
"""


def build_system() -> str:
    lines = [f"- {n}: {s['desc']}" for n, s in tools.SKILLS.items()]
    return SYSTEM_PROMPT.format(skills="\n".join(lines) or "(none)")


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---- static ---------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/branding")
def api_branding():
    return jsonify(load_branding())


@app.get("/assets/<path:name>")
def assets(name):
    return send_from_directory(os.path.join(HERE, "assets"), name)


# ---- config / models / skills ---------------------------------------------

@app.get("/api/config")
def api_config():
    return jsonify({
        "workdir": str(tools.SANDBOX),
        "skills_dir": CFG["skills"],
        "ollama": ollama is not None,
    })


@app.get("/api/models")
def api_models():
    if ollama is None:
        return jsonify({"models": [], "error": "ollama python lib not installed"})
    try:
        data = ollama.Client().list()
        names = [m.get("model") or m.get("name") for m in data.get("models", [])]
        return jsonify({"models": [n for n in names if n]})
    except Exception as e:
        return jsonify({"models": [], "error": str(e)})


@app.get("/api/skills")
def api_skills():
    tools.scan_skills(CFG["skills"])
    return jsonify({"skills": [
        {"name": n, "desc": s["desc"]} for n, s in tools.SKILLS.items()
    ]})


@app.get("/api/memory")
def api_memory():
    try:
        return jsonify({"memory": tools.read_file(tools.MEMORY_FILE)})
    except tools.ToolError:
        return jsonify({"memory": ""})


# ---- code view: file tree + read ------------------------------------------

@app.get("/api/tree")
def api_tree():
    root = tools.SANDBOX

    def walk(d):
        out = []
        for c in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name)):
            if c.name.startswith(".git"):
                continue
            rel = str(c.relative_to(root))
            if c.is_dir():
                out.append({"name": c.name, "path": rel, "dir": True,
                            "children": walk(c)})
            else:
                out.append({"name": c.name, "path": rel, "dir": False})
        return out

    return jsonify({"tree": walk(root)})


@app.get("/api/file")
def api_file():
    path = request.args.get("path", "")
    try:
        return jsonify({"path": path, "content": tools.read_file(path)})
    except tools.ToolError as e:
        return jsonify({"path": path, "content": "", "error": str(e)}), 404


# ---- VM view --------------------------------------------------------------
# The AI runs in a VM (see project docs). This backend exposes the VM's live
# stream URL and simple lifecycle actions. Configure VM_STREAM to point at the
# VM's VNC/MJPEG/WebRTC stream. Actions are wired to VM_* env hooks; with none
# set they report a clear "not configured" status instead of faking success.

VM = {
    "stream": os.environ.get("VM_STREAM", ""),
    "status": "unknown",
    "app_url": os.environ.get("VM_APP_URL", ""),
}


@app.get("/api/vm")
def api_vm():
    return jsonify(VM)


@app.post("/api/vm/action")
def api_vm_action():
    action = (request.get_json(force=True) or {}).get("action", "")
    hook = os.environ.get(f"VM_HOOK_{action.upper()}")
    if not hook:
        VM["status"] = f"'{action}' not configured (set VM_HOOK_{action.upper()})"
        return jsonify(VM)
    try:
        import subprocess
        subprocess.Popen(hook, shell=True)
        VM["status"] = f"{action}: launched"
    except Exception as e:
        VM["status"] = f"{action}: error {e}"
    return jsonify(VM)


@app.post("/api/approve")
def api_approve():
    body = request.get_json(force=True)
    p = PENDING.get(body.get("id"))
    if not p:
        return jsonify({"ok": False, "error": "unknown id"}), 404
    p["allow"] = bool(body.get("allow"))
    p["event"].set()
    return jsonify({"ok": True})


# ---- chat -----------------------------------------------------------------

def gate(name: str, args: dict, ask: bool):
    """Yield an SSE approval round-trip for a gated tool. Returns True if allowed."""
    if not ask or name not in tools.GATED:
        return True, ""
    cid = uuid.uuid4().hex
    ev = threading.Event()
    PENDING[cid] = {"event": ev, "allow": False}
    yield sse("approval", {"id": cid, "tool": name, "args": args})
    ev.wait(timeout=300)
    allowed = PENDING.pop(cid, {}).get("allow", False)
    return allowed, cid


@app.post("/api/chat")
def api_chat():
    body = request.get_json(force=True)
    model = body.get("model")
    history = body.get("messages", [])
    use_web = bool(body.get("web"))
    tool_mode = bool(body.get("tools", True))
    ask = bool(body.get("ask", True))

    def stream():
        if ollama is None:
            yield sse("error", "ollama python lib not installed on the server")
            yield sse("done", {})
            return
        client = ollama.Client()
        msgs = [{"role": "system", "content": build_system()}] + history

        schemas = None
        if tool_mode:
            schemas = list(tools.SCHEMAS)
            if use_web:
                schemas = schemas + web.SCHEMAS

        try:
            for _ in range(12):  # tool-loop cap
                acc = ""
                calls = []
                resp = client.chat(model=model, messages=msgs,
                                    tools=schemas, stream=True)
                for chunk in resp:
                    msg = chunk.get("message", {})
                    piece = msg.get("content") or ""
                    if piece:
                        acc += piece
                        yield sse("token", piece)
                    for tc in (msg.get("tool_calls") or []):
                        calls.append(tc)

                msgs.append({"role": "assistant", "content": acc,
                             "tool_calls": calls or None})

                if not calls:
                    break

                for tc in calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    yield sse("tool_call", {"name": name, "args": args})

                    allowed, _ = yield from gate(name, args, ask)
                    if not allowed:
                        result = "error: user denied this action"
                    elif name in web.REGISTRY:
                        result = web.run_web_tool(name, args) if use_web \
                            else "error: web tools disabled this turn"
                    else:
                        result = tools.run_tool(name, args)

                    yield sse("tool_result", {"name": name, "result": result})
                    msgs.append({"role": "tool", "content": result})
        except Exception as e:
            yield sse("error", str(e))
        yield sse("done", {})

    return Response(stream(), mimetype="text/event-stream")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=CFG["workdir"])
    ap.add_argument("--skills", default=CFG["skills"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5173)
    a = ap.parse_args()

    CFG["workdir"] = os.path.abspath(a.workdir)
    CFG["skills"] = os.path.abspath(a.skills)
    tools.set_sandbox(CFG["workdir"])
    tools.scan_skills(CFG["skills"])

    print(f"workdir (sandbox): {tools.SANDBOX}")
    print(f"skills: {CFG['skills']}  ({len(tools.SKILLS)} loaded)")
    print(f"ollama lib: {'yes' if ollama else 'NO — pip install ollama'}")
    print(f"open http://{a.host}:{a.port}")
    app.run(host=a.host, port=a.port, threaded=True)


if __name__ == "__main__":
    main()
