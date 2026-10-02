"""Whole-app smoke test: boots the backend with a stub Ollama and drives a realistic
session — explore, write, build, fail, fix, build again — checking the API, the approval
gate, the sandbox, compaction and the MCP servers.

    python tests_app.py

It never touches a real model, Blender/Unreal/Roblox, or anything outside a temp folder.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

WS = tempfile.mkdtemp(prefix="nc-test-")
DATA = tempfile.mkdtemp(prefix="nc-data-")
os.environ["NC_WORKSPACE"] = WS

import paths                                                   # noqa: E402
paths.data = lambda *p: os.path.join(DATA, *p)                 # keep real user data untouched

import app, apps, context, engines, live, tools, toolcalls, skill_router, vision  # noqa: E402

FAILS: list[str] = []
N = [0]


def check(name, ok, detail=""):
    N[0] += 1
    print(f"[{'ok' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


# ---------------------------------------------------------------- stub model
SCRIPT: list = []


class Stub:
    """Plays SCRIPT round by round; also answers the compaction summariser."""

    def __init__(self, *a, **k):
        pass

    def show(self, m):
        return {"capabilities": ["completion", "tools"]}

    def list(self):
        return {"models": [{"model": "stub-lead"}, {"model": "nomic-embed-text"}]}

    def chat(self, **kw):
        if not kw.get("stream"):
            return {"message": {"content": "Earlier: user is building a Java app."}}
        n = len([m for m in kw["messages"] if m.get("role") == "assistant"])
        return iter(SCRIPT[min(n, len(SCRIPT) - 1)])


def turn(text, script, ask=False, model="stub-lead"):
    global SCRIPT
    SCRIPT = script
    app.ollama = types.SimpleNamespace(Client=Stub)
    r = app.app.test_client().post("/api/chat", json={
        "model": model, "messages": [{"role": "user", "content": text}], "tools": True, "ask": ask})
    out = {"text": "", "calls": [], "results": [], "events": []}
    for b in r.get_data(as_text=True).split("\n\n"):
        e = re.search(r"event: (.*)", b)
        d = re.search(r"data: (.*)", b, re.S)
        if not e:
            continue
        out["events"].append(e.group(1))
        data = json.loads(d.group(1)) if d else None
        if e.group(1) == "token":
            out["text"] += data
        elif e.group(1) == "tool_call":
            out["calls"].append(data["name"])
        elif e.group(1) == "tool_result":
            out["results"].append(data["result"])
    return out


def call(name, args):
    """One round in which the model makes this tool call."""
    return [{"message": {"content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}}]


def say(text):
    """One round in which the model just talks."""
    return [{"message": {"content": text}}]


def main():
    tools.set_sandbox(WS)
    app.CFG["skills"] = os.path.join(HERE, "skills")        # what desktop.serve() does
    tools.scan_skills(app.CFG["skills"])
    app.seed_builtin_connectors()                            # what startup_bridges() does
    c = app.app.test_client()

    print("\n== API ==")
    for path in ("/api/branding", "/api/config", "/api/settings", "/api/skills", "/api/memory",
                 "/api/tree", "/api/apps", "/api/connectors", "/api/subagents", "/api/chats",
                 "/api/bridges", "/api/system", "/api/integrations"):
        try:
            r = c.get(path)
            check(f"GET {path}", r.status_code == 200, f"status {r.status_code}")
        except Exception as e:
            check(f"GET {path}", False, str(e))
    check("POST /api/chats needs X-NC", c.post("/api/chats", json={"convos": []}).status_code == 403)
    check("POST /api/workspace needs X-NC", c.post("/api/workspace", json={"path": WS}).status_code == 403)
    check("chats survive a round trip",
          c.post("/api/chats", json={"convos": [{"id": "1", "title": "t"}], "projects": [],
                                     "instructions": ""}, headers={"X-NC": "1"}).status_code == 200
          and c.get("/api/chats").json["convos"][0]["title"] == "t")

    print("\n== the sandbox holds ==")
    outside = os.path.join(tempfile.mkdtemp(), "secret.txt")
    open(outside, "w").write("do not touch")
    for label, fn in [("read outside", lambda: tools.read_file(outside)),
                      ("write outside", lambda: tools.write_file(outside, "x")),
                      ("delete outside", lambda: tools.delete_file(outside)),
                      ("command outside", lambda: tools.run_command("echo hi", cwd="/etc")),
                      ("escape with ..", lambda: tools.read_file("../../etc/passwd")),
                      ("delete the workspace", lambda: tools.delete_file("."))]:
        try:
            fn()
            check(f"blocked: {label}", False, "it was allowed")
        except tools.ToolError:
            check(f"blocked: {label}", True)
    check("the file outside survived", open(outside).read() == "do not touch")

    print("\n== a real session: explore -> write -> build -> fix -> build ==")
    os.makedirs(os.path.join(WS, "src"), exist_ok=True)
    open(os.path.join(WS, "notes.txt"), "w").write("the user's own notes")

    r = turn("what files are here", [call("list_dir", {"path": "."}), say("notes.txt and src/.")])
    check("lists real files", "notes.txt" in "".join(r["results"]))

    r = turn("read my notes", [call("read_file", {"path": "notes.txt"}), say("Read them.")])
    check("reads a real file", "the user's own notes" in "".join(r["results"]))

    r = turn("read the file that isn't there", [call("read_file", {"path": "nope.txt"}), say("Missing.")])
    joined = "".join(r["results"])
    check("missing file steers, never invents", "do NOT create it" in joined, joined[:80])

    bad = "public class Main { void x() { int y = ; } }"
    good = "public class Main { public static void main(String[] a){ System.out.println(1); } }"
    r = turn("write Main.java and compile it",
             [call("write_file", {"path": "src/Main.java", "content": bad}),
              call("run_command", {"command": "javac -d out src/Main.java", "timeout": 120}),
              call("write_file", {"path": "src/Main.java", "content": good}),
              call("run_command", {"command": "javac -d out src/Main.java", "timeout": 120}),
              say("Fixed the syntax error and it compiles now.")])
    check("wrote the file to disk", os.path.isfile(os.path.join(WS, "src", "Main.java")))
    check("compiled twice (the repeat guard allows a re-run after an edit)",
          r["calls"].count("run_command") == 2, str(r["calls"]))
    if shutil.which("javac") and len(r["results"]) >= 4:
        check("the real compiler error came back", "error" in r["results"][1].lower(), r["results"][1][:80])
        check("the second build passed", r["results"][3].startswith("exit=0"), r["results"][3][:80])
    check("no tool-call JSON leaked into the reply", not re.search(r'\{\s*"name"\s*:', r["text"]))

    r = turn("delete notes.txt", [call("delete_file", {"path": "notes.txt"}), say("Deleted it.")])
    check("delete_file really deletes", not os.path.exists(os.path.join(WS, "notes.txt")))

    print("\n== the honesty guards ==")
    r = turn("make me a mod", [say("I have created your Minecraft mod with ores and mobs.")])
    check("a false completion claim is caught", "⚠" in r["text"] or "called no tool" in r["text"].lower())
    r = turn("create the file", [say("We should create Main.java first."),
                                 call("write_file", {"path": "src/B.java", "content": "class B{}"}),
                                 say("Done.")])
    check("a proposal is pushed into action", "write_file" in r["calls"])
    r = turn("remember it", [call("remember", {"note": "k: v"})] * 6 + [say("Noted.")])
    check("a repeated call runs once", sum("already called" in x for x in r["results"]) >= 1)
    r = turn("hello", [[{"message": {"content": "", "thinking": "hmm"}}]])
    check("a thinking-only turn still says something", bool(r["text"].strip()))

    print("\n== approval gate ==")
    app.save_settings({"trust_workspace": True})
    r = turn("write a file", [call("write_file", {"path": "auto.txt", "content": "x"}), say("done")],
             ask=True)
    check("workspace file edits need no approval", "approval" not in r["events"]
          and os.path.isfile(os.path.join(WS, "auto.txt")))
    # run_command is still gated on purpose (only its cwd is jailed, not the command text)
    SCRIPT_LOCAL = [call("run_command", {"command": "echo pwned > owned.txt"}), say("ok")]
    global SCRIPT
    SCRIPT = SCRIPT_LOCAL
    app.ollama = types.SimpleNamespace(Client=Stub)
    resp = app.app.test_client().post("/api/chat", json={
        "model": "stub-lead", "messages": [{"role": "user", "content": "delete it"}],
        "tools": True, "ask": True}, buffered=False)
    body, denied = "", False
    for chunk in resp.iter_encoded():
        body += chunk.decode("utf-8", "replace")
        m = re.search(r'event: approval\ndata: (.*)', body)
        if m and not denied:
            denied = True
            app.app.test_client().post("/api/approve", json={"id": json.loads(m.group(1))["id"], "allow": False})
    check("approval is requested for commands when Auto is off", denied)
    check("a denied command does not run", not os.path.exists(os.path.join(WS, "owned.txt")))

    print("\n== context compaction ==")
    context._CACHE.clear()
    big = []
    for i in range(40):
        big += [{"role": "user", "content": f"turn {i} " + "x" * 900},
                {"role": "assistant", "content": f"ok {i} " + "y" * 900}]
    big.append({"role": "user", "content": "carry on"})
    SCRIPT = [say("Carrying on.")]
    app.ollama = types.SimpleNamespace(Client=Stub)
    r2 = app.app.test_client().post("/api/chat", json={"model": "stub-lead", "messages": big,
                                                       "tools": True, "ask": False})
    txt = r2.get_data(as_text=True)
    check("a long chat is compacted, not truncated", "compacted" in txt)

    print("\n== routing, skills, model test ==")
    check("typos still route", skill_router.domain_of("complie teh mod") == "java")
    tools.scan_skills(os.path.join(tempfile.mkdtemp(), "gone"))      # a bad path must not wipe them
    check("a missing skills folder does not wipe the catalogue",
          skill_router.domain_of("complie teh mod") == "java")
    check("the build tool is offered",
          "gradle" in [s["function"]["name"] for s in app.lead_app_tools("compile the mod")])
    check("the app's MCP server auto-loads by domain",
          any(c.get("builtin") for c in app.load_connectors()))
    app._CAPS.clear()
    v = app.test_model(Stub(), "stub-lead")
    check("the model fitness test runs", "verdict" in v, str(v)[:80])

    print("\n== our MCP servers ==")
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, "desktop.py"), "--mcp", "blender"],
                           input='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
                                 '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n',
                           capture_output=True, text=True, timeout=60)
        lines = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
        names = [t["name"] for t in lines[-1]["result"]["tools"]]
        check("the blender MCP server lists its tools", len(names) >= 10, f"{len(names)} tools")
    except Exception as e:
        check("the blender MCP server lists its tools", False, str(e))

    print("\n== UI wiring ==")
    html = open(os.path.join(HERE, "static", "index.html")).read()
    js = open(os.path.join(HERE, "static", "app.js")).read()
    for el in ("model-test", "model-test-all", "img-strip", "tb-ctrls", "titlebar",
               "set-think", "worker-model", "bridge-log"):
        check(f"#{el} exists in both HTML and JS", f'id="{el}"' in html and el in js)
    check("the orbit animation is wired", "showOrbit" in js and "orbit-sun" in
          open(os.path.join(HERE, "static", "style.css")).read())
    check("scrolling is pinned-aware", "pinned" in js)

    print(f"\n{N[0]} checks, {len(FAILS)} failed")
    if FAILS:
        print("FAILED:\n  " + "\n  ".join(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(WS, ignore_errors=True)
        shutil.rmtree(DATA, ignore_errors=True)
    sys.exit(code)
