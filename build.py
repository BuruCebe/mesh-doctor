"""Package the add-on as dist/mesh_doctor-<version>.zip (Blender 4.2+ extension)."""
import pathlib
import re
import zipfile

root = pathlib.Path(__file__).parent
src = root / "mesh_doctor"
version = re.search(r'(?m)^version = "(.+?)"', (src / "blender_manifest.toml").read_text()).group(1)
out = root / "dist" / f"mesh_doctor-{version}.zip"
out.parent.mkdir(exist_ok=True)

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(src.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts:
            z.write(f, f.relative_to(src))  # manifest must sit at the zip root
print(out)
