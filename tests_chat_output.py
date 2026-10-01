"""Regression test for the chat loop: what a small lead model TYPES must never reach the
chat as raw tool-call JSON, must not be repeated after a nudge, and must not leave a
blank reply. Runs offline against a stub Ollama client.

    python tests_chat_output.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app                                                  # noqa: E402

SCRIPT: list = []
FAILS: list = []
CALL_JSON = re.compile(r'\{\s*"(?:name|function)"\s*:')


class FakeClient:
    """Answers with SCRIPT[n] on the n-th round, streamed in small pieces."""

    def __init__(self, *a, **k):
        pass

    def chat(self, model=None, messages=None, **kw):
        n = len([m for m in messages if m.get("role") == "assistant"])
        text = SCRIPT[min(n, len(SCRIPT) - 1)]
        return ({"message": {"content": text[i:i + 7]}} for i in range(0, len(text), 7))

    def list(self):
        return {"models": []}


def run(name: str, script: list, expect_no_json: bool = True) -> str:
    global SCRIPT
    SCRIPT = script
    app.ollama = types.SimpleNamespace(Client=FakeClient)
    r = app.app.test_client().post("/api/chat", json={
        "model": "qwen2.5-coder:3b", "messages": [{"role": "user", "content": "yo qwen"}],
        "tools": True, "ask": False})
    seen = ""
    for block in r.get_data(as_text=True).split("\n\n"):
        ev = re.search(r"event: (.*)", block)
        dl = re.search(r"data: (.*)", block, re.S)
        if ev and ev.group(1) == "token":
            seen += json.loads(dl.group(1))
    leak = expect_no_json and CALL_JSON.search(seen)
    if leak:
        FAILS.append(name)
    print(f"[{'LEAK' if leak else 'ok'}] {name}\n     user sees: {seen!r}")
    return seen


CASES = [
    ("fenced json greeting", ['```json\n{"name": "world", "arguments": {"greeting": "hello!"}}\n```']),
    ("bare json, invented tool", ['{"name": "world", "arguments": {"greeting": "hello!"}}']),
    ("qwen <tool_call> tag, invented", ['<tool_call>\n{"name": "world", "arguments": {"x": 1}}\n</tool_call>']),
    ("qwen <tool_call> tag, real", ['<tool_call>\n{"name": "app_status", "arguments": {}}\n</tool_call>', 'All set.']),
    ("prose then invented json", ['Sure thing!\n{"name": "world", "arguments": {"x": 1}}']),
    ("prose then real call", ['Let me check.\n{"name": "app_status", "arguments": {}}', 'Blender is installed.']),
    ("fenced real call, prose after", ['```json\n{"name": "app_status", "arguments": {}}\n```\nChecking now.', 'Done.']),
    ("stream cut mid-call", ['{"name": "world", "arg']),
    ("two objects, one real", ['{"name": "app_status", "arguments": {}}{"name": "world", "arguments": {}}', 'ok']),
    ("prose + real call + junk call", ['Sure.\n{"name": "app_status", "arguments": {}}\n'
                                       '{"name": "world", "arguments": {"": "hello!"}}', 'ok']),
    ("plain greeting", ['Hey! What are we building tonight?']),
    ("real code block is kept", ['Here you go:\n```python\nprint("hi")\n```']),
    ("exec tag writes a file", ['Here is the model:\n```openscad file=models/box.scad\ncube([10,10,10]);\n```',
                                'Saved it.']),
]

if __name__ == "__main__":
    out = {name: run(name, script) for name, script in CASES}
    # prose the model wrote must be shown exactly once, never twice
    for name in ("prose then invented json", "plain greeting"):
        body = out[name].split("(")[0]
        half = body[:len(body) // 2].strip()
        if half and body.count(half) > 1:
            FAILS.append(f"{name} (shown twice)")
    # a turn must never end silent
    for name, seen in out.items():
        if not seen.strip():
            FAILS.append(f"{name} (blank reply)")
    print("\n" + ("FAILED: " + ", ".join(FAILS) if FAILS else
                  "all clear — no tool-call JSON in the chat, no repeats, no blank replies"))
    sys.exit(1 if FAILS else 0)
