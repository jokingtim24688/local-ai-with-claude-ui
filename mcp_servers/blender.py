"""nightcrew-blender: drives the OPEN Blender (Night Crew Bridge add-on) when it is running,
otherwise works headless on a .blend in the workspace (default models/scene.blend), so every
tool works with Blender closed too. Structured tools for small models; run_python for the rest.
Every live change is one undo step."""
from __future__ import annotations

import json
import os
import time

from mcp_servers.core import Server, color, setup_workspace, vec

DEFAULT_BLEND = "models/scene.blend"

PRE = r'''
import bpy, json, math, contextlib
def _ctx():
    wm = bpy.context.window_manager
    if wm and wm.windows and hasattr(bpy.context, "temp_override"):
        w = wm.windows[0]
        return bpy.context.temp_override(window=w, screen=w.screen)
    return contextlib.nullcontext()
def _obj(name):
    o = bpy.data.objects.get(name)
    if o is None:
        raise ValueError("no object %r. Objects: %s" % (name, ", ".join(x.name for x in bpy.data.objects)[:400]))
    return o
def _out(d):
    print("NC_JSON:" + json.dumps(d, default=str))
'''

SCENE = r'''
objs = []
for o in bpy.context.scene.objects:
    e = {"name": o.name, "type": o.type, "loc": [round(v, 3) for v in o.location]}
    if any(abs(v) > 1e-4 for v in o.rotation_euler):
        e["rot"] = [round(math.degrees(v), 1) for v in o.rotation_euler]
    if any(abs(v - 1) > 1e-4 for v in o.scale):
        e["scale"] = [round(v, 3) for v in o.scale]
    if o.type == "MESH":
        e["dims"] = [round(v, 3) for v in o.dimensions]
        e["verts"] = len(o.data.vertices)
        mats = [m.name for m in o.data.materials if m]
        if mats: e["mats"] = mats
    if o.modifiers: e["mods"] = [m.type.lower() for m in o.modifiers]
    if o.parent: e["parent"] = o.parent.name
    if o.hide_viewport or o.hide_get(): e["hidden"] = True
    objs.append(e)
s = bpy.context.scene
_out({"file": bpy.data.filepath or "(unsaved)", "scene": s.name, "frame": s.frame_current,
      "engine": s.render.engine, "count": len(objs), "objects": objs[:150],
      "materials": [m.name for m in bpy.data.materials][:60]})
'''

KINDS = {"cube": "mesh.primitive_cube_add", "sphere": "mesh.primitive_uv_sphere_add",
         "icosphere": "mesh.primitive_ico_sphere_add", "cylinder": "mesh.primitive_cylinder_add",
         "cone": "mesh.primitive_cone_add", "plane": "mesh.primitive_plane_add",
         "torus": "mesh.primitive_torus_add", "monkey": "mesh.primitive_monkey_add",
         "circle": "mesh.primitive_circle_add", "grid": "mesh.primitive_grid_add",
         "empty": "object.empty_add", "camera": "object.camera_add", "text": "object.text_add",
         "point_light": "object.light_add:POINT", "sun": "object.light_add:SUN",
         "spot_light": "object.light_add:SPOT", "area_light": "object.light_add:AREA"}

MODS = {"subdivision": "SUBSURF", "subsurf": "SUBSURF", "bevel": "BEVEL", "array": "ARRAY",
        "mirror": "MIRROR", "solidify": "SOLIDIFY", "decimate": "DECIMATE", "boolean": "BOOLEAN",
        "wireframe": "WIREFRAME", "remesh": "REMESH", "smooth": "SMOOTH", "screw": "SCREW",
        "displace": "DISPLACE", "weld": "WELD", "triangulate": "TRIANGULATE"}


def _abs(rel: str) -> str:
    import tools
    return rel if os.path.isabs(rel) else str(tools._jail(rel))


def _run(code: str, blend: str = "", save: bool = True, timeout: int = 600) -> tuple[bool, str, str]:
    """(ok, output, where). Live Blender if the add-on answers, else headless on `blend`."""
    import apps
    import live
    code = PRE + code
    if live.blender_live():
        ok, out = live.blender_exec(code, timeout)
        return ok, out, "live Blender"
    blend = blend or DEFAULT_BLEND
    path = _abs(blend)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    have = os.path.isfile(path)
    out = apps.blender_run(code=code, blend=blend if have else "", save_as=blend if save else "",
                           timeout=timeout)
    return out.startswith("exit=0"), out, f"headless {blend}" + ("" if have or save else " (new, not saved)")


def _json(out: str):
    for line in reversed(out.splitlines()):
        if line.startswith("NC_JSON:"):
            return json.loads(line[8:])
    return None


def _result(ok: bool, out: str, where: str, okmsg: str = "") -> str:
    data = _json(out)
    if not ok:
        return f"error ({where}):\n" + out[-3000:]
    return f"OK ({where}) " + (okmsg or "") + ("\n" + json.dumps(data) if data is not None else "")


def build() -> Server:
    setup_workspace()
    srv = Server("blender", "Blender tools. If Blender is open with the Night Crew Bridge add-on they "
                 "change the open scene (Ctrl+Z undoes); otherwise they edit a .blend in the workspace "
                 "(default models/scene.blend) headless. Start with `scene` to see what exists. "
                 "Coordinates are meters, rotations degrees, colors '#rrggbb' or names.")

    @srv.tool("Is Blender running with the bridge? Which Blender is installed?")
    def status() -> str:
        import apps
        import live
        return json.dumps({"live": live.blender_live(), "blender": apps.find_blender(),
                           "default_blend": DEFAULT_BLEND})

    @srv.tool("List the objects in the scene (type, location, size, materials, modifiers).",
              blend="headless only: .blend file to read (default models/scene.blend)")
    def scene(blend: str = "") -> str:
        ok, out, where = _run(SCENE, blend, save=False)
        return _result(ok, out, where)

    @srv.tool("Add an object: cube, sphere, icosphere, cylinder, cone, plane, torus, monkey, circle, "
              "grid, empty, camera, text, point_light, sun, spot_light, area_light.",
              kind="object kind", name="new object's name", location="[x,y,z] meters",
              rotation="[x,y,z] degrees", scale="[x,y,z] or one number", color="'#rrggbb' or a color name",
              size="base size in meters (default 2 for cube/plane)", text="body text for kind=text")
    def add_object(kind: str, name: str = "", location: list = None, rotation: list = None,
                   scale: list = None, color: str = "", size: float = 0, text: str = "",
                   blend: str = "") -> str:
        op = KINDS.get(kind.strip().lower().replace(" ", "_"))
        if not op:
            return "error: unknown kind. Use one of: " + ", ".join(KINDS)
        op, _, light = op.partition(":")
        kw = [f"location={vec(location)!r}",
              f"rotation={[round(v * 3.14159265 / 180, 6) for v in vec(rotation)]!r}"]
        if light:
            kw.append(f"type={light!r}")
        if size and op.startswith("mesh.") and "torus" not in op:
            kw.append(f"size={float(size)!r}" if op.endswith(("cube_add", "plane_add", "grid_add"))
                      else f"radius={float(size) / 2!r}")
        code = f"with _ctx():\n    bpy.ops.{op}({', '.join(kw)})\no = bpy.context.active_object\n"
        if name:
            code += f"o.name = {json.dumps(name)}\n"
        if scale not in (None, "", []):
            code += f"o.scale = {vec(scale, 3, 1.0)!r}\n"
        if text and kind == "text":
            code += f"o.data.body = {json.dumps(text)}\n"
        if color:
            code += _mat_code(f"{name or kind}_mat", color, 0.0, 0.5, "", 0.0)
        code += "_out({'created': o.name, 'loc': list(o.location), 'dims': list(o.dimensions)})\n"
        ok, out, where = _run(code, blend)
        return _result(ok, out, where)

    @srv.tool("Move / rotate / scale an object. Only the values you give change.",
              name="object name", location="[x,y,z]", rotation="[x,y,z] degrees", scale="[x,y,z] or one number")
    def transform(name: str, location: list = None, rotation: list = None, scale: list = None,
                  blend: str = "") -> str:
        code = f"o = _obj({json.dumps(name)})\n"
        if location not in (None, "", []):
            code += f"o.location = {vec(location)!r}\n"
        if rotation not in (None, "", []):
            code += f"o.rotation_euler = {[v * 3.14159265 / 180 for v in vec(rotation)]!r}\n"
        if scale not in (None, "", []):
            code += f"o.scale = {vec(scale, 3, 1.0)!r}\n"
        code += "_out({'name': o.name, 'loc': list(o.location), 'dims': list(o.dimensions)})\n"
        return _result(*_run(code, blend))

    @srv.tool("Give an object a material (Principled BSDF). Creates or reuses the material by name.",
              name="object name", color="'#rrggbb', a color name or [r,g,b]", metallic="0..1",
              roughness="0..1", material="material name (default <object>_mat)",
              emission="glow color (optional)", emission_strength="glow strength, e.g. 5")
    def set_material(name: str, color: str = "#cccccc", metallic: float = 0.0, roughness: float = 0.5,
                     material: str = "", emission: str = "", emission_strength: float = 0.0,
                     blend: str = "") -> str:
        code = f"o = _obj({json.dumps(name)})\n" + _mat_code(material or f"{name}_mat", color, metallic,
                                                            roughness, emission, emission_strength)
        code += "_out({'object': o.name, 'material': m.name})\n"
        return _result(*_run(code, blend))

    @srv.tool("Add a modifier: subdivision, bevel, array, mirror, solidify, decimate, boolean, "
              "wireframe, remesh, smooth, screw, displace, weld, triangulate. settings = its fields, "
              "e.g. {\"levels\":2} or {\"count\":5,\"relative_offset_displace\":[1.2,0,0]} or "
              "{\"object\":\"Cutter\",\"operation\":\"DIFFERENCE\"}. apply=true bakes it into the mesh.",
              name="object name", modifier="modifier kind", settings="modifier fields")
    def add_modifier(name: str, modifier: str, settings: dict = None, apply: bool = False,
                     blend: str = "") -> str:
        t = MODS.get(modifier.lower(), modifier.upper())
        code = (f"o = _obj({json.dumps(name)})\nmd = o.modifiers.new(name={json.dumps(modifier.title())}, type={t!r})\n"
                f"for k, v in json.loads({json.dumps(json.dumps(settings or {}))}).items():\n"
                "    if k == 'object': v = _obj(v)\n"
                "    if not hasattr(md, k): raise ValueError('modifier has no setting %r' % k)\n"
                "    setattr(md, k, v)\n")
        if apply:
            code += ("bpy.context.view_layer.objects.active = o\n"
                     "with _ctx():\n    bpy.ops.object.modifier_apply(modifier=md.name)\n")
        code += "_out({'object': o.name, 'modifiers': [m.name for m in o.modifiers], 'verts': len(o.data.vertices) if o.type == 'MESH' else 0})\n"
        return _result(*_run(code, blend))

    @srv.tool("Delete objects by name.", names="list of object names")
    def delete(names: list, blend: str = "") -> str:
        code = (f"gone = []\nfor n in {json.dumps(list(names) if not isinstance(names, str) else [names])}:\n"
                "    o = _obj(n); gone.append(o.name); bpy.data.objects.remove(o, do_unlink=True)\n"
                "_out({'deleted': gone})\n")
        return _result(*_run(code, blend))

    @srv.tool("Run any Blender Python (bpy). print() output comes back. Use for anything the "
              "other tools don't cover (geometry nodes, animation, rigging, bmesh).",
              code="bpy code", blend="headless only: .blend to edit (default models/scene.blend)",
              save="headless only: save the .blend afterwards (default true)")
    def run_python(code: str, blend: str = "", save: bool = True) -> str:
        ok, out, where = _run(code, blend, save=save)
        return (f"OK ({where})\n" if ok else f"error ({where}):\n") + out[-6000:]

    @srv.tool("Picture of the scene as PNG (live: the viewport; headless: a quick render, adding a "
              "temporary camera if there is none). Returns the file path.",
              out="PNG path in the workspace (default renders/blender_<time>.png)")
    def screenshot(out: str = "", blend: str = ""):
        rel = out or f"renders/blender_{int(time.time())}.png"
        path = _abs(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        import live
        if live.blender_live():
            code = (f"path = {path!r}\ns = bpy.context.scene\nold = s.render.filepath\n"
                    "win = bpy.context.window_manager.windows[0]\n"
                    "area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None)\n"
                    "if area is None: raise ValueError('no 3D viewport open')\n"
                    "region = next(r for r in area.regions if r.type == 'WINDOW')\n"
                    "s.render.filepath = path\n"
                    "with bpy.context.temp_override(window=win, area=area, region=region):\n"
                    "    bpy.ops.render.opengl(write_still=True)\n"
                    "s.render.filepath = old\n_out({'png': path})\n")
            ok, o, where = _run(code)
        else:
            code = (f"path = {path!r}\nfrom mathutils import Vector\ns = bpy.context.scene\n"
                    "ms = [o for o in s.objects if o.type in ('MESH','CURVE','FONT')]\n"
                    "if not s.camera:\n"
                    "    pts = [o.matrix_world @ Vector(c) for o in ms for c in o.bound_box] or [Vector((0,0,0))]\n"
                    "    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])\n"
                    "    c = (lo + hi) / 2; r = max((hi - lo).length, 1.0)\n"
                    "    cam = bpy.data.objects.new('NC_Cam', bpy.data.cameras.new('NC_Cam')); s.collection.objects.link(cam)\n"
                    "    cam.location = c + Vector((r, -r, r * 0.8))\n"
                    "    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler(); s.camera = cam\n"
                    "s.render.engine = 'BLENDER_WORKBENCH'\ns.render.resolution_x, s.render.resolution_y = 960, 540\n"
                    "s.render.resolution_percentage = 100\ns.render.image_settings.file_format = 'PNG'\n"
                    "s.render.filepath = path\nbpy.ops.render.render(write_still=True)\n_out({'png': path})\n")
            ok, o, where = _run(code, blend, save=False)
        if not ok or not os.path.isfile(path):
            return f"error ({where}): no image\n" + o[-2500:]
        return f"OK ({where}) {rel}", path

    @srv.tool("Export the scene (or listed objects) to glb, gltf, fbx, obj, stl or usd.",
              path="output file in the workspace, e.g. exports/ship.glb", objects="only these object names (optional)")
    def export(path: str, objects: list = None, blend: str = "") -> str:
        full = _abs(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        ext = os.path.splitext(full)[1].lower().lstrip(".")
        sel = json.dumps(list(objects or []))
        calls = {
            "glb": ["bpy.ops.export_scene.gltf(filepath=P, export_format='GLB', use_selection=SEL)"],
            "gltf": ["bpy.ops.export_scene.gltf(filepath=P, export_format='GLTF_SEPARATE', use_selection=SEL)"],
            "fbx": ["bpy.ops.export_scene.fbx(filepath=P, use_selection=SEL)"],
            "obj": ["bpy.ops.wm.obj_export(filepath=P, export_selected_objects=SEL)",
                    "bpy.ops.export_scene.obj(filepath=P, use_selection=SEL)"],
            "stl": ["bpy.ops.wm.stl_export(filepath=P, export_selected_objects=SEL)",
                    "bpy.ops.export_mesh.stl(filepath=P, use_selection=SEL)"],
            "usd": ["bpy.ops.wm.usd_export(filepath=P, selected_objects_only=SEL)"],
            "usdc": ["bpy.ops.wm.usd_export(filepath=P, selected_objects_only=SEL)"],
        }.get(ext)
        if not calls:
            return "error: use .glb .gltf .fbx .obj .stl or .usd"
        code = (f"P = {full!r}\nnames = {sel}\nSEL = bool(names)\n"
                "if SEL:\n    for o in bpy.data.objects: o.select_set(o.name in names)\n"
                "err = None\n")
        for c in calls:
            code += f"if err is not False:\n    try:\n        with _ctx():\n            {c}\n        err = False\n    except Exception as e:\n        err = e\n"
        code += "if err: raise err\n_out({'exported': P})\n"
        ok, out, where = _run(code, blend, save=False)
        if ok and os.path.isfile(full):
            return f"OK ({where}) {path} ({os.path.getsize(full) // 1024} KB)"
        return f"error ({where}):\n" + out[-3000:]

    @srv.tool("Save the live scene (live) or copy the headless .blend to a new path.",
              path="where to save, e.g. models/ship.blend (live: default = its current file)")
    def save(path: str = "", blend: str = "") -> str:
        target = _abs(path) if path else ""
        code = (f"t = {target!r} or bpy.data.filepath\nif not t: raise ValueError('give a path')\n"
                "bpy.ops.wm.save_as_mainfile(filepath=t, copy=False)\n_out({'saved': t})\n")
        return _result(*_run(code, blend, save=False))

    @srv.tool("Open a .blend (or the default scene file) in Blender's window for the user.")
    def open_in_blender(blend: str = "") -> str:
        import apps
        return apps.blender_open(blend or (DEFAULT_BLEND if os.path.isfile(_abs(DEFAULT_BLEND)) else ""))

    @srv.tool("Read an official Blender Python API docs page (cached offline). page = key from "
              "docs_index('blender') or an official URL.")
    def docs(page: str = "") -> str:
        import apps
        return apps.fetch_docs("blender", page) if page else apps.docs_index("blender")

    return srv


def _mat_code(mat: str, col, metallic: float, roughness: float, emission: str, strength: float) -> str:
    rgb = color(col)
    code = (f"m = bpy.data.materials.get({json.dumps(mat)}) or bpy.data.materials.new({json.dumps(mat)})\n"
            "m.use_nodes = True\nb = m.node_tree.nodes.get('Principled BSDF')\n"
            f"m.diffuse_color = ({rgb[0]}, {rgb[1]}, {rgb[2]}, 1)\n"
            "if b:\n"
            f"    b.inputs['Base Color'].default_value = ({rgb[0]}, {rgb[1]}, {rgb[2]}, 1)\n"
            f"    b.inputs['Metallic'].default_value = {float(metallic)}\n"
            f"    b.inputs['Roughness'].default_value = {float(roughness)}\n")
    if emission:
        e = color(emission)
        code += ("    k = 'Emission Color' if 'Emission Color' in b.inputs else 'Emission'\n"
                 f"    b.inputs[k].default_value = ({e[0]}, {e[1]}, {e[2]}, 1)\n"
                 f"    b.inputs['Emission Strength'].default_value = {float(strength or 1)}\n")
    code += ("if o.type in ('MESH', 'CURVE', 'FONT', 'SURFACE', 'META'):\n"
             "    (o.data.materials.__setitem__(0, m) if o.data.materials else o.data.materials.append(m))\n")
    return code
