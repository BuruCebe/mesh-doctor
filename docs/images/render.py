"""Render the README before/after images with Model Doctor's own checks and fixes.

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
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
from model_doctor import checks, fixes  # noqa: E402

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

# 4. Whole-scene look: flat CG defaults -> Model Doctor's fixes -------------
def build_look_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    eevee = next(i.identifier for i in
                 bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
                 if i.identifier.startswith("BLENDER_EEVEE"))
    sc.render.engine = eevee
    sc.render.resolution_x, sc.render.resolution_y = 640, 480
    sc.eevee.taa_render_samples = 64
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("Plain")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.05, 1)
    sc.world = world

    def mat(name, color, rough):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        p = m.node_tree.nodes["Principled BSDF"]
        p.inputs["Base Color"].default_value = color
        p.inputs["Roughness"].default_value = rough
        return m

    paint = mat("Painted_Steel", (0.55, 0.12, 0.08, 1), 0.35)
    floor_m = mat("Concrete", (0.42, 0.41, 0.39, 1), 0.8)
    rubber = mat("Rubber", (0.04, 0.04, 0.045, 1), 0.6)

    def part(name, build, m, loc):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        build(bm)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        o.location = loc
        o.data.materials.append(m)
        sc.collection.objects.link(o)
        return o

    floor = part("Floor", lambda bm: bmesh.ops.create_grid(bm, x_segments=1, y_segments=1,
                                                            size=4), floor_m, (0, 0, 0))
    floor.data.uv_layers.new()
    box = part("Toolbox", housing, paint, (0, 0, 0.35))
    box.data.uv_layers.new()
    wheel = part("Wheel", lambda bm: bmesh.ops.create_cone(
        bm, cap_ends=True, segments=48, radius1=0.28, radius2=0.28, depth=0.16), rubber,
        (1.15, -0.25, 0.28))
    wheel.rotation_euler = (math.radians(90), 0, math.radians(20))
    wheel.data.uv_layers.new()

    cam_obj = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    sc.collection.objects.link(cam_obj)
    sc.camera = cam_obj
    cam_obj.data.lens = 55
    cam_obj.location = (2.7, -3.3, 1.9)
    target = Vector((0.35, 0, 0.35))
    cam_obj.rotation_euler = (target - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
    return sc, (box, wheel), (paint, floor_m, rubber)


def look_codes(sc):
    bpy.context.view_layer.update()
    return {f.code for f in checks.scan(list(sc.objects), scene=sc)}


sc, parts, mats = build_look_scene()
before = look_codes(sc)
expect({"FLAT_LIGHTING", "FLAT_MATERIAL", "STANDARD_VIEW", "RAZOR_EDGES"} <= before,
       f"flat scene should be flagged, got {before}")
sc.render.filepath = os.path.join(RAW, "look_before.png")
bpy.ops.render.render(write_still=True)

for m in mats:
    fixes.add_surface_variation(bpy.context, m)
fixes.add_light_rig(bpy.context, sc)
fixes.use_agx(bpy.context, sc)
fixes.add_bevel(bpy.context, parts[0])
fixes.add_bevel(bpy.context, parts[1])
after = look_codes(sc)
expect(not ({"FLAT_LIGHTING", "FLAT_MATERIAL", "STANDARD_VIEW", "RAZOR_EDGES"} & after),
       f"fixes should clear the flags, still have {after}")
sc.render.filepath = os.path.join(RAW, "look_after.png")
bpy.ops.render.render(write_still=True)

# 5. Demo file for the batch checker screenshot ---------------------------
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
