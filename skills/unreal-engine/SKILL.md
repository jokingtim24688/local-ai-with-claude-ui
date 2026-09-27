---
name: unreal-engine
description: Unreal Engine 5 — editor Python automation, C++ gameplay classes, asset import, building and packaging.
domain: unreal
triggers: unreal, ue5, unreal engine, blueprint, c++ class, actor, uproject, uat, package game, editor python
---

# unreal-engine  (full docs: fetch_docs("unreal", "<key>"), keys via docs_index("unreal"))

## Editor Python (MAIN runs it with unreal_run_python)
Project needs plugins enabled (.uproject "Plugins"):
  {"Name": "PythonScriptPlugin", "Enabled": true}, {"Name": "EditorScriptingUtilities", "Enabled": true}
Headless: UnrealEditor-Cmd <Proj>.uproject -run=pythonscript -script="C:/abs/script.py"
In a running editor: Output Log -> Python, or -ExecutePythonScript="script.py" at launch.
Close the editor first if the script saves assets (package locks).

import unreal
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
les.load_level("/Game/Maps/Main")
mesh = unreal.EditorAssetLibrary.load_asset("/Game/Meshes/Rock")
a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 100), unreal.Rotator(0, 0, 0))
a.static_mesh_component.set_static_mesh(mesh)
a.set_actor_label("Rock_01")
les.save_current_level()
unreal.log("done")  # also unreal.log_warning / unreal.log_error; print() -> LogPython

Properties: obj.set_editor_property("cast_shadow", True); obj.get_editor_property("...")
Find actors: eas.get_all_level_actors(); unreal.EditorAssetLibrary.list_assets("/Game/Meshes")
Paths: "/Game/..." = the Content folder. Units: centimeters, Z up, X forward.

## Import FBX / glTF made in Blender
t = unreal.AssetImportTask()
t.filename = "C:/abs/out/rock.fbx"; t.destination_path = "/Game/Meshes"
t.automated = True; t.replace_existing = True; t.save = True
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
print(t.imported_object_paths)

## New Blueprint asset (logic belongs in C++ or the BP graph; Python can't draw graphs)
f = unreal.BlueprintFactory(); f.set_editor_property("parent_class", unreal.Actor)
bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset("BP_Door", "/Game/Blueprints", None, f)
unreal.EditorAssetLibrary.save_loaded_asset(bp)

## C++ gameplay class (Source/<Module>/Spinner.h + .cpp)
#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Spinner.generated.h"          // must be the LAST include
UCLASS()
class MYGAME_API ASpinner : public AActor  // MYGAME = module name in caps
{
    GENERATED_BODY()
public:
    ASpinner();
    virtual void Tick(float DeltaSeconds) override;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Spin")
    float DegreesPerSecond = 90.f;
    UFUNCTION(BlueprintCallable, Category = "Spin")
    void Reverse() { DegreesPerSecond = -DegreesPerSecond; }
};
// .cpp
#include "Spinner.h"
ASpinner::ASpinner() { PrimaryActorTick.bCanEverTick = true; }
void ASpinner::Tick(float Dt) { Super::Tick(Dt); AddActorLocalRotation(FRotator(0.f, DegreesPerSecond * Dt, 0.f)); }

Rules: UObject pointers need UPROPERTY() (GC); never `new` a UObject — NewObject<T>(),
CreateDefaultSubobject<T>() in constructors only, GetWorld()->SpawnActor<T>() at runtime.
Module deps in <Module>.Build.cs: PublicDependencyModuleNames.AddRange(new string[]
{ "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput" });
Header changes need a full rebuild (close editor); .cpp-only changes: Live Coding (Ctrl+Alt+F11).

## Build / package from the command line
Compile editor target:
  Win: Engine/Build/BatchFiles/Build.bat MyGameEditor Win64 Development -Project="C:/P/MyGame.uproject" -WaitMutex
  Mac: Engine/Build/BatchFiles/Mac/Build.sh MyGameEditor Mac Development -Project="/P/MyGame.uproject"
Package (MAIN runs with unreal_uat):
  BuildCookRun -project="C:/P/MyGame.uproject" -noP4 -platform=Win64 -clientconfig=Shipping
  -build -cook -stage -pak -archive -archivedirectory="C:/Builds"     (Mac: -platform=Mac)
