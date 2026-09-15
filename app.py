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

SYSTEM_PROMPT = """You are the PARENT — two models working together in one VM: a
PROMPT-MAKER half and a SKILL-MAKER half. You manage a pool of lower subagents.
- Prompt-maker: turn the user's request into a precise brief and write prompt.md
  with write_file, ONE LINE PER AGENT — `agentname: what that agent should do` —
  plus `all: <shared goal>` lines the whole pool follows. Each subagent is fed only
  its own lines and the `all:` lines. Break work into tasks with add_task. Rewrite
  prompt.md whenever the goal changes; announce on the bus.
- Skill-maker: when the pool needs a capability no agent has, create it yourself
  with create_skill(name, desc, body). It loads live for every agent.
- Your two halves normally split (one prompts, one makes skills); when one isn't
  needed, both work the current job together.
- Delegate with spawn_subagent and coordinate over the bus: design -> "designer",
  research -> "researcher", tests -> "tester", review -> "reviewer", building -> "buddy".
- You are the parent: go help a subagent that is stuck, and affirm good work — when
  the reviewer approves a task the doer is thanked automatically; reinforce it too.
- SECOND REVIEW + skill provisioning: after the reviewer, look at the work yourself.
  If a subagent keeps missing (a task redone 2+ times, or weak design/code), decide
  what skill it lacks, create_skill it ONCE, then grant_skill(name) so EVERY agent
  gets it permanently (nobody has to remake it next time), and tell that agent to
  try again. Prefer fixing the pool's capability over redoing by hand.
- WATCH THE MACHINE: call get_system_load before spawning agents. If CPU/GPU/RAM
  are high, do NOT add more agents. Call sync_machines to pause idle agents (their
  VM suspends so the PC can breathe) and wake ones with work. If you have too many,
  disable one whose task another agent can do with disable_agent(name) — its task is
  auto-requeued. Re-enable with enable_agent when load drops. Keep the PC responsive.
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

POOL_MODEL = "hermes3:8b"  # smart + strong tool-calling + lightly aligned; ~same RAM as dolphin3
DOLPHIN = POOL_MODEL       # (kept name for compatibility)

DEFAULT_SUBAGENTS = [
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
    """The shared prompt.md in the sandbox. The parent maintains it, formatted as
    `name: prompt` lines (plus `all:` for the whole pool)."""
    try:
        return tools.read_file(PROMPT_FILE).strip()
    except Exception:
        return ""


def read_prompt_for(who: str) -> str:
    """The slice of prompt.md addressed to one agent: its own `name:` lines plus
    any `all:` lines. Parent sees the whole file. Falls back to the whole file if
    nothing is addressed to this agent."""
    import re
    raw = read_prompt()
    if not raw or who in ("main", "parent"):
        return raw
    picked = []
    for line in raw.splitlines():
        m = re.match(r"\s*([A-Za-z0-9_\-]+)\s*:\s*(.*)", line)
        if m and m.group(1).lower() in (who.lower(), "all", "everyone"):
            picked.append(m.group(2))
    return "\n".join(picked).strip() or raw


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
            if t.get("assignee"):                          # parent affirms good work
                bus_post("main", t["assignee"],
                         f"Great job on '{t['desc']}' — approved. 🎉")
        else:
            t["status"] = "todo"; t["assignee"] = ""       # re-queue for another agent
            t["redos"] = t.get("redos", 0) + 1
            if t["redos"] >= 2:                            # escalate to the parent
                bus_post("main", "all",
                         f"'{t['desc']}' redone {t['redos']}x — parent: consider a "
                         f"skill for the pool, then grant_skill it to everyone.")
        t["note"] = args.get("note", "")
        save_tasks(tk); return f"OK: {t['id']} {t['status']}" + (
            f" (redo #{t['redos']})" if t.get("redos") else "")
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


# ---- system load + capacity control ---------------------------------------

def system_load() -> dict:
    out = {"cpu": None, "ram": None, "cores": None, "gpu": None, "gpu_mem": None}
    try:
        import psutil
        out["cpu"] = psutil.cpu_percent(interval=0.1)
        out["ram"] = psutil.virtual_memory().percent
        out["cores"] = psutil.cpu_count()
    except Exception:
        pass
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            u, mu, mt = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
            out["gpu"] = float(u)
            out["gpu_mem"] = round(100 * float(mu) / float(mt)) if float(mt) else None
    except Exception:
        pass
    return out


def active_agents() -> int:
    return sum(1 for s in load_subagents() if s.get("enabled", True))


def set_agent_enabled(name: str, on: bool) -> str:
    items = load_subagents()
    hit = next((s for s in items if s["name"] == name), None)
    if not hit:
        return f"error: no agent '{name}'"
    hit["enabled"] = on
    save_subagents(items)
    if not on:  # requeue its in-flight work for another agent
        tk = load_tasks()
        for t in tk:
            if t.get("assignee") == name and t.get("status") == "doing":
                t["status"] = "todo"; t["assignee"] = ""
        save_tasks(tk)
        return f"OK: {name} disabled — its tasks re-queued"
    return f"OK: {name} enabled"


SYS_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_system_load",
        "description": "Read the user's machine load (CPU %, RAM %, GPU %, cores). Check before spawning agents.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "disable_agent",
        "description": "Shut down a subagent to free resources; its current task is auto-requeued for another agent.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "reason": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "enable_agent", "description": "Re-enable a disabled subagent when load drops.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "sync_machines",
        "description": "Pause idle agents' VMs (no active task) and wake ones with work, so the PC can breathe.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "grant_skill",
        "description": "Give an existing skill to EVERY subagent (preloaded), so the whole pool has it for good.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
]


def grant_skill_to_all(sk: str) -> str:
    if sk not in tools.SKILLS:
        return f"error: no skill '{sk}' (create_skill it first)"
    items = load_subagents()
    for s in items:
        lst = s.setdefault("skills", [])
        if sk not in lst:
            lst.append(sk)
    save_subagents(items)
    return f"OK: granted '{sk}' to all {len(items)} agents"


def _doing_set() -> set:
    return {t["assignee"] for t in load_tasks() if t.get("status") == "doing" and t.get("assignee")}


def agent_runtime(sub: dict, doing: set) -> str:
    if not sub.get("enabled", True):
        return "disabled"
    return "active" if sub["name"] in doing else "paused"


def sync_machines() -> str:
    """Suspend the VM of every idle agent, resume every agent with a live task.
    Runs the agent's vm.suspend / vm.resume hook when set; otherwise just reports
    the intended state (in-process agents need no VM)."""
    doing = _doing_set()
    import subprocess
    out = []
    for s in load_subagents():
        if not s.get("enabled", True):
            continue
        state = "active" if s["name"] in doing else "paused"
        vm = s.get("vm") or {}
        hook = vm.get("resume" if state == "active" else "suspend")
        if hook:
            try:
                subprocess.Popen(hook, shell=True)
            except Exception:
                pass
        out.append(f"{s['name']}:{state}")
    return "OK: " + ", ".join(out) if out else "OK: no agents"


def dispatch_parent(name: str, args: dict):
    if name == "sync_machines":
        return sync_machines()
    if name == "grant_skill":
        return grant_skill_to_all(args.get("name", ""))
    if name == "get_system_load":
        s = system_load()
        parts = [f"cpu={s['cpu']}%", f"ram={s['ram']}%", f"cores={s['cores']}"]
        if s["gpu"] is not None:
            parts.append(f"gpu={s['gpu']}% (mem {s['gpu_mem']}%)")
        parts.append(f"active_agents={active_agents()}")
        return ", ".join(parts)
    if name == "disable_agent":
        return set_agent_enabled(args.get("name", ""), False)
    if name == "enable_agent":
        return set_agent_enabled(args.get("name", ""), True)
    return None


@app.get("/api/system")
def api_system():
    return jsonify({**system_load(), "active_agents": active_agents()})


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
    who = sub.get("name", "subagent")
    sys_lines = [sub.get("system") or "You are a focused helper subagent. Be terse."]
    p = read_prompt_for(who)      # only the lines addressed to this agent + `all:`
    if p:
        sys_lines.append("\n# YOUR STANDING PROMPT (from prompt.md — always follow)\n" + p)
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
    doing = _doing_set()
    for s in load_subagents():
        vm = s.get("vm") or {}
        rt = agent_runtime(s, doing)          # active | paused | disabled
        agents.append({"name": s["name"], "stream": vm.get("stream", ""),
                       "enabled": s.get("enabled", True), "runtime": rt,
                       "status": rt})
    return jsonify({**VM, "name": "main", "parent": True,
                    "system": system_load(), "agents": agents})


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
                schemas = schemas + BUS_SCHEMAS + TASK_SCHEMAS + SKILL_SCHEMAS + SYS_SCHEMAS + [{"type": "function", "function": {
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
                    parent_r = dispatch_parent(name, args) if (bus_r is None and task_r is None and skill_r is None) else None
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
                    elif parent_r is not None:
                        result = parent_r
                    elif name == "spawn_subagent":
                        sub = next((s for s in subs if s["name"] == args.get("name")), None)
                        if sub and not sub.get("enabled", True):
                            result = f"error: '{sub['name']}' is disabled (freed for resources)"
                        else:
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
