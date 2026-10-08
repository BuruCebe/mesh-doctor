"""One-click fixes. Each takes (context, obj) and raises FixError when it can't apply."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector


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


FIXES = {
    "merge_by_distance": ("Merge by Distance", merge_by_distance, False),
    "recalc_normals": ("Recalculate Normals", recalc_normals, True),
    "apply_scale": ("Apply Scale", apply_scale, True),
    "shade_by_angle": ("Shade Smooth by Angle", shade_by_angle, True),
    "add_bevel": ("Add Bevel + Weighted Normal", add_bevel, False),
    "smart_uv": ("Smart UV Project", smart_uv, False),
}
"""key -> (label, function, safe_for_fix_all). 'Fix All' skips fixes that change the look
or that can be intentional (split vertices keep hard edges in glTF exports)."""
