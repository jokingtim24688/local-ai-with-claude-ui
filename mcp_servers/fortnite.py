"""nightcrew-fortnite: UEFN / Fortnite Creative. There is no public UEFN editor API, so this
server does what CAN be automated well: write Verse straight into a project and lint it,
build islands (terrain + prop scatter + Verse rules + a device checklist) from plans, make
heightmaps, and open projects. Compile in UEFN: Verse > Build Verse Code."""
from __future__ import annotations

import json
import os
import re

from mcp_servers.core import Server, plan_arg, setup_workspace


def build() -> Server:
    setup_workspace()
    srv = Server("fortnite", "UEFN tools. Verse rules: `=` compares, `<>` not-equal, `and`/`or`, "
                 "`Name : type = value`, 4-space indents, `using { /Fortnite.com/Devices }`. Always "
                 "lint after writing; the user compiles in UEFN (Verse > Build Verse Code).")

    @srv.tool("UEFN installed? Which Fortnite projects exist?")
    def status() -> str:
        import engines
        return json.dumps({"uefn": engines.find_uefn()}) + "\n" + engines.uefn_list()

    @srv.tool("List the user's UEFN projects.")
    def projects() -> str:
        import engines
        return engines.uefn_list()

    @srv.tool("Write a .verse file into a UEFN project's Verse folder (or the workspace verse/ "
              "folder without a project) and lint it.",
              name="file name without .verse", code="Verse source", project="UEFN project name or path")
    def write_verse(name: str, code: str, project: str = "") -> str:
        import engines
        import tools
        name = re.sub(r"[^A-Za-z0-9_]", "", name) or "nightcrew_device"
        if project:
            path = os.path.join(engines.uefn_verse_dir(project), f"{name}.verse")
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
        else:
            path = str(tools._jail(f"verse/{name}.verse"))
            tools.write_file(f"verse/{name}.verse", code)
        issues = engines.verse_lint(code)
        return f"wrote {path}\n" + ("lint: clean" if not issues else "lint:\n- " + "\n- ".join(issues))

    @srv.tool("Lint Verse (file or inline code) for common mistakes.")
    def verse_check(file: str = "", code: str = "") -> str:
        import engines
        return engines.verse_check(file=file, code=code)

    @srv.tool("Build an island from an `island` plan JSON: 16-bit heightmap + preview, scattered props, "
              "game-rules Verse, prop-spawner Verse and a DEVICES.md checklist. With project= the Verse "
              "goes straight into that UEFN project. Pass the plan as `spec` (object) or a plan .json path.",
              spec='{"kind":"island","name":"SkyIsles","size":505,"seed":7,"style":"island","terraces":4,'
                   '"props":[{"asset":"pine_tree","count":60,"min_spacing":900}],'
                   '"devices":[{"type":"player_spawner_device","count":8}],"rules":{"mode":"elimination","score_to_win":10}}',
              plan="plan .json path (instead of spec)")
    def island(spec: dict = None, plan: str = "", project: str = "") -> str:
        import engines
        return engines.fortnite_island(plan_arg(plan, spec), project)

    @srv.tool("Make a 16-bit landscape heightmap PNG (island/hills/flat/canyon; terraces=4 for "
              "build-plateau style). Sizes 253/505/1009 match UE landscapes.")
    def heightmap(out: str = "terrain/heightmap.png", size: int = 505, seed: int = 1,
                  style: str = "island", terraces: int = 0) -> str:
        import engines
        return engines.terrain_heightmap(out, size, seed, style, terraces)

    @srv.tool("Creative devices Verse can reference (use these exact type names).")
    def devices() -> str:
        import engines
        return ", ".join(sorted(engines.KNOWN_DEVICES))

    @srv.tool("Open UEFN for the user, optionally on a project.")
    def open_uefn(project: str = "") -> str:
        import engines
        return engines.uefn_open(project)

    @srv.tool("Read a UEFN / Verse docs page (cached offline); no page = the index.")
    def docs(page: str = "") -> str:
        import apps
        return apps.fetch_docs("uefn", page) if page else apps.docs_index("uefn")

    return srv
