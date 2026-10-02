"""Keep the lead's context small so a 3B-8B model stays fast and coherent.

collapse_tool_outputs: old tool results -> head + tail (the model already acted on them).
compact: when the chat is still too big, SUMMARISE the oldest turns into one short note
instead of deleting them — dropping them outright is what made the lead forget the file it
had just written. trim_history is the last resort if there is no summariser.
"""
from __future__ import annotations

import hashlib

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


MARK = "[earlier in this chat]"
_CACHE: dict[str, str] = {}          # span fingerprint -> summary, so a long chat is
                                     # summarised once, not again on every single turn


def _key(msgs: list[dict]) -> str:
    h = hashlib.sha1()
    for m in msgs:
        h.update(f"{m.get('role')}:{str(m.get('content'))[:400]}".encode("utf-8", "replace"))
    return h.hexdigest()


def summarise_span(msgs: list[dict], summarise) -> str:
    """One short note standing in for `msgs`. Cached; "" if the model could not do it."""
    k = _key(msgs)
    if k in _CACHE:
        return _CACHE[k]
    lines = []
    for m in msgs:
        role = m.get("role")
        body = str(m.get("content") or "").strip().replace("\n", " ")
        for tc in m.get("tool_calls") or []:
            body += f" [called {tc.get('function', {}).get('name', '?')}]"
        if body:
            lines.append(f"{role}: {body[:600]}")
    if not lines:
        return ""
    try:
        out = (summarise("\n".join(lines)) or "").strip()
    except Exception:
        out = ""
    if out:
        _CACHE[k] = out
        if len(_CACHE) > 40:
            _CACHE.pop(next(iter(_CACHE)))
    return out


def compact(msgs: list[dict], budget_chars: int, summarise=None, keep_recent: int = 6) -> dict:
    """Fit `msgs` into the budget. Oldest turns become ONE summary message; the newest
    `keep_recent` messages are always kept word for word. Returns what it did."""
    total = sum(_size(m) for m in msgs)
    if total <= budget_chars:
        return {"compacted": 0, "dropped": 0, "chars": total}

    first = next((i for i, m in enumerate(msgs) if m.get("role") != "system"), None)
    if first is None or not summarise:
        return {"compacted": 0, "dropped": trim_history(msgs, budget_chars), "chars": total}

    end = len(msgs) - keep_recent                      # everything before this may be summarised
    while end > first and msgs[end].get("role") in ("tool", "assistant"):
        end -= 1                                        # never split a call from its result
    span = msgs[first:end]
    if len(span) < 2:
        return {"compacted": 0, "dropped": trim_history(msgs, budget_chars), "chars": total}

    note = summarise_span(span, summarise)
    if not note:
        return {"compacted": 0, "dropped": trim_history(msgs, budget_chars), "chars": total}

    msgs[first:end] = [{"role": "user", "content": f"{MARK} {note}"}]
    dropped = trim_history(msgs, budget_chars)          # still too big? then trim as well
    return {"compacted": len(span), "dropped": dropped, "chars": sum(_size(m) for m in msgs)}
