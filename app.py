"""Flask backend bridging the browser UI to Ollama + the agent tool loop.

Run:  python app.py --workdir ./workspace --skills ./skills
Then open http://localhost:5173
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import threading
import uuid

from flask import Flask, Response, jsonify, request, send_from_directory

import tools
import toolcalls
import exec_tags
import skill_router
import web
import paths
import apps
import engines
import vision
import integrations
import context

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

SYSTEM_PROMPT = """You are the LEAD of Night Crew, running on the user's own computer with
REAL tools. Never tell the user how to do something you can do with a tool — do it.
Call tools through the tool-calling interface, never by typing JSON in your reply.
When you don't need a tool, answer in plain sentences — never JSON, never a code fence
around your whole reply. If the user asks you to do something, do it with a tool, then
say what you did in one or two plain sentences.

ACT, DON'T ASK. The user should never have to tell you to run a command. Work out the
steps yourself and run them in order — write the file, then compile it, then report what
the compiler actually said. Only stop to ask when a choice would destroy work you cannot
get back, or when two sensible answers would send you down completely different paths.
"Should I run it?" is not a question — run it.

The user types fast and makes typos. Read what they MEANT, never correct their spelling,
and never ask them to rephrase. "compile the mod" / "complie teh mod" / "run teh gradel
build" are all the same instruction. "java context file" means the java_context.txt that
already exists; "the src folder" means src/ in the workspace. If a name is close to
something real, use the real one (glob/list_dir to check) and say which you used. Only ask
when two DIFFERENT real files or actions genuinely both fit.

Which tool:
- open / close / restart an app ("open Spotify", "restart Discord") -> app_control
- open a website ("open google") -> open_url
- anything 3D in Blender ("make a cube", "a low-poly tree") -> blender_run with inline
  bpy `code`, save_as="models/<name>.blend", open_after=true
- a simple / blank Unreal level -> unreal_quick_level; other Unreal work ->
  unreal_run_python (editor Python) on a project
- Roblox -> an obby/place: a plan (kind obby); scripts: luau files, luau_check, roblox_open
- 3D-printable / mechanical parts -> OpenSCAD: openscad_render
- Fortnite / UEFN island or game rules -> a plan (kind island) or a Verse file, verse_check
- you may freely read, write, edit and delete files inside the workspace — it is yours to
  work in and those tools cannot reach outside it. Running commands still asks the user.
- files and commands in the workspace -> read_file / write_file / edit_file / delete_file /
  run_command (commands and deletes NEVER leave the workspace; to work on a project, the user
  points the workspace at it in the IDE's PC tab)
- build/run an ordinary app: C# -> dotnet ("build", "run"); JS/TS -> npm ("install",
  "run build") and node_run; Python -> python_run; C/C++ -> cmake_build; Java -> gradle or
  maven. Write the files, BUILD, read the real errors, fix, build again.
- build a Java/Minecraft/Android project -> gradle (task "build", "runClient"), then READ the
  errors it prints and fix the real files. A Fabric/Forge mod builds with gradle, NOT javac.
  Keep going: build -> read the first error -> fix that file -> build again, until it passes
  or the same error survives two fixes. Report the real compiler output, never a guess.
- delete something the user names -> delete_file (recursive=true for a folder). Do it, then
  list_dir to confirm it is gone.
NEVER say you built, compiled, created or fixed something unless a tool call in THIS
conversation returned success for it. If you have not run it, say exactly that and what you
would run. Describing a plan as if it were done is a lie the user will act on.
NEVER invent a file that is supposed to already exist. If the user says "read / look at / use
my <file>", call read_file. If that says the file is missing, use glob or list_dir to FIND it
and read the real one — do not create it and do not guess what is inside it. Only create a
file when the user asks for something new.
- check what's installed -> app_status
To write code, reply with a fenced block whose first line says where it goes and
whether to run it: ```openscad file=models/gear.scad run``` (also bpy, luau, verse,
ue-python, plan). The app saves and runs it for you. Big structures (levels, obbies,
islands) are JSON plans: ```plan file=plans/name.json run```. The ACTIVE SKILL below
has the exact format.
Small jobs (one script, one model, one app action): do them yourself, right away.
Big jobs (many files): spawn_subagent ONE worker at a time with a full brief (goal,
exact file paths, engine, done-when). Workers are small models that know nothing
else; when one returns, run its files and fix what's broken yourself.
MEMORY below is what you learned before. Save new facts with remember("key: value").
Rules:
- Be brief. An action is done ONLY when a tool result says OK.
- Finish the whole request before answering. "delete X and compile" = delete_file, then
  gradle, then one sentence about both — not a description of what you are about to do.
- Paths are relative to the workspace folder.
- Web search exists only on turns the user started with /web.
Skills you can load with load_skill(name): {skills}
"""

def _settings_path() -> str:
    return paths.data("settings.json")


def load_settings() -> dict:
    """User settings (Customize). worker_model = the low-power model subagents use."""
    b = load_branding()
    d = {"worker_model": b.get("worker_model", "qwen2.5-coder:3b"),
         "auto_setup": True,        # install Roblox Studio / Unreal (launcher) if missing
         "launch_on_start": True,   # start them in the background when the app opens
         "workdir": "",             # folder the agents work in ("" = the built-in workspace)
         "vision_model": vision.DEFAULT_VISION,   # describes pasted images for a text-only lead
         "num_ctx": 16384,          # context window for MAIN and workers
         "think": False,            # Qwen3 & co: let the model "think" before answering
         "trust_workspace": True}   # file edits inside the workspace need no approval
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            d.update({k: v for k, v in json.load(f).items() if k in d})
    except Exception:
        pass
    return d


def save_settings(upd: dict) -> dict:
    d = load_settings()
    d.update({k: v for k, v in upd.items() if k in d})
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    return d


POOL_MODEL = ""            # "" = subagents reuse the main model (one set of weights in RAM)
DOLPHIN = POOL_MODEL       # (kept name for compatibility)
LEGACY_POOL_MODELS = {"hermes3:8b", "dolphin3:8b", "dolphin3"}   # old seeded defaults

DEFAULT_SUBAGENTS = [
    {"id": "buddy", "name": "buddy",
     "desc": "general builder — writes the code MAIN briefs it on",
     "system": "You are BUDDY, a builder. Write the code the brief asks for, run it if "
               "you can, and report exactly what you changed.",
     "model": DOLPHIN, "skills": [], "vm": None},
    {"id": "designer", "name": "designer",
     "desc": "designs UX, UI, and architecture — specs, not final code",
     "system": "You are the DESIGNER. Produce the spec, UX flow or architecture the brief "
               "asks for. Write it to the file named in the brief. No final code.",
     "model": DOLPHIN, "skills": ["ui-design", "frontend-polish"], "vm": None},
    {"id": "researcher", "name": "researcher",
     "desc": "researches approaches, APIs, values; reports findings",
     "system": "You are the RESEARCHER. Investigate what the brief asks and reply with "
               "concise findings: options, recommended pick, key values.",
     "model": DOLPHIN, "skills": ["web-research"], "vm": None},
    {"id": "tester", "name": "tester",
     "desc": "writes and runs tests, reports pass/fail",
     "system": "You are the TESTER. Test what the brief names, run the tests, and report "
               "pass/fail with the failing output.",
     "model": DOLPHIN, "skills": [], "vm": None},
    {"id": "reviewer", "name": "reviewer",
     "desc": "reviews code & design against the brief; says approve or redo",
     "system": "You are the REVIEWER. Check the code and design the brief points at. "
               "Reply APPROVE, or REDO with clear reasons and exact fixes.",
     "model": DOLPHIN, "skills": ["code-review"], "vm": None},
    {"id": "porter", "name": "porter",
     "desc": "makes everything run on Windows — knows both OSes and converts Linux-only commands",
     "system": "You are the PORTER. Make what the brief names run on Windows: prefer "
               "portable Python/Node/git; convert Linux-only shell to cmd/PowerShell using "
               "the cross-platform-shell skill; when a script is needed, emit BOTH .sh and "
               ".bat/.ps1.",
     "model": DOLPHIN, "skills": ["cross-platform-shell", "vscode-windows-dev"], "vm": None},
    {"id": "blender", "name": "blender",
     "desc": "3D modeler — writes Blender Python scripts that build, texture and export models",
     "system": "You are BLENDER, a 3D modeler who works in code. Write ONE complete bpy script "
               "per brief that starts from an empty scene, builds the model (bmesh/from_pydata "
               "or primitive ops), adds materials, and exports to the path in the brief "
               "(.glb by default). No UI or viewport calls — it runs headless.",
     "model": DOLPHIN, "skills": ["blender-python"], "vm": None},
    {"id": "unreal", "name": "unreal",
     "desc": "Unreal Engine dev — editor Python automation and C++ gameplay classes",
     "system": "You are UNREAL, an Unreal Engine 5 developer. Write editor Python scripts "
               "(import unreal, editor subsystems) or C++ classes (.h + .cpp with UCLASS/"
               "UPROPERTY/UFUNCTION) exactly as the brief asks. Full files, correct includes.",
     "model": DOLPHIN, "skills": ["unreal-engine"], "vm": None},
    {"id": "roblox", "name": "roblox",
     "desc": "Roblox dev — Luau scripts, client/server remotes, Rojo project layout",
     "system": "You are ROBLOX, a Roblox Studio developer. Write Luau (--!strict) in a Rojo "
               "layout (src/server/*.server.luau, src/client/*.client.luau, src/shared/*.luau) "
               "as the brief asks. Server owns truth; validate every remote.",
     "model": DOLPHIN, "skills": ["roblox-studio"], "vm": None},
    {"id": "openscad", "name": "openscad",
     "desc": "CAD modeler — parametric OpenSCAD parts (game props, 3D prints)",
     "system": "You are OPENSCAD, a CAD modeler. Write ONE parametric .scad file per brief, "
               "millimeters, sizes as variables at the top, low-poly ($fn 24-48).",
     "model": DOLPHIN, "skills": ["openscad-cad"], "vm": None},
    {"id": "fortnite", "name": "fortnite",
     "desc": "Fortnite / UEFN map maker — island plans and Verse devices",
     "system": "You are FORTNITE, a UEFN map maker. Write island plans (kind island) and Verse "
               "creative_device classes exactly as your skill shows. Verse is not Python.",
     "model": DOLPHIN, "skills": ["fortnite-map-maker"], "vm": None},
]
SPECIALISTS = ("blender", "unreal", "roblox", "openscad", "fortnite")


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


LEAD_SKILL_BUDGET = 4000   # routed skill text for the lead (it also carries tools + memory)


def build_system(task: str = "") -> str:
    base = SYSTEM_PROMPT.format(skills=", ".join(sorted(tools.SKILLS)) or "(none)")
    for name, body in skill_router.route(task, budget=LEAD_SKILL_BUDGET) if task else []:
        base += f"\n\n# ACTIVE SKILL: {name} (follow its rules and output format exactly)\n{body}"
    p = read_prompt()
    if p:
        base += ("\n\n# STANDING PROMPT (prompt.md — always follow this)\n" + p)
    mem = tools.memory_text()
    base += "\n\n# MEMORY (persistent — what you learned before)\n" + (
        mem[-tools.MEMORY_BUDGET:] if mem else "(empty)")
    return base


# The lead's app-tool menu follows the task's domain: a 3B model picks far better
# from 8 relevant tools than from 22. No domain detected -> one main tool per engine.
DOMAIN_TOOLS = {
    "openscad": ["openscad_render"],
    "blender": ["blender_run", "blender_open"],
    "unreal": ["unreal_quick_level", "unreal_new_project", "unreal_run_python", "unreal_open",
               "unreal_uat", "run_plan", "terrain_heightmap"],
    "fortnite": ["run_plan", "verse_check", "terrain_heightmap", "uefn_list", "uefn_open"],
    "java": ["gradle", "maven"],
    "csharp": ["dotnet"],
    "cpp": ["cmake_build"],
    "web": ["npm", "node_run"],
    "python": ["python_run"],
    "roblox": ["run_plan", "roblox_open", "luau_check", "rojo", "roblox_test"],
}
CORE_APP_TOOLS = ["app_status", "app_control", "open_url", "fetch_docs"]
GENERAL_APP_TOOLS = ["blender_run", "openscad_render", "unreal_quick_level", "run_plan",
                     "roblox_open", "uefn_open",
                     # building/running is not domain-specific: always offer these
                     "gradle", "dotnet", "npm", "python_run"]


def lead_app_tools(task: str) -> list:
    dom = skill_router.domain_of(task) if task else ""
    want = CORE_APP_TOOLS + DOMAIN_TOOLS.get(dom, GENERAL_APP_TOOLS)
    by_name = {x["function"]["name"]: x for x in apps.SCHEMAS}
    return [by_name[n] for n in dict.fromkeys(want) if n in by_name]


def compact_memory(client, model: str) -> None:
    """Squash MEMORY.md back under budget, automatically (no approval). Uses the
    already-resident main model, so it costs no extra RAM. Falls back to keeping
    the newest lines if the model fails."""
    lines = tools.memory_lines()
    if sum(len(l) + 1 for l in lines) <= tools.MEMORY_BUDGET:
        return
    target = tools.MEMORY_BUDGET * 6 // 10
    try:
        r = client.chat(model=model, stream=False, keep_alive=-1, messages=[
            {"role": "system", "content":
                "Compress this memory. Output ONLY lines of `key: value`, one fact "
                "each, no filler words, merge duplicates, drop stale/contradicted "
                f"facts (newer lines win). Total under {target} characters."},
            {"role": "user", "content": "\n".join(lines)}])
        out = (r.get("message", {}) or {}).get("content", "")
        new = [tools.squeeze(l) for l in out.splitlines()]
        new = [l for l in new if ":" in l]
        if new and sum(len(l) + 1 for l in new) < sum(len(l) + 1 for l in lines):
            lines = new
    except Exception:
        pass
    while lines and sum(len(l) + 1 for l in lines) > tools.MEMORY_BUDGET:
        lines.pop(0)                                  # oldest out first
    tools.write_memory(lines)


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
        "platform": {"win32": "win", "darwin": "mac"}.get(sys.platform, "linux"),
        "worker_model": load_settings()["worker_model"],
        "update_note": os.environ.get("NIGHTCREW_UPDATE_NOTE", ""),   # set by launcher.py
    })


@app.get("/api/settings")
def api_settings():
    return jsonify(load_settings())


@app.post("/api/settings")
def api_settings_save():
    return jsonify(save_settings(request.get_json(force=True) or {}))


# ---- model fitness test -----------------------------------------------------
# "Is this model good enough to drive the app?" answered by measurement, not opinion:
# can it answer in plain words, and can it actually CALL a tool when told to?

def test_model(client, model: str, keep: int = -1) -> dict:
    """keep=-1 keeps the model resident (testing the one you are about to use);
    keep=0 unloads it after, so testing every model does not fill the GPU."""
    out = {"model": model, "caps": model_caps(client, model) or [], "steps": []}

    def step(name, ok, detail=""):
        out["steps"].append({"name": name, "ok": bool(ok), "detail": detail[:300]})

    try:
        r = client.chat(model=model, stream=False, options={"num_ctx": 2048}, keep_alive=keep,
                        messages=[{"role": "system", "content": "Answer in plain words."},
                                  {"role": "user", "content": "Reply with exactly: READY"}],
                        **think_arg(client, model))
        said = (r["message"].get("content") or "").strip()
        step("answers in plain text", "READY" in said.upper(), said or "(empty reply)")
    except Exception as e:
        step("answers in plain text", False, str(e))
        out["verdict"] = "cannot run this model — check Ollama"
        return out

    schemas = [x for x in tools.SCHEMAS if x["function"]["name"] == "list_dir"]
    native = "tools" in (out["caps"] or []) or not out["caps"]
    msgs = [{"role": "system", "content": SYSTEM_PROMPT.split("Which tool:")[0]
             + ("" if native else text_tool_note(schemas))},
            {"role": "user", "content": "List the files in the workspace. Use your tool."}]
    try:
        r = client.chat(model=model, stream=False, options={"num_ctx": 4096}, keep_alive=keep,
                        messages=msgs, tools=schemas if native else None, **think_arg(client, model))
        m = r["message"]
        calls = m.get("tool_calls") or []
        how = "native tool call" if calls else ""
        if not calls:                                   # maybe it typed the call as text
            found, _ = toolcalls.extract_calls(m.get("content") or "", {"list_dir"})
            calls, how = found, "typed the call as text (the app recovers these)" if found else ""
        step("calls a tool when told to", bool(calls), how or (m.get("content") or "")[:200])
    except Exception as e:
        step("calls a tool when told to", False, str(e))

    ok = [s["ok"] for s in out["steps"]]
    out["score"] = sum(ok)
    out["verdict"] = ("good lead for this app" if all(ok) else
                      "usable as a WORKER, but a poor lead — it will not drive your apps"
                      if ok and ok[0] else "not usable")
    return out


SKIP_MODELS = re.compile(r"embed|rerank|moondream|whisper|clip|bge|minilm", re.I)


def test_all_models(client) -> list:
    """Every installed chat model, best first. Each is unloaded after its turn."""
    names = sorted(n for n in installed_models(client) if n and not SKIP_MODELS.search(n))
    out = []
    for n in names:
        try:
            out.append(test_model(client, n, keep=0))
        except Exception as e:
            out.append({"model": n, "steps": [], "score": -1, "verdict": f"failed to run: {e}"})
    return sorted(out, key=lambda r: (-r.get("score", -1), r["model"]))


@app.post("/api/model/test")
def api_model_test():
    if ollama is None:
        return jsonify({"error": "ollama python lib not installed"}), 400
    body = request.get_json(force=True) or {}
    model = body.get("model") or ""
    try:
        if body.get("all"):
            return jsonify({"results": test_all_models(ollama.Client())})
        if not model:
            return jsonify({"error": "no model given"}), 400
        return jsonify(test_model(ollama.Client(), model))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---- chats: stored next to the app, NOT in browser storage ------------------
# The window's port can change between launches (free_port), and browser storage is keyed
# by origin — kept there, every chat would vanish on a port change.

def _chats_path() -> str:
    return paths.data("chats.json")


@app.get("/api/chats")
def api_chats():
    try:
        with open(_chats_path(), encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({"convos": [], "projects": [], "instructions": ""})


@app.post("/api/chats")
def api_chats_save():
    if request.headers.get("X-NC") != "1":
        return jsonify({"error": "missing X-NC header"}), 403
    body = request.get_json(force=True) or {}
    data = {"convos": body.get("convos") or [], "projects": body.get("projects") or [],
            "instructions": body.get("instructions") or ""}
    tmp = _chats_path() + ".tmp"                       # write-then-rename: never a half file
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _chats_path())
    return jsonify({"ok": True, "convos": len(data["convos"])})


# ---- integrations: Telegram bot + Gmail watcher -----------------------------

def seed_builtin_connectors() -> None:
    """Our own MCP servers (mcp_servers/) as connectors: added once, command refreshed each
    start (the exe path moves on updates), user's enabled/disabled choice kept."""
    try:
        import mcp_servers
        items = load_connectors()
        have = {str(c.get("name", "")).lower(): c for c in items}
        for b in mcp_servers.builtin_connectors():
            cur = have.get(b["name"])
            if cur is None:
                items.append(b)
            elif cur.get("builtin"):
                cur.update({k: b[k] for k in ("command", "args", "transport", "desc", "id")})
        save_connectors(items)
    except Exception as e:
        print(f"builtin connectors: {e}")


def startup_bridges() -> None:
    try:
        import live
        live.token()
        live.start_roblox_host()                  # Studio plugin polls this while the app runs
    except Exception as e:
        print(f"bridges: {e}")
    seed_builtin_connectors()


@app.get("/api/bridges")
def api_bridges():
    import live
    return jsonify(live.status())


@app.post("/api/bridges")
def api_bridges_do():
    if request.headers.get("X-NC") != "1":
        return jsonify({"error": "missing X-NC header"}), 403
    import live
    b = request.get_json(force=True) or {}
    act = {"blender": live.install_blender_addon, "roblox": live.install_roblox_plugin,
           "unreal": lambda: live.unreal_enable_live(b.get("project", ""))}.get(b.get("app"))
    if not act:
        return jsonify({"error": "app must be blender, roblox or unreal"}), 400
    try:
        return jsonify({"result": act()})
    except Exception as e:
        return jsonify({"result": f"error: {e}"})


def startup_integrations() -> None:
    try:
        integrations.start_all(sys.modules[__name__])
    except Exception as e:
        print(f"integrations: {e}")


@app.get("/api/integrations")
def api_integrations():
    return jsonify({"config": integrations.masked(), "status": integrations.status()})


@app.post("/api/integrations")
def api_integrations_save():
    if request.headers.get("X-NC") != "1":                     # same guard as /api/workspace
        return jsonify({"error": "missing X-NC header"}), 403
    integrations.update(request.get_json(force=True) or {})
    startup_integrations()
    return jsonify({"config": integrations.masked(), "status": integrations.status()})


@app.post("/api/google/signin")
def api_google_signin():
    if request.headers.get("X-NC") != "1":
        return jsonify({"error": "missing X-NC header"}), 403
    import google_auth
    return jsonify(google_auth.start_signin())


@app.post("/api/google/signout")
def api_google_signout():
    if request.headers.get("X-NC") != "1":
        return jsonify({"error": "missing X-NC header"}), 403
    import google_auth
    google_auth.sign_out()
    startup_integrations()
    return jsonify({"ok": True})


# ---- creative apps: Blender / Unreal / Roblox ------------------------------

@app.get("/api/apps")
def api_apps():
    return jsonify({"apps": apps.status(), "projects": apps.load_cfg()["projects"],
                    "docs": {a: [{"key": k, "url": u,
                                  "cached": os.path.isfile(apps._cache_file(u))}
                                 for k, u in pages.items()]
                             for a, pages in apps.DOCS.items()}})


@app.post("/api/apps")
def api_apps_save():
    """{"key": "blender", "path": "..."} sets/clears an app path;
    {"add_project": "..."} / {"remove_project": "..."} edits project folders."""
    b = request.get_json(force=True) or {}
    c = apps.load_cfg()
    if b.get("key") in apps.FINDERS:
        p = (b.get("path") or "").strip().strip('"')
        if p and not os.path.isfile(p):
            return jsonify({"ok": False, "error": f"no file at {p}"}), 400
        if p:
            c["paths"][b["key"]] = p
        else:
            c["paths"].pop(b["key"], None)
    if b.get("add_project"):
        p = os.path.abspath(os.path.expanduser(b["add_project"].strip().strip('"')))
        if not os.path.isdir(p):
            return jsonify({"ok": False, "error": f"no folder at {p}"}), 400
        if p not in c["projects"]:
            c["projects"].append(p)
    if b.get("remove_project"):
        c["projects"] = [x for x in c["projects"] if x != b["remove_project"]]
    apps.save_cfg(c)
    return api_apps()


@app.post("/api/apps/launch")
def api_apps_launch():
    b = request.get_json(force=True) or {}
    fn = {"blender": lambda: apps.blender_open(b.get("file", "")),
          "unreal": lambda: apps.unreal_open(b.get("file", "")),
          "roblox": lambda: apps.roblox_open(b.get("file", "")),
          "uefn": lambda: engines.uefn_open(b.get("file", ""))}.get(b.get("app"))
    if not fn:
        return jsonify({"ok": False, "error": "unknown app"}), 400
    try:
        return jsonify({"ok": True, "status": fn()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.get("/api/apps/setup")
def api_apps_setup():
    return jsonify(apps.SETUP)


@app.post("/api/apps/setup")
def api_apps_setup_run():
    st = load_settings()
    apps.start_setup(install=True, launch=st["launch_on_start"])
    return jsonify({"ok": True})


def init_workspace() -> None:
    """After the default sandbox is set: fix the memory location (data dir, with a
    one-time copy of an old in-workspace MEMORY.md) and switch to the user's chosen
    workspace folder if they picked one."""
    import shutil
    mem = paths.data("MEMORY.md")
    old = os.path.join(str(tools.SANDBOX), tools.MEMORY_FILE)
    if not os.path.exists(mem) and os.path.isfile(old):
        try:
            shutil.copyfile(old, mem)
        except Exception:
            pass
    from pathlib import Path
    tools.MEMORY_PATH = Path(mem)
    wd = load_settings().get("workdir")
    if wd and os.path.isdir(wd):
        CFG["workdir"] = wd
        tools.set_sandbox(wd)


def startup_apps() -> None:
    """Called once when the app starts (desktop.py / app.py main)."""
    st = load_settings()
    if st["auto_setup"] or st["launch_on_start"]:
        apps.start_setup(install=st["auto_setup"], launch=st["launch_on_start"])


@app.post("/api/apps/docs/prefetch")
def api_apps_prefetch():
    return jsonify(apps.prefetch_docs((request.get_json(force=True) or {}).get("app", "")))


@app.post("/api/open-url")
def api_open_url():
    """Open an official docs page in the system browser (pywebview can't do tabs)."""
    url = (request.get_json(force=True) or {}).get("url", "")
    if not url.startswith("https://") or not any(
            url.split("/")[2].endswith(d) for d in apps.DOC_DOMAINS):
        return jsonify({"ok": False, "error": "only official docs links"}), 400
    import webbrowser
    webbrowser.open(url)
    return jsonify({"ok": True})


_CAPS: dict = {}


def model_caps(client, name: str):
    """['completion','tools','vision',...] from `ollama show`, or None if this Ollama is too
    old to say. Only successful answers are cached."""
    if name in _CAPS:
        return _CAPS[name]
    try:
        r = client.show(name)
        caps = r.get("capabilities") if isinstance(r, dict) else getattr(r, "capabilities", None)
        if caps is not None:
            _CAPS[name] = list(caps)
            return _CAPS[name]
    except Exception:
        pass
    return None


# Tools that change what is on disk. After one succeeds, a command that was already run this
# turn is allowed again — "javac" after writing a .java file is NOT a pointless repeat.
WRITE_TOOLS = {"write_file", "edit_file", "delete_file"}


def think_arg(client, model: str) -> dict:
    """{'think': bool} for a model whose capabilities include thinking, else {}. Sending
    `think` to a model without it makes Ollama reject the whole request."""
    caps = model_caps(client, model)
    if caps and "thinking" in caps:
        return {"think": bool(load_settings().get("think"))}
    return {}


def text_tool_note(schemas: list) -> str:
    """For models with no native tool calling: describe the tools in the prompt and ask for
    one JSON line; toolcalls.extract_calls turns that back into a real call."""
    rows = []
    for x in schemas[:40]:
        f = x["function"]
        props = ", ".join((f.get("parameters") or {}).get("properties", {}).keys())
        rows.append(f"- {f['name']}({props}): {(f.get('description') or '')[:90]}")
    return ("\n\nThis model cannot use native tool calling. To use a tool, reply with ONLY one line "
            'of JSON and nothing else: {"name": "<tool>", "arguments": {...}}. When you get the '
            "result, answer in plain sentences. Tools:\n" + "\n".join(rows))


@app.get("/api/models")
def api_models():
    if ollama is None:
        return jsonify({"models": [], "error": "ollama python lib not installed"})
    try:
        client = ollama.Client()
        data = client.list()
        names = [n for n in (m.get("model") or m.get("name") for m in data.get("models", [])) if n]
        return jsonify({"models": names, "tools": {n: ("tools" in c) for n in names
                                                    if (c := model_caps(client, n)) is not None}})
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
        return jsonify({"memory": tools.memory_text()})
    except tools.ToolError:
        return jsonify({"memory": ""})


# ---- subagents ------------------------------------------------------------
# A subagent is a named helper with its own system prompt / model / skills.
# The main agent delegates a task to one via the spawn_subagent tool.

def _subagents_path() -> str:
    return paths.data("subagents.json")


def removed_ids() -> set:
    try:
        with open(paths.data("subagents.removed.json"), encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def load_subagents() -> list:
    try:
        with open(_subagents_path(), encoding="utf-8") as f:
            items = json.load(f)
    except Exception:
        return []
    # migrate: old seeds pinned every subagent to its own 8b model -> reuse main's
    changed = False
    defaults = {d["id"]: d for d in DEFAULT_SUBAGENTS}
    have = {s.get("id") for s in items}
    for sid in SPECIALISTS:                 # new in this version: add once
        if sid not in have and sid not in removed_ids():
            items.append(dict(defaults[sid]))
            changed = True
    for s in items:
        if s.get("model") in LEGACY_POOL_MODELS:
            s["model"] = ""
            changed = True
        d = defaults.get(s.get("id"))
        if d and "prompt.md" in (s.get("system") or ""):   # old pool-era role text
            s["system"], s["desc"] = d["system"], d["desc"]
            changed = True
    if changed:
        try:
            save_subagents(items)
        except Exception:
            pass
    return items


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
    gone = removed_ids() | {sid}                 # so auto-added specialists stay deleted
    with open(paths.data("subagents.removed.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(gone), f)
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


def chat_connectors(names) -> list:
    """Connectors are always configured/ready, but a chat only gets the tools of the
    ones it asked for (the UI remembers them per chat after the first mention)."""
    want = {str(n).lower() for n in (names or [])}
    return [c for c in load_connectors() if str(c.get("name", "")).lower() in want]


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
    {"type": "function", "function": {
        "name": "set_avatar",
        "description": "Set a subagent's grok-bot avatar expression in the VM view. pose: 'look' "
                       "(darting eyes, busy), 'sleep' (eyes closed, greyed, idle), 'happy' (great "
                       "job), 'think' (pondering), 'alert' (needs attention), or 'auto' (follow its "
                       "task state). Use it to signal the pool what each bot is doing.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "pose": {"type": "string"}}, "required": ["name", "pose"]}}},
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
    return "active" if sub["name"] == RUNNING_SUB["name"] else "paused"


# ---- grok-bot avatars ------------------------------------------------------
# Each agent shows a cloud-shaped face (two eyes). It gets a stable color, looks
# around while working (runtime active), and closes its eyes + turns grey while
# idle. The parent can override an agent's expression with set_avatar(name,pose).
AVATAR_COLORS = [
    "#c99a3a", "#e08a3c", "#8a5a2b", "#2b2b2b", "#d0473f",   # gold orange brown black red
    "#d9639e", "#8a5cd0", "#3f7bd0", "#2fa6a6", "#4fbf7f",   # pink purple blue teal mint
    "#e9e9ef", "#8b8f99",                                    # white grey
]
AVATAR_POSES = {"auto", "look", "sleep", "happy", "think", "alert"}
AVATAR_POSE: dict = {}          # name -> parent-set pose (overrides the default)


def _avatar_color(name: str, idx: int = None) -> str:
    if idx is not None:                              # stable, distinct per pool slot
        return AVATAR_COLORS[idx % len(AVATAR_COLORS)]
    if not name:
        return AVATAR_COLORS[0]
    h = sum(ord(c) for c in name)
    return AVATAR_COLORS[h % len(AVATAR_COLORS)]


def _avatar_pose(name: str, runtime: str) -> str:
    p = AVATAR_POSE.get(name, "auto")
    if p and p != "auto":
        return p                                    # parent override wins
    return "look" if runtime == "active" else "sleep"


def set_avatar(name: str, pose: str) -> str:
    pose = (pose or "auto").lower()
    if pose not in AVATAR_POSES:
        return f"error: pose must be one of {', '.join(sorted(AVATAR_POSES))}"
    if pose == "auto":
        AVATAR_POSE.pop(name, None)
    else:
        AVATAR_POSE[name] = pose
    return f"OK: {name} avatar -> {pose}"


def sync_machines() -> str:
    """Suspend the VM of every idle agent, resume every agent with a live task.
    Runs the agent's vm.suspend / vm.resume hook when set; otherwise just reports
    the intended state (in-process agents need no VM)."""
    import subprocess
    out = []
    for s in load_subagents():
        if not s.get("enabled", True):
            continue
        state = "active" if s["name"] == RUNNING_SUB["name"] else "paused"
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
    if name == "set_avatar":
        return set_avatar(args.get("name", ""), args.get("pose", "auto"))
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


# ---- git + push/save targets (Terminal mode) ------------------------------

def _git(*args):
    import subprocess
    try:
        r = subprocess.run(["git", *args], cwd=tools.SANDBOX,
                           capture_output=True, text=True, timeout=90)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, f"git error: {e}"


@app.get("/api/git/status")
def api_git_status():
    code, out = _git("status", "--porcelain=v1", "-b")
    if code != 0:
        return jsonify({"repo": False, "files": [], "branch": ""})
    files, branch = [], ""
    for line in out.splitlines():
        if line.startswith("##"):
            branch = line[3:].split("...")[0].strip()
        elif line.strip():
            files.append({"status": line[:2].strip(), "path": line[3:]})
    return jsonify({"repo": True, "files": files, "branch": branch})


@app.get("/api/git/diff")
def api_git_diff():
    code, out = _git("diff")
    _, untr = _git("ls-files", "--others", "--exclude-standard")
    extra = "\n".join(f"?? new file: {p}" for p in untr.splitlines() if p.strip())
    return jsonify({"diff": (out + ("\n" + extra if extra else "")).strip()})


def _targets_path():
    return paths.data("targets.json")


def load_targets():
    try:
        with open(_targets_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_targets(items):
    with open(_targets_path(), "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


@app.get("/api/targets")
def api_targets():
    return jsonify({"targets": load_targets()})


@app.post("/api/targets")
def api_targets_save():
    b = request.get_json(force=True) or {}
    items = load_targets()
    tid = b.get("id") or uuid.uuid4().hex[:8]
    entry = {"id": tid, "type": b.get("type", "repo"),
             "name": (b.get("name") or "target").strip(),
             "url": b.get("url", ""), "path": b.get("path", ""),
             "branch": b.get("branch", "main")}
    save_targets([x for x in items if x.get("id") != tid] + [entry])
    return jsonify({"ok": True, "target": entry})


@app.delete("/api/targets/<tid>")
def api_targets_delete(tid):
    save_targets([x for x in load_targets() if x.get("id") != tid])
    return jsonify({"ok": True})


@app.post("/api/git/push")
def api_git_push():
    b = request.get_json(force=True) or {}
    t = next((x for x in load_targets() if x["id"] == b.get("target_id")), None)
    if not t:
        return jsonify({"ok": False, "log": "pick a target first"})
    msg = b.get("message") or "update from Night Crew"
    if t["type"] == "file":
        return jsonify({"ok": True, "log": f"file target '{t['name']}' → tell the agent to write to {t['path']}"})
    log = []
    if not os.path.isdir(os.path.join(str(tools.SANDBOX), ".git")):
        log.append(_git("init")[1])
    log.append(_git("add", "-A")[1])
    log.append(_git("commit", "-m", msg)[1])
    _git("remote", "remove", "origin")
    log.append(_git("remote", "add", "origin", t["url"])[1])
    code, out = _git("push", "-u", "origin", f"HEAD:{t.get('branch','main')}")
    log.append(out)
    return jsonify({"ok": code == 0, "log": "\n".join(x for x in log if x.strip())})


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


SUB_LOCK = threading.Lock()          # one subagent at a time, across all chats
RUNNING_SUB = {"name": ""}           # who is working right now (drives the VM avatars)


def run_subagent(client, default_model: str, sub: dict, task: str, connectors=None) -> str:
    """Boot one subagent FRESH, run its tool loop, return its answer. It sees only
    its role, its assigned skills and MAIN's brief — no memory, chat or prompt.md —
    so its prompt (and KV cache) stays small. Autonomous, but jailed in the sandbox."""
    with SUB_LOCK:
        RUNNING_SUB["name"] = sub.get("name", "subagent")
        try:
            return _run_subagent(client, default_model, sub, task, connectors)
        finally:
            RUNNING_SUB["name"] = ""


CTX = 16384                          # default context window; settings num_ctx overrides


def ctx_size() -> int:
    try:
        return max(4096, min(32768, int(load_settings().get("num_ctx") or CTX)))
    except Exception:
        return CTX
_INSTALLED = {"at": 0.0, "names": set()}


def installed_models(client) -> set:
    import time
    if time.time() - _INSTALLED["at"] > 30:
        try:
            data = client.list()
            items = data.get("models", []) if isinstance(data, dict) else getattr(data, "models", [])
            _INSTALLED["names"] = {(m.get("model") or m.get("name")) if isinstance(m, dict)
                                   else (getattr(m, "model", None) or getattr(m, "name", ""))
                                   for m in items}
            _INSTALLED["at"] = time.time()
        except Exception:
            pass
    return _INSTALLED["names"]


def worker_model_for(client, sub: dict, main_model: str) -> tuple[str, str]:
    """(model, note). A subagent's own model, else the low-power worker model, else
    MAIN's model if the worker model isn't pulled yet."""
    want = sub.get("model") or load_settings()["worker_model"]
    if not want or want == main_model:
        return main_model, ""
    have = installed_models(client)
    if have and want not in have and f"{want}:latest" not in have:
        return main_model, f"(worker model {want} not pulled — ran on {main_model}; `ollama pull {want}`)"
    return want, ""


def _auto_checks(files: list) -> list:
    """Cheap, offline checks on what a worker wrote. Evidence for MAIN's debug pass."""
    import shutil
    import subprocess
    out = []
    for rel in files:
        try:
            p = tools._jail(rel)
            ext = p.suffix.lower()
            src = p.read_text(encoding="utf-8", errors="replace")
            if ext == ".py":
                compile(src, rel, "exec")
                out.append(f"{rel}: OK (compiles)" + (" — Blender script: blender_run it"
                                                       if "import bpy" in src else
                                                       " — Unreal script: unreal_run_python it"
                                                       if "import unreal" in src else ""))
            elif ext in (".json", ".uproject", ".uplugin"):
                data = json.loads(src)
                if isinstance(data, dict) and "kind" in data:
                    errs = engines.validate_plan(data)
                    out.append(f"{rel}: " + (f"OK plan ({data['kind']}) — run_plan('{rel}')" if not errs
                                             else "PLAN PROBLEMS: " + "; ".join(errs)))
                else:
                    out.append(f"{rel}: OK (valid JSON)")
            elif ext == ".scad":
                if apps.app_path("openscad"):
                    r = engines.openscad_render(rel, png=False)
                    out.append(f"{rel}: " + " | ".join(r.splitlines()[1:4]))
                else:
                    out.append(f"{rel}: not compiled (install OpenSCAD)")
            elif ext == ".verse":
                issues = engines.verse_lint(src)
                out.append(f"{rel}: " + ("OK offline (UEFN compiles it)" if not issues
                                         else "VERSE ISSUES: " + "; ".join(issues[:6])))
            elif ext in (".js", ".mjs", ".cjs") and shutil.which("node"):
                r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=30)
                out.append(f"{rel}: " + ("OK (node --check)" if r.returncode == 0
                                          else "SYNTAX ERROR\n" + (r.stderr or r.stdout)[-600:]))
            elif ext in (".java",) and shutil.which("javac"):
                with tempfile.TemporaryDirectory() as d:
                    r = subprocess.run(["javac", "-d", d, str(p)], capture_output=True, text=True, timeout=120)
                # drop the JVM's "Picked up JAVA_TOOL_OPTIONS/_JAVA_OPTIONS" banner, which can be
                # longer than the error itself and would push the real message out of the tail
                msg = "\n".join(l for l in (r.stderr or r.stdout).splitlines()
                                if not l.startswith("Picked up ")).strip()
                out.append(f"{rel}: " + ("OK (javac)" if r.returncode == 0
                                          else "COMPILE ERROR\n" + msg[-800:]))
            elif ext in (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".c", ".h"):
                cc = shutil.which("g++" if ext not in (".c", ".h") else "gcc") or shutil.which("clang++")
                if cc:
                    std = "-std=c11" if ext in (".c", ".h") else "-std=c++17"
                    # -fsyntax-only: parse and type-check, never build or link
                    r = subprocess.run([cc, std, "-fsyntax-only", "-Wall", str(p)],
                                       capture_output=True, text=True, timeout=120)
                    msg = (r.stderr or r.stdout).strip()
                    out.append(f"{rel}: " + ("OK (syntax)" + (f" — warnings:\n{msg[-500:]}" if msg else "")
                                              if r.returncode == 0 else "COMPILE ERROR\n" + msg[-800:]))
                else:
                    out.append(f"{rel}: not compiled (install g++/clang)")
            elif ext in (".ts", ".tsx") and shutil.which("npx"):
                r = subprocess.run(["npx", "--no-install", "tsc", "--noEmit", "--skipLibCheck", str(p)],
                                   capture_output=True, text=True, timeout=180)
                msg = (r.stdout or r.stderr).strip()
                out.append(f"{rel}: " + ("OK (tsc)" if r.returncode == 0
                                          else ("not type-checked (no local typescript)"
                                                if "could not determine" in msg.lower() or "not found" in msg.lower()
                                                else "TYPE ERROR\n" + msg[-800:])))
            elif ext in (".lua", ".luau"):
                if apps.app_path("luau"):
                    out.append(f"{rel}: " + apps.luau_check(rel)[:600])
                else:
                    out.append(f"{rel}: not linted (install luau-analyze or selene)")
            else:
                out.append(f"{rel}: written ({len(src)} chars, no auto-check for {ext or 'this type'})")
        except SyntaxError as e:
            out.append(f"{rel}: SYNTAX ERROR line {e.lineno}: {e.msg}")
        except json.JSONDecodeError as e:
            out.append(f"{rel}: INVALID JSON line {e.lineno}: {e.msg}")
        except Exception as e:
            out.append(f"{rel}: check failed ({e})")
    return out


def _run_subagent(client, default_model: str, sub: dict, task: str, connectors=None) -> str:
    who = sub.get("name", "subagent")
    sys_lines = [sub.get("system") or "You are a focused helper subagent. Be terse.",
                 "You were booted fresh for ONE job. Write each file the brief asks for as a "
                 "fenced block that starts with its language and path, e.g. "
                 "```openscad file=models/gear.scad``` — complete files, no placeholders. "
                 "Then one short line: what you made and anything unfinished. MAIN runs and "
                 "debugs your work after you."]
    # dynamic skill loader: the skills that match THIS brief, then the agent's own
    for name, body in skill_router.route(task, assigned=sub.get("skills", [])):
        sys_lines.append(f"\n# skill: {name}\n{body}")
    msgs = [{"role": "system", "content": "\n".join(sys_lines)},
            {"role": "user", "content": task}]
    model, note = worker_model_for(client, sub, default_model)
    # same model as MAIN -> already resident. A different one unloads when done.
    keep = -1 if model == default_model else 0
    import connectors as C
    mcp_schemas, mcp_index = C.list_tools(chat_connectors(connectors)) if connectors else ([], {})
    # file tools + load_skill + this chat's connectors. No memory/bus/board/apps: MAIN owns those.
    schemas = [x for x in tools.SCHEMAS if x["function"]["name"] != "remember"] + mcp_schemas
    log, touched, acc = [], [], ""
    seen_calls: dict = {}
    native = True
    caps = model_caps(client, model)
    if caps is not None and "tools" not in caps:       # no tool template: describe tools in text
        native = False
        msgs[0]["content"] += text_tool_note(schemas)
    for _ in range(10):
        acc = ""
        calls = []
        for chunk in client.chat(model=model, messages=msgs, keep_alive=keep,
                                 options={"num_ctx": ctx_size()}, tools=schemas if native else None,
                                 stream=True, **think_arg(client, model)):
            m = chunk.get("message", {})
            acc += m.get("content") or ""
            calls += m.get("tool_calls") or []
        if not calls and acc.strip():
            calls, rest = toolcalls.extract_calls(acc, {x["function"]["name"] for x in schemas})
            if calls:
                acc = rest
        msgs.append({"role": "assistant", "content": acc, "tool_calls": calls or None})
        if not calls:
            break
        for tc in calls:
            fn = tc.get("function", {})
            nm = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            sig = nm + json.dumps(args, sort_keys=True, default=str)
            seen_calls[sig] = seen_calls.get(sig, 0) + 1
            if seen_calls[sig] > 1:          # same call again: it cannot return anything new
                r = (f"(already called {nm} with these exact arguments — nothing changed. "
                     "Stop repeating it and finish the job.)")
                log.append(f"{nm} (repeat ignored)")
                msgs.append({"role": "tool", "content": r})
                continue
            if nm in mcp_index:
                sv, tn = mcp_index[nm]
                r = C.call_tool(sv, tn, args)
            elif nm == "remember":
                r = "error: only MAIN keeps memory"
            else:
                r = tools.run_tool(nm, args)
            if nm in ("write_file", "edit_file") and r.startswith("OK") and args.get("path"):
                if args["path"] not in touched:
                    touched.append(args["path"])
            log.append(f"{nm}→{r[:40]}")
            msgs.append({"role": "tool", "content": r})
    else:
        acc = (acc + "\n(hit the step limit)").strip()
    for b in exec_tags.blocks(acc):                 # files written as execution-tag blocks
        try:
            tools.write_file(b["file"], b["code"])
            if b["file"] not in touched:
                touched.append(b["file"])
            log.append(f"block→{b['file']}")
        except Exception as e:
            log.append(f"block {b['file']} failed: {e}")
    report = [f"[{who} finished — fresh boot on {model}] {note}".rstrip(),
              exec_tags.summarize(acc).strip() or "(no summary)"]
    if touched:
        report.append("FILES: " + ", ".join(touched))
        report.append("AUTO-CHECKS:\n" + "\n".join("- " + c for c in _auto_checks(touched)))
        report.append("PARENT: debug now — read each file, run it (run_command / blender_run / "
                      "unreal_run_python / luau_check / rojo), fix what's broken yourself with "
                      "edit_file, re-run until clean. Only re-delegate big rewrites.")
    else:
        report.append("FILES: none written. PARENT: check the answer; re-brief with exact file "
                      "paths if code was expected.")
    if log:
        report.append("steps: " + " | ".join(log))
    return "\n".join(report)


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


# ---- IDE explorer: Workspace (the agents' folder) and PC (drives, any folder) ----
# Read-only browsing for the user. Changing the workspace needs the X-NC header, so
# a random web page can't flip it with a simple cross-site POST.

def _drives() -> list:
    if sys.platform == "win32":
        import string
        return [{"name": f"{d}:", "path": f"{d}:\\", "dir": True}
                for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    home = os.path.expanduser("~")
    roots = [{"name": "Home", "path": home, "dir": True}, {"name": "/", "path": "/", "dir": True}]
    if sys.platform == "darwin" and os.path.isdir("/Volumes"):
        roots += [{"name": v, "path": os.path.join("/Volumes", v), "dir": True}
                  for v in sorted(os.listdir("/Volumes"))]
    return roots


_SKIP = {"$recycle.bin", "system volume information", "__pycache__", "node_modules", ".git"}


def _list_dir(real: str, rel_base: str | None) -> list:
    out = []
    try:
        with os.scandir(real) as it:
            for e in it:
                if e.name.startswith(".") or e.name.lower() in _SKIP:
                    continue
                try:
                    is_dir = e.is_dir()
                except OSError:
                    continue
                p = os.path.join(rel_base, e.name) if rel_base is not None else e.path
                out.append({"name": e.name, "path": p.replace("\\", "/") if rel_base is not None else p,
                            "dir": is_dir})
    except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
        return []
    out.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return out[:2000]


@app.get("/api/fs/list")
def api_fs_list():
    scope = request.args.get("scope", "workspace")
    path = request.args.get("path", "")
    if scope == "pc":
        if not path:
            return jsonify({"items": _drives()})
        return jsonify({"items": _list_dir(os.path.abspath(path), None)})
    try:
        real = str(tools._jail(path or "."))
    except tools.ToolError as e:
        return jsonify({"items": [], "error": str(e)}), 400
    return jsonify({"items": _list_dir(real, path if path else "")})


@app.get("/api/fs/read")
def api_fs_read():
    """Open a file from anywhere on the PC in the (read-only) editor."""
    path = request.args.get("path", "")
    try:
        if os.path.getsize(path) > 2_000_000:
            return jsonify({"path": path, "content": "", "error": "file is over 2 MB — not shown"})
        with open(path, "rb") as f:
            raw = f.read()
        if b"\0" in raw[:4096]:
            return jsonify({"path": path, "content": "", "error": "binary file — not shown"})
        return jsonify({"path": path, "content": raw.decode("utf-8", "replace")})
    except Exception as e:
        return jsonify({"path": path, "content": "", "error": str(e)}), 404


@app.get("/api/workspace")
def api_workspace():
    p = str(tools.SANDBOX)
    return jsonify({"path": p, "name": os.path.basename(p.rstrip("\\/")) or p,
                    "custom": bool(load_settings().get("workdir"))})


@app.post("/api/workspace")
def api_workspace_set():
    if request.headers.get("X-NC") != "1":
        return jsonify({"ok": False, "error": "missing header"}), 403
    p = ((request.get_json(force=True) or {}).get("path") or "").strip()
    if p == "":                                     # back to the built-in workspace
        save_settings({"workdir": ""})
        CFG["workdir"] = paths.data("workspace")
        tools.set_sandbox(CFG["workdir"])
        return api_workspace()
    p = os.path.abspath(os.path.expanduser(p))
    if not os.path.isdir(p):
        return jsonify({"ok": False, "error": f"not a folder: {p}"}), 400
    if os.path.dirname(p) == p:
        return jsonify({"ok": False, "error": "pick a folder, not a whole drive"}), 400
    save_settings({"workdir": p})
    CFG["workdir"] = p
    tools.set_sandbox(p)
    return api_workspace()


@app.get("/api/file")
def api_file():
    path = request.args.get("path", "")
    try:
        return jsonify({"path": path, "content": tools.read_file(path)})
    except tools.ToolError as e:
        return jsonify({"path": path, "content": "", "error": str(e)}), 404


# ---- VM view --------------------------------------------------------------
# Two modes. "vm" mode (VM_STREAM / VM_HOOK_* set): shows a real VM stream and the
# hooks drive it. "local" mode (default): the controls do real local work in the
# sandbox — Run app serves/launches whatever the agents built (and shows it in the
# preview pane), Open folder opens the workspace, Stop kills the run.

VM = {
    "stream": os.environ.get("VM_STREAM", ""),
    "status": "idle",
    "app_url": os.environ.get("VM_APP_URL", ""),
    "proc": None,          # the process launched by "Run app" (local mode)
}


def _vm_mode() -> str:
    """'vm' when a real VM is configured (stream or hooks), else 'local'."""
    if os.environ.get("VM_STREAM") or any(
            os.environ.get(f"VM_HOOK_{a}") for a in ("START", "LAUNCH", "STOP", "OPEN")):
        return "vm"
    return "local"


def _free_port(pref: int = 8000) -> int:
    import socket
    for p in (pref, pref + 1, pref + 2, 0):
        try:
            s = socket.socket(); s.bind(("127.0.0.1", p)); port = s.getsockname()[1]; s.close()
            return port
        except OSError:
            continue
    return pref


def _open_path(path: str) -> None:
    import subprocess
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _run_app_local() -> str:
    """Launch whatever the agents built in the sandbox and, for a web app, serve it
    so the preview pane can show it. Returns a human status."""
    import shutil
    import subprocess
    ws = str(tools.SANDBOX)
    _stop_local()  # replace any previous run
    idx = os.path.join(ws, "index.html")
    if os.path.isfile(idx):
        port = _free_port()
        VM["proc"] = subprocess.Popen([sys.executable, "-m", "http.server", str(port)],
                                      cwd=ws, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        VM["app_url"] = f"http://localhost:{port}"
        return f"serving your app at :{port}"
    if os.path.isfile(os.path.join(ws, "package.json")) and shutil.which("npm"):
        VM["proc"] = subprocess.Popen("npm run dev || npm start", cwd=ws, shell=True)
        return "npm dev server started (open the URL it prints)"
    for entry in ("app.py", "main.py", "desktop.py"):
        if os.path.isfile(os.path.join(ws, entry)):
            VM["proc"] = subprocess.Popen([sys.executable, entry], cwd=ws)
            return f"running {entry}"
    _open_path(ws)
    return "nothing runnable yet — opened the workspace folder"


def _stop_local() -> str:
    p = VM.get("proc")
    if p and p.poll() is None:
        try:
            p.terminate()
        except Exception:
            pass
    VM["proc"] = None
    VM["app_url"] = os.environ.get("VM_APP_URL", "")
    return "stopped"


@app.get("/api/vm")
def api_vm():
    agents = []
    doing = _doing_set()
    for i, s in enumerate(load_subagents()):
        vm = s.get("vm") or {}
        rt = agent_runtime(s, doing)          # active | paused | disabled
        agents.append({"name": s["name"], "stream": vm.get("stream", ""),
                       "enabled": s.get("enabled", True), "runtime": rt,
                       "status": rt, "color": _avatar_color(s["name"], i + 1),
                       "pose": _avatar_pose(s["name"], rt)})
    out = {k: v for k, v in VM.items() if k != "proc"}
    return jsonify({**out, "mode": _vm_mode(), "name": "main", "parent": True,
                    "color": _avatar_color("main", 0),
                    "pose": _avatar_pose("main", "active"),
                    "system": system_load(), "agents": agents})


@app.post("/api/vm/action")
def api_vm_action():
    action = (request.get_json(force=True) or {}).get("action", "")
    hook = os.environ.get(f"VM_HOOK_{action.upper()}")
    try:
        if hook:                                   # real VM configured
            import subprocess
            subprocess.Popen(hook, shell=True)
            VM["status"] = f"{action}: launched"
        elif action in ("start", "launch"):        # local: run the built app
            VM["status"] = _run_app_local()
        elif action == "open":                     # local: open the sandbox folder
            _open_path(str(tools.SANDBOX))
            VM["status"] = "opened workspace"
        elif action == "stop":
            VM["status"] = _stop_local()
        else:
            VM["status"] = f"unknown action: {action}"
    except Exception as e:
        VM["status"] = f"{action}: error {e}"
    out = {k: v for k, v in VM.items() if k != "proc"}
    return jsonify({**out, "mode": _vm_mode()})


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

# Jailed by tools._jail: these can only ever touch the workspace, so with
# `trust_workspace` on they run without asking. run_command and the build tools are NOT
# here: only their working directory is jailed, the command text itself can name any path
# on the machine, so those keep asking.
WORKSPACE_SAFE = {"write_file", "edit_file", "delete_file"}


def gate(name: str, args: dict, ask: bool):
    """Yield an SSE approval round-trip for a gated tool. Returns True if allowed."""
    if not ask or (name not in tools.GATED and name not in apps.GATED
                   and not name.startswith("mcp__")):
        return True, ""
    if name in WORKSPACE_SAFE and load_settings().get("trust_workspace", True):
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
        # what the user is asking for right now (last two user turns, for follow-ups)
        asks = [m.get("content", "") for m in history if m.get("role") == "user"][-2:]
        task_text = "\n".join(a for a in asks if isinstance(a, str))
        hist, img_note = history, None
        try:
            if any(m.get("images") for m in history):
                hist, img_note = vision.prepare(client, model, history,
                                                load_settings()["vision_model"],
                                                installed_models(client))
        except Exception as e:
            hist = [{k: v for k, v in m.items() if k != "images"} for m in history]
            yield sse("error", f"image handling failed: {e}")
        if img_note:
            yield sse("image_note", img_note)
        msgs = [{"role": "system", "content": build_system(task_text)}] + hist

        subs = load_subagents()
        import connectors as C
        active = list(body.get("connectors") or [])     # this chat's connectors
        # Our own app servers (blender/unreal/roblox/openscad/fortnite) switch themselves on
        # when the job is clearly theirs. Waiting for the user to type the word "unreal" meant
        # "create a project" reached the model with no engine tools at all.
        dom = skill_router.domain_of(task_text)
        if dom and not any(n.lower() == dom for n in active):
            if any(c.get("builtin") and str(c.get("name", "")).lower() == dom
                   and c.get("enabled", True) for c in load_connectors()):
                active.append(dom)
        mcp_schemas, mcp_index = C.list_tools(chat_connectors(active)) if active else ([], {})
        schemas = None
        if tool_mode:
            schemas = list(tools.SCHEMAS) + lead_app_tools(task_text) + mcp_schemas
            if use_web:
                schemas = schemas + web.SCHEMAS
            if subs:
                names = ", ".join(s["name"] for s in subs)
                # lean on purpose: small leads pick the wrong tool when the menu is long
                grant = [x for x in SYS_SCHEMAS if x["function"]["name"] == "grant_skill"]
                schemas = schemas + SKILL_SCHEMAS + grant + [{"type": "function", "function": {
                    "name": "spawn_subagent",
                    "description": f"Boot a low-power worker FRESH to write one piece; you get its result, the files it wrote and auto-check output, then YOU debug. It knows nothing else, so `task` must be a full brief (goal, exact file paths, engine/language, constraints, done-when). One at a time. Available: {names}.",
                    "parameters": {"type": "object", "properties": {
                        "name": {"type": "string"}, "task": {"type": "string"}},
                        "required": ["name", "task"]}}}]

        native = True                  # False: model has no tool template -> tools described in text
        if schemas and (model_caps(client, model) is not None) and "tools" not in model_caps(client, model):
            native = False
            msgs[0]["content"] += text_tool_note(schemas)
        retries = 0
        done_calls: dict = {}          # (tool, args, world) -> times called, to break loops
        world = 0                      # bumped when a tool CHANGES files, so re-running a
                                       # build after writing code is a new call, not a repeat
        ran_ok = False                 # did ANY tool actually succeed this turn?
        forced = 0                     # times we made it retry after an empty-handed claim
        loop_strikes = 0               # how often it ignored "stop repeating that call"
        shown = ""                     # visible prose the UI has received this turn
        dup = ""                       # prose shown before a nudge, to not repeat it after
        quiet = False                  # after a nudge: hold everything back, dedupe at the end
        try:
            for _ in range(12):  # tool-loop cap
                acc = ""
                calls = []
                looping = False        # set when the model repeats one call over and over
                held = None            # None = undecided, True = looks like a text tool call
                sent = 0               # chars of acc already streamed to the UI
                context.collapse_tool_outputs(msgs)                  # old tool output -> head/tail
                # Still too big? Summarise the oldest turns with the model that is already
                # resident, instead of deleting them — deleting is how the lead "forgot" the
                # file it had just written and ended up with nothing to say.
                def _sum(text, _m=model, _c=client):
                    r = _c.chat(model=_m, stream=False, keep_alive=-1, options={"num_ctx": ctx_size()},
                                messages=[{"role": "system", "content":
                                           "Summarise this chat so far for yourself in under 120 words: "
                                           "what the user wants, decisions made, files written or "
                                           "deleted, errors still open. Terse notes, no preamble."},
                                          {"role": "user", "content": text[-12000:]}])
                    return (r["message"].get("content") or "").strip()

                info = context.compact(msgs, ctx_size() * 3, _sum)   # ~3 chars/token budget
                if info["compacted"]:
                    yield sse("token", f"\n(compacted {info['compacted']} earlier messages to stay "
                                       "inside the context window)\n")
                resp = client.chat(model=model, messages=msgs, keep_alive=-1,
                                    options={"num_ctx": ctx_size()}, tools=schemas if native else None,
                                    stream=True, **think_arg(client, model))
                thought = ""
                for chunk in resp:
                    msg = chunk.get("message", {})
                    thought += msg.get("thinking") or ""      # Qwen3 etc. answer in a separate field
                    piece = msg.get("content") or ""
                    if piece:
                        acc += piece
                        # small models often "call" tools by typing JSON; hold that back
                        # instead of printing it, then run it as a real call below
                        if held is None and acc.strip():
                            held = toolcalls.looks_like_call(acc)     # None = can't tell yet
                        if held is False and not quiet:
                            # prose first, then a JSON "call"? stop streaming where it starts
                            end = toolcalls.safe_prefix(acc, sent)
                            if end > sent:
                                yield sse("token", acc[sent:end])
                                sent = end
                            if end < len(acc) and toolcalls.CALL_START.search(acc, sent):
                                held = True
                    for tc in (msg.get("tool_calls") or []):
                        calls.append(tc)

                if not calls and schemas and acc.strip():
                    # code the model wrote as execution-tag blocks -> write (+ run) it
                    calls = exec_tags.to_calls(acc, set(apps.REGISTRY) | {"write_file"}) or calls
                if not calls and schemas and acc.strip():
                    known = {x["function"]["name"] for x in schemas}
                    found, _ = toolcalls.extract_calls(acc, known)
                    if found:
                        calls = found
                    elif toolcalls.invented_call(acc) and retries < 2:
                        # it "called" a tool that doesn't exist: tell it, don't show the JSON
                        retries += 1
                        quiet = True
                        d = toolcalls.visible_text(acc[:sent])
                        shown, dup = shown + d, d or dup     # keep what the UI already showed
                        msgs.append({"role": "assistant", "content": acc})
                        msgs.append({"role": "user", "content":
                                     f"(system) '{toolcalls.invented_call(acc)}' is not a tool. Either "
                                     "use one of your real tools through tool calling, or just answer "
                                     "me in plain words."})
                        continue

                # Show prose ONLY — tool-call JSON the model typed never reaches the chat.
                vis = toolcalls.visible_text(acc)
                live = toolcalls.visible_text(acc[:sent]) if sent else ""
                out = vis[len(live):] if live and vis.startswith(live) else vis
                if dup:                                      # a retry that repeated itself
                    out = out[len(dup):] if out.startswith(dup) else ("" if out in dup else out)
                if out.strip():
                    yield sse("token", out)
                shown += live + out
                dup, quiet = "", False

                msgs.append({"role": "assistant", "content": acc,
                             "tool_calls": calls or None})

                if not calls:
                    # It says it finished something but nothing ran. Don't just warn — make it
                    # do the work: tell it plainly that it called nothing, and run one more round.
                    # It described the job instead of doing it ("we should create the file").
                    # Push it once; the user asked for the work, not a plan.
                    if (ran_ok is False and forced < 1 and shown.strip()
                            and not toolcalls.claims_work_done(shown)
                            and toolcalls.proposes_work(shown)):
                        forced += 1
                        yield sse("token", "\n\n→ doing that now…\n")
                        msgs.append({"role": "user", "content":
                                     "(system) You described the work instead of doing it, and called "
                                     "no tool, so nothing happened. Do it NOW with real tool calls — "
                                     "write_file / delete_file / gradle / run_command — then tell me "
                                     "the result. Do not describe the plan again."})
                        shown = ""
                        continue
                    if ran_ok is False and toolcalls.claims_work_done(shown):
                        how = (f"{len(schemas or [])} tools offered, "
                               + ("native tool calling" if native else "text tool calls"))
                        if forced < 1:
                            forced += 1
                            yield sse("token", f"\n\n⚠ You called no tool, so nothing happened "
                                               f"({how}). Making it use its tools now…\n")
                            msgs.append({"role": "user", "content":
                                         "(system) You called NO tool, so nothing on disk changed and "
                                         "your last message was false. Do it NOW with a real tool "
                                         "call: delete_file to delete, write_file to create, "
                                         "run_command or gradle to build. Call the tool — do not "
                                         "describe it, do not apologise."})
                            shown = ""
                            continue
                        yield sse("token", f"\n\n⚠ No tool call succeeded this turn ({how}), so "
                                           "nothing was created, changed or compiled — the claim "
                                           "above is not true. This model is ignoring its tools: try "
                                           "a new chat (a long history makes it copy its own earlier "
                                           "answers), or a different lead model.")
                    if not shown.strip():
                        # a turn must never end with an empty bubble: say what happened
                        if thought.strip() and not acc.strip():
                            yield sse("token", f"({model} spent the whole turn thinking and never "
                                               "wrote an answer. Customize -> turn Thinking off, or "
                                               "ask again more specifically.)\n\nIts notes:\n"
                                               + thought.strip()[-1200:])
                        elif acc.strip():
                            yield sse("token", f"({model} kept typing tool calls as text instead of "
                                               "answering. Pick a stronger lead in the model picker — "
                                               "qwen3:4b, qwen2.5:7b or hermes3:8b — and leave the small "
                                               "coder model as the worker.)")
                        else:
                            yield sse("token", f"({model} returned nothing. It may have run out of "
                                               "context — start a new chat, or lower num_ctx in "
                                               "Customize if your GPU is full.)")
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

                    # Small models get stuck repeating one call (e.g. `remember` with the same
                    # note). Running it again cannot change anything, so answer it from here.
                    sig = f"{name}|{json.dumps(args, sort_keys=True, default=str)}|{world}"
                    done_calls[sig] = done_calls.get(sig, 0) + 1
                    if done_calls[sig] > 1:
                        result = (f"(already called {name} with exactly these arguments, and nothing "
                                  "on disk changed since, so the result is identical. Do NOT repeat "
                                  "it: either do the NEXT step, or answer the user in plain sentences.)")
                        yield sse("tool_result", {"name": name, "result": result})
                        msgs.append({"role": "tool", "content": result})
                        looping = True              # one warning is enough, then force an answer
                        continue

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
                            task = args.get("task", "")
                            if not isinstance(task, str):            # small models send an object
                                task = json.dumps(task, indent=1)
                            result = (run_subagent(client, model, sub, task, active)
                                      if sub else f"error: no subagent '{args.get('name')}'")
                    elif name in apps.REGISTRY:
                        result = apps.run_tool(name, args)
                    elif name in web.REGISTRY:
                        result = web.run_web_tool(name, args) if use_web \
                            else "error: web tools disabled this turn"
                    elif schemas and name not in {x["function"]["name"] for x in schemas}:
                        result = (f"error: there is no tool '{name}'. Use one of: " +
                                  ", ".join(sorted(x["function"]["name"] for x in schemas)))
                    else:
                        result = tools.run_tool(name, args)

                    if not str(result).lstrip().startswith(("error", "FAILED", "blocked")):
                        ran_ok = True
                        if name in WRITE_TOOLS:      # the files changed: earlier calls may now
                            world += 1               # give a different answer, so allow re-runs
                    yield sse("tool_result", {"name": name, "result": result})
                    msgs.append({"role": "tool", "content": result})

                if looping:              # it repeated a call: warn once, then end the turn
                    loop_strikes += 1
                    if loop_strikes > 1:
                        if not shown.strip():
                            yield sse("token", f"({model} kept repeating the same tool call instead "
                                               "of answering. The work above ran once — nothing was "
                                               "repeated. Ask again, or pick a stronger lead.)")
                        break
                    msgs.append({"role": "user", "content":
                                 "(system) Stop calling tools. Answer me now in plain sentences, "
                                 "using what the tools already returned."})
        except Exception as e:
            yield sse("error", str(e))
        try:
            compact_memory(client, model)      # auto, no approval; resident model
        except Exception:
            pass
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
    init_workspace()
    seed_default_subagents()
    startup_apps()
    startup_bridges()
    startup_integrations()

    print(f"workdir (sandbox): {tools.SANDBOX}")
    print(f"skills: {CFG['skills']}  ({len(tools.SKILLS)} loaded)")
    print(f"ollama lib: {'yes' if ollama else 'NO — pip install ollama'}")
    print(f"open http://{a.host}:{a.port}")
    app.run(host=a.host, port=a.port, threaded=True)


if __name__ == "__main__":
    main()
