"""Run: blender -b --factory-startup -P tests/test_model_doctor.py"""
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
import model_doctor  # noqa: E402
from model_doctor import checks, fixes, scene_checks  # noqa: E402

failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def codes(obj):
    bpy.context.view_layer.update()
    return {f.code for f in checks.scan([obj]) if f.target == obj.name}


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
model_doctor.register()
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
file_codes = {f.code for f in checks.scan(bpy.data.objects, bpy.data.texts) if not f.target}
check({"BOX_SCENE", "LEFTOVER_SCRIPTS"} <= file_codes, "BOX_SCENE and LEFTOVER_SCRIPTS")

# ---------------------------------------------------------------- beyond the mesh
scene = ctx.scene


def all_codes(objs=None):
    bpy.context.view_layer.update()
    objs = list(scene.objects) if objs is None else objs
    return {f.code for f in checks.scan(objs, bpy.data.texts, scene=scene)}


def by_target(name, objs=None):
    bpy.context.view_layer.update()
    objs = list(scene.objects) if objs is None else objs
    return {f.code for f in checks.scan(objs, scene=scene) if f.target == name}


# Materials: none, flat, color-only, baked lighting, missing file.
prop = new_obj("Prop", lambda bm: bmesh.ops.create_cube(bm, size=1))
check("NO_MATERIAL" in by_target("Prop", [prop]), "object without material -> NO_MATERIAL")

flat = bpy.data.materials.new("Painted_Metal")
flat.use_nodes = True
prop.data.materials.append(flat)
check("FLAT_MATERIAL" in by_target("Painted_Metal", [prop]), "plain principled -> FLAT_MATERIAL")
fixes.add_surface_variation(ctx, flat)
check("FLAT_MATERIAL" not in by_target("Painted_Metal", [prop]), "surface variation fixes it")
bsdf = scene_checks._principled(flat)
check(all(bsdf.inputs[n].is_linked for n in ("Base Color", "Roughness", "Normal")),
      "variation drives color, roughness and normal")
try:
    fixes.add_surface_variation(ctx, flat)
    check(False, "second variation is refused")
except fixes.FixError:
    check(True, "second variation is refused")


def textured(name, color, filepath=None, size=256):
    img = bpy.data.images.new(name + "_tex", size, size)
    img.pixels.foreach_set([c for _ in range(size * size) for c in color])
    if filepath:
        img.source = "FILE"
        img.filepath = filepath
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    mat.node_tree.links.new(tex.outputs["Color"],
                            scene_checks._principled(mat).inputs["Base Color"])
    o = new_obj(name + "_obj", lambda bm: bmesh.ops.create_cube(bm, size=1))
    o.data.materials.append(mat)
    return o, mat


o, m = textured("Generator_Skin", (0.6, 0.5, 0.4, 1))
c = by_target(m.name, [o])
check("COLOR_ONLY_TEXTURE" in c and "BAKED_LIGHTING" not in c, "color-only texture flagged")
fixes.add_surface_variation(ctx, m)
check("COLOR_ONLY_TEXTURE" not in by_target(m.name, [o]), "variation adds roughness/normal")

o, m = textured("Shadowed", (0.02, 0.02, 0.02, 1))
check("BAKED_LIGHTING" in by_target(m.name, [o]), "near-black albedo -> BAKED_LIGHTING")
o, m = textured("Palette", (0.6, 0.5, 0.4, 1), size=32)
check("COLOR_ONLY_TEXTURE" not in by_target(m.name, [o]), "tiny palette texture is fine")
o, m = textured("Padding", (0.0, 0.0, 0.0, 1))
check("BAKED_LIGHTING" not in by_target(m.name, [o]), "pure black padding is ignored")
o, m = textured("Lost", (0.5, 0.5, 0.5, 1), filepath="//does/not/exist.png")
check("MISSING_TEXTURE" in by_target(m.name, [o]), "missing image file -> MISSING_TEXTURE")

# UVs: shredded atlas.
def shredded(bm):
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=1)
    uv = bm.loops.layers.uv.new()
    import random as _r
    r = _r.Random(1)
    for f in bm.faces:
        for loop in f.loops:
            loop[uv].uv = (r.random(), r.random())
atlas = new_obj("Atlas", shredded)
check("FRAGMENTED_UVS" in by_target("Atlas", [atlas]), "random per-face UVs -> FRAGMENTED_UVS")
check("FRAGMENTED_UVS" not in by_target("Crate", [clean]), "clean unwrap passes")

# Camera.
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (7.3589, -6.9258, 4.9583)
check("DEFAULT_CAMERA" in all_codes(), "startup camera position -> DEFAULT_CAMERA")
cam.location = (3, -4, 1.6)
check("DEFAULT_CAMERA" not in all_codes(), "moved camera passes")

# Lighting and color management (only judged in files with a camera).
for o in [o for o in scene.objects if o.type == "LIGHT"]:
    bpy.data.objects.remove(o)
scene.world = None
check("FLAT_LIGHTING" in all_codes(), "no lights, no world -> FLAT_LIGHTING")
scene.camera = None
check("FLAT_LIGHTING" not in all_codes(), "asset file without camera: lighting not judged")
scene.camera = cam
fixes.add_light_rig(ctx, scene)
lights = [o for o in scene.objects if o.type == "LIGHT"]
check(len(lights) == 3 and "FLAT_LIGHTING" not in all_codes(), "light rig adds key/fill/rim")
fixes.add_light_rig(ctx, scene)
check(len([o for o in scene.objects if o.type == "LIGHT"]) == 3, "light rig replaces itself")
scene.view_settings.view_transform = "Standard"
check("STANDARD_VIEW" in all_codes(), "Standard view -> STANDARD_VIEW")
fixes.use_agx(ctx, scene)
check("STANDARD_VIEW" not in all_codes(), "use_agx fixes it")

# Identical clones + variation.
stone = bpy.data.meshes.new("Stone")
bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.2)
bm.to_mesh(stone)
bm.free()
clones = []
for i in range(8):
    o = bpy.data.objects.new(f"Stone_{i}", stone)
    o.location = (i * 0.5, 3, 0)
    scene.collection.objects.link(o)
    clones.append(o)
check("IDENTICAL_COPIES" in all_codes(clones), "8 identical clones -> IDENTICAL_COPIES")
fixes.vary_copies(ctx, clones[0])
check("IDENTICAL_COPIES" not in all_codes(clones), "vary_copies fixes it")

# Robotic animation.
anim = new_obj("Bouncer", lambda bm: bmesh.ops.create_cube(bm, size=0.3))
baked = new_obj("Baked_Sim", lambda bm: bmesh.ops.create_cube(bm, size=0.3))
for f in range(1, 40):
    baked.location.z = f * 0.01
    baked.keyframe_insert("location", index=2, frame=f)
check("MECHANICAL_TIMING" not in by_target("Baked_Sim", [baked]), "baked every-frame keys pass")
for i, f in enumerate(range(1, 50, 8)):
    anim.location.z = i % 2
    anim.keyframe_insert("location", index=2, frame=f)
for fc in scene_checks.fcurves(anim.animation_data.action):
    for k in fc.keyframe_points:
        k.interpolation = "LINEAR"
check("MECHANICAL_TIMING" in by_target("Bouncer", [anim]), "even linear keys -> MECHANICAL_TIMING")
fc = scene_checks.fcurves(anim.animation_data.action)[0]
fc.keyframe_points[2].co.x += 3
fc.keyframe_points[4].co.x -= 2
check("MECHANICAL_TIMING" not in by_target("Bouncer", [anim]), "varied timing passes")

# Scale and organization.
giant = new_obj("Giant", lambda bm: bmesh.ops.create_cube(bm, size=9000))
check("ODD_SCALE" in all_codes([giant]), "9 km object -> ODD_SCALE")
bpy.data.objects.remove(giant)

# Operators run end to end.
check(bpy.ops.model_doctor.scan() == {"FINISHED"}, "scan operator")
n = len(ctx.scene.model_doctor.items)
check(bpy.ops.model_doctor.fix_all() == {"FINISHED"}, "fix_all operator")
check(len(ctx.scene.model_doctor.items) <= n, "fix_all does not add findings")

model_doctor.unregister()
print(f"\n{'ALL OK' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
