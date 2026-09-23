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


# ---- tools -----------------------------------------------------------------

def read_file(path: str) -> str:
    p = _jail(path)
    if not p.is_file():
        raise ToolError(f"no file: {path}")
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
    p = _jail(path)
    if not p.is_dir():
        raise ToolError(f"no dir: {path}")
    rows = []
    for c in sorted(p.iterdir()):
        rows.append(("DIR  " if c.is_dir() else "FILE ") + c.name)
    return "\n".join(rows) or "(empty)"


def glob(pattern: str) -> str:
    if SANDBOX is None:
        raise ToolError("no sandbox set")
    hits = [str(m.relative_to(SANDBOX)) for m in SANDBOX.glob(pattern)]
    return "\n".join(sorted(hits)) or "(no matches)"


def grep(pattern: str, path: str = ".") -> str:
    import re
    root = _jail(path)
    rx = re.compile(pattern)
    out = []
    files = [root] if root.is_file() else root.rglob("*")
    for f in files:
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    out.append(f"{f.relative_to(SANDBOX)}:{i}: {line.strip()}")
        except Exception:
            continue
    return "\n".join(out[:200]) or "(no matches)"


def run_command(command: str) -> str:
    if SANDBOX is None:
        raise ToolError("no sandbox set")
    r = subprocess.run(
        command, shell=True, cwd=SANDBOX,
        capture_output=True, text=True, timeout=120,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return f"exit={r.returncode}\n{out}".strip()


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
        return [l for l in _jail(MEMORY_FILE).read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def memory_text() -> str:
    return "\n".join(memory_lines())


def write_memory(lines: list) -> None:
    p = _jail(MEMORY_FILE)
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
    "load_skill": load_skill,
    "remember": remember,
}

# Tools that mutate state or run code -> need user approval unless yolo.
GATED = {"write_file", "edit_file", "run_command"}

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
        "name": "run_command", "description": "Run a shell command in the workdir.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
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
        # crude frontmatter/description sniff
        for line in text.splitlines():
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
