"""Night Crew engine CLI — every engine step the agents use, from a terminal.

    python nightcrew_cli.py status
    python nightcrew_cli.py skills route "make a fortnite island with pine trees"
    python nightcrew_cli.py plan run plans/isle.json [--project MyIsland]
    python nightcrew_cli.py scad render models/gear.scad [--out models/gear.stl] [--no-png]
    python nightcrew_cli.py ue new MyGame [--template thirdperson] [--location pc]
    python nightcrew_cli.py ue quick [--name Arena] [--project path/to/X.uproject]
    python nightcrew_cli.py ue layout plans/arena.json [--project X.uproject]
    python nightcrew_cli.py ue py scripts/tweak.py --project X.uproject
    python nightcrew_cli.py ue open X.uproject
    python nightcrew_cli.py ue package X.uproject --platform Win64 --out Builds
    python nightcrew_cli.py uefn list | open [PROJECT] | island PLAN [--project P] | verse-check FILE
    python nightcrew_cli.py roblox obby PLAN | open PLACE | test PLACE SCRIPT | rojo ARGS...
    python nightcrew_cli.py terrain heightmap terrain/hm.png [--size 505 --seed 3 --style island --terraces 4]
    python nightcrew_cli.py blender run SCRIPT [--save-as models/x.blend] [--open]

Relative paths live in the workspace: the app's workspace folder by default, or
--workspace DIR (use this inside a VM, pointed at a shared folder). Absolute paths
must be inside a registered project folder or Documents/Unreal|Fortnite Projects.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import paths
import tools
import apps
import engines
import skill_router


def _workspace(arg: str | None) -> str:
    if arg:
        return os.path.abspath(arg)
    try:
        with open(paths.data("settings.json"), encoding="utf-8") as f:
            wd = json.load(f).get("workdir")
        if wd and os.path.isdir(wd):
            return wd
    except Exception:
        pass
    return paths.data("workspace")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="nightcrew", description="Night Crew engine bridge CLI")
    ap.add_argument("--workspace", help="folder for relative paths (default: the app's workspace)")
    sub = ap.add_subparsers(dest="group", required=True)

    sub.add_parser("status")
    sk = sub.add_parser("skills").add_subparsers(dest="cmd", required=True)
    r = sk.add_parser("route"); r.add_argument("task")

    pl = sub.add_parser("plan").add_subparsers(dest="cmd", required=True)
    r = pl.add_parser("run"); r.add_argument("plan"); r.add_argument("--project", default="")

    sc = sub.add_parser("scad").add_subparsers(dest="cmd", required=True)
    r = sc.add_parser("render"); r.add_argument("file"); r.add_argument("--out", default="")
    r.add_argument("--no-png", action="store_true")

    ue = sub.add_parser("ue").add_subparsers(dest="cmd", required=True)
    r = ue.add_parser("new"); r.add_argument("name"); r.add_argument("--template", default="blank")
    r.add_argument("--location", default="")
    r = ue.add_parser("quick"); r.add_argument("--name", default="SimpleLevel"); r.add_argument("--project", default="")
    r = ue.add_parser("layout"); r.add_argument("plan"); r.add_argument("--project", default="")
    r = ue.add_parser("py"); r.add_argument("script"); r.add_argument("--project", required=True)
    r = ue.add_parser("open"); r.add_argument("project", nargs="?", default="")
    r = ue.add_parser("package"); r.add_argument("project"); r.add_argument("--platform", default="Win64")
    r.add_argument("--config", default="Shipping"); r.add_argument("--out", default="Builds")

    fn = sub.add_parser("uefn").add_subparsers(dest="cmd", required=True)
    fn.add_parser("list")
    r = fn.add_parser("open"); r.add_argument("project", nargs="?", default="")
    r = fn.add_parser("island"); r.add_argument("plan"); r.add_argument("--project", default="")
    r = fn.add_parser("verse-check"); r.add_argument("file")

    rb = sub.add_parser("roblox").add_subparsers(dest="cmd", required=True)
    r = rb.add_parser("obby"); r.add_argument("plan")
    r = rb.add_parser("open"); r.add_argument("place", nargs="?", default="")
    r = rb.add_parser("test"); r.add_argument("place"); r.add_argument("script")
    r = rb.add_parser("rojo"); r.add_argument("args", nargs=argparse.REMAINDER)

    tr = sub.add_parser("terrain").add_subparsers(dest="cmd", required=True)
    r = tr.add_parser("heightmap"); r.add_argument("out"); r.add_argument("--size", type=int, default=505)
    r.add_argument("--seed", type=int, default=1); r.add_argument("--style", default="island")
    r.add_argument("--terraces", type=int, default=0)

    bl = sub.add_parser("blender").add_subparsers(dest="cmd", required=True)
    r = bl.add_parser("run"); r.add_argument("script"); r.add_argument("--save-as", default="")
    r.add_argument("--open", action="store_true")

    a = ap.parse_args(argv)
    tools.set_sandbox(_workspace(a.workspace))
    tools.scan_skills(paths.data("skills") if os.path.isdir(paths.data("skills")) else paths.res("skills"))
    g, c = a.group, getattr(a, "cmd", "")

    try:
        if g == "status":
            out = f"workspace: {tools.SANDBOX}\n" + apps.app_status()
        elif g == "skills":
            picks = skill_router.route(a.task)
            out = (f"domain: {skill_router.domain_of(a.task) or '(none)'}\n" +
                   "\n".join(f"- {n} ({len(b)} chars)" for n, b in picks)) if picks else "no skill matched"
        elif g == "plan":
            out = engines.run_plan(a.plan, a.project)
        elif g == "scad":
            out = engines.openscad_render(a.file, out=a.out, png=not a.no_png)
        elif g == "ue":
            out = {"new": lambda: engines.unreal_new_project(a.name, a.template, a.location),
                   "quick": lambda: apps.unreal_quick_level(a.name, a.project),
                   "layout": lambda: engines.unreal_apply_layout(a.plan, a.project),
                   "py": lambda: apps.unreal_run_python(a.script, a.project),
                   "open": lambda: apps.unreal_open(a.project),
                   "package": lambda: apps.unreal_uat(
                       f'BuildCookRun -project="{apps.resolve(a.project)}" -noP4 -platform={a.platform} '
                       f'-clientconfig={a.config} -build -cook -stage -pak -archive '
                       f'-archivedirectory="{engines._out_dir(a.out)}"')}[c]()
        elif g == "uefn":
            out = {"list": engines.uefn_list,
                   "open": lambda: engines.uefn_open(a.project),
                   "island": lambda: engines.fortnite_island(a.plan, a.project),
                   "verse-check": lambda: engines.verse_check(a.file)}[c]()
        elif g == "roblox":
            out = {"obby": lambda: engines.roblox_build_obby(a.plan),
                   "open": lambda: apps.roblox_open(a.place),
                   "test": lambda: engines.roblox_test(a.place, a.script),
                   "rojo": lambda: apps.rojo(a.args)}[c]()
        elif g == "terrain":
            out = engines.terrain_heightmap(a.out, a.size, a.seed, a.style, a.terraces)
        elif g == "blender":
            out = apps.blender_run(script=a.script, save_as=a.save_as, open_after=a.open)
        else:
            ap.error("unknown command")
    except tools.ToolError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(out)
    text = str(out)
    failed = text.startswith(("error", "FAILED")) or "\nFAILED" in text or \
        (text.startswith("exit=") and not text.startswith("exit=0"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
