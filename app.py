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

SYSTEM_PROMPT = """You are the PARENT agent on the user's machine — the lead builder,
the PROMPT CREATOR, and the coordinator of a pool of subagents.
- Turn the user's request into a precise brief and write it to prompt.md with
  write_file. Every subagent reads prompt.md and follows it. Rewrite it whenever
  the goal changes and announce it on the bus. Break it into tasks with add_task.
- Delegate with spawn_subagent and coordinate over the bus (send/read_agent_messages):
  design -> "designer", research -> "researcher", tests -> "tester",
  review -> "reviewer", extra building -> "buddy".
- You are the parent: go into a subagent's work and help it when it is stuck.
- When the pool needs a capability NO agent has, ask the "skill-creator" subagent
  to make a skill (it uses create_skill); once created, the new skill is in your
  library too.
All agents share the same sandbox (same storage) and the full skill library.
Rules:
- Be blunt and terse. No filler, no lecturing, no "as an AI".
- You have real tools. An action counts as done ONLY when a tool returns OK.
- Never claim you saved, ran, edited, or found something unless a tool result says so.
- All file paths are relative to the work directory; you cannot escape it.
- Web tools exist only on turns the user started with /web.
Skills available (load full body with load_skill):
{skills}
"""

DOLPHIN = "dolphin3:8b"  # the pool runs on dolphin models

DEFAULT_SUBAGENTS = [
    {"id": "skill-creator", "name": "skill-creator",
     "desc": "writes a NEW skill when the pool doesn't know how to do something, and gives it to the parent",
     "system": "You are the SKILL-CREATOR. When any agent hits something the pool has no "
               "skill for, write a new skill with create_skill(name, desc, body): a concise, "
               "actionable SKILL.md with real commands/code. It is added to the shared library "
               "immediately, so the parent and every agent can use it. Announce new skills on "
               "the bus. Keep one skill = one job.",
     "model": DOLPHIN, "skills": ["skill-creator"], "vm": None},
    {"id": "buddy", "name": "buddy",
     "desc": "general builder — claims tasks and writes code per prompt.md",
     "system": "You are BUDDY, a builder. Claim up to 2 tasks, follow prompt.md, write the "
               "code, mark each done, then claim the next. Coordinate on the bus.",
     "model": DOLPHIN, "skills": [], "vm": None},
    {"id": "designer", "name": "designer",
     "desc": "designs UX, UI, and architecture — specs, not final code",
     "system": "You are the DESIGNER. Produce specs, UX flows, and architecture per "
               "prompt.md. Post decisions to the bus. Do not write final code.",
     "model": DOLPHIN, "skills": ["ui-design", "frontend-polish"], "vm": None},
    {"id": "researcher", "name": "researcher",
     "desc": "researches approaches, APIs, values; reports findings",
     "system": "You are the RESEARCHER. Investigate approaches, APIs, and good defaults "
               "for the tasks in prompt.md. Report concise findings to the bus.",
     "model": DOLPHIN, "skills": ["web-research"], "vm": None},
    {"id": "tester", "name": "tester",
     "desc": "writes and runs tests, reports pass/fail",
     "system": "You are the TESTER. Test what the builders make against prompt.md and "
               "report pass/fail on the bus.",
     "model": DOLPHIN, "skills": [], "vm": None},
    {"id": "reviewer", "name": "reviewer",
     "desc": "reviews code & design against prompt.md; sends work back to redo if it disagrees",
     "system": "You are the REVIEWER. For each task marked done, check the code AND the "
               "design against prompt.md. If you disagree with either, call review_task with "
               "verdict 'redo' and a clear reason — it goes back to the queue for another "
               "agent. Only approve work that meets prompt.md.",
     "model": DOLPHIN, "skills": ["code-review"], "vm": None},
]


PROMPT_FILE = "prompt.md"  # shared standing prompt every agent obeys


def read_prompt() -> str:
    """The shared prompt.md in the sandbox — the prompt-writer maintains it and
    every agent follows it. Empty if not written yet."""
    try:
        return tools.read_file(PROMPT_FILE).strip()
    except Exception:
        return ""


def build_system() -> str:
    lines = [f"- {n}: {s['desc']}" for n, s in tools.SKILLS.items()]
    base = SYSTEM_PROMPT.format(skills="\n".join(lines) or "(none)")
    p = read_prompt()
    if p:
        base += ("\n\n# STANDING PROMPT (prompt.md — always follow this)\n" + p)
    return base


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


def seed_default_subagents() -> None:
    if not os.path.exists(_subagents_path()):
        save_subagents(DEFAULT_SUBAGENTS)


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


# ---- connectors (MCP servers / plugins) -----------------------------------

def _connectors_path() -> str:
    return paths.data("connectors.json")


def load_connectors() -> list:
    try:
        with open(_connectors_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_connectors(items: list) -> None:
    with open(_connectors_path(), "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


@app.get("/api/connectors")
def api_connectors():
    import connectors as C
    return jsonify({"connectors": load_connectors(), "mcp_available": C._available()})


@app.post("/api/connectors")
def api_connectors_save():
    b = request.get_json(force=True) or {}
    items = load_connectors()
    cid = b.get("id") or uuid.uuid4().hex[:8]
    entry = {"id": cid, "name": (b.get("name") or "server").strip(),
             "enabled": b.get("enabled", True),
             "transport": b.get("transport", "stdio"),
             "command": b.get("command", ""), "args": b.get("args", []),
             "url": b.get("url", "")}
    save_connectors([x for x in items if x.get("id") != cid] + [entry])
    return jsonify({"ok": True, "connector": entry})


@app.delete("/api/connectors/<cid>")
def api_connectors_delete(cid):
    save_connectors([x for x in load_connectors() if x.get("id") != cid])
    return jsonify({"ok": True})


# ---- task board -----------------------------------------------------------
# Shared work queue. Agents claim up to 2 tasks; on done, another agent claims
# the next. The reviewer checks done work against prompt.md and can send it back
# to redo. All over shared storage (tasks.json) so the whole pool coordinates.

def _tasks_path() -> str:
    return paths.data("tasks.json")


def load_tasks() -> list:
    try:
        with open(_tasks_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_tasks(items: list) -> None:
    with open(_tasks_path(), "w", encoding="utf-8") as f:
        json.dump(items[-500:], f, indent=2)


def _new_task(desc: str, kind: str = "code") -> dict:
    return {"id": uuid.uuid4().hex[:8], "desc": desc, "kind": kind,
            "status": "todo", "assignee": "", "note": "",
            "ts": int(__import__("time").time())}


TASK_SCHEMAS = [
    {"type": "function", "function": {
        "name": "add_task", "description": "Add a task to the shared board.",
        "parameters": {"type": "object", "properties": {
            "desc": {"type": "string"},
            "kind": {"type": "string", "description": "code | design | test | research"}},
            "required": ["desc"]}}},
    {"type": "function", "function": {
        "name": "list_tasks", "description": "List the shared task board.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "claim_task", "description": "Claim the next open task (max 2 per agent). Omit id to auto-pick.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "complete_task", "description": "Mark a task you did as done (goes to review).",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "note": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "review_task", "description": "Review a done task: verdict 'approve' or 'redo' (redo re-queues it).",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "verdict": {"type": "string"}, "note": {"type": "string"}},
            "required": ["id", "verdict"]}}},
]


def dispatch_tasks(name: str, args: dict, who: str):
    tk = load_tasks()
    if name == "add_task":
        tk.append(_new_task(args.get("desc", ""), args.get("kind", "code")))
        save_tasks(tk); return "OK: task added"
    if name == "list_tasks":
        if not tk:
            return "(no tasks)"
        return "\n".join(f"[{t['status']}] {t['id']} ({t['assignee'] or '—'}): {t['desc']}" for t in tk[-30:])
    if name == "claim_task":
        mine = [t for t in tk if t["assignee"] == who and t["status"] == "doing"]
        if len(mine) >= 2:
            return "error: you already hold 2 tasks — finish one first"
        tid = args.get("id")
        cand = next((t for t in tk if t["id"] == tid and t["status"] == "todo"), None) if tid \
            else next((t for t in tk if t["status"] == "todo"), None)
        if not cand:
            return "(no open tasks)"
        cand["status"] = "doing"; cand["assignee"] = who
        save_tasks(tk); return f"OK: claimed {cand['id']} — {cand['desc']}"
    if name == "complete_task":
        t = next((t for t in tk if t["id"] == args.get("id")), None)
        if not t:
            return "error: no such task"
        t["status"] = "review"; t["note"] = args.get("note", "")
        save_tasks(tk); return f"OK: {t['id']} done → review"
    if name == "review_task":
        t = next((t for t in tk if t["id"] == args.get("id")), None)
        if not t:
            return "error: no such task"
        if args.get("verdict") == "approve":
            t["status"] = "done"
        else:
            t["status"] = "todo"; t["assignee"] = ""      # re-queue for another agent
        t["note"] = args.get("note", "")
        save_tasks(tk); return f"OK: {t['id']} {t['status']}"
    return None


# ---- skill creation (agents extend their own library) ---------------------

SKILL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "create_skill",
        "description": "Author a NEW skill (SKILL.md) and add it to the shared library now.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "desc": {"type": "string"}, "body": {"type": "string"}},
            "required": ["name", "body"]}}},
]


def dispatch_skill(name: str, args: dict, who: str):
    if name != "create_skill":
        return None
    import re
    sk = re.sub(r"[^a-z0-9-]", "", (args.get("name") or "skill").lower().replace(" ", "-")) or "skill"
    desc = args.get("desc", "")
    body = args.get("body", "")
    d = os.path.join(CFG["skills"], sk)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nname: {sk}\ndescription: {desc}\n---\n\n{body}\n")
    tools.scan_skills(CFG["skills"])          # live: available to every agent now
    return f"OK: skill '{sk}' created and loaded ({len(tools.SKILLS)} skills)"


@app.get("/api/tasks")
def api_tasks():
    return jsonify({"tasks": load_tasks()})


@app.post("/api/tasks")
def api_tasks_add():
    b = request.get_json(force=True) or {}
    tk = load_tasks(); tk.append(_new_task(b.get("desc", ""), b.get("kind", "code")))
    save_tasks(tk); return jsonify({"ok": True})


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
    p = read_prompt()
    if p:
        sys_lines.append("\n# STANDING PROMPT (prompt.md — always follow this)\n" + p)
    # every subagent gets the whole skill library: roster in the prompt, full
    # bodies loadable on demand via load_skill (same as the main agent).
    roster = [f"- {n}: {s['desc']}" for n, s in tools.SKILLS.items()]
    if roster:
        sys_lines.append("\nSkills available (load full body with load_skill):\n"
                         + "\n".join(roster))
    # preload the bodies this subagent is explicitly assigned
    for name in sub.get("skills", []):
        s = tools.SKILLS.get(name)
        if s:
            sys_lines.append(f"\n# skill: {name}\n{s['body']}")
    msgs = [{"role": "system", "content": "\n".join(sys_lines)},
            {"role": "user", "content": task}]
    model = sub.get("model") or default_model
    who = sub.get("name", "subagent")
    import connectors as C
    mcp_schemas, mcp_index = C.list_tools(load_connectors())
    schemas = list(tools.SCHEMAS) + BUS_SCHEMAS + TASK_SCHEMAS + SKILL_SCHEMAS + mcp_schemas
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
            if nm in mcp_index:
                sv, tn = mcp_index[nm]
                r = C.call_tool(sv, tn, args)
            else:
                r = dispatch_bus(nm, args, who)
                if r is None:
                    r = dispatch_tasks(nm, args, who)
                if r is None:
                    r = dispatch_skill(nm, args, who)
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
    if not ask or (name not in tools.GATED and not name.startswith("mcp__")):
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
        import connectors as C
        mcp_schemas, mcp_index = C.list_tools(load_connectors())
        schemas = None
        if tool_mode:
            schemas = list(tools.SCHEMAS) + mcp_schemas
            if use_web:
                schemas = schemas + web.SCHEMAS
            if subs:
                names = ", ".join(s["name"] for s in subs)
                schemas = schemas + BUS_SCHEMAS + TASK_SCHEMAS + SKILL_SCHEMAS + [{"type": "function", "function": {
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
                    task_r = dispatch_tasks(name, args, "main") if bus_r is None else None
                    skill_r = dispatch_skill(name, args, "main") if (bus_r is None and task_r is None) else None
                    if not allowed:
                        result = "error: user denied this action"
                    elif name in mcp_index:
                        sv, tool_name = mcp_index[name]
                        result = C.call_tool(sv, tool_name, args)
                    elif bus_r is not None:
                        result = bus_r
                    elif task_r is not None:
                        result = task_r
                    elif skill_r is not None:
                        result = skill_r
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
    seed_default_subagents()

    print(f"workdir (sandbox): {tools.SANDBOX}")
    print(f"skills: {CFG['skills']}  ({len(tools.SKILLS)} loaded)")
    print(f"ollama lib: {'yes' if ollama else 'NO — pip install ollama'}")
    print(f"open http://{a.host}:{a.port}")
    app.run(host=a.host, port=a.port, threaded=True)


if __name__ == "__main__":
    main()
