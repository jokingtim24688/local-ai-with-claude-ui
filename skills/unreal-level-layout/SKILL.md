---
name: unreal-level-layout
description: Unreal Engine 5 level layout — rooms, walls, doors, props, lights from a JSON plan; small editor-Python edits.
domain: unreal
triggers: unreal, ue5, ue, unreal engine, level, layout, arena, dungeon, rooms, room, corridor, blockout, greybox, gray box, player start, uproject
---
# Unreal Engine Level Layout skill

OUTPUT A (preferred) — describe the level as a plan; the app builds it:
```plan file=plans/<name>.json run
{"kind":"ue_layout","level":"Arena","template":"blank",
 "floor":{"size":[6000,6000]},
 "rooms":[{"name":"Spawn","pos":[0,0],"size":[1200,1200],"wall_height":400,"doors":["north"]},
          {"name":"Hall","pos":[0,2000],"size":[800,2400],"wall_height":500,"doors":["south","north"]}],
 "props":[{"mesh":"/Engine/BasicShapes/Cube","pos":[300,200,50],"scale":[1,1,1],"rot":[0,0,45]},
          {"mesh":"/Engine/BasicShapes/Cylinder","pos":[-300,-200,100],"scale":[1,1,2]}],
 "lights":[{"pos":[0,0,350],"intensity":5000}],
 "player_start":[0,0,120]}
```
- Units: centimeters (100 = 1 m). +X forward, +Y right, Z up. Room pos = its center.
- doors: north (+Y) south (-Y) east (+X) west (-X); each makes a 2 m doorway.
- template: blank | thirdperson | firstperson | topdown (new project when none is open).
- meshes: /Engine/BasicShapes/Cube Sphere Cylinder Cone Plane (Cube is 100 cm, scale 2 = 2 m).
- Sun, sky, fog and saving are added automatically. Keep rooms from overlapping.

OUTPUT B — a small change to an existing level, editor Python:
```ue-python file=scripts/<name>.py run project=<path to .uproject>
```
ONLY THESE:
import unreal
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
les.load_level("/Game/Maps/Arena")   les.save_current_level()
a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x, y, z), unreal.Rotator(roll=0.0, pitch=0.0, yaw=90.0))
a.static_mesh_component.set_static_mesh(unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube"))
a.set_actor_scale3d(unreal.Vector(2, 2, 1))   a.set_actor_label("Crate")
eas.get_all_level_actors()   a.get_actor_label()   eas.destroy_actor(a)
unreal.PointLight / unreal.SpotLight / unreal.PlayerStart with spawn_actor_from_class
Always end with les.save_current_level(). Don't invent other functions.
