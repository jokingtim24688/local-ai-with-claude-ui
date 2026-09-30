"""nightcrew-roblox: edits the place open in Roblox Studio through the Night Crew Bridge
plugin (every change = one undo step). Offline tools (new obby place, Luau lint, Rojo) work
without Studio. Paths look like Workspace.Map.Part or ServerScriptService.GameRules."""
from __future__ import annotations

import json

from mcp_servers.core import Server, plan_arg, setup_workspace


def _call(op: str, args: dict, timeout: float = 60) -> str:
    import live
    r = live.roblox_call(op, args, timeout)
    out = r.get("output")
    text = out if isinstance(out, str) else json.dumps(out)
    return ("OK\n" if r.get("ok") else "error: ") + text


def build() -> Server:
    setup_workspace()
    import live
    live.start_roblox_host()                   # host the plugin queue if the app isn't already
    srv = Server("roblox", "Roblox Studio tools. Needs Studio open with the Night Crew plugin "
                 "(install_plugin once, then the Night Crew > Connect button). Look first with "
                 "`explore`. Properties use plain JSON: Position [x,y,z], Color '#rrggbb' or a "
                 "BrickColor name, Material 'Neon', Anchored true.")

    @srv.tool("Is Studio connected? Where does the plugin go?")
    def status() -> str:
        import apps
        return json.dumps({"connected": live.roblox_connected(), "studio": apps.find_roblox(),
                           "plugin_dir": live.roblox_plugins_dir()})

    @srv.tool("Copy the Night Crew Bridge plugin into Studio's plugins folder (restart Studio after).")
    def install_plugin() -> str:
        return live.install_roblox_plugin()

    @srv.tool("Show the instance tree under a path (name, class, position/size of parts).",
              path="e.g. Workspace, ServerScriptService, Workspace.Map", depth="levels deep, 0-5")
    def explore(path: str = "Workspace", depth: int = 2) -> str:
        return _call("tree", {"path": path, "depth": depth})

    @srv.tool("Create an instance (Part, Model, SpawnLocation, PointLight, Folder, ...). Parts are anchored.",
              class_name="Roblox class", parent="parent path", name="Name",
              props="properties, e.g. {\"Size\":[4,1,4],\"Position\":[0,5,0],\"Color\":\"#ff8800\",\"Material\":\"Neon\"}")
    def create(class_name: str, parent: str = "Workspace", name: str = "", props: dict = None) -> str:
        return _call("create", {"class": class_name, "parent": parent, "name": name, "props": props or {}})

    @srv.tool("Set properties on an instance.", path="instance path", props="property -> value")
    def set_props(path: str, props: dict) -> str:
        return _call("set", {"path": path, "props": props})

    @srv.tool("Read properties of an instance.", path="instance path", props="property names")
    def get_props(path: str, props: list = None) -> str:
        return _call("get", {"path": path, "props": list(props or [])})

    @srv.tool("Delete instances.", paths="instance paths")
    def delete(paths: list) -> str:
        return _call("delete", {"paths": [paths] if isinstance(paths, str) else list(paths)})

    @srv.tool("Create or replace a Script / LocalScript / ModuleScript with this Luau source. "
              "Lints it first when luau-analyze is installed.",
              name="script name", source="Luau code", parent="e.g. ServerScriptService, StarterPlayer.StarterPlayerScripts",
              kind="Script | LocalScript | ModuleScript")
    def write_script(name: str, source: str, parent: str = "ServerScriptService", kind: str = "Script") -> str:
        import apps
        import tools
        note = ""
        try:
            rel = f"roblox/lint/{name}.luau"
            tools.write_file(rel, source)
            chk = apps.luau_check(rel)
            if chk and "error" in chk.lower():
                note = "\nlint:\n" + chk[-1500:]
        except Exception:
            pass
        return _call("script", {"name": name, "source": source, "parent": parent, "kind": kind}) + note

    @srv.tool("Run Luau in Studio's edit context (plugin security). print() output comes back.",
              code="Luau code")
    def run_luau(code: str) -> str:
        return _call("run", {"code": code}, timeout=120)

    @srv.tool("Recent Studio Output window lines (prints, warnings, errors).", count="how many lines")
    def output(count: int = 40, clear: bool = False) -> str:
        return _call("logs", {"count": count, "clear": clear})

    @srv.tool("Paths of what the user has selected in Studio.")
    def selection() -> str:
        return _call("selection", {})

    @srv.tool("Build a whole obby place file (.rbxlx) from an obby plan JSON — works without Studio.",
              spec="obby plan object (kind obby)", plan="or a plan .json path")
    def build_obby(spec: dict = None, plan: str = "") -> str:
        import engines
        return engines.roblox_build_obby(plan_arg(plan, spec))

    @srv.tool("Open Roblox Studio, optionally with a .rbxl/.rbxlx place.")
    def open_studio(place: str = "") -> str:
        import apps
        return apps.roblox_open(place)

    @srv.tool("Static-check Luau files with luau-analyze / selene.", path="file or folder in the workspace")
    def lint(path: str) -> str:
        import apps
        return apps.luau_check(path)

    @srv.tool("Rojo CLI: 'init', 'build -o game.rbxlx', 'serve'.", args="rojo arguments")
    def rojo(args: str) -> str:
        import apps
        return apps.rojo(args)

    @srv.tool("Read an official Roblox docs page (cached offline); no page = the index.")
    def docs(page: str = "") -> str:
        import apps
        return apps.fetch_docs("roblox", page) if page else apps.docs_index("roblox")

    return srv
