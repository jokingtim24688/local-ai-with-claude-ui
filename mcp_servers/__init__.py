"""Night Crew's own MCP servers, one per app. Run one:

    python desktop.py --mcp blender          (dev)
    "Night Crew.exe" --mcp blender           (built app)

The app registers them as built-in connectors (connectors.json, `builtin: true`), so a
chat gets `mcp__blender__*` etc. after it mentions the app. Any other MCP client
(Claude Desktop, Cursor...) can use the same command.
"""
from __future__ import annotations

import importlib
import os
import sys

SERVERS = {
    "blender": "Blender — live session (add-on) or headless .blend: scene, objects, materials, render, export",
    "unreal": "Unreal Engine 5 — live editor (Remote Control) or headless: actors, layouts, screenshots, builds",
    "roblox": "Roblox Studio — live place edits via the Night Crew plugin: tree, parts, scripts, output",
    "openscad": "OpenSCAD — parametric CAD: render STL/3MF + preview, list/override parameters",
    "fortnite": "UEFN / Fortnite — Verse write + lint, islands from plans, heightmaps, open projects",
}


def launch_cmd(name: str) -> tuple[str, list]:
    import paths
    if paths.FROZEN:
        exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
        return exe, ["--mcp", name]
    return sys.executable, [os.path.join(paths.HERE, "desktop.py"), "--mcp", name]


def builtin_connectors() -> list:
    out = []
    for name, desc in SERVERS.items():
        cmd, args = launch_cmd(name)
        out.append({"id": f"nc-{name}", "name": name, "enabled": True, "transport": "stdio",
                    "command": cmd, "args": args, "builtin": True, "desc": desc})
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in SERVERS:
        print("usage: --mcp " + "|".join(SERVERS), file=sys.stderr)
        return 2
    mod = importlib.import_module(f"mcp_servers.{argv[0]}")
    return mod.build().run()
