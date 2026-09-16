"""Web search tools, gated to /web turns only (same as the CLI agent)."""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0 (local-ollama-agent)"}


def web_search(query: str) -> str:
    url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        page = r.read().decode("utf-8", "replace")
    # anchors: href precedes class="result-link"; hrefs are html-escaped
    hits = re.findall(r'href="([^"]+)"[^>]*class="result-link"', page)
    hits = [html.unescape(h) for h in hits]
    if not hits:
        return "(no results)"
    return "\n".join(hits[:8])


def web_fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        page = r.read().decode("utf-8", "replace")
    text = re.sub(r"<script.*?</script>", "", page, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text))
    return text[:4000]


REGISTRY = {"web_search": web_search, "web_fetch": web_fetch}

SCHEMAS = [
    {"type": "function", "function": {
        "name": "web_search", "description": "Search the web, return top links.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "web_fetch", "description": "Fetch a URL and return readable text.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
]


def run_web_tool(name: str, args: dict) -> str:
    fn = REGISTRY.get(name)
    if not fn:
        return f"error: unknown web tool {name}"
    try:
        return fn(**args)
    except Exception as e:
        return f"error: {name} failed: {e}"
