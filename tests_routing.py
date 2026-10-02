"""Typos must still reach the right skill and tools — the user types fast.

    python tests_routing.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app                                                     # noqa: E402
import skill_router                                            # noqa: E402
import tools                                                   # noqa: E402

tools.scan_skills(os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills"))

CASES = [
    # (what the user typed, domain it must reach, must the gradle tool be offered?)
    ("make a cube in blender", "blender", False), ("make a cube in blendr", "blender", False),
    ("compile the mod", "java", True), ("complie teh mod", "java", True),
    ("run teh gradel build", "java", True), ("build my minecraft mod", "java", True),
    ("delete context.txt and compile", "java", True),
    ("a fortnite island", "fortnite", False), ("a fortnite iland", "fortnite", False),
    ("write a python script", "python", False), ("write a python scrpit", "python", False),
    ("open roblax studio", "roblox", False), ("unreel level", "unreal", False),
    ("make a gear in openscad", "openscad", False),
    ("c# winforms app menu", "csharp", False), ("c++ qt app", "cpp", False),
    ("electron desktop app menu", "web", False),
]

if __name__ == "__main__":
    bad = []
    for text, want, needs_gradle in CASES:
        got = skill_router.domain_of(text)
        names = {s["function"]["name"] for s in app.lead_app_tools(text)}
        ok = got == want and (not needs_gradle or "gradle" in names)
        print(f"[{'ok' if ok else 'FAIL'}] {text:34} -> {got or '(none)':9}"
              + ("  +gradle" if "gradle" in names else ""))
        if not ok:
            bad.append(f"{text!r} -> {got!r} (wanted {want!r})")
    print("\n" + ("FAILED:\n  " + "\n  ".join(bad) if bad else
                  "all clear — every phrasing, typo or not, reaches the right skill"))
    sys.exit(1 if bad else 0)
