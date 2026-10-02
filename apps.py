"""Creative apps the agents drive: Blender, Unreal Engine, Roblox Studio.

Works on Windows and macOS. Each app is found in its standard install location,
or from a path the user sets in Customize -> Apps (apps.json in the data dir).

Path rule (same spirit as the sandbox jail): scripts and files the agents make live
in the sandbox. Existing projects (.uproject, .blend, .rbxl, Rojo projects) may also
live in folders the user explicitly registers as project roots. Nothing else.

Public docs: DOCS is an index of the official pages for each app. fetch_docs pulls a
page (official domains only), strips it to text and caches it on disk so it keeps
working offline afterwards. Condensed references also ship as skills
(blender-python, unreal-engine, roblox-studio).
"""
from __future__ import annotations

import glob as _glob
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import paths
import tools

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"
HOME = os.path.expanduser("~")
LOCAL = os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local"))

# ---- config (apps.json) ----------------------------------------------------

def _cfg_path() -> str:
    return paths.data("apps.json")


def load_cfg() -> dict:
    try:
        with open(_cfg_path(), encoding="utf-8") as f:
            c = json.load(f)
    except Exception:
        c = {}
    c.setdefault("paths", {})
    c.setdefault("projects", [])
    return c


def save_cfg(c: dict) -> None:
    with open(_cfg_path(), "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2)


# ---- detection ---------------------------------------------------------------

def _newest(patterns: list) -> str | None:
    hits = []
    for p in patterns:
        hits += [h for h in _glob.glob(p) if os.path.isfile(h)]
    if not hits:
        return None
    # highest version folder wins (UE_5.4 > UE_5.3, Blender 4.2 > 4.1); for folders
    # without a version (Roblox's version-<hash>) the newest install wins
    def key(h):
        m = re.search(r"(?:Blender|UE_)\s*(\d+(?:\.\d+)*)", h)
        ver = tuple(int(n) for n in m.group(1).split(".")) if m else ()
        return (ver, os.path.getmtime(h))
    return sorted(hits, key=key)[-1]


def _epic_installs() -> list:
    """Engine roots from the Epic launcher's own install list (catches custom drives)."""
    dat = (r"C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat" if WIN else
           os.path.join(HOME, "Library/Application Support/Epic/UnrealEngineLauncher/LauncherInstalled.dat"))
    try:
        with open(dat, encoding="utf-8") as f:
            items = json.load(f).get("InstallationList", [])
        return [i["InstallLocation"] for i in items if str(i.get("AppName", "")).startswith("UE_")]
    except Exception:
        return []


def _tool_dirs() -> list:
    """Where Roblox toolchain managers put rojo / selene / luau-analyze."""
    return [os.path.join(HOME, d, "bin") for d in (".aftman", ".rokit", ".foreman", ".cargo")]


def _which(name: str) -> str | None:
    exe = shutil.which(name)
    if exe:
        return exe
    for d in _tool_dirs():
        for n in (name + ".exe", name) if WIN else (name,):
            c = os.path.join(d, n)
            if os.path.isfile(c):
                return c
    return None


def find_blender() -> str | None:
    if WIN:
        return _newest([r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
                        r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"]) \
            or shutil.which("blender")
    if MAC:
        return _newest(["/Applications/Blender*.app/Contents/MacOS/Blender",
                        os.path.join(HOME, "Applications/Blender*.app/Contents/MacOS/Blender")]) \
            or shutil.which("blender")
    return shutil.which("blender")


def find_unreal(gui: bool = False) -> str | None:
    """UnrealEditor-Cmd (headless) or UnrealEditor (gui) for the newest engine."""
    roots = _epic_installs()
    if WIN:
        roots += _glob.glob(r"C:\Program Files\Epic Games\UE_*")
        name = "UnrealEditor.exe" if gui else "UnrealEditor-Cmd.exe"
        pats = [os.path.join(r, "Engine", "Binaries", "Win64", name) for r in roots]
    elif MAC:
        roots += _glob.glob("/Users/Shared/Epic Games/UE_*")
        # macOS has no separate -Cmd binary; the editor runs commandlets itself
        pats = [os.path.join(r, "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor")
                for r in roots]
    else:
        pats = [os.path.join(r, "Engine/Binaries/Linux/UnrealEditor") for r in roots]
    return _newest(pats)


def find_roblox() -> str | None:
    if WIN:
        return _newest([os.path.join(LOCAL, "Roblox", "Versions", "*", "RobloxStudioBeta.exe"),
                        r"C:\Program Files (x86)\Roblox\Versions\*\RobloxStudioBeta.exe",
                        r"C:\Program Files\Roblox\Versions\*\RobloxStudioBeta.exe"])
    if MAC:
        for c in ("/Applications/RobloxStudio.app/Contents/MacOS/RobloxStudio",
                  os.path.join(HOME, "Applications/RobloxStudio.app/Contents/MacOS/RobloxStudio")):
            if os.path.isfile(c):
                return c
    return None


FINDERS = {
    "blender": find_blender,
    "unreal": find_unreal,
    "roblox": find_roblox,
    "rojo": lambda: _which("rojo"),
    "luau": lambda: _which("luau-analyze") or _which("selene"),
    "openscad": lambda: __import__("engines").find_openscad(),
    "uefn": lambda: __import__("engines").find_uefn(),
    "runinroblox": lambda: _which("run-in-roblox"),
}

LABELS = {"blender": "Blender", "unreal": "Unreal Engine", "roblox": "Roblox Studio",
          "rojo": "Rojo (Roblox sync)", "luau": "luau-analyze / selene",
          "openscad": "OpenSCAD", "uefn": "UEFN (Unreal Editor for Fortnite)",
          "runinroblox": "run-in-roblox (Studio test runner)"}


def app_path(key: str) -> str | None:
    p = load_cfg()["paths"].get(key)
    if p and os.path.isfile(p):
        return p
    try:
        return FINDERS[key]()
    except Exception:
        return None


def status() -> list:
    cfg = load_cfg()
    out = []
    for k in FINDERS:
        p = app_path(k)
        out.append({"key": k, "label": LABELS[k], "path": p or "",
                    "found": bool(p), "custom": bool(cfg["paths"].get(k))})
    return out


# ---- path policy -----------------------------------------------------------

def _std_roots() -> list:
    """Documents/Unreal Projects and Documents/Fortnite Projects, where the engines keep
    projects on this PC (engines.py) — engine tools may work there directly."""
    try:
        import engines
        return engines.standard_roots()
    except Exception:
        return []


def resolve(p: str, must_exist: bool = True) -> str:
    """Relative -> inside the sandbox. Absolute -> must sit inside the sandbox or a
    registered project root. Raises ToolError otherwise."""
    if not p:
        raise tools.ToolError("empty path")
    if not os.path.isabs(p):
        j = tools._jail(p)
        if must_exist and not j.exists():
            raise tools.ToolError(f"not found in sandbox: {p}")
        return str(j)
    real = Path(p).expanduser().resolve()
    roots = [tools.SANDBOX] + [Path(r).expanduser().resolve() for r in load_cfg()["projects"] + _std_roots()]
    if not any(r and (real == r or r in real.parents) for r in roots):
        raise tools.ToolError(f"blocked: '{p}' is outside the sandbox and the registered "
                              "project folders (add it in Customize -> Apps)")
    if must_exist and not real.exists():
        raise tools.ToolError(f"not found: {p}")
    return str(real)


def _need(key: str) -> str:
    p = app_path(key)
    if not p:
        raise tools.ToolError(f"{LABELS[key]} not found — install it or set its path in "
                              "Customize -> Apps")
    return p


def _run(cmd: list, timeout: int, cwd: str | None = None) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd or str(tools.SANDBOX), capture_output=True, text=True,
                       timeout=timeout, errors="replace", stdin=subprocess.DEVNULL)   # never eat MCP stdin
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _spawn(cmd: list, cwd: str | None = None) -> None:
    kw = {"cwd": cwd or str(tools.SANDBOX)}
    if WIN:
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)


def _tail(text: str, n: int = 4000) -> str:
    return text if len(text) <= n else "…" + text[-n:]


# ---- tools -----------------------------------------------------------------

def app_status() -> str:
    rows = [f"{s['label']}: {s['path'] or 'NOT FOUND'}" for s in status()]
    roots = load_cfg()["projects"]
    rows.append("project folders: " + (", ".join(roots) if roots else "(none — sandbox only)"))
    return "\n".join(rows)


def blender_run(script: str = "", blend: str = "", args=None, timeout: int = 900,
                code: str = "", save_as: str = "", open_after: bool = False) -> str:
    """Run a bpy script headless (a sandbox file, or inline `code`). Optional: save the
    result as a .blend (`save_as`) and open it in Blender's window (`open_after`)."""
    exe = _need("blender")
    if code:
        rel = f"scripts/nc_blender_{int(time.time())}.py"
        tools.write_file(rel, code)
        script = rel
    if not script:
        raise tools.ToolError("give `script` (a .py in the sandbox) or `code`")
    run = resolve(script)
    if save_as:                                   # wrap: run the script, then save
        out = str(tools._jail(save_as)) if not os.path.isabs(save_as) else resolve(save_as, must_exist=False)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        wrap = f"scripts/nc_wrap_{int(time.time())}.py"
        tools.write_file(wrap, f"import bpy, runpy\nrunpy.run_path({run!r}, run_name='__main__')\n"
                               f"bpy.ops.wm.save_as_mainfile(filepath={out!r})\nprint('NC_SAVED', {out!r})\n")
        run = resolve(wrap)
    cmd = [exe, "-b"] + ([resolve(blend)] if blend else []) + \
          ["--python-exit-code", "1", "--python", run, "--"] + [str(a) for a in (args or [])]
    code_, out_ = _run(cmd, timeout)
    keep = [l for l in out_.splitlines() if not l.startswith(("Read prefs", "Blender quit"))]
    result = f"exit={code_}\n" + _tail("\n".join(keep))
    if code_ == 0 and save_as and open_after:
        try:
            result += "\n" + blender_open(save_as)
        except Exception as e:
            result += f"\n(couldn't open it in Blender: {e})"
    return result


def blender_open(blend: str = "") -> str:
    exe = _need("blender")
    _spawn([exe] + ([resolve(blend)] if blend else []))
    return "OK: Blender opened" + (f" with {blend}" if blend else "")


def unreal_run_python(script: str, project: str, timeout: int = 1800) -> str:
    """Run an editor Python script headless via the PythonScript commandlet.
    The project must have the 'Python Editor Script Plugin' enabled."""
    exe = _need("unreal")
    cmd = [exe, resolve(project), "-run=pythonscript", f"-script={resolve(script)}",
           "-unattended", "-nosplash", "-nullrhi", "-stdout", "-FullStdOutLogOutput"]
    code, out = _run(cmd, timeout)
    lines = out.splitlines()
    hot = [l for l in lines if re.search(r"LogPython|Error|Warning|Traceback", l)]
    body = "\n".join(hot[-80:]) + "\n--- tail ---\n" + "\n".join(lines[-25:])
    return f"exit={code}\n" + _tail(body)


def unreal_uat(args, timeout: int = 3600) -> str:
    """RunUAT (e.g. BuildCookRun) for the newest engine. args: list or string."""
    ed = _need("unreal")
    root = ed.split(os.sep + "Engine" + os.sep)[0]
    uat = os.path.join(root, "Engine", "Build", "BatchFiles", "RunUAT.bat" if WIN else "RunUAT.sh")
    if not os.path.isfile(uat):
        raise tools.ToolError(f"RunUAT not found under {root}")
    if isinstance(args, str):
        args = args.split()
    code, out = _run([uat] + [str(a) for a in args], timeout)
    return f"exit={code}\n" + _tail(out)


def unreal_open(project: str = "") -> str:
    exe = (load_cfg()["paths"].get("unreal") and _need("unreal")) or find_unreal(gui=True) \
        or _need("unreal")
    if exe.endswith(("UnrealEditor-Cmd.exe", "UE4Editor-Cmd.exe")):   # want the windowed editor
        gui = exe.replace("-Cmd.exe", ".exe")
        exe = gui if os.path.isfile(gui) else exe
    _spawn([exe] + ([resolve(project)] if project else []))
    return "OK: Unreal Editor opening" + (f" {project}" if project else "")


def roblox_open(place: str = "") -> str:
    exe = _need("roblox")
    target = resolve(place) if place else ""
    if MAC:
        app = exe.split("/Contents/")[0]
        _spawn(["open", "-a", app] + ([target] if target else []))
    else:
        _spawn([exe] + ([target] if target else []))
    return "OK: Roblox Studio opened" + (f" with {place}" if place else "")


def rojo(args) -> str:
    """Rojo CLI in the sandbox: init / build -o game.rbxlx / serve (runs in background)."""
    exe = _need("rojo")
    if isinstance(args, str):
        args = args.split()
    args = [str(a) for a in args]
    if args[:1] == ["serve"]:
        _spawn([exe] + args)
        return "OK: rojo serve running (default port 34872) — connect from the Rojo plugin in Studio"
    code, out = _run([exe] + args, 300)
    return f"exit={code}\n" + _tail(out)


def luau_check(path: str) -> str:
    """Static-check a .lua/.luau file or folder (luau-analyze, else selene)."""
    exe = _need("luau")
    code, out = _run([exe, resolve(path)], 120)
    return f"exit={code}\n" + _tail(out or "no issues")


# ---- public docs -----------------------------------------------------------

DOCS = {
    "blender": {
        "api": "https://docs.blender.org/api/current/index.html",
        "quickstart": "https://docs.blender.org/api/current/info_quickstart.html",
        "overview": "https://docs.blender.org/api/current/info_overview.html",
        "gotchas": "https://docs.blender.org/api/current/info_gotcha.html",
        "bpy.data": "https://docs.blender.org/api/current/bpy.data.html",
        "bpy.ops": "https://docs.blender.org/api/current/bpy.ops.html",
        "bpy.types": "https://docs.blender.org/api/current/bpy.types.html",
        "mesh": "https://docs.blender.org/api/current/bpy.types.Mesh.html",
        "bmesh": "https://docs.blender.org/api/current/bmesh.html",
        "mathutils": "https://docs.blender.org/api/current/mathutils.html",
        "principled-bsdf": "https://docs.blender.org/api/current/bpy.types.ShaderNodeBsdfPrincipled.html",
        "export-ops": "https://docs.blender.org/api/current/bpy.ops.export_scene.html",
        "wm-ops (obj export)": "https://docs.blender.org/api/current/bpy.ops.wm.html",
        "command-line": "https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html",
        "gltf": "https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html",
        "manual": "https://docs.blender.org/manual/en/latest/",
    },
    "unreal": {
        "home": "https://dev.epicgames.com/documentation/en-us/unreal-engine",
        "python-scripting": "https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python",
        "python-api": "https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/",
        "cpp": "https://dev.epicgames.com/documentation/en-us/unreal-engine/programming-with-cplusplus-in-unreal-engine",
        "gameplay-framework": "https://dev.epicgames.com/documentation/en-us/unreal-engine/gameplay-framework-in-unreal-engine",
        "blueprints": "https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprints-visual-scripting-in-unreal-engine",
        "uproperty": "https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-uproperties",
        "ufunction": "https://dev.epicgames.com/documentation/en-us/unreal-engine/ufunctions-in-unreal-engine",
        "enhanced-input": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input-in-unreal-engine",
        "command-line": "https://dev.epicgames.com/documentation/en-us/unreal-engine/command-line-arguments-in-unreal-engine",
        "uat": "https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-automation-tool-for-unreal-engine",
        "packaging": "https://dev.epicgames.com/documentation/en-us/unreal-engine/packaging-your-project",
    },
    "roblox": {
        "home": "https://create.roblox.com/docs",
        "scripting": "https://create.roblox.com/docs/scripting",
        "luau": "https://create.roblox.com/docs/luau",
        "client-server": "https://create.roblox.com/docs/projects/client-server",
        "remote-events": "https://create.roblox.com/docs/scripting/events/remote",
        "engine-api": "https://create.roblox.com/docs/reference/engine",
        "instance": "https://create.roblox.com/docs/reference/engine/classes/Instance",
        "task-library": "https://create.roblox.com/docs/reference/engine/libraries/task",
        "tweenservice": "https://create.roblox.com/docs/reference/engine/classes/TweenService",
        "data-stores": "https://create.roblox.com/docs/cloud-services/data-stores",
        "open-cloud": "https://create.roblox.com/docs/cloud/open-cloud",
        "rojo": "https://rojo.space/docs/v7/",
        "luau-syntax": "https://luau.org/syntax",
        "luau-types": "https://luau.org/typecheck",
    },
    "openscad": {
        "cheatsheet": "https://openscad.org/cheatsheet/",
        "manual": "https://en.wikibooks.org/wiki/OpenSCAD_User_Manual",
        "command-line": "https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/Using_OpenSCAD_in_a_command_line_environment",
        "documentation": "https://openscad.org/documentation.html",
    },
    "uefn": {
        "home": "https://dev.epicgames.com/documentation/en-us/uefn",
        "verse-reference": "https://dev.epicgames.com/documentation/en-us/uefn/verse-language-reference",
        "verse-api": "https://dev.epicgames.com/documentation/en-us/uefn/verse-api",
        "devices-api": "https://dev.epicgames.com/documentation/en-us/uefn/verse-api/fortnitedotcom/devices",
        "learn-verse": "https://dev.epicgames.com/documentation/en-us/uefn/learn-the-basics-of-writing-code-in-verse",
        "landscape": "https://dev.epicgames.com/documentation/en-us/uefn/landscape-mode-in-unreal-editor-for-fortnite",
    },
}
DOC_DOMAINS = ("docs.blender.org", "dev.epicgames.com", "create.roblox.com",
               "rojo.space", "luau.org", "luau-lang.org", "openscad.org", "en.wikibooks.org")


def _cache_file(url: str) -> str:
    d = paths.data("docs-cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")


def _page_text(page: str) -> str:
    m = re.search(r"<(main|article)\b.*?</\1>", page, flags=re.S | re.I)
    page = m.group(0) if m else page
    t = re.sub(r"<(script|style|nav|header|footer|svg)\b.*?</\1>", "", page, flags=re.S | re.I)
    t = re.sub(r"<(br|/p|/li|/h\d|/tr|/pre|/div)>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def fetch_docs(app: str = "", page: str = "", max_chars: int = 12000) -> str:
    """Official docs page as text. `page` = a key from docs_index(app) or a full URL
    on an official docs domain. Cached on disk -> works offline after one fetch."""
    url = DOCS.get(app, {}).get(page, page)
    if not url.startswith("https://") or not any(
            url.split("/")[2].endswith(d) for d in DOC_DOMAINS):
        return (f"error: not an official docs page. Use a key from docs_index('{app}') "
                f"or a URL on: {', '.join(DOC_DOMAINS)}")
    cf = _cache_file(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NightCrew docs)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            text = _page_text(r.read().decode("utf-8", "replace"))
        with open(cf, "w", encoding="utf-8") as f:
            f.write(text)
        src = "live"
    except Exception as e:
        if not os.path.isfile(cf):
            return (f"error: couldn't fetch {url} ({e}) and it isn't cached yet. "
                    f"Use the bundled skill instead: load_skill('{SKILL_FOR.get(app, '')}').")
        text = open(cf, encoding="utf-8").read()
        src = "offline cache"
    return f"[{src}] {url}\n\n" + text[:max_chars]


SKILL_FOR = {"blender": "blender-python", "unreal": "unreal-engine", "roblox": "roblox-studio",
             "openscad": "openscad-cad", "uefn": "fortnite-map-maker"}


def docs_index(app: str = "") -> str:
    apps = [app] if app in DOCS else list(DOCS)
    rows = []
    for a in apps:
        rows.append(f"# {a} (skill: {SKILL_FOR[a]})")
        rows += [f"- {k}: {u}{'  [cached]' if os.path.isfile(_cache_file(u)) else ''}"
                 for k, u in DOCS[a].items()]
    return "\n".join(rows)


def prefetch_docs(app: str = "") -> dict:
    """Download every indexed page for offline use. Returns {ok, failed}."""
    ok, failed = 0, []
    for a in ([app] if app in DOCS else list(DOCS)):
        for k in DOCS[a]:
            r = fetch_docs(a, k, max_chars=1)
            if r.startswith("[live]") or r.startswith("[offline cache]"):
                ok += 1
            else:
                failed.append(f"{a}/{k}")
    return {"ok": ok, "failed": failed}


# ---- desktop apps + websites ------------------------------------------------
# app_control opens / closes / restarts ANY installed app by name. Windows looks the
# name up in the Start menu (Get-StartApps covers Store apps like Spotify too);
# macOS uses `open -a` / AppleScript quit.

SITES = {"google": "https://www.google.com", "youtube": "https://www.youtube.com",
         "gmail": "https://mail.google.com", "github": "https://github.com",
         "roblox": "https://www.roblox.com/create", "chatgpt": "https://chatgpt.com"}
PROTECTED = {"explorer", "system", "svchost", "winlogon", "csrss", "lsass", "services", "dwm",
             "python", "pythonw", "ollama", "night crew", "nightcrew", "finder", "loginwindow",
             "windowserver", "kernel_task", "launchd"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def open_url(url: str) -> str:
    import webbrowser
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    webbrowser.open(url)
    return f"OK: opened {url} in your browser"


def _win_open(name: str) -> str | None:
    q = name.replace("'", "''")
    ps = ("$a = Get-StartApps | Where-Object { $_.Name -like '*" + q + "*' } | "
          "Sort-Object { $_.Name.Length } | Select-Object -First 1; "
          "if ($a) { Start-Process ('shell:AppsFolder\\' + $a.AppID); $a.Name }")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                       timeout=30, creationflags=0x08000000)
    found = (r.stdout or "").strip()
    if found:
        return found
    try:                                         # App Paths (chrome, msedge, excel, ...)
        subprocess.run(["cmd", "/c", "start", "", name], check=True, timeout=15,
                       capture_output=True, creationflags=0x08000000)
        return name
    except Exception:
        return None


def _open_app(name: str) -> str:
    key = _norm(name)
    if key in ("google", "googlesearch"):
        return open_url(SITES["google"])
    if WIN:
        if key == "spotify":
            try:
                os.startfile("spotify:")  # type: ignore[attr-defined]
                return "OK: opened Spotify"
            except Exception:
                pass
        got = _win_open(name)
        return f"OK: opened {got}" if got else f"error: couldn't find an app called '{name}' in the Start menu"
    if MAC:
        for n in (name, name.title()):
            if subprocess.run(["open", "-a", n], capture_output=True).returncode == 0:
                return f"OK: opened {n}"
        return f"error: no app called '{name}' in Applications"
    return f"error: opening apps isn't supported on {sys.platform}"


def _close_app(name: str) -> str:
    key = _norm(name)
    if len(key) < 3 or key in {_norm(p) for p in PROTECTED}:
        return f"error: won't close '{name}'"
    if MAC:
        r = subprocess.run(["osascript", "-e", f'quit app "{name}"'], capture_output=True, text=True)
        return f"OK: closed {name}" if r.returncode == 0 else f"error: {r.stderr.strip()[:200]}"
    try:
        import psutil
    except Exception:
        return "error: psutil missing (pip install psutil)"
    procs = [p for p in psutil.process_iter(["name", "pid"])
             if key in _norm((p.info.get("name") or "").rsplit(".", 1)[0])
             and _norm((p.info.get("name") or "").rsplit(".", 1)[0]) not in {_norm(x) for x in PROTECTED}
             and p.info["pid"] != os.getpid()]
    if not procs:
        return f"OK: {name} wasn't running"
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    _, alive = psutil.wait_procs(procs, timeout=4)
    for p in alive:
        try:
            p.kill()
        except Exception:
            pass
    return f"OK: closed {name} ({len(procs)} process{'es' if len(procs) != 1 else ''})"


def app_control(app: str = "", action: str = "open", command: str = "") -> str:
    """Open / close / restart a desktop app by name (e.g. Spotify, Chrome, Discord)."""
    action = (command or action or "open").lower().strip()
    if not app:
        return "error: which app?"
    if action in ("close", "quit", "kill", "stop"):
        return _close_app(app)
    if action in ("restart", "reopen", "relaunch"):
        first = _close_app(app)
        time.sleep(2)
        return first + "; " + _open_app(app)
    return _open_app(app)


# ---- Unreal: a playable simple level in one step ------------------------------

QUICK_LEVEL_PY = """import unreal
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
path = "/Game/Maps/{name}"
if unreal.EditorAssetLibrary.does_asset_exist(path):
    les.load_level(path)
else:
    les.new_level(path)
floor = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
floor.static_mesh_component.set_static_mesh(unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane"))
floor.set_actor_scale3d(unreal.Vector(40, 40, 1))
floor.set_actor_label("Floor")
sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 800),
                                 unreal.Rotator(roll=0.0, pitch=-40.0, yaw=30.0))
sun.set_actor_label("Sun")
for cls in (unreal.SkyAtmosphere, unreal.SkyLight, unreal.ExponentialHeightFog):
    eas.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0))
eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, 120))
les.save_current_level()
unreal.log("NC_LEVEL_OK")
"""


def _new_ue_project(name: str) -> str:
    ed = _need("unreal")
    root = ed.split(os.sep + "Engine" + os.sep)[0]
    tpl = next((os.path.join(root, "Templates", t) for t in ("TP_BlankBP", "TP_Blank")
                if os.path.isdir(os.path.join(root, "Templates", t))), None)
    if not tpl:
        raise tools.ToolError(f"no blank project template under {root}\\Templates")
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


def unreal_quick_level(name: str = "SimpleLevel", project: str = "") -> str:
    """Make a simple playable level (floor, sun, sky, fog, player start). With no
    `project`, creates a new blank Blueprint project in the sandbox first. Then opens
    it in the Unreal Editor."""
    name = re.sub(r"[^A-Za-z0-9_]", "", name) or "SimpleLevel"
    up = resolve(project) if project else _new_ue_project(name + "Project")
    script = f"scripts/nc_level_{name}.py"
    tools.write_file(script, QUICK_LEVEL_PY.replace("{name}", name))
    res = unreal_run_python(script, up)
    if "NC_LEVEL_OK" not in res:
        return "error: the level script didn't finish:\n" + res
    ini = os.path.join(os.path.dirname(up), "Config", "DefaultEngine.ini")
    try:                                          # open straight into the new level
        txt = open(ini, encoding="utf-8").read() if os.path.isfile(ini) else ""
        m = f"/Game/Maps/{name}.{name}"
        sec = "[/Script/EngineSettings.GameMapsSettings]"
        if sec not in txt:
            txt = txt.rstrip() + f"\n\n{sec}\n"
        for k in ("EditorStartupMap", "GameDefaultMap"):
            if re.search(rf"^{k}=", txt, re.M):
                txt = re.sub(rf"^{k}=.*$", f"{k}={m}", txt, flags=re.M)
            else:
                txt = txt.replace(sec, f"{sec}\n{k}={m}", 1)
        open(ini, "w", encoding="utf-8").write(txt)
    except Exception:
        pass
    return f"OK: level /Game/Maps/{name} saved in {up}\n" + unreal_open(up)


# ---- registry (MAIN only; subagents write, MAIN runs + debugs) --------------

def gradle(task: str = "build", project: str = "", timeout: int = 900) -> str:
    """Run the Gradle wrapper in a project folder (Minecraft mods, Android, plain Java).
    Finds gradlew / gradlew.bat by walking up from `project`, falling back to a `gradle`
    on PATH. Returns the tail plus every error line."""
    root = Path(resolve(project)) if project else Path(str(tools.SANDBOX))
    if root.is_file():
        root = root.parent
    wrapper, here = None, root
    for _ in range(4):
        cand = here / ("gradlew.bat" if WIN else "gradlew")
        if cand.is_file():
            wrapper, root = str(cand), here
            break
        if here.parent == here:
            break
        here = here.parent
    if wrapper is None:
        wrapper = _which("gradle")
        if not wrapper:
            raise tools.ToolError(
                f"no gradlew in {root} or its parents, and no gradle on PATH. Open the project "
                "folder in Customize -> Apps and check it really is a Gradle project.")
    cmd = [wrapper] + task.split()
    code, out = _run(cmd, max(30, min(int(timeout), 3600)), cwd=str(root))
    lines = out.splitlines()
    bad = [l for l in lines if re.search(r"error:|FAILURE|Caused by|^e: ", l)][:40]
    body = ("ERRORS:\n" + "\n".join(bad) + "\n--- tail ---\n" if bad else "") + "\n".join(lines[-40:])
    return f"exit={code} (gradle {task} in {root})\n{_tail(body, 5000)}"


REGISTRY = {
    "gradle": gradle,
    "app_status": app_status,
    "blender_run": blender_run,
    "blender_open": blender_open,
    "unreal_run_python": unreal_run_python,
    "unreal_uat": unreal_uat,
    "unreal_open": unreal_open,
    "roblox_open": roblox_open,
    "rojo": rojo,
    "luau_check": luau_check,
    "fetch_docs": fetch_docs,
    "docs_index": docs_index,
    "app_control": app_control,
    "open_url": open_url,
    "unreal_quick_level": unreal_quick_level,
    # engines.py (looked up at call time: apps <-> engines import each other)
    "openscad_render": lambda **a: __import__("engines").openscad_render(**a),
    "verse_check": lambda **a: __import__("engines").verse_check(**a),
    "run_plan": lambda **a: __import__("engines").run_plan(**a),
    "unreal_new_project": lambda **a: __import__("engines").unreal_new_project(**a),
    "terrain_heightmap": lambda **a: __import__("engines").terrain_heightmap(**a),
    "uefn_open": lambda **a: __import__("engines").uefn_open(**a),
    "uefn_list": lambda **a: __import__("engines").uefn_list(**a),
    "roblox_test": lambda **a: __import__("engines").roblox_test(**a),
}
# run code or launch programs -> approval unless Auto is on
GATED = {"gradle", "blender_run", "blender_open", "unreal_run_python", "unreal_uat", "unreal_open",
         "roblox_open", "rojo", "app_control", "unreal_quick_level", "openscad_render", "run_plan",
         "unreal_new_project", "uefn_open", "roblox_test"}


def _fn(name, desc, props=None, req=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": req or []}}}


_S = {"type": "string"}
SCHEMAS = [
    _fn("gradle", "Build/run a Gradle project (Minecraft mod, Android, Java app) with its own "
        "gradlew: task 'build', 'runClient', 'clean build', 'test'. project = the project folder "
        "(registered in Customize -> Apps). Compile errors come back with file and line.",
        {"task": _S, "project": _S, "timeout": {"type": "integer"}}),
    _fn("app_status", "Which of Blender / Unreal Engine / Roblox Studio / Rojo / luau-analyze are "
        "installed (paths) and which project folders you may touch."),
    _fn("blender_run", "Run Blender Python headless: pass inline `code` (bpy) or a sandbox `script`. "
        "save_as='models/x.blend' saves the result; open_after=true then shows it in Blender. "
        "Use for any 3D model. exit!=0 means the script raised.",
        {"code": _S, "script": _S, "save_as": _S, "open_after": {"type": "boolean"}, "blend": _S,
         "args": {"type": "array", "items": _S}}),
    _fn("blender_open", "Open Blender's window (optionally with a .blend) for the user.", {"blend": _S}),
    _fn("unreal_run_python", "Run an Unreal Editor Python script headless on a .uproject "
        "(-run=pythonscript). Needs the Python Editor Script Plugin enabled in that project.",
        {"script": _S, "project": _S}, ["script", "project"]),
    _fn("unreal_uat", "Run Unreal's RunUAT, e.g. 'BuildCookRun -project=X.uproject -platform=Win64 "
        "-clientconfig=Development -build -cook -stage -pak -archive -archivedirectory=Build'.",
        {"args": _S}, ["args"]),
    _fn("unreal_open", "Open the Unreal Editor window on a .uproject for the user.",
        {"project": _S}, ["project"]),
    _fn("roblox_open", "Open Roblox Studio (optionally with a .rbxl/.rbxlx place file).", {"place": _S}),
    _fn("rojo", "Rojo CLI in the sandbox: 'init', 'build -o game.rbxlx', 'serve' (live-sync to Studio).",
        {"args": _S}, ["args"]),
    _fn("luau_check", "Static-check Roblox Luau code (file or folder) with luau-analyze / selene.",
        {"path": _S}, ["path"]),
    _fn("app_control", "Open, close or restart ANY app on the user's computer by name "
        "(Spotify, Chrome, Discord, Steam, Blender...). action: open | close | restart.",
        {"app": _S, "action": _S}, ["app"]),
    _fn("open_url", "Open a website in the user's browser (google.com, youtube.com, ...).",
        {"url": _S}, ["url"]),
    _fn("unreal_quick_level", "Make a simple playable Unreal level in one step (floor, sun, sky, "
        "player start) and open it in the editor. No project given = creates a new one.",
        {"name": _S, "project": _S}),
    _fn("openscad_render", "Compile an OpenSCAD model to .stl + .png preview; reports errors and "
        "triangle count. Give `file` (.scad in the workspace) or inline `code`.",
        {"file": _S, "code": _S, "out": _S}),
    _fn("run_plan", "Build from a JSON plan file: kind ue_layout (Unreal level), obby (Roblox place), "
        "island (Fortnite terrain + props + Verse), terrain (heightmap). project= optional.",
        {"plan": _S, "project": _S}, ["plan"]),
    _fn("verse_check", "Offline check of a UEFN Verse file for common mistakes (UEFN does the real compile).",
        {"file": _S}, ["file"]),
    _fn("unreal_new_project", "New UE5 project from an engine template: blank, thirdperson, firstperson, "
        "topdown, vehicle. location: '' = workspace, 'pc' = Documents/Unreal Projects.",
        {"name": _S, "template": _S, "location": _S}, ["name"]),
    _fn("terrain_heightmap", "Make a 16-bit landscape heightmap PNG (style island/hills/flat/canyon, "
        "terraces=4 for Fortnite-style plateaus) for UE5 or UEFN Landscape import.",
        {"out": _S, "size": {"type": "integer"}, "seed": {"type": "integer"}, "style": _S,
         "terraces": {"type": "integer"}}),
    _fn("uefn_list", "List the user's UEFN (Fortnite) projects."),
    _fn("uefn_open", "Open UEFN, optionally on a project (name from uefn_list or a path).", {"project": _S}),
    _fn("roblox_test", "Run a Luau test script inside Roblox Studio on a place (needs run-in-roblox).",
        {"place": _S, "script": _S}, ["place", "script"]),
    _fn("fetch_docs", "Read an OFFICIAL docs page for blender / unreal / roblox (cached for offline). "
        "page = a key from docs_index or a full official docs URL.",
        {"app": _S, "page": _S}, ["app", "page"]),
    _fn("docs_index", "List the official docs pages available for blender / unreal / roblox.",
        {"app": _S}),
]


def run_tool(name: str, args: dict) -> str:
    fn = REGISTRY.get(name)
    if not fn:
        return f"error: unknown app tool {name}"
    try:
        return fn(**(args or {}))
    except tools.ToolError as e:
        return f"error: {e}"
    except subprocess.TimeoutExpired:
        return f"error: {name} timed out"
    except TypeError as e:
        return f"error: bad arguments for {name}: {e}"
    except Exception as e:
        return f"error: {name} failed: {e}"


# ---- startup: install if missing, launch in the background ------------------
# Roblox Studio installs unattended. Unreal Engine can't: Epic only ships it through
# the Epic Games Launcher behind an Epic sign-in, so we install the launcher and open
# its Unreal Engine page for the user (one-time). Everything is logged to SETUP.

import threading
import time

SETUP = {"running": False, "done": False, "log": []}
_SETUP_LOCK = threading.Lock()
EPIC_UE_URI = "com.epicgames.launcher://ue"
ROBLOX_STUDIO_PAGE = "https://create.roblox.com/docs/studio/setup"


def _log(msg: str) -> None:
    SETUP["log"].append(time.strftime("%H:%M:%S ") + msg)
    del SETUP["log"][:-60]


def find_epic_launcher() -> str | None:
    if WIN:
        return _newest([r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
                        r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
                        r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"])
    if MAC:
        for c in ("/Applications/Epic Games Launcher.app",
                  os.path.join(HOME, "Applications/Epic Games Launcher.app")):
            if os.path.isdir(c):
                return c
    return None


def _try(cmd: list, timeout: int = 1800) -> bool:
    """Run an installer command; True on exit 0. Missing tool -> False."""
    if not shutil.which(cmd[0]):
        return False
    _log("$ " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
    except Exception as e:
        _log(f"  failed: {e}")
        return False
    tail = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
    _log(f"  exit {r.returncode} {tail[0][:160]}")
    return r.returncode == 0


def _winget(pkg: str) -> bool:
    return _try(["winget", "install", "-e", "--id", pkg, "--silent",
                 "--accept-package-agreements", "--accept-source-agreements"])


def _brew_cask(*names) -> bool:
    return any(_try(["brew", "install", "--cask", n]) for n in names)


def _open_uri(uri: str) -> None:
    try:
        if WIN:
            os.startfile(uri)  # type: ignore[attr-defined]
        elif MAC:
            subprocess.Popen(["open", uri])
        else:
            subprocess.Popen(["xdg-open", uri])
    except Exception as e:
        _log(f"  couldn't open {uri}: {e}")


def install_roblox() -> bool:
    _log("Roblox Studio not found — installing")
    ok = False
    if WIN:
        ok = _winget("Roblox.RobloxStudio")
        if not ok:   # official bootstrapper: installs itself for the current user
            try:
                exe = os.path.join(paths.data("downloads"), "RobloxStudioInstaller.exe")
                os.makedirs(os.path.dirname(exe), exist_ok=True)
                _log("downloading the official Roblox Studio installer")
                urllib.request.urlretrieve("https://setup.rbxcdn.com/RobloxStudioInstaller.exe", exe)
                ok = subprocess.run([exe], timeout=1800).returncode == 0
            except Exception as e:
                _log(f"  installer download failed: {e}")
    elif MAC:
        ok = _brew_cask("roblox-studio", "robloxstudio")
    if ok and find_roblox():
        _log("Roblox Studio installed")
        return True
    _log("couldn't install Roblox Studio automatically — opening the download page")
    _open_uri(ROBLOX_STUDIO_PAGE)
    return False


def install_unreal() -> None:
    _log("Unreal Engine not found")
    if not find_epic_launcher():
        _log("installing the Epic Games Launcher (Unreal Engine ships through it)")
        if WIN:
            _winget("EpicGames.EpicGamesLauncher")
        elif MAC:
            _brew_cask("epic-games")
    if find_epic_launcher():
        _log("ONE-TIME STEP: sign in to the Epic Games Launcher -> Unreal Engine -> Install "
             "(Epic requires your account; it can't be installed silently)")
        _open_uri(EPIC_UE_URI)
    else:
        _log("couldn't install the Epic Games Launcher — get it from "
             "https://store.epicgames.com/download")


def _running(*names) -> bool:
    try:
        import psutil
        want = {n.lower() for n in names}
        return any((p.info.get("name") or "").lower() in want for p in psutil.process_iter(["name"]))
    except Exception:
        return False


def _ram_busy(limit: float = 85.0) -> float | None:
    try:
        import psutil
        pct = psutil.virtual_memory().percent
        return pct if pct >= limit else None
    except Exception:
        return None


def launch_background(exe: str) -> None:
    """Start a GUI app minimized / hidden, without stealing focus."""
    if MAC:
        app = exe.split("/Contents/")[0] if "/Contents/" in exe else exe
        subprocess.Popen(["open", "-g", "-j", "-a", app])
        return
    kw = {"cwd": os.path.dirname(exe), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if WIN:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7                        # SW_SHOWMINNOACTIVE
        kw.update(startupinfo=si, creationflags=0x00000008 | 0x00000200)
    else:
        kw["start_new_session"] = True
    subprocess.Popen([exe], **kw)


def run_setup(install: bool = True, launch: bool = True) -> None:
    """Startup pass: make sure Roblox Studio + Unreal Engine are there, then start
    them in the background. Safe to call again; one pass at a time."""
    if not _SETUP_LOCK.acquire(blocking=False):
        return
    SETUP.update(running=True, done=False)
    try:
        roblox = find_roblox() or app_path("roblox")
        if not roblox and install:
            install_roblox()
            roblox = find_roblox()
        if install and not app_path("openscad"):
            _log("OpenSCAD not found — installing")
            ok = _winget("OpenSCAD.OpenSCAD") if WIN else _brew_cask("openscad") if MAC else False
            _log("OpenSCAD installed" if ok else "couldn't install OpenSCAD automatically — https://openscad.org/downloads.html")
        unreal = find_unreal(gui=True) or app_path("unreal")
        if unreal and unreal.endswith("-Cmd.exe") and os.path.isfile(unreal.replace("-Cmd.exe", ".exe")):
            unreal = unreal.replace("-Cmd.exe", ".exe")          # launch the windowed editor
        if not unreal and install:
            install_unreal()
        _log(f"Roblox Studio: {'ready' if roblox else 'missing'} · "
             f"Unreal Engine: {'ready' if unreal else 'waiting for the Epic launcher install'}")
        if launch:
            busy = _ram_busy()
            if busy:
                _log(f"not launching apps in the background: RAM already at {busy:.0f}%")
            else:
                for label, exe, procs in (
                        ("Roblox Studio", roblox, ("RobloxStudioBeta.exe", "RobloxStudio")),
                        ("Unreal Editor", unreal, ("UnrealEditor.exe", "UnrealEditor"))):
                    if not exe:
                        continue
                    if _running(*procs):
                        _log(f"{label} already running")
                        continue
                    try:
                        launch_background(exe)
                        _log(f"{label} started in the background")
                    except Exception as e:
                        _log(f"couldn't start {label}: {e}")
    except Exception as e:
        _log(f"setup error: {e}")
    finally:
        SETUP.update(running=False, done=True)
        _SETUP_LOCK.release()


def start_setup(install: bool = True, launch: bool = True) -> None:
    threading.Thread(target=run_setup, args=(install, launch), daemon=True).start()
