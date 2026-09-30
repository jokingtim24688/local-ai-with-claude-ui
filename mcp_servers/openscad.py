"""nightcrew-openscad: parametric CAD for 3D-print parts and low-poly game props. Render to
STL/3MF/OFF/AMF with a PNG preview, and read/override the model's top-level parameters
(OpenSCAD Customizer style) without editing the file."""
from __future__ import annotations

import json
import os
import re
import time

from mcp_servers.core import Server, setup_workspace

PARAM = re.compile(r"^([A-Za-z_]\w*)\s*=\s*([^;]+);\s*(?://\s*(.*))?$")


def params_of(src: str) -> list:
    """Top-level `name = value; // note` lines before the first module/function."""
    out, depth = [], 0
    for line in src.splitlines():
        s = line.strip()
        if depth == 0 and re.match(r"(module|function)\s", s):
            break
        if depth == 0:
            m = PARAM.match(s)
            if m:
                out.append({"name": m.group(1), "value": m.group(2).strip(), "note": (m.group(3) or "").strip()})
        depth += s.count("{") - s.count("}")
    return out


def _lit(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_lit(x) for x in v) + "]"
    s = str(v).strip()
    if re.fullmatch(r"-?[\d.]+(e-?\d+)?|true|false|\[.*\]|undef", s):
        return s
    return json.dumps(s)


def build() -> Server:
    setup_workspace()
    srv = Server("openscad", "OpenSCAD CAD tools. Write .scad with top-level parameters "
                 "(`width = 40; // mm`) so `render` can override them. Keep game props low-poly "
                 "($fn 24-48). Errors come back with line numbers.")

    @srv.tool("Is OpenSCAD installed?")
    def status() -> str:
        import engines
        return json.dumps({"openscad": engines.find_openscad()})

    @srv.tool("List a model's top-level parameters (name, default, comment).",
              file=".scad in the workspace")
    def parameters(file: str) -> str:
        import apps
        with open(apps.resolve(file), encoding="utf-8") as f:
            return json.dumps(params_of(f.read()))

    @srv.tool("Render a model to a mesh + PNG preview. Give `file` or inline `code`; `params` "
              "overrides top-level parameters, e.g. {\"width\": 60, \"holes\": 4}.",
              file=".scad in the workspace", code="OpenSCAD source (saved to models/)",
              params="parameter overrides", format="stl (default), 3mf, off or amf",
              out="output path (default next to the .scad)")
    def render(file: str = "", code: str = "", params: dict = None, format: str = "stl", out: str = ""):
        import apps
        import engines
        import tools
        if code:
            file = f"models/nc_{int(time.time())}.scad"
            tools.write_file(file, code)
        if not file:
            return "error: give file or code"
        src = apps.resolve(file)
        defines = {}
        if params:
            with open(src, encoding="utf-8") as f:
                known = {p["name"] for p in params_of(f.read())}
            bad = [k for k in params if k not in known]
            if bad:
                return f"error: unknown parameter(s) {bad}; this model has: {sorted(known)}"
            defines = {k: _lit(v) for k, v in params.items()}
        fmt = format.lower().lstrip(".")
        if fmt not in ("stl", "3mf", "off", "amf"):
            return "error: format must be stl, 3mf, off or amf"
        stl_out = out if (out and fmt == "stl") else ""
        res = engines.openscad_render(file=file, out=stl_out, defines=defines)
        if fmt != "stl" and "OK:" in res:
            target = engines._out_path(out) if out else os.path.splitext(src)[0] + "." + fmt
            code_, log = apps._run([engines.find_openscad(), "-o", target,
                                    *[f"-D{k}={v}" for k, v in defines.items()], src], 600)
            res += f"\n{fmt}: " + (target if code_ == 0 else "FAILED\n" + log[-800:])
        png = os.path.splitext(src)[0] + ".png"
        return (res, png) if os.path.isfile(png) and "OK:" in res else res

    @srv.tool("Show the source of a .scad file with line numbers (to fix reported errors).")
    def read(file: str) -> str:
        import apps
        with open(apps.resolve(file), encoding="utf-8") as f:
            return "\n".join(f"{i:4} {l}" for i, l in enumerate(f.read().splitlines(), 1))

    @srv.tool("Read an OpenSCAD docs page (cached offline); no page = the index.")
    def docs(page: str = "") -> str:
        import apps
        return apps.fetch_docs("openscad", page) if page else apps.docs_index("openscad")

    return srv
