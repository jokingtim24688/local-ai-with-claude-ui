---
name: game-programming
description: Game code, engines, anticheat, scripting languages.
---

# game-programming

Languages by engine:
- Unity -> C#
- Unreal -> C++ / Blueprints
- Godot -> GDScript / C#
- Roblox -> Luau
- Love2D / Defold -> Lua

Anticheat basics (defensive):
- server-authoritative state; never trust the client
- validate inputs, rate-limit actions, sanity-check movement/physics
- checksum assets; detect memory tampering server-side by outcome, not by
  scanning the user's machine

Scripting:
- Lua: small, embeddable; `require`, tables as everything
- Python: tooling, build scripts, ML/glue
- keep hot loops out of interpreted code; profile before optimizing
