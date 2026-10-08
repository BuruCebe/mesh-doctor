"""Mesh checks and the scan entry point. Pure data access (no operators), so it runs in
the UI and headless. Material, lighting, camera, scene and animation checks live in
scene_checks.py."""

import math
import re

import numpy as np

from . import scene_checks
from .finding import (  # noqa: F401  (re-exported for callers)
    CATEGORIES, CODES, ERROR, INFO, MATERIAL, OBJECT, SCENE, TITLES, WARNING, Finding,
)

GENERIC_NAME = re.compile(
    r"^(mesh|geometry|geom|object|obj|model|material|mat|texture|tex|image|node|default)"
    r"[_\-. ]?\d*(\.\d{3})?$", re.I)
PRIMITIVE_NAME = re.compile(
    r"^(Cube|Cylinder|Sphere|Icosphere|Plane|Cone|Torus|Circle|Grid)(\.\d{3})?$")
GENERATOR_NAME = re.compile(
    r"(tripo|meshy|rodin|hyper3d|hunyuan|trellis|luma|csm_|kaedim|sf3d|instantmesh)", re.I)

COMPONENT_VERT_LIMIT = 1_000_000  # skip loose-part analysis above this (too slow)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def _components(nv, ev):
    """Connected-component label per vertex (vectorised label propagation)."""
    lab = np.arange(nv)
    for _ in range(500):
        m = np.minimum(lab[ev[:, 0]], lab[ev[:, 1]])
        new = lab.copy()
        np.minimum.at(new, ev[:, 0], m)
        np.minimum.at(new, ev[:, 1], m)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    return lab


def mesh_metrics(obj):
    """Topology statistics for one mesh object, or None if it has no faces."""
    me = obj.data
    nv, ne, nf, nl = len(me.vertices), len(me.edges), len(me.polygons), len(me.loops)
    if nf == 0:
        return None

    co = np.empty(nv * 3, np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    ev = np.empty(ne * 2, np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    lt = np.empty(nf, np.int64)
    me.polygons.foreach_get("loop_total", lt)
    ls = np.empty(nf, np.int64)
    me.polygons.foreach_get("loop_start", ls)
    le = np.empty(nl, np.int64)
    me.loops.foreach_get("edge_index", le)
    lv = np.empty(nl, np.int64)
    me.loops.foreach_get("vertex_index", lv)
    normal = np.empty(nf * 3, np.float64)
    me.polygons.foreach_get("normal", normal)
    normal = normal.reshape(-1, 3)
    center = np.empty(nf * 3, np.float64)
    me.polygons.foreach_get("center", center)
    center = center.reshape(-1, 3)
    area = np.empty(nf, np.float64)
    me.polygons.foreach_get("area", area)
    smooth = np.empty(nf, bool)
    me.polygons.foreach_get("use_smooth", smooth)

    diag = float(np.linalg.norm(co.max(0) - co.min(0))) or 1e-9
    faces_per_edge = np.bincount(le, minlength=ne)
    valence = np.bincount(ev.ravel(), minlength=nv)
    used = valence[valence > 0]

    # Dihedral angles between the two faces of each manifold edge.
    loop_poly = np.repeat(np.arange(nf), lt)
    order = np.argsort(le, kind="stable")
    starts = np.concatenate(([0], np.cumsum(faces_per_edge)[:-1]))
    two = np.nonzero(faces_per_edge == 2)[0]
    f1 = loop_poly[order[starts[two]]]
    f2 = loop_poly[order[starts[two] + 1]]
    cos = np.einsum("ij,ij->i", normal[f1], normal[f2])
    sharp_edges = int((cos < math.cos(math.radians(60))).sum())

    # Overlapping vertices (same position within a tiny tolerance).
    key = np.round(co / (diag * 1e-6)).astype(np.int64)
    duplicate_verts = nv - len(np.unique(key, axis=0))

    # Signed volume; negative on a closed mesh means normals point inward.
    closed = not (faces_per_edge == 1).any() and not (faces_per_edge > 2).any()
    volume = float((np.einsum("ij,ij->i", center, normal) * area).sum() / 3)

    uv_split = None
    if len(me.uv_layers):
        uv = np.empty(nl * 2, np.float64)
        me.uv_layers.active.data.foreach_get("uv", uv)
        q = np.round(uv.reshape(-1, 2) * 8192).astype(np.int64)
        pairs = np.stack((lv, q[:, 0], q[:, 1]), axis=1)
        uv_split = len(np.unique(pairs, axis=0)) / max(nv, 1)

    components = box_parts = None
    if nv <= COMPONENT_VERT_LIMIT and ne:
        lab = _components(nv, ev)
        roots, comp_of_vert = np.unique(lab, return_inverse=True)
        components = len(roots)
        comp_verts = np.bincount(comp_of_vert, minlength=components)
        comp_faces = np.bincount(comp_of_vert[lv[ls]], minlength=components)
        box_parts = int(((comp_verts == 8) & (comp_faces == 6)).sum())

    sc = obj.matrix_world.to_scale()  # always positive; mirroring shows in the determinant
    return {
        "verts": nv,
        "faces": nf,
        "tri_pct": 100 * float((lt == 3).mean()),
        "quad_pct": 100 * float((lt == 4).mean()),
        "valence6_pct": 100 * float((used == 6).mean()) if len(used) else 0.0,
        "sharp_edges": sharp_edges,
        "sharp_pct": 100 * sharp_edges / max(len(two), 1),
        "boundary_edges": int((faces_per_edge == 1).sum()),
        "nonmanifold_edges": int((faces_per_edge > 2).sum()),
        "duplicate_verts": int(duplicate_verts),
        "closed": closed,
        "volume": volume,
        "components": components,
        "box_parts": box_parts,
        "smooth_pct": 100 * float(smooth.mean()),
        "has_uv": len(me.uv_layers) > 0,
        "uv_split": uv_split,
        "scale": tuple(sc),
        "mirrored": obj.matrix_world.determinant() < 0,
        "is_box": nv == 8 and nf == 6,
        "modifiers": {m.type for m in obj.modifiers},
    }


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------

def object_findings(obj, m):
    f, name = [], obj.name

    def add(code, sev, msg, fix=""):
        f.append(Finding(name, code, sev, msg, fix))

    soup = m["faces"] >= 20_000 and m["tri_pct"] >= 90 and m["valence6_pct"] >= 40
    if soup:
        add("TRIANGLE_SOUP", WARNING,
            f"Triangle soup: {m['faces']:,} evenly sized triangles with no edge flow "
            "(scan / generator style). Retopologize (Remesh in Quad mode, QuadriFlow or "
            "manual), then rebuild crisp edges.")
    elif m["tri_pct"] >= 99 and m["faces"] >= 200:
        add("TRIANGULATED", INFO,
            "Fully triangulated. Keep quads in the source file and triangulate only on export.")

    if m["faces"] >= 150_000:
        add("HEAVY", INFO,
            f"Heavy mesh ({m['faces']:,} faces). Make density follow detail: flat areas "
            "need few faces. Consider Decimate (Planar) or LODs.")

    if m["box_parts"] and m["box_parts"] >= 20 and m["box_parts"] >= 0.3 * m["components"]:
        add("LOOSE_BOXES", WARNING,
            f"Built from {m['box_parts']:,} loose boxes inside one object. Model the "
            "detail (insets, bevels, booleans) instead of stacking cubes.")

    if m["nonmanifold_edges"]:
        add("NON_MANIFOLD", WARNING,
            f"{m['nonmanifold_edges']:,} non-manifold edges (shared by 3+ faces). "
            "Select > All by Trait > Non Manifold and repair.")

    if m["duplicate_verts"] and m["duplicate_verts"] >= max(1, 0.005 * m["verts"]):
        add("DUPLICATE_VERTS", INFO,
            f"{m['duplicate_verts']:,} overlapping vertices. Common in generator and glTF "
            "exports; intentional only if they keep hard edges or UV seams split. "
            "Merge by Distance, then mark sharp edges.", "merge_by_distance")

    if m["closed"] and m["volume"] < 0:
        add("INVERTED_NORMALS", WARNING,
            "Normals point inward (negative volume). Recalculate Outside.",
            "recalc_normals")

    sx, sy, sz = m["scale"]
    if m["mirrored"]:
        add("NEGATIVE_SCALE", WARNING,
            "Negative scale (mirrored by scale). Breaks normals, bevels and exports.",
            "apply_scale")
    elif max(abs(sx - sy), abs(sy - sz), abs(sx - sz)) > 1e-4:
        add("NONUNIFORM_SCALE", WARNING,
            f"Unapplied non-uniform scale ({sx:.3g}, {sy:.3g}, {sz:.3g}). Bevels, "
            "modifiers and physics come out distorted. Apply Scale.", "apply_scale")
    elif abs(sx - 1) > 1e-4:
        add("UNAPPLIED_SCALE", INFO,
            f"Unapplied scale ({sx:.3g}). Apply it so bevel widths and physics are "
            "in real units.", "apply_scale")

    solid = m["boundary_edges"] <= 0.05 * max(m["faces"], 1)  # not leaf cards / planes
    if (solid and "BEVEL" not in m["modifiers"] and m["faces"] <= 20_000
            and m["sharp_edges"] >= 8 and m["sharp_pct"] >= 20):
        add("RAZOR_EDGES", INFO,
            f"{m['sharp_edges']:,} razor-sharp edges and no bevel. Real objects have "
            "softened edges that catch light. Add Bevel + Weighted Normal.",
            "add_bevel")

    if (m["smooth_pct"] == 0 and m["faces"] >= 200 and m["sharp_pct"] < 5
            and not soup):
        add("FACETED", INFO,
            "Curved surface is flat-shaded and looks faceted. Shade Smooth by Angle.",
            "shade_by_angle")

    if not m["has_uv"] and m["faces"] >= 6:
        add("NO_UVS", INFO,
            "No UV map, so it can't take real textures (only flat colors). Unwrap it.",
            "smart_uv")

    if m["uv_split"] and m["uv_split"] >= 2.0 and m["faces"] >= 1000 and not soup:
        add("FRAGMENTED_UVS", INFO,
            f"UVs are cut into many small pieces (each vertex split {m['uv_split']:.1f}x on "
            "average), typical of automatic atlases. Textures will show seams; re-unwrap "
            "with seams in hidden places.")
    elif m["uv_split"] and m["uv_split"] >= 2.0 and soup:
        add("FRAGMENTED_UVS", WARNING,
            "Generator-style UV atlas: shredded into many islands on a triangle-soup mesh. "
            "Retopologize first, then unwrap and re-bake or re-texture.")

    if PRIMITIVE_NAME.match(name) or GENERIC_NAME.match(name):
        add("GENERIC_NAME", INFO,
            "Default or generic name. Name parts for what they are.")
    if GENERATOR_NAME.search(name) or GENERATOR_NAME.search(obj.data.name):
        add("GENERATOR_NAME", INFO,
            "Name comes from an AI generator export. Rename it.")

    return f


def scan(objects, texts=(), materials=(), images=(), scene=None):
    """Run all checks. Objects sharing a mesh are analysed once. Pass `scene` to also
    check lighting, camera and render settings."""
    findings, seen, metrics = [], set(), []
    for obj in objects:
        if obj.type != "MESH" or obj.data is None or obj.data.name in seen:
            continue
        seen.add(obj.data.name)
        m = mesh_metrics(obj)
        if m is None:
            continue
        metrics.append(m)
        findings.extend(object_findings(obj, m))

    boxes = sum(1 for m in metrics if m["is_box"])
    if boxes >= 20 and boxes >= 0.3 * len(metrics):
        findings.append(Finding(
            "", "BOX_SCENE", WARNING,
            f"{boxes} of {len(metrics)} meshes are untouched 8-vertex boxes. Scenes "
            "built from raw primitives read as placeholder or scripted geometry.",
            kind=SCENE))

    scripts = [t.name for t in texts
               if any("import bpy" in line.body for line in list(t.lines)[:40])]
    if scripts:
        findings.append(Finding(
            "", "LEFTOVER_SCRIPTS", INFO,
            f"{len(scripts)} generator script(s) left in the file: "
            f"{', '.join(scripts[:6])}{'…' if len(scripts) > 6 else ''}. "
            "They're clutter for anyone opening the file; remove them before sharing.",
            kind=SCENE))

    generic = [d.name for d in (*materials, *images)
               if GENERIC_NAME.match(d.name) or GENERATOR_NAME.search(d.name)]
    if generic:
        findings.append(Finding(
            "", "GENERIC_DATA_NAMES", INFO,
            f"Generic or generator material/texture names: {', '.join(generic[:6])}. "
            "Name materials for what they are (Brushed_Steel, Oak_Worn).", kind=SCENE))

    findings.extend(scene_checks.run(objects, scene))

    order = {ERROR: 0, WARNING: 1, INFO: 2}
    findings.sort(key=lambda x: (order[x.severity], CATEGORIES.index(x.category),
                                 x.target, x.code))
    return findings
