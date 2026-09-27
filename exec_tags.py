"""Structured execution tags: the output format for small models.

Writing a whole script inside a JSON tool call (escaped quotes, newlines) is where
3B models fall apart. Instead they answer with ordinary fenced code blocks whose
info string says what to do with them:

    ```openscad file=models/gear.scad run
    ...code...
    ```

    lang        what it is             `run` does
    openscad    OpenSCAD model         openscad_render -> .stl + .png preview
    bpy         Blender Python         blender_run (headless)
    ue-python   Unreal editor Python   unreal_run_python (needs project=...)
    luau        Roblox Luau            luau_check
    verse       UEFN Verse             verse_check (offline lint; UEFN compiles it)
    plan        JSON plan (see skills) run_plan -> ue_layout / obby / island / scatter
    any other   file only (cpp, ini, json, md, ...)

Only blocks with file= are acted on, so example code in an explanation is never
executed. `run` without file= writes to drafts/ first. to_calls() turns the blocks
into ordinary tool calls, so they go through the same approval gate as any tool.
"""
from __future__ import annotations

import re
import shlex
import time

FENCE = re.compile(r"```[ \t]*([A-Za-z][\w+.-]*)([^\n]*)\n(.*?)(?:\n```|$)", re.S)
EXT = {"openscad": "scad", "scad": "scad", "bpy": "py", "blender": "py", "ue-python": "py",
       "unreal-python": "py", "luau": "luau", "lua": "lua", "verse": "verse", "plan": "json",
       "json": "json", "cpp": "cpp", "python": "py"}
LANG_ALIAS = {"scad": "openscad", "blender": "bpy", "unreal-python": "ue-python", "lua": "luau"}


def _attrs(rest: str) -> dict:
    try:
        parts = shlex.split(rest)
    except ValueError:
        parts = rest.split()
    out = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().lower()] = v.strip().strip('"\'')
        elif p.strip():
            out[p.strip().lower()] = True
    return out


def blocks(text: str) -> list:
    """[{lang, file, run, project, code}] for fenced blocks that carry file= or run."""
    found = []
    for i, m in enumerate(FENCE.finditer(text)):
        lang = LANG_ALIAS.get(m.group(1).lower(), m.group(1).lower())
        a = _attrs(m.group(2))
        if not a.get("file") and not a.get("run"):
            continue
        f = a.get("file") if isinstance(a.get("file"), str) else ""
        if not f:
            f = f"drafts/nc_{int(time.time())}_{i}.{EXT.get(lang, 'txt')}"
        found.append({"lang": lang, "file": f.replace("\\", "/"), "run": bool(a.get("run")),
                      "project": a.get("project") if isinstance(a.get("project"), str) else "",
                      "code": m.group(3).rstrip() + "\n"})
    return found


def _call(name, args):
    return {"function": {"name": name, "arguments": args}}


def run_call(b: dict):
    lang, f = b["lang"], b["file"]
    if lang == "openscad":
        return _call("openscad_render", {"file": f})
    if lang == "bpy":
        return _call("blender_run", {"script": f})
    if lang == "ue-python":
        return _call("unreal_run_python", {"script": f, "project": b["project"]}) if b["project"] else None
    if lang == "luau":
        return _call("luau_check", {"path": f})
    if lang == "verse":
        return _call("verse_check", {"file": f})
    if lang == "plan":
        return _call("run_plan", {"plan": f, "project": b["project"]})
    return None


def to_calls(text: str, known: set) -> list:
    calls = []
    for b in blocks(text):
        calls.append(_call("write_file", {"path": b["file"], "content": b["code"]}))
        if b["run"]:
            c = run_call(b)
            if c and c["function"]["name"] in known:
                calls.append(c)
    return calls
