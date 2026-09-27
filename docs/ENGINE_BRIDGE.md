# Night Crew engine bridge — OpenSCAD · Unreal Engine 5 · UEFN · Roblox Studio

How a 3B model (`qwen2.5-coder:3b`) creates projects, 3D assets, game scripts and
whole levels across four engines, on the host PC or inside an isolated workspace.

## The core idea: small models write *text*, deterministic code does the engine work

A 3B model is bad at three things this job needs: long tool-call JSON with escaped
code inside, big unfamiliar APIs, and long prompts. So:

| Problem for a 3B model | What Night Crew does |
|---|---|
| Code inside JSON tool calls (escaping, newlines) | **Execution tags** — plain fenced blocks: ```` ```openscad file=models/gear.scad run ```` |
| Huge engine APIs it hallucinates | **Plans** — a small JSON document (`kind: ue_layout / obby / island / terrain`) that `engines.py` turns into engine calls |
| Long prompts, many tools | **Dynamic skill loader** — only the matching domain skill (≤ 4–6k chars) + a tool menu filtered to that domain (~5–9 tools) |
| Typing tool calls as text | `toolcalls.py` recovers and runs them; invented tools get a nudge |
| Silent mistakes | **Auto-checks** after every worker: OpenSCAD compile + triangle count, Verse lint, plan validation, Luau lint, Python compile |

```
user ──► lead (qwen, resident, memory)
          │  system prompt = core rules + ACTIVE SKILL (skill_router.route(task))
          │  tools         = core + DOMAIN_TOOLS[domain_of(task)]
          ├─► reply with execution tags ──► exec_tags.to_calls ──► write_file + engine step
          ├─► reply with a plan          ──► run_plan ──► engines.{ue_layout|obby|island|terrain}
          └─► spawn_subagent (worker, fresh, routed skill) ──► files ──► AUTO-CHECKS ──► lead debugs
```

## Component 1 — System prompt & dynamic skill loader

* **Lead prompt** (`app.py` `SYSTEM_PROMPT`): "you have real tools, do it, don't explain",
  a which-tool list, the execution-tag format, then `# ACTIVE SKILL` blocks and MEMORY.
* **Skill loader** (`skill_router.py`): every skill declares
  `domain:` and `triggers:` in its frontmatter. `route(task)` scores triggers against the
  last two user turns, takes the best domain's skills (then the agent's assigned ones),
  and trims to a character budget (lead 4000, workers 6000 ≈ 1.6k tokens).
* **Tool menu by domain** (`app.py` `lead_app_tools`): core tools + that domain's tools
  only. No domain → one main tool per engine.
* **Domain skills** (strict API allowlists, syntax traps, output format, one verified
  template each):

| Skill | Domain | Output the model writes |
|---|---|---|
| `openscad-cad` | openscad | ```` ```openscad file=models/x.scad run ```` |
| `fortnite-map-maker` | fortnite | ```` ```plan ```` kind `island`, or ```` ```verse file=verse/x.verse run ```` |
| `roblox-obby-builder` | roblox | ```` ```plan ```` kind `obby`, extra ```` ```luau ... run ```` |
| `unreal-level-layout` | unreal | ```` ```plan ```` kind `ue_layout`, or ```` ```ue-python ... run project=... ```` |
| `blender-python`, `unreal-engine`, `roblox-studio` | blender / unreal / roblox | bpy / editor Python / Luau |

Every template inside those skills is verified: the OpenSCAD ones compile, the Verse
one passes the linter, the plans validate.

## Component 2 — Execution tags (`exec_tags.py`)

```` ```<lang> file=<path> [run] [project=<.uproject>] ````

| lang | `run` does |
|---|---|
| `openscad` | `openscad_render` → `.stl` + `.png`, errors, triangle count |
| `bpy` | `blender_run` headless |
| `ue-python` | `unreal_run_python` on `project=` |
| `luau` | `luau_check` |
| `verse` | `verse_check` (offline lint) |
| `plan` | `run_plan` |

Only blocks with `file=` (or `run`) act; placeholders like `<name>` and empty blocks
are ignored, so example code in an explanation never runs. For the lead, blocks become
normal tool calls (same approval gate as everything else). For workers, files are
written directly and the block text in their report is replaced by `[wrote path]`.

## Component 3 — Engines (`engines.py`) and dual-environment projects

**Where files go:** relative paths → the workspace (the agents' isolated folder; can be
switched in the IDE's PC tab). Absolute paths → only inside a registered project folder
(Customize → Apps) or the engines' standard folders `Documents/Unreal Projects` and
`Documents/Fortnite Projects`. The same code runs in a VM: point `--workspace` at the
VM's folder (engines installed there are used; plans, heightmaps, Verse lint, rbxlx
generation need no engine at all).

| Engine | Create / load | Run / build | Honest limits |
|---|---|---|---|
| **OpenSCAD** | `.scad` in the workspace | `openscad -o x.stl`, `--imgsize --viewall` PNG | PNG preview needs OpenGL (fine on desktops) |
| **UE5** | `unreal_new_project` copies an engine template (`TP_BlankBP`, `TP_ThirdPersonBP`, …), enables the Python plugins | `-run=pythonscript` commandlet, `ue_layout` plans, `RunUAT BuildCookRun` | first open compiles shaders (minutes) |
| **UEFN** | finds `Documents/Fortnite Projects/*/*.uefnproject`; island plans write Verse into `Plugins/<Project>/Content` | launches `UnrealEditorFortnite-Win64-Shipping.exe` | Windows only. No public CLI to create islands or compile Verse, and no editor Python: create the island once in UEFN, then **Verse > Build Verse Code**; devices are placed by hand using the generated `DEVICES.md` checklist |
| **Roblox** | `obby` plans write a real `.rbxlx` (course, checkpoints, kill bricks, rules script) + Rojo `src/` | `roblox_open`, `rojo build/serve`, `run-in-roblox` tests | local server "Play" is Studio UI; automated tests go through run-in-roblox |

**Fortnite map making**
* `island` plan → 16-bit heightmap (terraced "build plateau" style, UE landscape sizes
  253/505/1009) + preview, Poisson-style prop scatter that avoids water/cliffs, Verse:
  `<name>_game` (elimination scoring → end game via score/end-game devices) and
  `<name>_props` (SpawnProp at the scattered points), plus `DEVICES.md`.
* Heightmap import: Landscape mode → Import from File, scale X/Y 100, Z 100.

## Component 4 — CLI (`nightcrew_cli.py`)

```
python nightcrew_cli.py status
python nightcrew_cli.py skills route "make a zone wars island"
python nightcrew_cli.py plan run plans/isle.json [--project MyIsland]
python nightcrew_cli.py scad render models/gear.scad
python nightcrew_cli.py ue new MyGame --template thirdperson --location pc
python nightcrew_cli.py ue layout plans/arena.json
python nightcrew_cli.py ue package MyGame.uproject --platform Win64 --out Builds
python nightcrew_cli.py uefn list | open [P] | island PLAN --project P | verse-check FILE
python nightcrew_cli.py roblox obby plans/obby.json | open PLACE | test PLACE SCRIPT
python nightcrew_cli.py terrain heightmap terrain/hm.png --size 505 --style island --terraces 4
```

## Verified in the cloud sandbox

* OpenSCAD 2021.01: skill templates compile (gear 576 tris, bracket 284), syntax errors
  come back with line numbers.
* Island: 505×505 16-bit heightmap in 0.6 s, 90 scattered props, both Verse files lint clean.
* Obby: `.rbxlx` parses as XML with Start/Checkpoints/KillBricks/Finish/rules script.
* UE layout: generated editor Python parses; doorways split walls.
* Full chat loop with a fake qwen: right skill injected, domain tool menu, execution
  tags written + run, worker Verse errors (`==`, missing usings) reported to the lead.

Not testable there (no Windows / engines): UE, UEFN, Roblox Studio launches, Blender runs.
The Unreal and UEFN steps follow Epic's documented commandlet / project layouts; run
them once on the PC and check `update.log` / the chat's tool results.
