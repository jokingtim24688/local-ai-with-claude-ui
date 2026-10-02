"""Tool registry + sandbox guard for the local Ollama agent.

Every file op is confined to a work directory (the "sandbox jail").
Attempts to escape via .., absolute paths, or symlinks are blocked.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# Set by the app at startup. All file ops confined here.
SANDBOX: Path | None = None
# Loaded skills: name -> {"desc": str, "body": str, "path": str}
SKILLS: dict[str, dict] = {}
# Persistent notes written by the model.
MEMORY_FILE = "MEMORY.md"
# The lead's memory lives in the app's data folder (set by the app), NOT in the
# workspace — switching workspaces must not lose or scatter memory.
MEMORY_PATH: Path | None = None


class ToolError(Exception):
    pass


def set_sandbox(path: str) -> Path:
    global SANDBOX
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    SANDBOX = p
    return p


def _jail(rel: str) -> Path:
    """Resolve a path and prove it stays inside the sandbox."""
    if SANDBOX is None:
        raise ToolError("no sandbox set")
    target = (SANDBOX / rel).resolve()
    try:
        target.relative_to(SANDBOX)
    except ValueError:
        raise ToolError(f"blocked: '{rel}' escapes sandbox")
    return target


def read_roots() -> list:
    """Folders the agents may READ from: the workspace + the project folders the user
    registered in Customize -> Apps (+ the engines' standard project folders). Writing
    still only ever happens inside the workspace."""
    roots = [SANDBOX] if SANDBOX else []
    try:
        import apps
        extra = apps.load_cfg()["projects"] + apps._std_roots()
    except Exception:
        extra = []
    for r in extra:
        try:
            p = Path(r).expanduser().resolve()
            if p.is_dir() and p not in roots:
                roots.append(p)
        except Exception:
            continue
    return roots


def _read_jail(rel: str) -> Path:
    """Like _jail but also accepts a path inside a registered project folder."""
    if not os.path.isabs(rel):
        try:
            return _jail(rel)
        except ToolError:
            raise
    real = Path(rel).expanduser().resolve()
    for root in read_roots():
        if real == root or root in real.parents:
            return real
    raise ToolError(f"blocked: '{rel}' is outside the workspace and the registered project "
                    "folders — add its folder in Customize -> Apps to read it")


def _near(name: str, limit: int = 8) -> list:
    """Existing files whose name looks like `name`, to steer a model that would otherwise
    invent the file. Searches the workspace and the registered project folders."""
    want = os.path.basename(name).lower()
    stem = os.path.splitext(want)[0]
    hits = []
    for root in read_roots():
        try:
            for f in root.rglob("*"):
                if not f.is_file() or f.name.startswith("."):
                    continue
                n = f.name.lower()
                if n == want or stem and (stem in n or os.path.splitext(n)[0] in stem):
                    hits.append(str(f))
                    if len(hits) >= limit:
                        return hits
        except Exception:
            continue
    return hits


# ---- tools -----------------------------------------------------------------

def read_file(path: str) -> str:
    p = _read_jail(path)
    if not p.is_file():
        near = _near(path)
        hint = ("\nDid you mean one of these? Read one of these paths instead:\n- " +
                "\n- ".join(near)) if near else (
            "\nUse glob/list_dir to find it. If it is outside the workspace, the user must add "
            "its folder in Customize -> Apps.")
        raise ToolError(f"no file: {path}. This file does NOT exist — do NOT create it or invent "
                        f"its contents.{hint}")
    return p.read_text(encoding="utf-8", errors="replace")


def write_file(path: str, content: str) -> str:
    p = _jail(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"OK: wrote {path} ({len(content)} bytes)"


def edit_file(path: str, old: str, new: str) -> str:
    p = _jail(path)
    if not p.is_file():
        raise ToolError(f"no file: {path}")
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise ToolError("old string not found")
    if text.count(old) > 1:
        raise ToolError("old string not unique")
    p.write_text(text.replace(old, new), encoding="utf-8")
    return f"OK: edited {path}"


def list_dir(path: str = ".") -> str:
    p = _read_jail(path)
    if not p.is_dir():
        raise ToolError(f"no dir: {path}")
    rows = []
    for c in sorted(p.iterdir()):
        rows.append(("DIR  " if c.is_dir() else "FILE ") + c.name)
    return "\n".join(rows) or "(empty)"


def glob(pattern: str) -> str:
    """Search the workspace, then the registered project folders (so the agents can FIND an
    existing file instead of assuming it is missing)."""
    if SANDBOX is None:
        raise ToolError("no sandbox set")
    hits = [str(m.relative_to(SANDBOX)) for m in SANDBOX.glob(pattern)]
    if not hits:
        for root in read_roots()[1:]:
            hits += [str(m) for m in root.glob(pattern)][:50]
            if len(hits) >= 50:
                break
    return "\n".join(sorted(hits)[:200]) or "(no matches)"


def grep(pattern: str, path: str = ".") -> str:
    import re
    root = _read_jail(path)
    rx = re.compile(pattern)
    out = []
    files = [root] if root.is_file() else root.rglob("*")
    for f in files:
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    try:
                        where = f.relative_to(SANDBOX)
                    except ValueError:
                        where = f                      # a registered project folder
                    out.append(f"{where}:{i}: {line.strip()}")
        except Exception:
            continue
    return "\n".join(out[:200]) or "(no matches)"


def run_command(command: str, cwd: str = "", timeout: int = 120) -> str:
    """Run a shell command INSIDE THE WORKSPACE only (`cwd` may be a subfolder of it).
    Point the workspace at the project you want to build (IDE -> PC -> Use). Builds are
    slow, so raise `timeout` (seconds, up to 1800) for gradle/maven."""
    if SANDBOX is None:
        raise ToolError("no sandbox set")
    where = _jail(cwd) if cwd else SANDBOX
    if not where.is_dir():
        raise ToolError(f"not a folder: {cwd}")
    try:
        r = subprocess.run(command, shell=True, cwd=str(where), capture_output=True,
                           text=True, errors="replace", timeout=max(5, min(int(timeout), 1800)))
    except subprocess.TimeoutExpired:
        return (f"error: '{command[:60]}' hit the {timeout}s timeout in {where}. Builds are slow — "
                "call it again with a bigger timeout (up to 1800).")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if len(out) > 6000:                       # keep a small model's context usable
        out = out[:1500] + f"\n…[{len(out) - 4500} chars cut]…\n" + out[-3000:]
    return f"exit={r.returncode} (in {where})\n{out}".strip()


def delete_file(path: str, recursive: bool = False) -> str:
    """Delete a file (or, with recursive=true, a folder) INSIDE THE WORKSPACE only.
    Never the workspace itself, and never anything outside it."""
    import shutil as _sh
    p = _jail(path)
    if p == SANDBOX:
        raise ToolError("refusing to delete the workspace itself")
    if not p.exists():
        raise ToolError(f"no such file: {path}")
    if p.is_dir():
        if not recursive:
            n = sum(1 for _ in p.rglob("*"))
            raise ToolError(f"{path} is a folder with {n} item(s) — pass recursive=true to delete it")
        _sh.rmtree(p)
        return f"OK: deleted folder {path}"
    size = p.stat().st_size
    p.unlink()
    return f"OK: deleted {path} ({size} bytes)"


def load_skill(name: str) -> str:
    s = SKILLS.get(name)
    if not s:
        return f"no skill '{name}'. have: {', '.join(SKILLS) or 'none'}"
    return s["body"]


# Memory is kept as terse `key: value` lines so it stays tiny in the main model's
# prompt. New notes are squeezed (filler dropped), deduped, and a note whose key
# already exists replaces the old line instead of piling up.
MEMORY_BUDGET = 2000          # chars; over this the app auto-compacts it
_FILLER = re.compile(
    r"\b(a|an|the|please|really|just|very|basically|actually|"
    r"definitely|kind of|sort of)\b\s*", re.I)


def squeeze(note: str) -> str:
    s = " ".join(str(note).split())                 # collapse whitespace/newlines
    s = _FILLER.sub("", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s).strip(" .")
    return s[:200]


def _mem_key(line: str):
    m = re.match(r"\s*[-*]?\s*([A-Za-z0-9_ \-]{1,32}):\s", line)
    return m.group(1).strip().lower() if m else None


def memory_lines() -> list:
    try:
        return [l for l in _mem_file().read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def memory_text() -> str:
    return "\n".join(memory_lines())


def _mem_file() -> Path:
    return MEMORY_PATH or _jail(MEMORY_FILE)


def write_memory(lines: list) -> None:
    p = _mem_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(l for l in lines if l.strip()) + "\n", encoding="utf-8")


def remember(note: str) -> str:
    s = squeeze(note)
    if not s:
        return "error: empty note"
    lines = memory_lines()
    key = _mem_key(s)
    if key:
        lines = [l for l in lines if _mem_key(l) != key]     # upsert by key
    lines = [l for l in lines if l.strip().lower() != s.lower()]
    lines.append(s)
    write_memory(lines)
    return f"OK: remembered ({len(s)} chars, memory {sum(len(l) + 1 for l in lines)}/{MEMORY_BUDGET})"


# ---- registry --------------------------------------------------------------

REGISTRY = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_dir": list_dir,
    "glob": glob,
    "grep": grep,
    "run_command": run_command,
    "delete_file": delete_file,
    "load_skill": load_skill,
    "remember": remember,
}

# Tools that mutate state or run code -> need user approval unless yolo.
GATED = {"write_file", "edit_file", "run_command", "delete_file"}

# JSON schemas exposed to models that support native tool calling.
SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a text file inside the workdir.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Write/overwrite a file inside the workdir.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit_file", "description": "Replace one unique substring in a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
            "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {
        "name": "list_dir", "description": "List a directory inside the workdir.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "glob", "description": "Glob for files, e.g. **/*.py",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "grep", "description": "Regex search files under a path.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Run a shell command in the workspace (cwd = a subfolder of it). "
                       "timeout seconds, default 120 — use 600+ for a Gradle/Maven build.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}, "cwd": {"type": "string"},
            "timeout": {"type": "integer"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "delete_file",
        "description": "Delete a file in the workspace. recursive=true also deletes a folder "
                       "and everything in it. Workspace only — nothing outside it.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "recursive": {"type": "boolean"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "load_skill", "description": "Load a skill body by name.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "remember", "description": "Save one terse fact to persistent memory as `key: value` (same key replaces the old value). Auto-approved; memory auto-compacts.",
        "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}}},
]


def scan_skills(skills_dir: str) -> dict[str, dict]:
    """Load name+desc+body from skills/**/SKILL.md files."""
    SKILLS.clear()
    root = Path(skills_dir)
    if not root.is_dir():
        return SKILLS
    for md in root.rglob("SKILL.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        name = md.parent.name
        desc = ""
        # read name/description from the --- frontmatter only (a code line like
        # `name: str` in the body must not rename the skill)
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                low = line.lower().strip()
                if low.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif low.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
        if not desc:
            for line in text.splitlines():
                s = line.strip()
                if s and not s.startswith("#") and not s.startswith("---"):
                    desc = s[:200]
                    break
        SKILLS[name] = {"desc": desc, "body": text, "path": str(md)}
    return SKILLS


def run_tool(name: str, args: dict) -> str:
    fn = REGISTRY.get(name)
    if not fn:
        return f"error: unknown tool {name}"
    try:
        return fn(**args)
    except ToolError as e:
        return f"error: {e}"
    except TypeError as e:
        return f"error: bad args for {name}: {e}"
    except Exception as e:
        return f"error: {name} failed: {e}"
