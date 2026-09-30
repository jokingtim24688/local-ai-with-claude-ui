"""Keep the lead's context small so a 3B-8B model stays fast and coherent.

collapse_tool_outputs: old tool results -> head + tail with a marker (the model already
acted on them). trim_history: if the chat is still over budget, drop the oldest turns.
"""
from __future__ import annotations

HEAD = 400
TAIL = 150


def collapse_tool_outputs(msgs: list[dict], keep_last: int = 2) -> int:
    """Shrink all but the newest `keep_last` tool results in place. Returns chars saved."""
    idx = [i for i, m in enumerate(msgs) if m.get("role") == "tool"]
    saved = 0
    for i in idx[:-keep_last] if keep_last else idx:
        c = msgs[i].get("content")
        if isinstance(c, str) and len(c) > HEAD + TAIL + 80 and "chars collapsed" not in c:
            cut = len(c) - HEAD - TAIL
            msgs[i]["content"] = f"{c[:HEAD]}\n…[{cut} chars collapsed]…\n{c[-TAIL:]}"
            saved += cut
    return saved


def _size(m: dict) -> int:
    n = len(str(m.get("content") or ""))
    for tc in m.get("tool_calls") or []:
        n += len(str(tc))
    return n


def trim_history(msgs: list[dict], budget_chars: int) -> int:
    """Drop oldest non-system messages until under budget. Always keeps the newest user
    turn and whatever follows it. Returns number of messages dropped."""
    dropped = 0
    while sum(_size(m) for m in msgs) > budget_chars:
        last_user = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=-1)
        first = next((i for i, m in enumerate(msgs) if m.get("role") != "system"), None)
        if first is None or first >= last_user:
            break
        del msgs[first]
        dropped += 1
        while first < len(msgs) and first < last_user - dropped + 1 and msgs[first].get("role") == "tool":
            del msgs[first]                       # never leave an orphan tool result
            dropped += 1
    return dropped
