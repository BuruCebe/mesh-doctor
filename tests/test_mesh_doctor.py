"""Run: blender -b --factory-startup -P tests/test_mesh_doctor.py"""
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mesh_doctor  # noqa: E402
from mesh_doctor import checks, fixes  # noqa: E402

failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def codes(obj):
    bpy.context.view_layer.update()
    return {f.code for f in checks.scan([obj]) if f.object == obj.name}


def new_obj(name, build):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


bpy.ops.wm.read_factory_settings(use_empty=True)
mesh_doctor.register()
ctx = bpy.context

# Triangle soup: dense, uniform, all triangles.
soup = new_obj("Scan", lambda bm: bmesh.ops.create_icosphere(bm, subdivisions=6, radius=1))
check("TRIANGLE_SOUP" in codes(soup), "icosphere(6) is triangle soup")

# Clean, beveled, smooth, unwrapped model: no warnings.
def clean_build(bm):
    bmesh.ops.create_cube(bm, size=2, calc_uvs=True)
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.05, segments=3, affect="EDGES",
                    profile=0.5)
clean = new_obj("Crate", clean_build)
clean.data.uv_layers.new()
clean.data.shade_smooth()
clean.data.set_sharp_from_angle(angle=math.radians(30))
warn = {f.code for f in checks.scan([clean]) if f.severity != checks.INFO}
check(not warn, f"beveled crate has no warnings (got {warn})")

# Loose boxes packed in one object.
def boxes(bm):
    for i in range(40):
        geom = bmesh.ops.create_cube(bm, size=0.2)
        bmesh.ops.translate(bm, verts=geom["verts"], vec=(i * 0.3, 0, 0))
kit = new_obj("Detail", boxes)
check("LOOSE_BOXES" in codes(kit), "40 cubes in one object -> LOOSE_BOXES")
check("GENERIC_NAME" not in codes(kit), "'Detail' is not a generic name")

# Inverted normals + fix.
inv = new_obj("Inverted", lambda bm: (bmesh.ops.create_cube(bm, size=1),
                                      bmesh.ops.reverse_faces(bm, faces=bm.faces)))
check("INVERTED_NORMALS" in codes(inv), "reversed cube -> INVERTED_NORMALS")
fixes.recalc_normals(ctx, inv)
check("INVERTED_NORMALS" not in codes(inv), "recalc_normals fixes it")

# Duplicate verts + fix.
def split_build(bm):
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1)
    bmesh.ops.split_edges(bm, edges=list(bm.edges))
dup = new_obj("Split", split_build)
check("DUPLICATE_VERTS" in codes(dup), "split sphere -> DUPLICATE_VERTS")
fixes.merge_by_distance(ctx, dup)
check("DUPLICATE_VERTS" not in codes(dup), "merge_by_distance fixes it")

# Non-uniform scale + fix keeps child world position.
sc = new_obj("Box", lambda bm: bmesh.ops.create_cube(bm, size=1))
sc.scale = (2, 1, 0.5)
child = new_obj("Knob", lambda bm: bmesh.ops.create_cube(bm, size=0.1))
child.parent = sc
child.location = (0.5, 0, 0)
ctx.view_layer.update()
before = child.matrix_world.translation.copy()
check("NONUNIFORM_SCALE" in codes(sc), "scale (2,1,0.5) -> NONUNIFORM_SCALE")
fixes.apply_scale(ctx, sc)
ctx.view_layer.update()
check("NONUNIFORM_SCALE" not in codes(sc), "apply_scale fixes it")
check((child.matrix_world.translation - before).length < 1e-5, "child stays in place")
check(abs(sc.dimensions.x - 2) < 1e-5, "mesh keeps its size")

# Negative scale flips normals; apply fixes both.
neg = new_obj("Mirror", lambda bm: bmesh.ops.create_cube(bm, size=1))
neg.scale = (-1, 1, 1)
ctx.view_layer.update()
check("NEGATIVE_SCALE" in codes(neg), "negative scale flagged")
fixes.apply_scale(ctx, neg)
check(not ({"NEGATIVE_SCALE", "INVERTED_NORMALS"} & codes(neg)), "apply_scale handles mirror")

# Razor edges + bevel fix; no UVs + smart UV fix.
sharp = new_obj("Panel", lambda bm: bmesh.ops.create_cube(bm, size=1))
c = codes(sharp)
check("RAZOR_EDGES" in c and "NO_UVS" in c, "plain cube -> RAZOR_EDGES and NO_UVS")
fixes.add_bevel(ctx, sharp)
fixes.smart_uv(ctx, sharp)
c = codes(sharp)
check("RAZOR_EDGES" not in c and "NO_UVS" not in c, "add_bevel and smart_uv fix them")

# Faceted curved surface + fix.
cyl = new_obj("Ball", lambda bm: bmesh.ops.create_uvsphere(
    bm, u_segments=32, v_segments=16, radius=1))
check("FACETED" in codes(cyl), "flat-shaded sphere -> FACETED")
fixes.shade_by_angle(ctx, cyl)
check("FACETED" not in codes(cyl), "shade_by_angle fixes it")

# Generic / generator names.
g = new_obj("mesh_0", lambda bm: bmesh.ops.create_cube(bm, size=1))
check("GENERIC_NAME" in codes(g), "'mesh_0' -> GENERIC_NAME")
g.name = "tripo_model"
check("GENERATOR_NAME" in codes(g), "'tripo_model' -> GENERATOR_NAME")

# Box scene + leftover scripts (file-level findings).
for i in range(25):
    new_obj(f"Part{i}", lambda bm: bmesh.ops.create_cube(bm, size=1))
t = bpy.data.texts.new("builder")
t.write("import bpy\nbpy.ops.mesh.primitive_cube_add()\n")
file_codes = {f.code for f in checks.scan(bpy.data.objects, bpy.data.texts) if not f.object}
check({"BOX_SCENE", "LEFTOVER_SCRIPTS"} <= file_codes, "BOX_SCENE and LEFTOVER_SCRIPTS")

# Operators run end to end.
check(bpy.ops.mesh_doctor.scan() == {"FINISHED"}, "scan operator")
n = len(ctx.scene.mesh_doctor.items)
check(bpy.ops.mesh_doctor.fix_all() == {"FINISHED"}, "fix_all operator")
check(len(ctx.scene.mesh_doctor.items) <= n, "fix_all does not add findings")

mesh_doctor.unregister()
print(f"\n{'ALL OK' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
