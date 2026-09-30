"""nightcrew-unreal: drives the OPEN Unreal Editor through the Remote Control API (live,
undoable transactions), or runs editor Python headless on a .uproject when the editor is
closed. Units: centimeters; rotation [roll, pitch, yaw] degrees."""
from __future__ import annotations

import json
import os
import time

from mcp_servers.core import Server, color, plan_arg, setup_workspace, vec

PRE = r'''
import unreal, json
def _out(d):
    print("NC_JSON:" + json.dumps(d, default=str))
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def _actor(label):
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    raise ValueError("no actor %r. Some actors: %s" % (label, ", ".join(a.get_actor_label() for a in EAS.get_all_level_actors()[:40])))
'''

LEVEL = r'''
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
acts = []
for a in EAS.get_all_level_actors():
    l = a.get_actor_location()
    e = {"label": a.get_actor_label(), "class": a.get_class().get_name(), "loc": [round(l.x), round(l.y), round(l.z)]}
    r = a.get_actor_rotation()
    if abs(r.roll) + abs(r.pitch) + abs(r.yaw) > 0.01:
        e["rot"] = [round(r.roll, 1), round(r.pitch, 1), round(r.yaw, 1)]
    s = a.get_actor_scale3d()
    if abs(s.x - 1) + abs(s.y - 1) + abs(s.z - 1) > 0.001:
        e["scale"] = [round(s.x, 3), round(s.y, 3), round(s.z, 3)]
    if isinstance(a, unreal.StaticMeshActor):
        m = a.static_mesh_component.static_mesh
        e["mesh"] = m.get_path_name() if m else None
    acts.append(e)
_out({"level": world.get_path_name() if world else None, "count": len(acts), "actors": acts[:200]})
'''

SHAPES = {"cube": "/Engine/BasicShapes/Cube.Cube", "sphere": "/Engine/BasicShapes/Sphere.Sphere",
          "cylinder": "/Engine/BasicShapes/Cylinder.Cylinder", "cone": "/Engine/BasicShapes/Cone.Cone",
          "plane": "/Engine/BasicShapes/Plane.Plane"}
CLASSES = {"point_light": "PointLight", "spot_light": "SpotLight", "directional_light": "DirectionalLight",
           "sun": "DirectionalLight", "sky_light": "SkyLight", "sky_atmosphere": "SkyAtmosphere",
           "fog": "ExponentialHeightFog", "player_start": "PlayerStart", "camera": "CameraActor",
           "text": "TextRenderActor", "trigger_box": "TriggerBox", "post_process": "PostProcessVolume"}


def _run(code: str, project: str = "", timeout: int = 900) -> tuple[bool, str, str]:
    import apps
    import live
    import tools
    code = PRE + code
    if live.unreal_live():
        ok, out = live.unreal_exec(code, timeout)
        return ok, out, "live editor"
    if not project:
        return False, ("Unreal isn't open with Remote Control. Use open_editor(project) (after "
                       "enable_live once), or pass project= to run headless."), "no editor"
    rel = f"scripts/nc_ue_{int(time.time() * 1000)}.py"
    tools.write_file(rel, code)
    out = apps.unreal_run_python(rel, project, timeout)
    return ("NC_JSON:" in out or "exit=0" in out) and "Traceback" not in out, out, f"headless {project}"


def _result(ok: bool, out: str, where: str) -> str:
    data = None
    for line in reversed(out.splitlines()):
        i = line.find("NC_JSON:")
        if i >= 0:
            data = line[i + 8:]
            break
    if not ok:
        return f"error ({where}):\n" + out[-3000:]
    return f"OK ({where})" + (f"\n{data}" if data else "")


def build() -> Server:
    setup_workspace()
    srv = Server("unreal", "Unreal Engine 5 tools. Live (editor open with Remote Control) changes are "
                 "undoable; call `level` first to see actors. Units cm, rotation [roll,pitch,yaw]. "
                 "First time on a project: enable_live(project) then open_editor(project).")

    @srv.tool("Editor reachable? Engine installed? Which projects exist?")
    def status() -> str:
        import apps
        import live
        return json.dumps({"live": live.unreal_live(), "engine": apps.find_unreal(),
                           "editor": apps.find_unreal(gui=True)})

    @srv.tool("List actors in the open level (label, class, location, mesh).",
              project="headless only: .uproject path")
    def level(project: str = "") -> str:
        return _result(*_run(LEVEL, project))

    @srv.tool("Spawn an actor: cube, sphere, cylinder, cone, plane, point_light, spot_light, sun, sky_light, "
              "sky_atmosphere, fog, player_start, camera, text, trigger_box, post_process — or an asset path "
              "like /Game/Props/SM_Crate.",
              kind="what to spawn", label="actor label", location="[x,y,z] cm", rotation="[roll,pitch,yaw]",
              scale="[x,y,z] or one number (1 = 100 cm for shapes)", color="'#rrggbb' for shapes")
    def spawn(kind: str, label: str = "", location: list = None, rotation: list = None, scale: list = None,
              color: str = "", project: str = "") -> str:
        k = kind.strip().lower().replace(" ", "_")
        l, r = vec(location), vec(rotation)
        code = f"loc = unreal.Vector({l[0]}, {l[1]}, {l[2]})\nrot = unreal.Rotator(roll={r[0]}, pitch={r[1]}, yaw={r[2]})\n"
        if k in SHAPES or kind.startswith("/"):
            path = SHAPES.get(k, kind)
            code += (f"asset = unreal.load_asset({json.dumps(path)})\n"
                     f"if asset is None: raise ValueError('asset not found: ' + {json.dumps(path)})\n"
                     "a = EAS.spawn_actor_from_object(asset, loc, rot)\n")
        elif k in CLASSES:
            code += f"a = EAS.spawn_actor_from_class(unreal.{CLASSES[k]}, loc, rot)\n"
        else:
            return "error: unknown kind. Use: " + ", ".join(list(SHAPES) + list(CLASSES)) + " or /Game/... asset path"
        if label:
            code += f"a.set_actor_label({json.dumps(label)})\n"
        if scale not in (None, "", []):
            s = vec(scale, 3, 1.0)
            code += f"a.set_actor_scale3d(unreal.Vector({s[0]}, {s[1]}, {s[2]}))\n"
        if color and k in SHAPES:
            code += _color_code(label or k, color)
        code += "_out({'spawned': a.get_actor_label(), 'class': a.get_class().get_name()})\n"
        return _result(*_run(code, project))

    @srv.tool("Move / rotate / scale an actor by label. Only the values you give change.",
              label="actor label", location="[x,y,z] cm", rotation="[roll,pitch,yaw]", scale="[x,y,z]")
    def transform(label: str, location: list = None, rotation: list = None, scale: list = None,
                  project: str = "") -> str:
        code = f"a = _actor({json.dumps(label)})\n"
        if location not in (None, "", []):
            l = vec(location)
            code += f"a.set_actor_location(unreal.Vector({l[0]}, {l[1]}, {l[2]}), False, False)\n"
        if rotation not in (None, "", []):
            r = vec(rotation)
            code += f"a.set_actor_rotation(unreal.Rotator(roll={r[0]}, pitch={r[1]}, yaw={r[2]}), False)\n"
        if scale not in (None, "", []):
            s = vec(scale, 3, 1.0)
            code += f"a.set_actor_scale3d(unreal.Vector({s[0]}, {s[1]}, {s[2]}))\n"
        code += "l = a.get_actor_location()\n_out({'label': a.get_actor_label(), 'loc': [l.x, l.y, l.z]})\n"
        return _result(*_run(code, project))

    @srv.tool("Color a shape actor (makes a material instance in /Game/NightCrew).",
              label="actor label", color="'#rrggbb' or a color name")
    def set_color(label: str, color: str, project: str = "") -> str:
        code = f"a = _actor({json.dumps(label)})\n" + _color_code(label, color) + \
            "_out({'label': a.get_actor_label(), 'material': mi.get_path_name()})\n"
        return _result(*_run(code, project))

    @srv.tool("Delete actors by label.", labels="list of actor labels")
    def delete(labels: list, project: str = "") -> str:
        names = [labels] if isinstance(labels, str) else list(labels)
        code = (f"gone = []\nfor n in {json.dumps(names)}:\n"
                "    a = _actor(n); gone.append(n); EAS.destroy_actor(a)\n_out({'deleted': gone})\n")
        return _result(*_run(code, project))

    @srv.tool("Run any Unreal editor Python (import unreal). print() output comes back.",
              code="editor Python", project="headless only: .uproject path")
    def run_python(code: str, project: str = "") -> str:
        ok, out, where = _run(code, project)
        return (f"OK ({where})\n" if ok else f"error ({where}):\n") + out[-6000:]

    @srv.tool("Build a level from a ue_layout plan JSON file (floors, walls with doorways, lights, "
              "spawns). Live if the editor is open, else headless on project.",
              spec="ue_layout plan object", plan="or a plan .json path", project=".uproject (headless)")
    def layout(spec: dict = None, plan: str = "", project: str = "") -> str:
        import engines
        import live
        plan = plan_arg(plan, spec)
        if live.unreal_live():
            p = engines._load_plan(plan)
            errs = engines.validate_plan(p)
            if errs:
                return "error: plan problems:\n- " + "\n- ".join(errs)
            ok, out = live.unreal_exec(engines.ue_layout_script(p), 900)
            return ("OK (live editor)\n" if ok else "error (live editor):\n") + out[-3000:]
        return engines.unreal_apply_layout(plan, project)

    @srv.tool("Screenshot the level viewport to a PNG (live editor only).",
              width="pixels", height="pixels")
    def screenshot(width: int = 1280, height: int = 720):
        import live
        import tools
        if not live.unreal_live():
            return "error: needs the editor open (open_editor)"
        rel = f"renders/unreal_{int(time.time())}.png"
        path = str(tools._jail(rel))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ok, out, where = _run(f"unreal.AutomationLibrary.take_high_res_screenshot({int(width)}, {int(height)}, {path!r})\n_out({{'png': {path!r}}})\n")
        for _ in range(40):                                      # it is written a moment later
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return f"OK (live editor) {rel}", path
            time.sleep(0.5)
        return f"error: screenshot not written ({where}):\n" + out[-1500:]

    @srv.tool("Save the current level and Night Crew materials.")
    def save(project: str = "") -> str:
        code = ("ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()\n"
                "unreal.EditorAssetLibrary.save_directory('/Game/NightCrew', only_if_is_dirty=True)\n"
                "_out({'saved': ok})\n")
        return _result(*_run(code, project))

    @srv.tool("Create a new empty level and open it, e.g. /Game/Maps/Arena.", path="/Game/... level path")
    def new_level(path: str, project: str = "") -> str:
        code = (f"ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).new_level({json.dumps(path)})\n"
                "_out({'created': ok})\n")
        return _result(*_run(code, project))

    @srv.tool("Open an existing level, e.g. /Game/Maps/Arena.", path="/Game/... level path")
    def load_level(path: str, project: str = "") -> str:
        code = (f"ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level({json.dumps(path)})\n"
                "_out({'loaded': ok})\n")
        return _result(*_run(code, project))

    @srv.tool("New UE5 project from an engine template: blank, thirdperson, firstperson, topdown, vehicle. "
              "Python + Remote Control get enabled. location '' = workspace, 'pc' = Documents/Unreal Projects.")
    def new_project(name: str, template: str = "blank", location: str = "") -> str:
        import engines
        return engines.unreal_new_project(name, template, location)

    @srv.tool("Turn on live control for a project (Python + Remote Control plugins, web server auto-start).",
              project=".uproject path")
    def enable_live(project: str) -> str:
        import live
        return live.unreal_enable_live(project)

    @srv.tool("Open the Unreal Editor (Remote Control on) for the user, optionally on a project.")
    def open_editor(project: str = "") -> str:
        import live
        return live.unreal_open_live(project)

    @srv.tool("Package a game with RunUAT BuildCookRun.", project=".uproject", platform="Win64 / Mac / Linux",
              config="Development or Shipping", out="output folder in the workspace")
    def package(project: str, platform: str = "Win64", config: str = "Development", out: str = "Builds") -> str:
        import apps
        import engines
        return apps.unreal_uat(f'BuildCookRun -project="{apps.resolve(project)}" -noP4 -platform={platform} '
                               f'-clientconfig={config} -build -cook -stage -pak -archive '
                               f'-archivedirectory="{engines._out_dir(out)}"')

    @srv.tool("Read an official Unreal docs page (cached offline); no page = the index.")
    def docs(page: str = "") -> str:
        import apps
        return apps.fetch_docs("unreal", page) if page else apps.docs_index("unreal")

    return srv


def _color_code(label: str, col: str) -> str:
    rgb = color(col)
    safe = "".join(c if c.isalnum() else "_" for c in label)[:40] or "Shape"
    return ("tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
            f"mp = '/Game/NightCrew/MI_{safe}'\n"
            "mi = unreal.load_asset(mp) if unreal.EditorAssetLibrary.does_asset_exist(mp) else "
            f"tools.create_asset('MI_{safe}', '/Game/NightCrew', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())\n"
            "unreal.MaterialEditingLibrary.set_material_instance_parent(mi, unreal.load_asset('/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial'))\n"
            f"unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mi, 'Color', unreal.LinearColor({rgb[0]}, {rgb[1]}, {rgb[2]}, 1.0))\n"
            "a.static_mesh_component.set_material(0, mi)\n")
