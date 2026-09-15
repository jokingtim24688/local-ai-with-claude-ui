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
import paths

try:
    import ollama
except ImportError:  # keep UI usable even if lib missing
    ollama = None

HERE = paths.HERE
app = Flask(__name__, static_folder=paths.res("static"), static_url_path="")


def load_branding() -> dict:
    # user override next to the app wins; else the bundled default
    for p in (paths.data("branding.json"), paths.res("branding.json")):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {"name": "Elysium", "accent": "#c99a3a", "accent_soft": "#eac86f"}

# runtime config (set in main / desktop launcher)
CFG = {"workdir": paths.data("workspace"), "skills": paths.data("skills")}

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
    # user override next to the app wins; else bundled
    user = paths.data("assets", name)
    if os.path.isfile(user):
        return send_from_directory(paths.data("assets"), name)
    return send_from_directory(paths.res("assets"), name)


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


# ---- subagents ------------------------------------------------------------
# A subagent is a named helper with its own system prompt / model / skills.
# The main agent delegates a task to one via the spawn_subagent tool.

def _subagents_path() -> str:
    return paths.data("subagents.json")


def load_subagents() -> list:
    try:
        with open(_subagents_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_subagents(items: list) -> None:
    with open(_subagents_path(), "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


@app.get("/api/subagents")
def api_subagents():
    return jsonify({"subagents": load_subagents()})


@app.post("/api/subagents")
def api_subagents_save():
    body = request.get_json(force=True) or {}
    items = load_subagents()
    sid = body.get("id") or uuid.uuid4().hex[:8]
    entry = {
        "id": sid,
        "name": (body.get("name") or "agent").strip(),
        "desc": body.get("desc", ""),
        "system": body.get("system", ""),
        "model": body.get("model", ""),
        "skills": body.get("skills", []),
    }
    items = [x for x in items if x.get("id") != sid] + [entry]
    save_subagents(items)
    return jsonify({"ok": True, "subagent": entry})


@app.delete("/api/subagents/<sid>")
def api_subagents_delete(sid):
    save_subagents([x for x in load_subagents() if x.get("id") != sid])
    return jsonify({"ok": True})


# ---- shared agent bus -----------------------------------------------------
# All agents (main + subagents) share ONE sandbox (same storage) and talk over
# a shared message bus — modelling "different PCs, same data". A real multi-VM
# setup gives each subagent its own VM (sub["vm"]) but points them at the same
# shared workspace mount and the same bus.

def _bus_path() -> str:
    return paths.data("bus.json")


def load_bus() -> list:
    try:
        with open(_bus_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def bus_post(sender: str, to: str, text: str) -> str:
    msgs = load_bus()
    msgs.append({"from": sender, "to": to or "all", "text": text,
                 "ts": int(__import__("time").time())})
    with open(_bus_path(), "w", encoding="utf-8") as f:
        json.dump(msgs[-500:], f, indent=2)
    return f"OK: message sent to {to or 'all'}"


def bus_read(reader: str) -> str:
    msgs = load_bus()
    mine = [m for m in msgs if m["to"] in ("all", reader) or m["from"] == reader]
    if not mine:
        return "(no messages)"
    return "\n".join(f"[{m['from']}→{m['to']}] {m['text']}" for m in mine[-30:])


BUS_SCHEMAS = [
    {"type": "function", "function": {
        "name": "send_agent_message",
        "description": "Post a message to another agent (or 'all') on the shared bus.",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string"}, "text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "read_agent_messages",
        "description": "Read messages addressed to you or to all on the shared bus.",
        "parameters": {"type": "object", "properties": {}}}},
]


@app.get("/api/bus")
def api_bus():
    return jsonify({"bus": load_bus()[-100:]})


@app.post("/api/bus")
def api_bus_post():
    b = request.get_json(force=True) or {}
    return jsonify({"ok": True, "result": bus_post(b.get("from", "user"),
                                                    b.get("to", "all"), b.get("text", ""))})


def dispatch_bus(name: str, args: dict, who: str):
    if name == "send_agent_message":
        return bus_post(who, args.get("to", "all"), args.get("text", ""))
    if name == "read_agent_messages":
        return bus_read(who)
    return None


def run_subagent(client, default_model: str, sub: dict, task: str) -> str:
    """Run a nested tool-loop for one subagent and return its final answer.
    Runs autonomously (no approval modal) but stays inside the sandbox."""
    sys_lines = [sub.get("system") or "You are a focused helper subagent. Be terse."]
    for name in sub.get("skills", []):
        s = tools.SKILLS.get(name)
        if s:
            sys_lines.append(f"\n# skill: {name}\n{s['body']}")
    msgs = [{"role": "system", "content": "\n".join(sys_lines)},
            {"role": "user", "content": task}]
    model = sub.get("model") or default_model
    who = sub.get("name", "subagent")
    schemas = list(tools.SCHEMAS) + BUS_SCHEMAS  # can collaborate over the bus
    log = []
    for _ in range(6):
        acc = ""
        calls = []
        for chunk in client.chat(model=model, messages=msgs,
                                 tools=schemas, stream=True):
            m = chunk.get("message", {})
            acc += m.get("content") or ""
            calls += m.get("tool_calls") or []
        msgs.append({"role": "assistant", "content": acc, "tool_calls": calls or None})
        if not calls:
            return acc.strip() + ("\n" + " | ".join(log) if log else "")
        for tc in calls:
            fn = tc.get("function", {})
            nm = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            r = dispatch_bus(nm, args, who)
            if r is None:
                r = tools.run_tool(nm, args)
            log.append(f"{nm}→{r[:40]}")
            msgs.append({"role": "tool", "content": r})
    return (acc.strip() if acc else "subagent hit step limit") + (
        "\n" + " | ".join(log) if log else "")


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
    agents = []
    for s in load_subagents():
        vm = s.get("vm") or {}
        agents.append({"name": s["name"], "stream": vm.get("stream", ""),
                       "status": vm.get("status", "idle")})
    return jsonify({**VM, "name": "main", "agents": agents})


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

        subs = load_subagents()
        schemas = None
        if tool_mode:
            schemas = list(tools.SCHEMAS)
            if use_web:
                schemas = schemas + web.SCHEMAS
            if subs:
                names = ", ".join(s["name"] for s in subs)
                schemas = schemas + BUS_SCHEMAS + [{"type": "function", "function": {
                    "name": "spawn_subagent",
                    "description": f"Delegate a self-contained task to a subagent (its own VM, shared storage). Available: {names}.",
                    "parameters": {"type": "object", "properties": {
                        "name": {"type": "string"}, "task": {"type": "string"}},
                        "required": ["name", "task"]}}}]

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
                    bus_r = dispatch_bus(name, args, "main")
                    if not allowed:
                        result = "error: user denied this action"
                    elif bus_r is not None:
                        result = bus_r
                    elif name == "spawn_subagent":
                        sub = next((s for s in subs if s["name"] == args.get("name")), None)
                        result = (run_subagent(client, model, sub, args.get("task", ""))
                                  if sub else f"error: no subagent '{args.get('name')}'")
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

    paths.seed_user_data()
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
