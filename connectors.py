"""MCP connector bridge — makes Ai Heaven an MCP client.

Registered MCP servers (stdio command or SSE url) expose tools that get
namespaced `mcp__<server>__<tool>` and handed to the agent alongside the
built-in tools. Every agent (main + subagents) shares the same connectors.

This is best-effort and fail-closed: if the `mcp` SDK or a server is missing,
tools simply don't appear and nothing breaks. Install with `pip install mcp`.

Config: a list of dicts, each:
  {"id","name","enabled",
   "transport": "stdio"|"sse",
   "command","args":[...],           # stdio
   "url":"https://…/sse"}            # sse
"""
from __future__ import annotations

import asyncio


def _available() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except Exception:
        return False


async def _session(server):
    """Yield an initialized MCP ClientSession for one server (context manager)."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _cm():
        from mcp import ClientSession
        if server.get("transport") == "sse":
            from mcp.client.sse import sse_client
            async with sse_client(server["url"]) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    yield s
        else:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(
                command=server.get("command", ""),
                args=server.get("args", []),
            )
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    yield s

    return _cm()


def list_tools(servers: list) -> tuple[list, dict]:
    """Return (openai-style tool schemas, index name->(server, tool))."""
    if not _available():
        return [], {}
    schemas, index = [], {}

    async def gather():
        for sv in servers:
            if not sv.get("enabled", True):
                continue
            try:
                cm = await _session(sv)
                async with cm as s:
                    listed = await s.list_tools()
                    for t in listed.tools:
                        nm = f"mcp__{sv['name']}__{t.name}"
                        schemas.append({"type": "function", "function": {
                            "name": nm,
                            "description": (t.description or "")[:300],
                            "parameters": t.inputSchema or {"type": "object", "properties": {}},
                        }})
                        index[nm] = (sv, t.name)
            except Exception:
                continue

    try:
        asyncio.run(gather())
    except Exception:
        return [], {}
    return schemas, index


def call_tool(server: dict, tool: str, args: dict) -> str:
    if not _available():
        return "error: mcp SDK not installed (pip install mcp)"

    async def go():
        cm = await _session(server)
        async with cm as s:
            res = await s.call_tool(tool, args or {})
            parts = []
            for c in getattr(res, "content", []) or []:
                parts.append(getattr(c, "text", "") or str(c))
            return "\n".join(parts) or "(no output)"

    try:
        return asyncio.run(go())
    except Exception as e:
        return f"error: mcp call failed: {e}"
