"""Render the README before/after images with Mesh Doctor's own checks and fixes.

    blender -b --factory-startup -P docs/images/render.py
    python docs/images/compose.py

Every "before" must trigger the check and every "after" must clear it, or this fails.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from mesh_doctor import checks, fixes  # noqa: E402

RAW = os.path.join(HERE, "_raw")
os.makedirs(RAW, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x, scene.render.resolution_y = 640, 480
scene.render.film_transparent = False
shading = scene.display.shading
shading.light = "STUDIO"
shading.color_type = "OBJECT"
shading.show_specular_highlight = True
shading.show_cavity = False
scene.world = bpy.data.worlds.new("bg")
scene.world.color = (0.035, 0.037, 0.045)
scene.view_settings.view_transform = "Standard"

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
scene.collection.objects.link(cam)
scene.camera = cam


def make(name, build, color=(0.78, 0.78, 0.8, 1)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.color = color
    scene.collection.objects.link(obj)
    return obj


def codes(obj):
    bpy.context.view_layer.update()
    return {f.code for f in checks.scan([obj])}


def shoot(obj, path, dist=4.2, height=0.55, lens=50, extra=(), target=None):
    for o in scene.objects:
        if o.type == "MESH":
            o.hide_render = o is not obj and o not in extra
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    center = Vector(target) if target else sum(corners, Vector()) / 8
    d = Vector((0.75, -1.0, height)).normalized() * dist
    cam.location = center + d
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def expect(cond, msg):
    if not cond:
        raise SystemExit(f"image check failed: {msg}")


# 1. Razor edges -> Add Bevel + Weighted Normal ----------------------------
def housing(bm):
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(1.6, 1.0, 0.7), verts=bm.verts)
    top = max(bm.faces, key=lambda f: f.calc_center_median().z)
    bmesh.ops.inset_region(bm, faces=[top], thickness=0.12)
    bmesh.ops.translate(bm, vec=(0, 0, -0.08), verts=list({v for f in [top] for v in f.verts}))

for label, do_fix in (("edges_before", False), ("edges_after", True)):
    obj = make(label, housing)
    if do_fix:
        fixes.add_bevel(bpy.context, obj)
        expect("RAZOR_EDGES" not in codes(obj), "bevel fix should clear RAZOR_EDGES")
    else:
        expect("RAZOR_EDGES" in codes(obj), "raw housing should be RAZOR_EDGES")
    # Close-up on a corner: the default bevel is small (0.4% of the object), as it should be.
    shoot(obj, os.path.join(RAW, label + ".png"), dist=0.9, lens=60,
          target=(0.62, -0.34, 0.22))

# 2. Faceted shading -> Shade Smooth by Angle ------------------------------
def capsule(bm):
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.6)
    bmesh.ops.scale(bm, vec=(1, 1, 1.35), verts=bm.verts)

for label, do_fix in (("shading_before", False), ("shading_after", True)):
    obj = make(label, capsule)
    if do_fix:
        fixes.shade_by_angle(bpy.context, obj)
        expect("FACETED" not in codes(obj), "smooth fix should clear FACETED")
    else:
        expect("FACETED" in codes(obj), "flat cylinder should be FACETED")
    shoot(obj, os.path.join(RAW, label + ".png"), dist=3.4)

# 3. Triangle soup vs clean quads (wireframe overlay) ---------------------
def with_wire(obj):
    wire = obj.copy()
    wire.data = obj.data.copy()
    wire.name = obj.name + "_wire"
    wire.color = (0.08, 0.09, 0.11, 1)
    scene.collection.objects.link(wire)
    mod = wire.modifiers.new("w", "WIREFRAME")
    mod.thickness = 0.004
    mod.use_even_offset = False
    return wire

def soup(bm):
    bmesh.ops.create_icosphere(bm, subdivisions=6, radius=0.8)  # 20,480 tris
    for v in bm.verts:  # lumpy, like a reconstructed surface
        v.co *= 1 + 0.035 * math.sin(v.co.x * 9) * math.cos(v.co.y * 7)

def quads(bm):
    bmesh.ops.create_cube(bm, size=1.1)
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=5, use_grid_fill=True)
    for v in bm.verts:  # cube-sphere: clean quad flow
        v.co = v.co.normalized() * 0.8

s = make("soup", soup)
expect("TRIANGLE_SOUP" in codes(s), "icosphere should be TRIANGLE_SOUP")
shoot(s, os.path.join(RAW, "soup.png"), dist=3.0, extra=(with_wire(s),))
q = make("quads", quads)
q.data.shade_smooth()
expect("TRIANGLE_SOUP" not in codes(q), "quad sphere should not be soup")
shoot(q, os.path.join(RAW, "quads.png"), dist=3.0, extra=(with_wire(q),))

# 4. Demo file for the batch checker screenshot ---------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

def demo_obj(name, build):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    return o

demo_obj("mesh_0", soup)
def detail(bm):
    for i in range(48):
        g = bmesh.ops.create_cube(bm, size=0.1)
        bmesh.ops.translate(bm, verts=g["verts"], vec=((i % 8) * 0.15, (i // 8) * 0.15, 0))
demo_obj("Panel_Detail", detail)
h = demo_obj("Housing", lambda bm: bmesh.ops.create_cube(bm, size=1))
h.scale = (2, 1, 0.4)
demo_obj("Lid", lambda bm: (bmesh.ops.create_cube(bm, size=1),
                            bmesh.ops.reverse_faces(bm, faces=bm.faces)))
bpy.data.texts.new("build_scene").write("import bpy\n")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(RAW, "demo_scene.blend"))
print("RENDER_OK")
