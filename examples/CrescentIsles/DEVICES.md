# CrescentIsles — place these in UEFN

1. Landscape mode > Import from File: `terrain/CrescentIsles_heightmap.png` (505x505), location 0,0,0, scale X/Y 100, **Z 12** (props below are placed for exactly this Z; height span ≈ 61 m).
2. Verse > Build Verse Code (Ctrl+Shift+B). Drag the new devices from the Content Browser (`crescentisles_game`, `crescentisles_props`) into the level.
3. Place and wire:
   - 8 x player_spawner_device — 4 per team, on opposite mid plateaus
   - 12 x item_spawner_device — loot on the mid ring
   - 1 x mutator_zone_device — covers the top plateau (high ground)
   - 1 x item_granter_device — reward for taking high ground
   - 1 x score_manager_device
   - 1 x end_game_device
4. `crescentisles_game` Details: set ScoreManager + EndGame to the devices above.
5. `crescentisles_props` Details: pick a Fortnite prop for each *Asset field.
6. `crescent_highground` (verse/crescent_highground.verse): drag it in, set Peak = the mutator zone, Reward = the item granter.
7. Launch Session to playtest.
