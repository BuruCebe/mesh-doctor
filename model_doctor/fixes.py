"""One-click fixes. Each takes (context, target), where target is the object, material or
scene the finding names, and raises FixError when it can't apply."""

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from .scene_checks import _principled


class FixError(Exception):
    pass


def _local_diag(obj):
    """Bounding-box diagonal in the object's local units."""
    corners = [Vector(c) for c in obj.bound_box]
    lo = Vector(min(c[i] for c in corners) for i in range(3))
    hi = Vector(max(c[i] for c in corners) for i in range(3))
    return (hi - lo).length or 1.0


def _editable(obj):
    if obj.library or obj.data.library:
        raise FixError(f"{obj.name} is linked from another file")


def _with_bmesh(obj, fn):
    _editable(obj)
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    fn(bm)
    bm.to_mesh(me)
    bm.free()
    me.update()


def merge_by_distance(context, obj):
    dist = _local_diag(obj) * 1e-6
    _with_bmesh(obj, lambda bm: bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist))


def recalc_normals(context, obj):
    _with_bmesh(obj, lambda bm: bmesh.ops.recalc_face_normals(bm, faces=bm.faces))


def apply_scale(context, obj):
    _editable(obj)
    if obj.data.users > 1:
        raise FixError(f"{obj.name}'s mesh is shared by {obj.data.users} objects; "
                       "make it single-user first")
    scale = Matrix.Diagonal(obj.scale).to_4x4()
    obj.data.transform(scale)
    if obj.scale.x * obj.scale.y * obj.scale.z < 0:
        _with_bmesh(obj, lambda bm: bmesh.ops.reverse_faces(bm, faces=bm.faces))
    # Keep children where they are, as Apply Scale does.
    for child in obj.children:
        child.matrix_parent_inverse = scale @ child.matrix_parent_inverse
    obj.scale = (1.0, 1.0, 1.0)


def add_bevel(context, obj):
    _editable(obj)
    if "BEVEL" not in {m.type for m in obj.modifiers}:
        bevel = obj.modifiers.new("Bevel", "BEVEL")
        bevel.width = _local_diag(obj) * 0.004
        bevel.segments = 3
        bevel.limit_method = "ANGLE"
        bevel.angle_limit = math.radians(30)
        bevel.harden_normals = True
        bevel.use_clamp_overlap = True
    if "WEIGHTED_NORMAL" not in {m.type for m in obj.modifiers}:
        obj.modifiers.new("Weighted Normal", "WEIGHTED_NORMAL").keep_sharp = True
    obj.data.shade_smooth()


def shade_by_angle(context, obj):
    _editable(obj)
    obj.data.shade_smooth()
    obj.data.set_sharp_from_angle(angle=math.radians(30))


def smart_uv(context, obj):
    _editable(obj)
    view_layer = context.view_layer
    view_layer.update()
    prev_active = view_layer.objects.active
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    try:
        view_layer.objects.active = obj
    except (ValueError, RuntimeError):
        raise FixError(f"{obj.name} is not in the current view layer") from None
    try:
        with context.temp_override(active_object=obj, object=obj,
                                   selected_objects=[obj],
                                   selected_editable_objects=[obj]):
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003)
            bpy.ops.object.mode_set(mode="OBJECT")
    finally:
        view_layer.objects.active = prev_active



# --------------------------------------------------------------------------
# Materials, lighting and scene
# --------------------------------------------------------------------------

VARIATION_TAG = "model_doctor_variation"


def _socket(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)


def add_surface_variation(context, mat):
    """Roughness breakup, subtle color variation and micro bump on a flat material."""
    if mat.library:
        raise FixError(f"{mat.name} is linked from another file")
    bsdf = _principled(mat)
    if bsdf is None:
        raise FixError(f"{mat.name} has no Principled BSDF")
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    if any(n.get(VARIATION_TAG) for n in nodes):
        raise FixError(f"{mat.name} already has surface variation")
    x, y = bsdf.location

    def new(kind, dx, dy, label):
        node = nodes.new(kind)
        node.location = (x + dx, y + dy)
        node.label = label
        node[VARIATION_TAG] = True
        return node

    coord = new("ShaderNodeTexCoord", -1100, 0, "Object coordinates")

    def noise(dy, label, scale, detail):
        n = new("ShaderNodeTexNoise", -800, dy, label)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        links.new(coord.outputs["Object"], n.inputs["Vector"])
        return n

    changed = False
    if not bsdf.inputs["Roughness"].is_linked:
        r = bsdf.inputs["Roughness"].default_value
        rng = new("ShaderNodeMapRange", -500, -200, "Roughness range")
        rng.inputs["From Min"].default_value = 0.35
        rng.inputs["From Max"].default_value = 0.65
        rng.inputs["To Min"].default_value = max(0.0, r - 0.12)
        rng.inputs["To Max"].default_value = min(1.0, r + 0.12)
        links.new(noise(-200, "Roughness breakup", 6.0, 8.0).outputs["Fac"],
                  rng.inputs["Value"])
        links.new(rng.outputs["Result"], bsdf.inputs["Roughness"])
        changed = True

    if not bsdf.inputs["Base Color"].is_linked:
        c = tuple(bsdf.inputs["Base Color"].default_value)
        amount = new("ShaderNodeMapRange", -500, 250, "Variation amount")
        amount.inputs["To Min"].default_value = 0.0
        amount.inputs["To Max"].default_value = 0.35
        links.new(noise(250, "Color variation", 2.5, 4.0).outputs["Fac"],
                  amount.inputs["Value"])
        mix = new("ShaderNodeMix", -250, 250, "Color variation")
        mix.data_type = "RGBA"
        _socket(mix.inputs, "A_Color").default_value = c
        _socket(mix.inputs, "B_Color").default_value = (c[0] * 0.82, c[1] * 0.8, c[2] * 0.76, 1)
        links.new(amount.outputs["Result"], _socket(mix.inputs, "Factor_Float"))
        links.new(_socket(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
        changed = True

    if not bsdf.inputs["Normal"].is_linked:
        bump = new("ShaderNodeBump", -500, -500, "Micro bump")
        bump.inputs["Strength"].default_value = 0.08
        links.new(noise(-500, "Micro surface", 60.0, 6.0).outputs["Fac"],
                  bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        changed = True

    if not changed:
        nodes.remove(coord)
        raise FixError(f"{mat.name} already has textures on color, roughness and normal")


LIGHT_RIG = "Model Doctor Lights"


def add_light_rig(context, scene):
    """Key, fill and rim area lights sized to the scene, placed relative to the camera."""
    meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    if not meshes:
        raise FixError("Nothing to light")
    # Size the rig to the subject, not to ground planes or backdrops.
    solid = [o for o in meshes if min(o.dimensions) > 0.02 * max(o.dimensions)] or meshes
    pts = [o.matrix_world @ Vector(c) for o in solid for c in o.bound_box]
    lo = Vector(min(p[i] for p in pts) for i in range(3))
    hi = Vector(max(p[i] for p in pts) for i in range(3))
    center, radius = (lo + hi) / 2, max((hi - lo).length / 2, 0.05)

    old = bpy.data.collections.get(LIGHT_RIG)
    if old is not None:
        for o in list(old.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new(LIGHT_RIG)
    scene.collection.children.link(coll)
    target = bpy.data.objects.new("Light Target", None)
    target.location = center
    coll.objects.link(target)

    # Directions relative to the camera, so the key light always reads as the key.
    back = Vector((0, -1, 0))
    if scene.camera is not None:
        v = scene.camera.matrix_world.translation - center
        v.z = 0
        if v.length > 1e-6:
            back = v.normalized()
    up = Vector((0, 0, 1))
    right = back.cross(up).normalized()
    d = radius * 3
    rig = (
        ("Key Light", back * 0.7 - right * 0.7 + up * 0.8, 12, 0.6, (1.0, 0.95, 0.88)),
        ("Fill Light", back * 0.8 + right * 0.8 + up * 0.2, 3, 1.0, (0.85, 0.92, 1.0)),
        ("Rim Light", -back * 0.9 + right * 0.2 + up * 0.7, 9, 0.4, (1.0, 1.0, 1.0)),
    )
    for name, direction, power, size, color in rig:
        light = bpy.data.lights.new(name, "AREA")
        light.energy = power * d * d
        light.size = d * size
        light.color = color
        obj = bpy.data.objects.new(name, light)
        obj.location = center + direction.normalized() * d
        con = obj.constraints.new("TRACK_TO")
        con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
        coll.objects.link(obj)

    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
        scene.world.color = (0.05, 0.05, 0.055)


def use_agx(context, scene):
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        scene.view_settings.view_transform = "Filmic"  # Blender before 4.0
    scene.view_settings.look = "None"


def vary_copies(context, obj):
    """Jitter rotation (about local Z) and scale of every object sharing obj's mesh."""
    rng = random.Random(obj.data.name)
    for o in [o for o in context.scene.objects if o.data == obj.data]:
        if o.library:
            continue
        o.rotation_euler.z += math.radians(rng.uniform(-4, 4))
        o.scale *= rng.uniform(0.97, 1.03)


FIXES = {
    "merge_by_distance": ("Merge by Distance", merge_by_distance, False),
    "recalc_normals": ("Recalculate Normals", recalc_normals, True),
    "apply_scale": ("Apply Scale", apply_scale, True),
    "shade_by_angle": ("Shade Smooth by Angle", shade_by_angle, True),
    "add_bevel": ("Add Bevel + Weighted Normal", add_bevel, False),
    "smart_uv": ("Smart UV Project", smart_uv, False),
    "add_surface_variation": ("Add Surface Variation", add_surface_variation, False),
    "add_light_rig": ("Add Key/Fill/Rim Lights", add_light_rig, False),
    "use_agx": ("Use AgX Color", use_agx, False),
    "vary_copies": ("Vary Rotation and Scale", vary_copies, False),
}
"""key -> (label, function, safe_for_fix_all). 'Fix All' skips fixes that change the look
or that can be intentional (split vertices keep hard edges in glTF exports)."""
