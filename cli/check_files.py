"""Batch-check .blend / .obj / .fbx / .glb / .gltf / .stl files without opening the UI.

    blender -b --factory-startup -P cli/check_files.py -- PATH [PATH ...] [--json OUT] [--all]

PATH may be a file or a folder (searched recursively). Files are opened read-only:
nothing is ever saved. By default only warnings are printed; --all adds suggestions.
Exit code is 1 if any warnings were found.
"""
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from mesh_doctor import checks  # noqa: E402

EXTS = {".blend", ".obj", ".fbx", ".glb", ".gltf", ".stl"}


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path, load_ui=False, use_scripts=False)
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path)


def expand(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                for n in sorted(names):
                    if os.path.splitext(n)[1].lower() in EXTS:
                        yield os.path.join(root, n)
        else:
            yield p


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out, show_all, paths = None, False, []
    it = iter(argv)
    for a in it:
        if a == "--json":
            out = next(it)
        elif a == "--all":
            show_all = True
        else:
            paths.append(a)
    if not paths:
        print(__doc__)
        sys.exit(2)

    report, total_warn = {}, 0
    for path in expand(paths):
        try:
            load(path)
        except Exception as e:  # unreadable or unsupported file
            print(f"\n## {path}\n  could not open: {e}")
            continue
        objs = [o for o in bpy.data.objects if o.users_scene]
        found = checks.scan(objs, bpy.data.texts, bpy.data.materials, bpy.data.images)
        warn = [f for f in found if f.severity != checks.INFO]
        total_warn += len(warn)
        report[path] = [f.__dict__ for f in found]
        print(f"\n## {path}\n  {len(warn)} warning(s), {len(found) - len(warn)} suggestion(s)")
        for f in found if show_all else warn:
            where = f"{f.object}: " if f.object else ""
            print(f"  [{f.severity}] {where}{f.message}")

    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
        print(f"\nWrote {out}")
    sys.exit(1 if total_warn else 0)


main()
