---
name: fortnite-map-maker
description: Fortnite / UEFN map making — island plans (terrain, props, devices), Verse game rules with Fortnite devices.
domain: fortnite
triggers: fortnite, uefn, verse, fortnite map, fortnite island, island, creative, creative device, fortnite creative, battle royale, zone wars, box fight, tycoon, deathrun, player spawner, item spawner, mutator zone, elimination, score manager, end game device
---
# Fortnite Map Maker skill (UEFN + Verse)

TWO OUTPUT FORMATS — pick one, then one short sentence.
A) A whole island (terrain + props + rules + device checklist) -> a plan:
```plan file=plans/<name>.json run
{"kind":"island","name":"SkyIsles","size":505,"seed":7,"style":"island","terraces":4,"water":0.18,
 "props":[{"asset":"pine_tree","count":60,"min_spacing":900,"height":[0.25,0.8]},
          {"asset":"rock","count":30,"min_spacing":600}],
 "devices":[{"type":"player_spawner_device","count":8,"note":"spread on high ground"},
            {"type":"item_spawner_device","count":12}],
 "rules":{"mode":"elimination","score_to_win":10}}
```
style: island | hills | flat | canyon. size: 253, 505, 1009. max 6 prop groups, 100 each.
z_scale (default 12 = ~61 m tall, ~11 m per terrace; 20 = taller cliffs). Import the heightmap with that Z.
B) Custom game logic -> one Verse device:
```verse file=verse/<name>.verse run
```
(`run` = offline Verse check. The user builds it in UEFN: Verse > Build Verse Code.)

VERSE RULES (Verse is NOT Python/C#/Lua)
- 4-space indents, `:` opens a block. Device class: `my_thing := class(creative_device):`
- `@editable` on its own line above the field. Devices in the level are wired through @editable fields.
- `OnBegin<override>()<suspends> : void =` runs when the game starts.
- Function: `OnPressed(Agent : agent) : void =`   Constant: `Max : int = 10`
  Variable: `var Count : int = 0` then `set Count += 1`
- Compare with `=`, not-equal `<>`, logic `and` `or` `not`. Booleans: `true` `false` (type logic).
- Failable calls use `[]` and live in `if (...)`: `if (FC := Agent.GetFortCharacter[]):`
- Options: `?type`, unwrap `X?`. Strings: `"Score {Count}"`. Arrays: `array{}`, maps: `map{}`
  and `if (set Scores[Agent] = 5) {}`.
- NEVER: `==` `!=` `&&` `||` `self.` `null` `def` `function` `;` `let`
USINGS (add the ones you use)
/Fortnite.com/Devices (all *_device, SpawnProp) /Fortnite.com/Characters (fort_character)
/Fortnite.com/Game /Verse.org/Simulation (Sleep, suspends) /Verse.org/Random (GetRandomInt/Float)
/UnrealEngine.com/Temporary/Diagnostics (Print) /UnrealEngine.com/Temporary/SpatialMath (vector3, IdentityRotation)

DEVICE API — ONLY THESE
button_device: InteractedWithEvent (agent)        trigger_device: TriggeredEvent (?agent), Trigger()
mutator_zone_device: AgentEntersEvent, AgentExitsEvent (agent), Enable(), Disable()
player_spawner_device: SpawnedEvent (agent)       item_spawner_device: ItemPickedUpEvent (agent), SpawnItem()
item_granter_device: GrantItem(Agent)             score_manager_device: Activate(Agent), SetScoreAward(Value)
end_game_device: Activate(Agent)                  barrier_device / teleporter_device: Enable(), Disable(); Teleport(Agent)
Eliminations: `FC.EliminatedEvent().Subscribe(Handler)`, Handler(Result : elimination_result),
  killer = `Result.EliminatingCharacter?` then `.GetAgent[]`.
Players: `GetPlayspace().GetPlayers()`. Props: `SpawnProp(Asset, vector3{X:=0.0,Y:=0.0,Z:=0.0}, IdentityRotation())`.
Subscribe events in OnBegin: `Button.InteractedWithEvent.Subscribe(OnPressed)`

TEMPLATE — zone gives an item, button scores
```verse file=verse/arena_logic.verse run
using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

arena_logic := class(creative_device):
    @editable
    Zone : mutator_zone_device = mutator_zone_device{}
    @editable
    Granter : item_granter_device = item_granter_device{}
    @editable
    ScoreButton : button_device = button_device{}
    @editable
    ScoreManager : score_manager_device = score_manager_device{}

    OnBegin<override>()<suspends> : void =
        Zone.AgentEntersEvent.Subscribe(OnEnterZone)
        ScoreButton.InteractedWithEvent.Subscribe(OnPressed)

    OnEnterZone(Agent : agent) : void =
        Granter.GrantItem(Agent)

    OnPressed(Agent : agent) : void =
        ScoreManager.Activate(Agent)
        Print("Point scored")
```
After writing Verse, tell the user which devices to place and which @editable field each goes in.
