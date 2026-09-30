# Crescent Isles — zone-wars island (made by Night Crew's MCP tools)

Built end-to-end through `nightcrew-fortnite` MCP calls, the way the lead agent does it:
`status` → `devices` → `island(spec)` → `write_verse` (a first draft with `==` / `;` was
caught by the lint, fixed, re-linted clean).

| File | What |
|---|---|
| `plan.json` | the island plan (re-run: `python nightcrew_cli.py --workspace examples/CrescentIsles uefn island plan.json`) |
| `terrain/CrescentIsles_heightmap.png` | 505×505 16-bit heightmap, 4 terraces (~11 m each) |
| `terrain/CrescentIsles_heightmap_preview.png` | 8-bit preview |
| `verse/crescentisles_game.verse` | elimination scoring, first to 15 ends the game |
| `verse/crescentisles_props.verse` | spawns 70 pines, 35 rocks, 16 crates at scattered points |
| `verse/crescent_highground.verse` | first player onto the empty peak gets an item |
| `CrescentIsles_props.json` | the prop points (UE cm) |
| `DEVICES.md` | step-by-step UEFN setup checklist |

**Into UEFN:** copy the three `.verse` files into your island's Verse folder
(`Documents/Fortnite Projects/<Project>/Plugins/<Project>/Content`), or call
`island(spec, project="<Project>")` to write them there directly. Then follow `DEVICES.md`.
Import the heightmap with **Z scale 12** — the prop heights assume it.

Not verified inside UEFN (no Windows/UEFN where this was built): the Verse passes Night
Crew's offline lint, but UEFN's compiler is the real check — send back any errors it shows.
