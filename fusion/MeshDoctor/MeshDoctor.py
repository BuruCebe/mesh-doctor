"""Mesh Doctor for Fusion: flags the habits that make CAD models look generated or unfinished.

Install: Utilities > Add-Ins > Scripts and Add-Ins > + > select this MeshDoctor folder > Run.
Read-only: it never changes the design.
"""
import re
import traceback

import adsk.core
import adsk.fusion

DEFAULT_NAME = re.compile(r"^(Body|Component|Sketch)\d+$")
MAX_LINES = 40


def check(design):
    warnings, tips = [], []

    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        warnings.append("Direct modeling mode: no timeline, so nothing can be edited "
                        "by changing a dimension. Use parametric mode for real parts.")
    if design.userParameters.count == 0:
        tips.append("No user parameters. Drive key sizes (wall thickness, hole "
                    "diameter, overall size) from named parameters.")

    loose_sketches, default_names, mesh_comps, no_edge_breaks = [], [], [], []
    for comp in design.allComponents:
        for sk in comp.sketches:
            if not sk.isFullyConstrained:
                loose_sketches.append(f"{comp.name} / {sk.name}")
            if DEFAULT_NAME.match(sk.name):
                default_names.append(f"{comp.name} / {sk.name}")
        for body in comp.bRepBodies:
            if DEFAULT_NAME.match(body.name):
                default_names.append(f"{comp.name} / {body.name}")
        if comp != design.rootComponent and DEFAULT_NAME.match(comp.name):
            default_names.append(comp.name)
        if comp.meshBodies.count:
            mesh_comps.append(f"{comp.name} ({comp.meshBodies.count})")
        feats = comp.features
        if (comp.bRepBodies.count and feats.filletFeatures.count == 0
                and feats.chamferFeatures.count == 0):
            no_edge_breaks.append(comp.name)

    if loose_sketches:
        warnings.append(f"{len(loose_sketches)} sketch(es) not fully constrained (blue "
                        "lines). Add dimensions and constraints so edits don't break "
                        "the model: " + ", ".join(loose_sketches[:8]))
    if mesh_comps:
        warnings.append("Mesh bodies (triangles, not solid geometry): "
                        + ", ".join(mesh_comps[:8])
                        + ". Rebuild them as solids, or convert with Mesh > Convert "
                          "Mesh (prismatic) as a starting point.")
    if no_edge_breaks:
        tips.append("No fillets or chamfers in: " + ", ".join(no_edge_breaks[:8])
                    + ". Real parts have broken edges; razor-sharp edges read as CG.")
    if default_names:
        tips.append(f"{len(default_names)} default name(s) (Body1, Sketch3, ...): "
                    + ", ".join(default_names[:8]) + ". Name things for what they are.")
    return warnings, tips


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("Open a design first.", "Mesh Doctor")
            return
        warnings, tips = check(design)
        if not warnings and not tips:
            ui.messageBox("No problems found.", "Mesh Doctor")
            return
        lines = [f"WARNING: {w}" for w in warnings] + [f"TIP: {t}" for t in tips]
        text = "\n\n".join(lines[:MAX_LINES])
        app.log(text)  # also in Text Commands, for copy/paste
        ui.messageBox(text, f"Mesh Doctor: {len(warnings)} warning(s), {len(tips)} tip(s)")
    except Exception:
        if ui:
            ui.messageBox("Mesh Doctor failed:\n" + traceback.format_exc())
