"""Engine bridge: OpenSCAD, Unreal Engine 5, UEFN (Fortnite) and Roblox Studio.

Design for a 3B model: it writes either
  * small code files through execution tags (```openscad file=... run```), or
  * a JSON *plan* (```plan file=plans/x.json run```) that the deterministic code
    below turns into engine work — levels, obbies, Fortnite islands, terrain.
Plans keep the model out of big engine APIs it would hallucinate.

Where things go ("dual environment"):
  * relative paths          -> the workspace (the agents' isolated sandbox)
  * absolute paths          -> must be inside a registered project folder, or one of
                               the standard engine project folders on this PC
                               (Documents/Unreal Projects, Documents/Fortnite Projects)
Every function here is also a CLI command (nightcrew_cli.py).
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import time
import zlib
from xml.sax.saxutils import escape as xml_escape

import apps
import tools
from apps import MAC, WIN, HOME, _need, _run, _spawn, _tail, resolve

DOCS_DIR = next((d for d in (os.path.join(HOME, "OneDrive", "Documents"), os.path.join(HOME, "Documents"))
                 if os.path.isdir(d)), os.path.join(HOME, "Documents"))
UE_PROJECTS = os.path.join(DOCS_DIR, "Unreal Projects")
UEFN_PROJECTS = os.path.join(DOCS_DIR, "Fortnite Projects")


def standard_roots() -> list:
    return [d for d in (UE_PROJECTS, UEFN_PROJECTS) if os.path.isdir(d)]


def _out_path(rel_or_abs: str) -> str:
    """Where to WRITE: sandbox for relative paths, else an allowed project root."""
    if not os.path.isabs(rel_or_abs):
        p = str(tools._jail(rel_or_abs))
    else:
        p = resolve(rel_or_abs, must_exist=False)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def _out_dir(rel_or_abs: str) -> str:
    p = str(tools._jail(rel_or_abs)) if not os.path.isabs(rel_or_abs) else resolve(rel_or_abs, must_exist=False)
    os.makedirs(p, exist_ok=True)
    return p


def _load_plan(plan) -> dict:
    if isinstance(plan, dict):
        return plan
    with open(resolve(plan), encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# OpenSCAD
# =============================================================================

def find_openscad() -> str | None:
    if WIN:
        for c in (r"C:\Program Files\OpenSCAD\openscad.com", r"C:\Program Files\OpenSCAD\openscad.exe",
                  r"C:\Program Files (x86)\OpenSCAD\openscad.com"):
            if os.path.isfile(c):
                return c          # .com = console build: prints errors to stdout
    if MAC:
        for c in ("/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
                  os.path.join(HOME, "Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD")):
            if os.path.isfile(c):
                return c
    return shutil.which("openscad")


def _stl_triangles(path: str) -> int:
    try:
        with open(path, "rb") as f:
            data = f.read()
        if data[:5] == b"solid" and b"facet normal" in data[:4096]:
            return data.count(b"facet normal")                    # ASCII STL
        return struct.unpack("<I", data[80:84])[0]                # binary STL
    except Exception:
        return -1


def openscad_render(file: str = "", code: str = "", out: str = "", png: bool = True,
                    size: str = "900,700") -> str:
    """Compile a .scad to .stl (and a .png preview). Reports errors, warnings and the
    triangle count (keep game assets low-poly: $fn 24-48)."""
    exe = _need("openscad")
    if code:
        file = f"models/nc_{int(time.time())}.scad"
        tools.write_file(file, code)
    if not file:
        raise tools.ToolError("give `file` (.scad) or `code`")
    src = resolve(file)
    stl = _out_path(out) if out else os.path.splitext(src)[0] + ".stl"
    code_, log = _run([exe, "-o", stl, src], 600)
    issues = [l for l in log.splitlines() if re.search(r"ERROR|WARNING|Parser error", l)]
    ok = code_ == 0 and os.path.isfile(stl) and os.path.getsize(stl) > 0
    lines = [f"exit={code_}", ("OK: " if ok else "FAILED: ") + (stl if ok else "no mesh produced")]
    if ok:
        lines.append(f"triangles: {_stl_triangles(stl)}")
    if issues:
        lines.append("\n".join(issues[:25]))
    if ok and png:
        img = os.path.splitext(stl)[0] + ".png"
        pc, plog = _run([exe, "-o", img, f"--imgsize={size}", "--viewall", "--autocenter",
                         "--colorscheme=Tomorrow Night", src], 300)
        lines.append(f"preview: {img}" if pc == 0 and os.path.isfile(img)
                     else "preview: skipped (no OpenGL here) — the .stl is fine")
    if not ok and not issues:
        lines.append(_tail(log, 1500))
    return "\n".join(lines)


# =============================================================================
# Verse (UEFN) — offline lint. Real compilation only happens inside UEFN.
# =============================================================================

KNOWN_DEVICES = {
    "creative_device", "player_spawner_device", "item_spawner_device", "item_granter_device",
    "mutator_zone_device", "elimination_manager_device", "score_manager_device", "end_game_device",
    "button_device", "trigger_device", "timer_device", "hud_message_device", "barrier_device",
    "teleporter_device", "capture_area_device", "damage_volume_device", "class_designer_device",
    "team_settings_and_inventory_device", "tracker_device", "billboard_device", "sfx_player_device",
    "vfx_spawner_device", "prop_mover_device", "conditional_button_device", "switch_device",
    "round_settings_device", "vending_machine_device", "guard_spawner_device",
}
USING_NEEDS = [
    (r"\bPrint\s*\(", "/UnrealEngine.com/Temporary/Diagnostics"),
    (r"\bSleep\s*\(|<suspends>|\bspawn\s*[:{]", "/Verse.org/Simulation"),
    (r"\bvector3\b|\bIdentityRotation\b|\brotation\b|MakeRotation", "/UnrealEngine.com/Temporary/SpatialMath"),
    (r"\bGetRandom(Int|Float)\b", "/Verse.org/Random"),
    (r"_device\b|\bSpawnProp\b|creative_prop", "/Fortnite.com/Devices"),
    (r"\bfort_character\b|\bGetFortCharacter\b|\belimination_result\b", "/Fortnite.com/Characters"),
]
BAD = [
    (r"(?<![=<>!:])==(?!=)", "Verse compares with `=` (not `==`)"),
    (r"!=", "Verse uses `<>` for not-equal"),
    (r"&&|\|\|", "Verse uses `and` / `or`"),
    (r"\bself\.", "Verse uses `Self` (usually just call the member directly)"),
    (r"\b(null|None|nil)\b", "Verse has no null — use an option: `?type`, `false`"),
    (r"\b(True|False)\b", "Verse booleans are `true` / `false` (type `logic`)"),
    (r"^\s*(def|function|func)\s", "Verse functions: `Name(Arg : type) : return_type ="),
    (r";\s*$", "no `;` at line ends in Verse"),
    (r"^\s*(let|const)\s", "Verse constants: `Name : type = value`, variables: `var Name : type = value`"),
]


def verse_lint(src: str) -> list:
    issues = []
    lines = src.splitlines()
    if any("\t" in l[: len(l) - len(l.lstrip())] for l in lines) and \
            any(l.startswith("    ") for l in lines):
        issues.append("mixes tabs and spaces for indentation — pick one (4 spaces)")
    usings = set(re.findall(r"using\s*\{\s*([^}\s]+)\s*\}", src))
    body = "\n".join(l for l in lines if not l.strip().startswith(("using", "#")))
    for pat, mod in USING_NEEDS:
        if re.search(pat, body) and mod not in usings:
            issues.append(f"add `using {{ {mod} }}`")
    for n, line in enumerate(lines, 1):
        code = line.split("#", 1)[0]
        if not code.strip() or code.strip().startswith("using"):
            continue
        for pat, msg in BAD:
            if re.search(pat, code):
                issues.append(f"line {n}: {msg}")
        m = re.match(r"\s*(\w+)\s*(\+|-|\*)=", code)
        if m:
            issues.append(f"line {n}: mutating `{m.group(1)}` needs `set {m.group(1)} {m.group(2)}= ...` (and `var` on its declaration)")
        for dev in re.findall(r"\b(\w+_device)\b", code):
            if dev not in KNOWN_DEVICES and not dev.startswith("my_") and not re.search(rf"\b{dev}\s*:=\s*class", src):
                issues.append(f"line {n}: `{dev}` isn't a device I know — check the Verse API (fetch_docs uefn)")
        if re.search(r"\bOnBegin\b", code) and "<override>" not in code:
            issues.append(f"line {n}: `OnBegin<override>()<suspends> : void =`")
    if re.search(r":=\s*class\s*\(\s*creative_device\s*\)", src) is None and "_device" in src:
        issues.append("no `name := class(creative_device):` — devices need a creative_device class to live in the level")
    seen, out = set(), []
    for i in issues:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def verse_check(file: str = "", code: str = "") -> str:
    src = code or open(resolve(file), encoding="utf-8").read()
    issues = verse_lint(src)
    if not issues:
        return "OK: no Verse problems found offline. UEFN does the real compile: Verse > Build Verse Code (Ctrl+Shift+B)."
    return "Verse issues:\n" + "\n".join("- " + i for i in issues[:30])


# =============================================================================
# UEFN (Unreal Editor for Fortnite) — Windows only
# =============================================================================

def find_uefn() -> str | None:
    if not WIN:
        return None
    roots = [r"C:\Program Files\Epic Games\Fortnite"]
    try:
        with open(r"C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat", encoding="utf-8") as f:
            roots += [i["InstallLocation"] for i in json.load(f).get("InstallationList", [])
                      if str(i.get("AppName", "")).lower() == "fortnite"]
    except Exception:
        pass
    for r in roots:
        exe = os.path.join(r, "FortniteGame", "Binaries", "Win64", "UnrealEditorFortnite-Win64-Shipping.exe")
        if os.path.isfile(exe):
            return exe
    return None


def uefn_list() -> str:
    if not os.path.isdir(UEFN_PROJECTS):
        return f"no UEFN projects folder at {UEFN_PROJECTS} — create an island in UEFN once"
    rows = []
    for name in sorted(os.listdir(UEFN_PROJECTS)):
        d = os.path.join(UEFN_PROJECTS, name)
        up = [f for f in os.listdir(d) if f.endswith(".uefnproject")] if os.path.isdir(d) else []
        if up:
            rows.append(f"- {name}: {os.path.join(d, up[0])}")
    return "UEFN projects:\n" + ("\n".join(rows) if rows else "(none yet)")


def _uefn_project_file(project: str) -> str:
    if project and not os.path.isabs(project) and os.path.isdir(os.path.join(UEFN_PROJECTS, project)):
        project = os.path.join(UEFN_PROJECTS, project)
    p = resolve(project)
    if os.path.isdir(p):
        ups = [f for f in os.listdir(p) if f.endswith(".uefnproject")]
        if not ups:
            raise tools.ToolError(f"no .uefnproject in {p}")
        p = os.path.join(p, ups[0])
    return p


def uefn_verse_dir(project: str) -> str:
    """Where UEFN reads Verse from: <Project>/Plugins/<Project>/Content (created if missing)."""
    up = _uefn_project_file(project)
    root, name = os.path.dirname(up), os.path.splitext(os.path.basename(up))[0]
    for dp, _, files in os.walk(os.path.join(root, "Plugins")):
        if any(f.endswith(".verse") for f in files):
            return dp
    d = os.path.join(root, "Plugins", name, "Content")
    os.makedirs(d, exist_ok=True)
    return d


def uefn_open(project: str = "") -> str:
    exe = _need("uefn")
    _spawn([exe] + ([_uefn_project_file(project)] if project else []))
    return "OK: UEFN opening" + (f" {project}" if project else " (pick or create an island in the project browser)")


# =============================================================================
# Terrain: 16-bit heightmaps (UE5 + UEFN landscape import) and prop scatter
# =============================================================================

LANDSCAPE_SIZES = (127, 253, 505, 1009, 2017)          # UE-recommended landscape resolutions


def _png(path: str, w: int, h: int, rows, bit16: bool) -> None:
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw += struct.pack(f">{w}H", *row) if bit16 else bytes(row)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16 if bit16 else 8, 0, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def _noise_field(n: int, seed: int, octaves: int = 5) -> list:
    """fBm value noise on an n x n grid, 0..1."""
    rnd = random.Random(seed)
    field = [[0.0] * n for _ in range(n)]
    amp, total = 1.0, 0.0
    cells = 4
    for _ in range(octaves):
        g = [[rnd.random() for _ in range(cells + 2)] for _ in range(cells + 2)]
        step = (n - 1) / cells
        for y in range(n):
            gy = y / step
            y0 = int(gy)
            ty = gy - y0
            ty = ty * ty * (3 - 2 * ty)
            r0, r1 = g[y0], g[y0 + 1]
            row = field[y]
            for x in range(n):
                gx = x / step
                x0 = int(gx)
                tx = gx - x0
                tx = tx * tx * (3 - 2 * tx)
                a = r0[x0] + (r0[x0 + 1] - r0[x0]) * tx
                b = r1[x0] + (r1[x0 + 1] - r1[x0]) * tx
                row[x] += (a + (b - a) * ty) * amp
        total += amp
        amp *= 0.5
        cells *= 2
    return [[v / total for v in row] for row in field]


def make_heightmap(size: int = 505, seed: int = 1, style: str = "island", water: float = 0.2,
                   terraces: int = 0) -> list:
    """size x size floats 0..1. style: island (falls off to sea), hills, flat, canyon."""
    size = min(LANDSCAPE_SIZES, key=lambda s: abs(s - size))
    f = _noise_field(size, seed)
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            v = f[y][x]
            if style == "island":
                d = math.hypot(x - c, y - c) / c
                v = v * max(0.0, 1 - d ** 2.2) * 1.35
            elif style == "flat":
                v = 0.45 + (v - 0.5) * 0.08
            elif style == "canyon":
                v = abs(v - 0.5) * 2
            if terraces:                                   # Fortnite-style build plateaus
                v = round(v * terraces) / terraces * 0.7 + v * 0.3
            f[y][x] = max(0.0, min(1.0, v))
    return f


def write_heightmap(field: list, out: str) -> dict:
    n = len(field)
    _png(out, n, n, ([int(v * 65535) for v in row] for row in field), True)
    prev = out[:-4] + "_preview.png"
    k = max(1, n // 256)
    _png(prev, len(range(0, n, k)), len(range(0, n, k)),
         ([int(field[y][x] * 255) for x in range(0, n, k)] for y in range(0, n, k)), False)
    return {"heightmap": out, "preview": prev, "size": n}


def terrain_heightmap(out: str = "terrain/heightmap.png", size: int = 505, seed: int = 1,
                      style: str = "island", terraces: int = 0) -> str:
    field = make_heightmap(size, seed, style, terraces=terraces)
    info = write_heightmap(field, _out_path(out))
    n = info["size"]
    return (f"OK: {info['heightmap']} ({n}x{n}, 16-bit) + {info['preview']}\n"
            f"Import: Landscape mode > Import from File, resolution {n}x{n}, scale X/Y 100, Z 100 "
            f"(1 px = 1 m, heights span 512 m).")


def scatter(field: list, count: int, spacing_px: float, hmin: float, hmax: float,
            max_slope: float = 0.02, seed: int = 1) -> list:
    """Poisson-disk-ish points on the heightmap, avoiding water, peaks and cliffs."""
    rnd = random.Random(seed)
    n = len(field)
    pts, tries = [], 0
    while len(pts) < count and tries < count * 60:
        tries += 1
        x, y = rnd.uniform(2, n - 3), rnd.uniform(2, n - 3)
        xi, yi = int(x), int(y)
        h = field[yi][xi]
        if not hmin <= h <= hmax:
            continue
        slope = max(abs(field[yi][xi + 1] - field[yi][xi - 1]), abs(field[yi + 1][xi] - field[yi - 1][xi]))
        if slope > max_slope:
            continue
        if any((x - px) ** 2 + (y - py) ** 2 < spacing_px ** 2 for px, py, _ in pts):
            continue
        pts.append((x, y, h))
    return pts


def to_world(n: int, x: float, y: float, h: float, xy_scale: float = 100.0, z_scale: float = 100.0):
    """Heightmap pixel -> UE world cm, landscape centered on the origin."""
    wx = (x - (n - 1) / 2) * xy_scale
    wy = (y - (n - 1) / 2) * xy_scale
    wz = (h * 65535 - 32768) / 128.0 * z_scale
    return round(wx, 1), round(wy, 1), round(wz, 1)


# =============================================================================
# Fortnite island (UEFN): terrain + props + Verse game rules + device checklist
# =============================================================================

def _verse_ident(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower() or "island"
    return s if s[0].isalpha() else "i_" + s


def verse_game_manager(cls: str, rules: dict) -> str:
    to_win = int(rules.get("score_to_win", 10))
    return f'''using {{ /Fortnite.com/Devices }}
using {{ /Fortnite.com/Characters }}
using {{ /Fortnite.com/Game }}
using {{ /Verse.org/Simulation }}
using {{ /UnrealEngine.com/Temporary/Diagnostics }}

# Night Crew: elimination rules. Drag this device into the level, then fill the
# @editable fields in its Details panel (ScoreManager, EndGame).
{cls}_game := class(creative_device):
    @editable
    ScoreManager : score_manager_device = score_manager_device{{}}
    @editable
    EndGame : end_game_device = end_game_device{{}}

    ScoreToWin : int = {to_win}
    var Scores : [agent]int = map{{}}

    OnBegin<override>()<suspends> : void =
        for (Player : GetPlayspace().GetPlayers(), FortCharacter := Player.GetFortCharacter[]):
            FortCharacter.EliminatedEvent().Subscribe(OnEliminated)
        GetPlayspace().PlayerAddedEvent().Subscribe(OnPlayerAdded)

    OnPlayerAdded(Player : player) : void =
        if (FortCharacter := Player.GetFortCharacter[]):
            FortCharacter.EliminatedEvent().Subscribe(OnEliminated)

    OnEliminated(Result : elimination_result) : void =
        if:
            Eliminator := Result.EliminatingCharacter?
            Agent := Eliminator.GetAgent[]
        then:
            ScoreManager.Activate(Agent)
            NewScore := (if (Old := Scores[Agent]) then Old else 0) + 1
            if (set Scores[Agent] = NewScore) {{}}
            Print("Elimination! Score: {{NewScore}}")
            if (NewScore >= ScoreToWin):
                EndGame.Activate(Agent)
'''


def verse_prop_spawner(cls: str, groups: list) -> str:
    fields, loops, used = [], [], set()
    for g in groups:
        ident = _verse_ident(g["asset"])
        while ident in used:
            ident += "_x"
        used.add(ident)
        pts = ", ".join(f"vector3{{X := {x:.1f}, Y := {y:.1f}, Z := {z:.1f}}}" for x, y, z in g["points"])
        fields.append(f"    @editable\n    {ident.title().replace('_', '')}Asset : creative_prop_asset = DefaultCreativePropAsset\n"
                      f"    {ident.title().replace('_', '')}Points : []vector3 = array{{{pts}}}")
        loops.append(f"        for (P : {ident.title().replace('_', '')}Points):\n"
                     f"            SpawnProp({ident.title().replace('_', '')}Asset, P, IdentityRotation())")
    return f'''using {{ /Fortnite.com/Devices }}
using {{ /Verse.org/Simulation }}
using {{ /UnrealEngine.com/Temporary/SpatialMath }}

# Night Crew: spawns the scattered props when the game starts. Put this device in the
# level and pick a prop for each *Asset field (Details panel). Max 100 points per group.
{cls}_props := class(creative_device):
{chr(10).join(fields)}

    OnBegin<override>()<suspends> : void =
{chr(10).join(loops)}
'''


def fortnite_island(plan, project: str = "") -> str:
    """plan kind "island": terrain heightmap + prop scatter + Verse rules + devices.md.
    With `project` (a UEFN project name/path) the Verse goes straight into it."""
    p = _load_plan(plan)
    name = re.sub(r"[^A-Za-z0-9_]", "", p.get("name", "Island")) or "Island"
    cls = _verse_ident(name)
    base = f"fortnite/{name}"
    field = make_heightmap(int(p.get("size", 505)), int(p.get("seed", 1)), p.get("style", "island"),
                           terraces=int(p.get("terraces", 4)))
    n = len(field)
    hm = write_heightmap(field, _out_path(f"{base}/terrain/{name}_heightmap.png"))
    water = float(p.get("water", 0.18))
    groups, report = [], []
    for i, g in enumerate(p.get("props", [])[:6]):
        spacing = float(g.get("min_spacing", 800)) / 100.0                 # cm -> px (1 px = 1 m)
        lo, hi = (g.get("height") or [water + 0.03, 0.85])[:2]
        pts = scatter(field, min(int(g.get("count", 40)), 100), spacing, lo, hi, seed=int(p.get("seed", 1)) + i)
        world = [to_world(n, x, y, h) for x, y, h in pts]
        groups.append({"asset": g.get("asset", f"prop{i}"), "points": world})
        report.append(f"{g.get('asset')}: {len(world)} points")
    with open(_out_path(f"{base}/{name}_props.json"), "w", encoding="utf-8") as f:
        json.dump(groups, f, indent=1)
    verse = {f"{cls}_game.verse": verse_game_manager(cls, p.get("rules", {}))}
    if groups:
        verse[f"{cls}_props.verse"] = verse_prop_spawner(cls, groups)
    dest = uefn_verse_dir(project) if project else _out_dir(f"{base}/verse")
    for fn, src in verse.items():
        with open(os.path.join(dest, fn), "w", encoding="utf-8") as f:
            f.write(src)
    devices = p.get("devices") or [{"type": "player_spawner_device", "count": 8},
                                   {"type": "score_manager_device", "count": 1},
                                   {"type": "end_game_device", "count": 1}]
    md = [f"# {name} — place these in UEFN", "",
          f"1. Landscape mode > Import from File: `{hm['heightmap']}` ({n}x{n}), scale X/Y 100, Z 100.",
          "2. Verse > Build Verse Code (Ctrl+Shift+B). Drag the new devices from the Content Browser "
          f"(`{cls}_game`, `{cls}_props`) into the level.", "3. Place and wire:"]
    md += [f"   - {d.get('count', 1)} x {d['type']}" + (f" — {d['note']}" if d.get("note") else "") for d in devices]
    md += [f"4. `{cls}_game` Details: set ScoreManager + EndGame to the devices above.",
           f"5. `{cls}_props` Details: pick a Fortnite prop for each *Asset field.",
           "6. Launch Session to playtest."]
    with open(_out_path(f"{base}/DEVICES.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    lint = [f"{fn}: " + ("clean" if not verse_lint(src) else "; ".join(verse_lint(src)[:3])) for fn, src in verse.items()]
    return (f"OK: island {name}\n- terrain: {hm['heightmap']} ({n}x{n}) + preview {hm['preview']}\n"
            f"- props: {', '.join(report) or 'none'}\n- verse -> {dest}: {', '.join(verse)}\n"
            f"- checklist: {base}/DEVICES.md\n- verse lint: " + " | ".join(lint))


# =============================================================================
# Roblox: .rbxlx place files + obby generator + run-in-roblox tests
# =============================================================================

_REF = [0]


def _ref() -> str:
    _REF[0] += 1
    return f"RBX{_REF[0]:04d}"


def _color(rgb) -> int:
    r, g, b = rgb
    return 0xFF000000 | (int(r) << 16) | (int(g) << 8) | int(b)


MATERIAL = {"plastic": 256, "smoothplastic": 272, "neon": 288, "wood": 512, "slate": 800,
            "concrete": 816, "grass": 1280, "ice": 1536, "metal": 1088}


def rbx_part(name, pos, size, color=(163, 162, 165), material="smoothplastic", cls="Part",
             anchored=True, can_collide=True, transparency=0.0) -> str:
    x, y, z = pos
    sx, sy, sz = size
    extra = '<bool name="Neutral">true</bool><bool name="AllowTeamChangeOnTouch">false</bool>' if cls == "SpawnLocation" else ""
    return (f'<Item class="{cls}" referent="{_ref()}"><Properties>'
            f'<string name="Name">{xml_escape(name)}</string>'
            f'<bool name="Anchored">{str(anchored).lower()}</bool>'
            f'<bool name="CanCollide">{str(can_collide).lower()}</bool>'
            f'<float name="Transparency">{transparency}</float>'
            f'<Color3uint8 name="Color3uint8">{_color(color)}</Color3uint8>'
            f'<token name="Material">{MATERIAL.get(material.lower(), 272)}</token>'
            f'<token name="TopSurface">0</token><token name="BottomSurface">0</token>'
            f'<Vector3 name="size"><X>{sx}</X><Y>{sy}</Y><Z>{sz}</Z></Vector3>'
            f'<CoordinateFrame name="CFrame"><X>{x}</X><Y>{y}</Y><Z>{z}</Z>'
            f'<R00>1</R00><R01>0</R01><R02>0</R02><R10>0</R10><R11>1</R11><R12>0</R12>'
            f'<R20>0</R20><R21>0</R21><R22>1</R22></CoordinateFrame>{extra}</Properties></Item>')


def rbx_script(name, source, cls="Script") -> str:
    return (f'<Item class="{cls}" referent="{_ref()}"><Properties><string name="Name">{xml_escape(name)}</string>'
            f'<ProtectedString name="Source"><![CDATA[{source.replace("]]>", "]] >")}]]></ProtectedString>'
            f'</Properties></Item>')


def rbxlx(workspace_items: list, server_scripts: list = (), client_scripts: list = ()) -> str:
    folder = lambda cls, items: (f'<Item class="{cls}" referent="{_ref()}"><Properties>'
                                 f'<string name="Name">{cls}</string></Properties>{"".join(items)}</Item>')
    starter = (f'<Item class="StarterPlayer" referent="{_ref()}"><Properties><string name="Name">StarterPlayer</string></Properties>'
               f'{folder("StarterPlayerScripts", list(client_scripts))}</Item>') if client_scripts else ""
    return ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">'
            f'{folder("Workspace", workspace_items)}{folder("ServerScriptService", list(server_scripts))}'
            f'{starter}</roblox>')


OBBY_SERVER = """-- Night Crew obby rules: KillBricks reset you, CheckpointN saves your stage (you
-- respawn there), Finish = +1 Win. Only "Start" is a SpawnLocation, on purpose.
local Players = game:GetService("Players")
local course = workspace:WaitForChild("Obby")

local function checkpoint(n: number): BasePart?
	return course:FindFirstChild("Checkpoint" .. n) :: BasePart?
end

Players.PlayerAdded:Connect(function(player)
	local stats = Instance.new("Folder")
	stats.Name = "leaderstats"
	stats.Parent = player
	local stage = Instance.new("IntValue")
	stage.Name = "Stage"
	stage.Parent = stats
	local wins = Instance.new("IntValue")
	wins.Name = "Wins"
	wins.Parent = stats
	player.CharacterAdded:Connect(function(character)
		task.wait()
		local cp = checkpoint(stage.Value)
		if cp then
			character:PivotTo(cp.CFrame + Vector3.new(0, 4, 0))
		end
	end)
end)

local function playerFrom(hit: BasePart): Player?
	local model = hit:FindFirstAncestorOfClass("Model")
	return if model then Players:GetPlayerFromCharacter(model) else nil
end

for _, part in course:GetDescendants() do
	if not part:IsA("BasePart") then continue end
	if part.Name == "KillBrick" then
		part.Touched:Connect(function(hit)
			local hum = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
			if hum then hum.Health = 0 end
		end)
	elseif string.match(part.Name, "^Checkpoint%d+$") then
		local n = tonumber(string.match(part.Name, "%d+")) or 0
		part.Touched:Connect(function(hit)
			local player = playerFrom(hit)
			local stats = player and player:FindFirstChild("leaderstats")
			local stage = stats and stats:FindFirstChild("Stage") :: IntValue?
			if stage and n > stage.Value then
				stage.Value = n
			end
		end)
	elseif part.Name == "Finish" then
		local done: {[Player]: boolean} = {}
		part.Touched:Connect(function(hit)
			local player = playerFrom(hit)
			if not player or done[player] then return end
			local stats = player:FindFirstChild("leaderstats")
			local wins = stats and stats:FindFirstChild("Wins") :: IntValue?
			if wins then
				done[player] = true
				wins.Value += 1
				task.delay(3, function() done[player] = nil end)
			end
		end)
	end
end
"""

THEMES = {"neon": [(0, 255, 170), (255, 0, 170), (0, 170, 255)], "classic": [(90, 170, 255), (255, 200, 60), (120, 220, 120)],
          "lava": [(60, 60, 70), (90, 90, 100), (70, 70, 80)], "candy": [(255, 150, 200), (160, 220, 255), (255, 240, 150)]}


def build_obby(p: dict) -> tuple:
    rnd = random.Random(int(p.get("seed", 1)))
    stages = max(3, min(int(p.get("stages", 10)), 60))
    diff = {"easy": 0.6, "medium": 1.0, "hard": 1.45}.get(p.get("difficulty", "medium"), 1.0)
    theme = THEMES.get(p.get("theme", "classic"), THEMES["classic"])
    mat = "neon" if p.get("theme") == "neon" else "smoothplastic"
    items = [rbx_part("Baseplate", (0, -10, 0), (256, 20, 256), (70, 75, 80), "concrete"),
             rbx_part("Start", (0, 1, 0), (12, 1, 12), (255, 255, 255), "smoothplastic", "SpawnLocation")]
    course = []
    x, y, z = 0.0, 1.0, 16.0
    for s in range(1, stages + 1):
        gap = (6 + s * 0.6) * diff
        for j in range(3):                                  # three jumps per stage
            z += gap + rnd.uniform(0, 3)
            x += rnd.uniform(-6, 6) * diff
            y += rnd.uniform(-0.5, 2.0)
            w = max(3.0, 8 - s * 0.25 * diff)
            course.append(rbx_part(f"Platform{s}_{j}", (round(x, 2), round(y, 2), round(z, 2)),
                                   (round(w, 2), 1, round(w, 2)), theme[(s + j) % len(theme)], mat))
            if diff >= 1 and rnd.random() < 0.25 * diff:
                course.append(rbx_part("KillBrick", (round(x, 2), round(y - 3, 2), round(z - gap / 2, 2)),
                                       (14, 1, max(2.0, gap - 2)), (255, 60, 40), "neon"))
        if s % 3 == 0 or s == stages:
            z += 12
            course.append(rbx_part(f"Checkpoint{s}", (round(x, 2), round(y, 2), round(z, 2)), (12, 1, 12),
                                   (240, 240, 255), "neon"))
    z += 14
    course.append(rbx_part("Finish", (round(x, 2), round(y, 2), round(z, 2)), (16, 1, 16), (255, 215, 0), "neon"))
    items.append(f'<Item class="Model" referent="{_ref()}"><Properties><string name="Name">Obby</string></Properties>'
                 f'{"".join(course)}</Item>')
    return items, stages, len(course)


def roblox_build_obby(plan, out: str = "") -> str:
    """plan kind "obby" -> a .rbxlx place (course + checkpoints + kill bricks + rules
    script) that Studio opens directly, plus the script as a Rojo-ready file."""
    p = _load_plan(plan)
    name = re.sub(r"[^A-Za-z0-9_]", "", p.get("name", "Obby")) or "Obby"
    items, stages, parts = build_obby(p)
    place = _out_path(out or f"roblox/{name}/{name}.rbxlx")
    with open(place, "w", encoding="utf-8") as f:
        f.write(rbxlx(items, [rbx_script("ObbyRules", OBBY_SERVER)]))
    src = _out_path(f"roblox/{name}/src/server/ObbyRules.server.luau")
    with open(src, "w", encoding="utf-8") as f:
        f.write(OBBY_SERVER)
    shown = os.path.relpath(place, str(tools.SANDBOX)) if place.startswith(str(tools.SANDBOX)) else place
    return f"OK: {place} ({stages} stages, {parts} parts, rules script inside)\nOpen it: roblox_open('{shown}')"


def roblox_test(place: str, script: str) -> str:
    """Run a Luau script inside Roblox Studio against a place and return its output
    (needs run-in-roblox: `aftman add rojo-rbx/run-in-roblox` / cargo install)."""
    exe = _need("runinroblox")
    code, out = _run([exe, "--place", resolve(place), "--script", resolve(script)], 600)
    return f"exit={code}\n" + _tail(out)


# =============================================================================
# Unreal Engine 5: new project from a template, JSON layout -> level
# =============================================================================

UE_TEMPLATES = {"blank": "TP_BlankBP", "thirdperson": "TP_ThirdPersonBP", "firstperson": "TP_FirstPersonBP",
                "topdown": "TP_TopDownBP", "vehicle": "TP_VehicleAdvBP", "blank_cpp": "TP_Blank"}


def unreal_new_project(name: str, template: str = "blank", location: str = "") -> str:
    """Create a UE5 project from one of the engine's own templates.
    location: "" = workspace/unreal/<name>, "pc" = Documents/Unreal Projects/<name>,
    or an absolute folder inside a registered project folder."""
    ed = _need("unreal")
    root = ed.split(os.sep + "Engine" + os.sep)[0]
    name = re.sub(r"[^A-Za-z0-9_]", "", name) or "NightCrewGame"
    tname = UE_TEMPLATES.get(template.lower().replace(" ", "").replace("-", ""), template)
    tpl = os.path.join(root, "Templates", tname)
    if not os.path.isdir(tpl):
        have = [d for d in os.listdir(os.path.join(root, "Templates"))] if os.path.isdir(os.path.join(root, "Templates")) else []
        raise tools.ToolError(f"template {tname} not found; this engine has: {', '.join(have) or 'none'}")
    if location == "pc":
        dest = os.path.join(UE_PROJECTS, name)
    elif location:
        dest = os.path.join(_out_dir(location), name)
    else:
        dest = str(tools._jail(f"unreal/{name}"))
    if not os.path.isdir(dest):
        shutil.copytree(tpl, dest, ignore=shutil.ignore_patterns("Saved", "Intermediate", "Binaries", "DerivedDataCache"))
        old = next(f for f in os.listdir(dest) if f.endswith(".uproject"))
        os.rename(os.path.join(dest, old), os.path.join(dest, f"{name}.uproject"))
    up = os.path.join(dest, f"{name}.uproject")
    with open(up, encoding="utf-8") as f:
        data = json.load(f)
    plugins = data.setdefault("Plugins", [])
    for pl in ("PythonScriptPlugin", "EditorScriptingUtilities"):
        if not any(x.get("Name") == pl for x in plugins):
            plugins.append({"Name": pl, "Enabled": True})
    with open(up, "w", encoding="utf-8") as f:
        json.dump(data, f, indent="\t")
    return up


def ue_layout_script(p: dict) -> str:
    """JSON layout plan -> Unreal editor Python (runs in the PythonScript commandlet)."""
    level = re.sub(r"[^A-Za-z0-9_]", "", p.get("level", "Layout")) or "Layout"
    L = ["import unreal",
         "les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)",
         "eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)",
         "lib = unreal.EditorAssetLibrary",
         f"path = '/Game/Maps/{level}'",
         "les.load_level(path) if lib.does_asset_exist(path) else les.new_level(path)",
         "CUBE = lib.load_asset('/Engine/BasicShapes/Cube')",
         "PLANE = lib.load_asset('/Engine/BasicShapes/Plane')",
         "def mesh(label, m, loc, scale, yaw=0.0):",
         "    a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*loc), unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(yaw)))",
         "    a.static_mesh_component.set_static_mesh(m)",
         "    a.set_actor_scale3d(unreal.Vector(*scale))",
         "    a.set_actor_label(label)",
         "    return a"]
    fx, fy = (p.get("floor") or {}).get("size", [4000, 4000])
    L.append(f"mesh('Floor', PLANE, (0, 0, 0), ({fx / 100}, {fy / 100}, 1))")
    for r in p.get("rooms", []):
        (rx, ry), (w, d) = r.get("pos", [0, 0]), r.get("size", [1000, 1000])
        h, t = float(r.get("wall_height", 400)), 20.0
        doors = set(r.get("doors", []))
        nm = re.sub(r"[^A-Za-z0-9_]", "", r.get("name", "Room"))
        walls = {"north": ((rx, ry + d / 2), (w, t)), "south": ((rx, ry - d / 2), (w, t)),
                 "east": ((rx + w / 2, ry), (t, d)), "west": ((rx - w / 2, ry), (t, d))}
        for side, ((cx, cy), (sx, sy)) in walls.items():
            if side in doors:                       # two segments with a 200 cm doorway
                long_x = sx > sy
                seg = ((sx if long_x else sy) - 200) / 2
                for k in (-1, 1):
                    off = (200 / 2 + seg / 2) * k
                    sc = (seg / 100, t / 100, h / 100) if long_x else (t / 100, seg / 100, h / 100)
                    loc = (cx + off, cy, h / 2) if long_x else (cx, cy + off, h / 2)
                    L.append(f"mesh('{nm}_{side}_{'a' if k < 0 else 'b'}', CUBE, {loc}, {sc})")
            else:
                L.append(f"mesh('{nm}_{side}', CUBE, ({cx}, {cy}, {h / 2}), ({sx / 100}, {sy / 100}, {h / 100}))")
    for i, pr in enumerate(p.get("props", [])):
        m = pr.get("mesh", "/Engine/BasicShapes/Cube")
        L.append(f"mesh('Prop{i}', lib.load_asset({m!r}) or CUBE, {tuple(pr.get('pos', [0, 0, 50]))}, "
                 f"{tuple(pr.get('scale', [1, 1, 1]))}, {float((pr.get('rot') or [0, 0, 0])[-1])})")
    for i, lt in enumerate(p.get("lights", [])):
        L.append(f"l = eas.spawn_actor_from_class(unreal.PointLight, unreal.Vector(*{tuple(lt.get('pos', [0, 0, 300]))}))")
        L.append(f"l.point_light_component.set_intensity({float(lt.get('intensity', 5000))})")
        L.append(f"l.set_actor_label('Light{i}')")
    L += ["eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1000), unreal.Rotator(roll=0.0, pitch=-40.0, yaw=30.0))",
          "for cls in (unreal.SkyAtmosphere, unreal.SkyLight, unreal.ExponentialHeightFog):",
          "    eas.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0))",
          f"eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(*{tuple(p.get('player_start', [0, 0, 120]))}))",
          "les.save_current_level()", "unreal.log('NC_LEVEL_OK')"]
    return "\n".join(L) + "\n"


def unreal_apply_layout(plan, project: str = "") -> str:
    p = _load_plan(plan)
    up = resolve(project) if project else unreal_new_project(p.get("project", p.get("level", "Layout") + "Project"),
                                                             p.get("template", "blank"))
    level = re.sub(r"[^A-Za-z0-9_]", "", p.get("level", "Layout")) or "Layout"
    script = f"scripts/nc_layout_{level}.py"
    tools.write_file(script, ue_layout_script(p))
    res = apps.unreal_run_python(script, up)
    if "NC_LEVEL_OK" not in res:
        return "error: layout script failed:\n" + res
    return f"OK: /Game/Maps/{level} built in {up}\n" + apps.unreal_open(up)


# =============================================================================
# plans
# =============================================================================

PLAN_KINDS = {
    "ue_layout": lambda p, project: unreal_apply_layout(p, project),
    "obby": lambda p, project: roblox_build_obby(p),
    "island": lambda p, project: fortnite_island(p, project),
    "terrain": lambda p, project: terrain_heightmap(p.get("out", "terrain/heightmap.png"), int(p.get("size", 505)),
                                                    int(p.get("seed", 1)), p.get("style", "island"),
                                                    int(p.get("terraces", 0))),
}


def validate_plan(p: dict) -> list:
    kind = p.get("kind")
    if kind not in PLAN_KINDS:
        return [f"`kind` must be one of {', '.join(PLAN_KINDS)}"]
    errs = []
    if kind == "ue_layout":
        for r in p.get("rooms", []):
            if len(r.get("size", [1, 1])) != 2:
                errs.append(f"room {r.get('name')}: size must be [width, depth] in cm")
    if kind == "obby" and not 3 <= int(p.get("stages", 10)) <= 60:
        errs.append("stages must be 3..60")
    if kind == "island" and len(p.get("props", [])) > 6:
        errs.append("at most 6 prop groups")
    return errs


def run_plan(plan: str, project: str = "") -> str:
    p = _load_plan(plan)
    errs = validate_plan(p)
    if errs:
        return "error: plan problems:\n" + "\n".join("- " + e for e in errs)
    return PLAN_KINDS[p["kind"]](p, project)
