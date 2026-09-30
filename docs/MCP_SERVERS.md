# Night Crew MCP servers — one per app

Five MCP servers, written for this project, that any MCP client can run:

```
"Night Crew.exe" --mcp blender|unreal|roblox|openscad|fortnite     # built app
python desktop.py --mcp blender                                    # from source
```

Inside Night Crew they are registered automatically as built-in connectors, so a chat gets
`mcp__blender__*` etc. once it mentions the app (Customize → Connectors lists them).
No MCP SDK is needed to *run* them (`mcp_servers/core.py` speaks JSON-RPC over stdio);
`pip install "mcp>=1.2,<2"` is only needed for Night Crew to act as a *client*.

## Why not the existing ones
Existing community servers wrap one app and give up when it is closed. These:
* **work live or headless** — same tool names either way, the result says which ran;
* **are written for 3B models** — flat arguments (`location: [0,0,5]`, `color: "#ff8800"`),
  one obvious tool per job, errors that name the fix;
* **return pictures** — `screenshot` sends a real MCP image, so a vision model can look;
* **are undoable** — every live change is one Ctrl+Z step;
* **share Night Crew's sandbox** — files land in the workspace the app is already using.

## The bridges (live mode)
| App | How | Install |
|---|---|---|
| Blender | add-on, TCP 127.0.0.1:9876, token from `~/.nightcrew/bridge.token`, runs on Blender's main thread | Customize → Apps → *Install Blender add-on* |
| Roblox Studio | plugin polls Night Crew's queue on 127.0.0.1:9877 (`X-NC: 1` header, token on the write side) | *Install Roblox Studio plugin*, then allow its HTTP prompt in Studio |
| Unreal | official Remote Control API on 127.0.0.1:30010 + PythonScriptLibrary | *Enable* on a `.uproject`, then open it |
All are localhost-only and token- or header-guarded. With the app closed, Blender/Unreal fall
back to headless runs and Roblox falls back to file generation (`.rbxlx`, Rojo).

## Tools (60)
* **blender** (13) status · scene · add_object · transform · set_material · add_modifier · delete ·
  run_python · screenshot · export (glb/gltf/fbx/obj/stl/usd) · save · open_in_blender · docs
* **unreal** (17) status · level · spawn · transform · set_color · delete · run_python · layout ·
  screenshot · save · new_level · load_level · new_project · enable_live · open_editor · package · docs
* **roblox** (16) status · install_plugin · explore · create · set_props · get_props · delete ·
  write_script · run_luau · output · selection · build_obby · open_studio · lint · rojo · docs
* **openscad** (5) status · parameters · render (params override, stl/3mf/off/amf + PNG) · read · docs
* **fortnite** (9) status · projects · write_verse · verse_check · island · heightmap · devices ·
  open_uefn · docs

Plan tools (`island`, `build_obby`, `layout`) take the plan inline as `spec` and save a copy to
`plans/<name>.json`, so an agent never has to write the file first.

## Verified in the cloud sandbox
Real MCP client (`connectors.py`) → 60 tools listed in 0.7 s, all schemas valid.
OpenSCAD renders with `-D` parameter overrides (stl + 3mf), unknown parameters are rejected by name.
Blender add-on protocol tested against a stand-in `bpy` (exec, tracebacks, bad token, HTTP junk).
Roblox bridge tested against a stand-in plugin (create/tree round-trip; unauthenticated
`/poll` and `/enqueue` both 403). Unreal live paths need a real editor — untested.
