"""Dynamic skill loader for small (3B) models.

A 3B model can't hold 75 skills. Each domain skill declares, in its frontmatter,
    domain: fortnite
    triggers: fortnite, uefn, verse, island, creative device, ...
route() scores the task text against every skill's triggers and returns the best
domain's skills (plus any the agent is explicitly assigned), trimmed to a character
budget so the prompt stays well inside an 8k context. The chosen skill text is what
keeps the model on the rails: allowed APIs, syntax rules, and the exact output
format (execution tags / JSON plans) it must use.
"""
from __future__ import annotations

import re

import tools

BUDGET = 6000            # chars of skill text injected into a 3B model's prompt (~1.6k tokens)


def _meta(body: str) -> dict:
    """domain / triggers / budget_priority from the --- frontmatter."""
    out = {}
    lines = body.splitlines()
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip().lower()] = v.strip()
    return out


def catalog() -> dict:
    """name -> {domain, triggers[], body} for skills that opted into routing."""
    cat = {}
    for name, s in tools.SKILLS.items():
        m = _meta(s["body"])
        if m.get("triggers"):
            cat[name] = {"domain": m.get("domain", name),
                         "triggers": [t.strip().lower() for t in m["triggers"].split(",") if t.strip()],
                         "body": s["body"]}
    return cat


def score(task: str, triggers: list) -> int:
    t = task.lower()
    total = 0
    for trig in triggers:
        # whole-word / phrase match; longer phrases count more
        if re.search(r"(?<![a-z0-9])" + re.escape(trig) + r"(?![a-z0-9])", t):
            total += 2 + trig.count(" ")
    return total


def route(task: str, assigned=None, budget: int = BUDGET) -> list:
    """-> [(skill_name, text)] to inject: the best-scoring domain's skills first, then
    the agent's assigned skills if there's room. Cut to fit `budget` characters."""
    cat = catalog()
    picked, seen = [], set()
    ranked = sorted(((score(task, c["triggers"]), n) for n, c in cat.items()), reverse=True)
    if ranked and ranked[0][0] > 0:                 # task-matched skills first: they fit THIS job
        top_domain = cat[ranked[0][1]]["domain"]
        for sc, n in ranked:
            if sc > 0 and cat[n]["domain"] == top_domain and n not in seen:
                picked.append(n)
                seen.add(n)
    for name in assigned or []:                     # then the agent's own skills, if room
        if name in tools.SKILLS and name not in seen:
            picked.append(name)
            seen.add(name)
    out, used = [], 0
    for n in picked:
        body = tools.SKILLS[n]["body"]
        room = budget - used
        if room < 400:
            break
        if len(body) > room:
            body = body[:room].rsplit("\n", 1)[0] + "\n…(trimmed; load_skill for the rest)"
        out.append((n, body))
        used += len(body)
    return out


def domain_of(task: str) -> str:
    cat = catalog()
    best = max(((score(task, c["triggers"]), c["domain"]) for c in cat.values()), default=(0, ""))
    return best[1] if best[0] > 0 else ""
