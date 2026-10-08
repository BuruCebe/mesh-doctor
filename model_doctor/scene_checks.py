"""Checks beyond the mesh: materials, textures, lighting, camera, scene layout, animation."""

import os
from collections import defaultdict

import bpy
import numpy as np
from mathutils import Vector

from .finding import ERROR, INFO, MATERIAL, SCENE, WARNING, Finding

STARTUP_CAMERA = Vector((7.3589, -6.9258, 4.9583))  # camera in Blender's default scene
COLOR_INPUTS = ("Base Color", "Roughness", "Metallic", "Normal")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _render_hidden_collections(scene):
    """Collections hidden from renders, directly or through a parent."""
    hidden = set()

    def walk(coll, parent_hidden):
        h = parent_hidden or coll.hide_render
        if h:
            hidden.add(coll.name)
        for child in coll.children:
            walk(child, h)

    if scene is not None:
        walk(scene.collection, False)
    return hidden


def _visible_meshes(objects, scene=None):
    """Meshes that actually render (skips rig widgets, helpers in hidden collections)."""
    hidden = _render_hidden_collections(scene)
    out = []
    for o in objects:
        if o.type != "MESH" or o.data is None or o.hide_render:
            continue
        colls = o.users_collection
        if colls and all(c.name in hidden or c.hide_render for c in colls):
            continue
        out.append(o)
    return out


def _principled(mat):
    if mat is None or not mat.node_tree:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def _linked(node, name):
    sock = node.inputs.get(name)
    return sock is not None and sock.is_linked


def _upstream_image(socket):
    """First image texture feeding `socket`, following links through any nodes."""
    stack, seen = [link.from_node for link in socket.links], set()
    while stack:
        node = stack.pop()
        if node.name in seen:
            continue
        seen.add(node.name)
        if node.type == "TEX_IMAGE" and node.image:
            return node.image
        for inp in node.inputs:
            stack.extend(link.from_node for link in inp.links)
    return None


def _image_missing(img):
    if img.source not in {"FILE", "SEQUENCE", "TILED"} or img.packed_file:
        return False
    if img.source == "TILED":
        return False  # UDIM paths contain a <UDIM> token; skip
    path = bpy.path.abspath(img.filepath, library=img.library)
    return bool(img.filepath) and not os.path.exists(path)


def _dark_fraction(img):
    """Share of near-black (but not pure black padding) pixels, from a ~64x64 sample."""
    try:
        w, h = img.size
        if w == 0 or h == 0:
            return None
        if w * h > 2048 * 2048 and img.source == "FILE":
            # Large file on disk: shrink a copy instead of reading every pixel.
            small = img.copy()
            try:
                small.scale(64, 64)
                px = np.empty(64 * 64 * 4, np.float32)
                small.pixels.foreach_get(px)
            finally:
                bpy.data.images.remove(small)
        else:
            # Generated or packed images can't be copied (the copy regenerates blank).
            px = np.empty(w * h * img.channels, np.float32)
            img.pixels.foreach_get(px)
            px = px.reshape(h, w, img.channels)
            px = px[::max(1, h // 64), ::max(1, w // 64)]
            if img.channels < 4:
                px = np.concatenate([px[..., :3] if img.channels >= 3 else
                                     np.repeat(px[..., :1], 3, axis=-1),
                                     np.ones(px.shape[:2] + (1,), np.float32)], axis=-1)
    except (RuntimeError, ReferenceError):
        return None
    px = px.reshape(-1, 4)
    rgb = np.clip(px[:, :3], 0, 1)
    if img.is_float:
        rgb = rgb ** (1 / 2.2)  # roughly to display values
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    opaque = px[:, 3] > 0.5
    lum = lum[opaque & (lum > 0.004)]  # pure black is usually atlas padding
    return float((lum < 0.06).mean()) if len(lum) else None


def fcurves(action):
    """All F-curves of an action, for both legacy and slotted (4.4+) actions."""
    if hasattr(action, "layers"):
        return [fc for layer in action.layers for strip in layer.strips
                for bag in strip.channelbags for fc in bag.fcurves]
    return list(action.fcurves)


def _world_is_flat(world):
    """True when the world is a single plain color (no HDRI, sky or gradient)."""
    if world is None or not world.node_tree:
        return True
    out = next((n for n in world.node_tree.nodes
                if n.type == "OUTPUT_WORLD" and n.is_active_output), None)
    if out is None or not out.inputs["Surface"].is_linked:
        return True
    src = out.inputs["Surface"].links[0].from_node
    return src.type == "BACKGROUND" and not src.inputs["Color"].is_linked


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def material_findings(meshes):
    found = []
    materials = {}
    for obj in meshes:
        mats = [s.material for s in obj.material_slots if s.material]
        if not mats:
            found.append(Finding(
                obj.name, "NO_MATERIAL", INFO,
                "No material, so it renders as default gray. Give every visible part a "
                "material that says what it's made of."))
        for m in mats:
            materials[m.name] = m

    for mat in materials.values():
        if mat.node_tree:
            missing = [n.image.name for n in mat.node_tree.nodes
                       if n.type == "TEX_IMAGE" and n.image and _image_missing(n.image)]
            if missing:
                found.append(Finding(
                    mat.name, "MISSING_TEXTURE", ERROR,
                    f"Texture file(s) not found: {', '.join(missing[:4])}. They render "
                    "pink or black. Relink them (File > External Data > Find Missing Files).",
                    kind=MATERIAL))

        bsdf = _principled(mat)
        if bsdf is None:
            continue  # custom shader: assume it's intentional
        if not any(_linked(bsdf, name) for name in COLOR_INPUTS):
            found.append(Finding(
                mat.name, "FLAT_MATERIAL", INFO,
                "One flat color and one roughness value everywhere. Real surfaces vary: "
                "add roughness breakup, slight color variation and micro bump.",
                "add_surface_variation", MATERIAL))
            continue

        img = _upstream_image(bsdf.inputs["Base Color"])
        if img is None:
            continue
        if (not _linked(bsdf, "Roughness") and not _linked(bsdf, "Normal")
                and min(img.size) > 128):  # tiny images are palette textures: fine
            found.append(Finding(
                mat.name, "COLOR_ONLY_TEXTURE", INFO,
                f"Only a color texture ({img.name}): no roughness or normal detail, so "
                "the whole surface has the same sheen. Typical of generator exports.",
                "add_surface_variation", MATERIAL))
        dark = None if _image_missing(img) else _dark_fraction(img)
        if dark is not None and dark > 0.08:
            found.append(Finding(
                mat.name, "BAKED_LIGHTING", INFO,
                f"{dark:.0%} of the color texture {img.name} is near-black. Color maps "
                "should hold no lighting; dark patches usually mean shadows or AO were "
                "baked in, which fights your scene lights. Paint them out or re-texture.",
                kind=MATERIAL))
    return found


def lighting_findings(scene, meshes):
    # Only judge lighting in files set up as a shot; asset files have no camera.
    if not meshes or scene.camera is None:
        return []
    found = []
    lights = [o for o in scene.objects if o.type == "LIGHT" and not o.hide_render]
    flat_world = _world_is_flat(scene.world)
    if not lights and flat_world:
        found.append(Finding(
            "", "FLAT_LIGHTING", WARNING,
            "No lights and a plain world color: everything is lit evenly from nowhere. "
            "Flat lighting is one of the fastest ways to look CG. Add a key/fill/rim rig "
            "or an HDRI.", "add_light_rig", SCENE))
    elif len(lights) == 1 and flat_world:
        found.append(Finding(
            "", "SINGLE_LIGHT", INFO,
            "One light and a plain world: hard shadows with no fill. Add fill and rim "
            "lights or an HDRI.", "add_light_rig", SCENE))

    if (scene.render.engine != "BLENDER_WORKBENCH"
            and scene.view_settings.view_transform == "Standard"):
        found.append(Finding(
            "", "STANDARD_VIEW", INFO,
            "Color management is set to 'Standard', which clips highlights and makes "
            "lighting look harsh and synthetic. Use AgX.", "use_agx", SCENE))
    return found


def camera_findings(scene, meshes):
    if not meshes:
        return []
    cam = scene.camera
    if cam is None:
        return []  # an asset file, not a shot
    if (cam.matrix_world.translation - STARTUP_CAMERA).length < 1e-3:
        return [Finding(
            cam.name, "DEFAULT_CAMERA", INFO,
            "Still the startup scene's camera angle. Pick a deliberate angle and lens: "
            "70-100 mm for products, eye level for things people stand next to.")]
    return []


def scene_layout_findings(scene, meshes):
    found = []
    groups = defaultdict(list)
    for o in meshes:
        groups[o.data.name].append(o)
    for data_name, objs in groups.items():
        if len(objs) < 6:
            continue
        rot = np.array([tuple(o.matrix_world.to_euler()) for o in objs])
        scl = np.array([tuple(o.matrix_world.to_scale()) for o in objs])
        if np.ptp(rot, axis=0).max() < 1e-4 and np.ptp(scl, axis=0).max() < 1e-4:
            found.append(Finding(
                objs[0].name, "IDENTICAL_COPIES", INFO,
                f"{len(objs)} copies of '{data_name}' with exactly the same rotation and "
                "scale. Real repeated objects are never perfectly identical; add slight "
                "rotation and scale variation.", "vary_copies"))

    if meshes:
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = Vector(min(p[i] for p in pts) for i in range(3))
        hi = Vector(max(p[i] for p in pts) for i in range(3))
        size = (hi - lo).length
        if size > 5000 or size < 0.01:
            found.append(Finding(
                "", "ODD_SCALE", INFO,
                f"The scene is {size:.3g} m across. Lighting falloff, depth of field and "
                "physics all assume real-world size; scale it to real units.", kind=SCENE))

    if scene is not None:
        loose = [o for o in scene.collection.objects if o.type == "MESH"]
        if len(loose) >= 40 and not scene.collection.children:
            found.append(Finding(
                "", "UNORGANIZED", INFO,
                f"{len(loose)} objects with no collections. Group parts into collections "
                "(Props, Architecture, Lights) so the file is workable.", kind=SCENE))
    return found


def animation_findings(objects):
    found = []
    for obj in objects:
        ad = obj.animation_data
        if not ad or not ad.action:
            continue
        for fc in fcurves(ad.action):
            keys = fc.keyframe_points
            if len(keys) < 4:
                continue
            frames = np.array([k.co[0] for k in keys])
            gaps = np.diff(frames)
            if gaps.min() <= 2:
                continue  # baked simulation or mocap: keys on (nearly) every frame
            even = np.ptp(gaps) < 1e-6
            all_linear = all(k.interpolation == "LINEAR" for k in keys)
            if even and (all_linear or len(keys) >= 8):
                found.append(Finding(
                    obj.name, "MECHANICAL_TIMING", INFO,
                    f"Keyframes on '{fc.data_path}' are perfectly evenly spaced"
                    f"{' and linear' if all_linear else ''}. Motion reads as robotic; vary "
                    "the timing and add ease in/out and overshoot."))
                break
    return found


def run(objects, scene=None):
    meshes = _visible_meshes(objects, scene)
    found = material_findings(meshes) + scene_layout_findings(scene, meshes)
    found += animation_findings(objects)
    if scene is not None:
        found += lighting_findings(scene, meshes) + camera_findings(scene, meshes)
    return found
