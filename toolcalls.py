"""Recover tool calls that small models write as TEXT instead of real tool calls.

llama3.2 / small qwen / hermes often answer with
    {"name": "blender_run", "arguments": {...}}
    <tool_call>{"name": ..., "arguments": ...}</tool_call>
    ```json {"name": ..., "parameters": {...}} ```
in the message body. Ollama returns that as plain content, so without this the app
would just print the JSON. extract_calls() turns it back into real calls.
"""
from __future__ import annotations

import json
import re

# what a model's "tool call as text" can start with (after whitespace)
LEADS = ("{", "[", "<tool_call>", "```", "<function", "functions.")
# tool names models invent that clearly mean one of ours
ALIASES = {
    "open_app": "app_control", "launch_app": "app_control", "close_app": "app_control",
    "run_app": "app_control", "open_application": "app_control", "app-control": "app_control",
    "open_website": "open_url", "browse": "open_url", "open_browser": "open_url",
    "spawn_agent": "spawn_subagent", "delegate": "spawn_subagent",
    "run_blender": "blender_run", "blender": "blender_run",
}


def looks_like_call(text: str):
    """True / False, or None while it's too short to tell (e.g. "<tool_c")."""
    t = text.lstrip()
    if t.startswith(LEADS):
        return True
    if any(lead.startswith(t) for lead in LEADS):
        return None
    return False


CALL_START = re.compile(r'\{\s*"(?:name|function)"\s*:')


def safe_prefix(text: str, start: int) -> int:
    """How far text can be streamed: up to a JSON tool call, and never through a
    trailing '{' that might be the start of one."""
    m = CALL_START.search(text, start)
    if m:
        return m.start()
    tail = text.rfind("{", start)
    if tail >= 0 and len(text) - tail < 14 and '"name"'.startswith(re.sub(r"\s", "", text[tail + 1:])[:6]):
        return tail
    return len(text)


def invented_call(text: str):
    """Name of a tool the model 'called' in text that doesn't exist, else None."""
    for obj, _, _ in _objects(text):
        if isinstance(obj, dict) and isinstance(obj.get("name"), str) and \
                any(k in obj for k in ("arguments", "parameters", "args")):
            return obj["name"]
    return None


def _objects(text: str):
    dec = json.JSONDecoder()
    i = 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return
        try:
            obj, end = dec.raw_decode(text, i)
            yield obj, i, end
            i = end
        except ValueError:
            i += 1


CALL_KEYS = ("arguments", "parameters", "args")
TAGS = re.compile(r"</?tool_call>|</?function[^>]*>|\bfunctions\.\w+")
EMPTY_FENCE = re.compile(r"```[a-zA-Z]*\s*```")
FENCE = re.compile(r"```[a-zA-Z]*")


def _is_call_shaped(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    if "function" in obj and isinstance(obj["function"], dict):
        obj = obj["function"]
    return isinstance(obj.get("name") or obj.get("tool"), str) and any(k in obj for k in CALL_KEYS)


def visible_text(text: str) -> str:
    """The prose a user should SEE: every tool-call-shaped JSON object removed, whether or
    not the tool exists, plus the wrapper tags/fences models put around them. A model that
    only typed a call leaves "" — the user never gets raw JSON in the chat."""
    spans = []
    for obj, a, b in _objects(text):
        items = obj if isinstance(obj, list) else [obj]
        if items and all(_is_call_shaped(it) for it in items):
            spans.append((a, b))
    out = text
    for a, b in reversed(spans):
        out = out[:a] + out[b:]
    out = TAGS.sub("", out)
    cut = CALL_START.search(out)          # a call the stream stopped in the middle of
    if cut and out.count("{", cut.start()) > out.count("}", cut.start()):
        out = out[:cut.start()]
    if spans:
        # the call sat inside ```json … ```: drop the fence it left behind, but never
        # touch the fences around a real code block the model also wrote
        out = EMPTY_FENCE.sub("", out)
        if len(FENCE.findall(out)) % 2:
            out = FENCE.sub("", out, count=1) if out.lstrip().startswith("```") else out[::-1].replace("```"[::-1], "", 1)[::-1]
    return out.strip()


def extract_calls(text: str, known: set) -> tuple[list, str]:
    """-> (calls in Ollama's shape, leftover prose). Only names in `known` (after
    aliasing) count, so a JSON example in a normal answer isn't executed."""
    calls, spans = [], []
    for obj, a, b in _objects(text):
        items = obj if isinstance(obj, list) else [obj]
        for it in items:
            if not isinstance(it, dict):
                continue
            if "function" in it and isinstance(it["function"], dict):   # {"function": {...}}
                it = it["function"]
            name = it.get("name") or it.get("tool") or ""
            args = it.get("arguments", it.get("parameters", it.get("args", {})))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            name = ALIASES.get(name, name)
            if name in known and isinstance(args, dict):
                calls.append({"function": {"name": name, "arguments": args}})
                spans.append((a, b))
    return calls, visible_text(text)
