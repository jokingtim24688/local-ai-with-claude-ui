---
name: blender-python
description: Blender 4.x/5.x Python (bpy) — build 3D models by script, materials, modifiers, export glb/fbx/obj, headless runs.
---

# blender-python  (full docs: fetch_docs("blender", "<key>"), keys via docs_index("blender"))

## Run headless (MAIN runs it with blender_run)
blender -b [scene.blend] --python-exit-code 1 --python make.py -- --out rock.glb
Script args come after `--`:  argv = sys.argv[sys.argv.index("--") + 1:]
Start clean:  bpy.ops.wm.read_factory_settings(use_empty=True)
Background mode has NO 3D viewport: prefer bpy.data over bpy.ops; view3d.* ops fail.

## Mesh from data (fastest, no context needed)
import bpy, bmesh, math
from mathutils import Vector
mesh = bpy.data.meshes.new("CrateMesh")
mesh.from_pydata(verts, [], faces)      # verts=[(x,y,z)], faces=[(0,1,2,3), ...]
mesh.update()
obj = bpy.data.objects.new("Crate", mesh)
bpy.context.scene.collection.objects.link(obj)
# bmesh primitives (3.0+ uses radius, not diameter)
bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
bm.to_mesh(mesh); bm.free()
# primitive ops also work headless:
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.5, depth=2, location=(0, 0, 1))
cyl = bpy.context.active_object

## Transform
obj.location = (0, 0, 1); obj.rotation_euler = (math.radians(90), 0, 0); obj.scale = (1, 1, 2)
bpy.context.view_layer.update()        # before reading obj.matrix_world
Units: 1 Blender unit = 1 m, Z up.  Unreal = cm (FBX/glTF import converts). Roblox = studs (rescale in 3D Importer).

## Modifiers (keep live; glTF export applies them with export_apply=True)
m = obj.modifiers.new("Bevel", "BEVEL"); m.width = 0.03; m.segments = 3
s = obj.modifiers.new("Smooth", "SUBSURF"); s.levels = 2; s.render_levels = 2
Apply for real: bpy.context.view_layer.objects.active = obj; bpy.ops.object.modifier_apply(modifier="Bevel")
Shade smooth w/o ops: for p in mesh.polygons: p.use_smooth = True

## Material (Principled BSDF)
mat = bpy.data.materials.new("Wood"); mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.45, 0.28, 0.12, 1.0)   # RGBA 0-1 linear
bsdf.inputs["Roughness"].default_value = 0.6; bsdf.inputs["Metallic"].default_value = 0.0
obj.data.materials.append(mat)
4.0+ socket names: "Emission Color", "Emission Strength", "Specular IOR Level",
"Transmission Weight", "Subsurface Weight", "Coat Weight" (old names raise KeyError).

## Export / save
bpy.ops.export_scene.gltf(filepath="out/rock.glb", export_format='GLB', export_apply=True)
bpy.ops.export_scene.fbx(filepath="out/rock.fbx", apply_scale_options='FBX_SCALE_ALL')
bpy.ops.wm.obj_export(filepath="out/rock.obj")          # 3.2+ (old export_scene.obj is gone in 4.x)
bpy.ops.wm.stl_export(filepath="out/rock.stl")          # 4.1+
bpy.ops.wm.save_as_mainfile(filepath="out/rock.blend")
Selection-only export: use_selection=True (select with obj.select_set(True)).

## Render a preview headless
sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 32
sc.render.resolution_x, sc.render.resolution_y = 800, 600
sc.render.filepath = "//preview.png"; bpy.ops.render.render(write_still=True)
(needs a camera: cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); link it; sc.camera = cam)
EEVEE engine id: 'BLENDER_EEVEE_NEXT' in 4.2–4.5, 'BLENDER_EEVEE' in 5.x.

## Game-ready checklist
Apply scale (or export_apply), origin at the base, real-world size, <20k tris per mesh for Roblox,
name objects clearly, one material per surface type, UVs: bpy.ops.uv.smart_project() needs edit mode
(bpy.context.view_layer.objects.active = obj; bpy.ops.object.mode_set(mode='EDIT');
bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.uv.smart_project(); bpy.ops.object.mode_set(mode='OBJECT')).
