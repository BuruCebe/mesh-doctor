"""Model Doctor: find and fix what makes 3D work look generated or unfinished."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from . import checks, fixes

SEVERITY_ICON = {checks.ERROR: "CANCEL", checks.WARNING: "ERROR", checks.INFO: "INFO"}
KIND_ICON = {checks.OBJECT: "OBJECT_DATA", checks.MATERIAL: "MATERIAL",
             checks.SCENE: "SCENE_DATA"}


class CheckItem(bpy.types.PropertyGroup):
    target: StringProperty()
    kind: StringProperty()
    category: StringProperty()
    code: StringProperty()
    severity: StringProperty()
    message: StringProperty()
    fix: StringProperty()


class DoctorState(bpy.types.PropertyGroup):
    items: CollectionProperty(type=CheckItem)
    index: IntProperty()
    selected_only: BoolProperty(
        name="Selected Only", default=False,
        description="Check only the selected objects (lighting and camera are always checked)")
    show_info: BoolProperty(
        name="Show Suggestions", default=True,
        description="Also list suggestions, not just warnings")
    category: EnumProperty(
        name="Show",
        items=[("ALL", "All Categories", "")] + [(c, c, "") for c in checks.CATEGORIES])
    scanned: BoolProperty()


def _shown(state, item):
    return ((state.show_info or item.severity != checks.INFO)
            and state.category in ("ALL", item.category))


def _resolve(context, kind, name):
    if kind == checks.MATERIAL:
        return bpy.data.materials.get(name)
    if kind == checks.SCENE:
        return context.scene
    return bpy.data.objects.get(name)


def run_scan(context):
    state = context.scene.model_doctor
    context.view_layer.update()  # world matrices must reflect fixes just applied
    objs = context.selected_objects if state.selected_only else context.scene.objects
    found = checks.scan(objs, bpy.data.texts, bpy.data.materials, bpy.data.images,
                        scene=context.scene)
    state.items.clear()
    for f in found:
        item = state.items.add()
        item.target, item.kind, item.category = f.target, f.kind, f.category
        item.code, item.severity, item.message, item.fix = f.code, f.severity, f.message, f.fix
    state.index = 0
    state.scanned = True
    return found


def _apply(context, kind, name, key):
    target = _resolve(context, kind, name)
    if target is None:
        raise fixes.FixError(f"{name} no longer exists")
    fixes.FIXES[key][1](context, target)


class MODEL_DOCTOR_OT_scan(bpy.types.Operator):
    bl_idname = "model_doctor.scan"
    bl_label = "Scan"
    bl_description = "Check the scene (or selection) for common problems"

    def execute(self, context):
        found = run_scan(context)
        warn = sum(1 for f in found if f.severity != checks.INFO)
        self.report({"INFO"}, f"{warn} warning(s), {len(found) - warn} suggestion(s)")
        return {"FINISHED"}


class MODEL_DOCTOR_OT_select(bpy.types.Operator):
    bl_idname = "model_doctor.select"
    bl_label = "Select Object"
    bl_description = "Select this object and make it active"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty()

    def execute(self, context):
        obj = context.scene.objects.get(self.name)
        if obj is None:
            self.report({"WARNING"}, f"{self.name} not found in this scene")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


class MODEL_DOCTOR_OT_fix(bpy.types.Operator):
    bl_idname = "model_doctor.fix"
    bl_label = "Fix"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty()
    kind: StringProperty(default=checks.OBJECT)
    fix: StringProperty()

    @classmethod
    def description(cls, context, props):
        label = fixes.FIXES.get(props.fix, ("Fix",))[0]
        return f"{label} on {props.name}" if props.name else label

    def execute(self, context):
        if self.fix not in fixes.FIXES:
            return {"CANCELLED"}
        try:
            _apply(context, self.kind, self.name, self.fix)
        except fixes.FixError as e:
            self.report({"WARNING"}, str(e))
            return {"CANCELLED"}
        run_scan(context)
        self.report({"INFO"}, fixes.FIXES[self.fix][0] + (f": {self.name}" if self.name else ""))
        return {"FINISHED"}


class MODEL_DOCTOR_OT_fix_all(bpy.types.Operator):
    bl_idname = "model_doctor.fix_all"
    bl_label = "Fix All Safe"
    bl_description = ("Recalculate normals, apply scale and smooth shading everywhere "
                      "they were flagged. Anything that changes the look (bevels, "
                      "materials, lights, UVs) is left for you to decide")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        state = context.scene.model_doctor
        done, skipped = 0, []
        todo = [(i.kind, i.target, i.fix) for i in state.items
                if i.fix and fixes.FIXES[i.fix][2]]
        for kind, name, key in todo:
            try:
                _apply(context, kind, name, key)
                done += 1
            except fixes.FixError as e:
                skipped.append(str(e))
        run_scan(context)
        msg = f"Applied {done} fix(es)"
        if skipped:
            msg += f", skipped {len(skipped)}: {skipped[0]}"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


def _fix_button(layout, item, text=""):
    op = layout.operator("model_doctor.fix", text=text, icon="MODIFIER")
    op.name, op.kind, op.fix = item.target, item.kind, item.fix


class MODEL_DOCTOR_UL_items(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        title = checks.TITLES.get(item.code, item.code)
        label = f"{title}  ·  {item.target}" if item.target else title
        row.label(text=label, icon=SEVERITY_ICON.get(item.severity, "DOT"))
        if item.target and item.kind == checks.OBJECT:
            row.operator("model_doctor.select", text="", icon="RESTRICT_SELECT_OFF",
                         emboss=False).name = item.target
        if item.fix:
            _fix_button(row, item)

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        return [self.bitflag_filter_item if _shown(data, i) else 0 for i in items], []


class VIEW3D_PT_model_doctor(bpy.types.Panel):
    bl_label = "Model Doctor"
    bl_idname = "VIEW3D_PT_model_doctor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Model Doctor"

    def draw(self, context):
        layout = self.layout
        state = context.scene.model_doctor

        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("model_doctor.scan", icon="VIEWZOOM")
        row.operator("model_doctor.fix_all", icon="BRUSH_DATA")
        row = layout.row(align=True)
        row.prop(state, "selected_only")
        row.prop(state, "show_info")

        if not state.scanned:
            layout.label(text="Press Scan to check this scene.")
            return
        if not any(_shown(state, i) for i in state.items) and state.category == "ALL":
            layout.label(text="No problems found.", icon="CHECKMARK")
            return

        warn = sum(1 for i in state.items if i.severity != checks.INFO)
        layout.label(text=f"{warn} warning(s), {len(state.items) - warn} suggestion(s)")
        layout.prop(state, "category", text="")
        layout.template_list("MODEL_DOCTOR_UL_items", "", state, "items", state, "index",
                             rows=8)

        if 0 <= state.index < len(state.items) and _shown(state, state.items[state.index]):
            item = state.items[state.index]
            box = layout.box()
            col = box.column(align=True)
            col.label(text=f"{checks.TITLES.get(item.code, item.code)}  ({item.category})",
                      icon=SEVERITY_ICON.get(item.severity, "DOT"))
            if item.target:
                col.label(text=item.target, icon=KIND_ICON.get(item.kind, "DOT"))
            for line in _wrap(item.message, max(20, int(context.region.width / 7))):
                col.label(text=line)
            if item.fix:
                _fix_button(box, item, fixes.FIXES[item.fix][0])


def _wrap(text, width):
    lines, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width and line:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else lines


classes = (
    CheckItem,
    DoctorState,
    MODEL_DOCTOR_OT_scan,
    MODEL_DOCTOR_OT_select,
    MODEL_DOCTOR_OT_fix,
    MODEL_DOCTOR_OT_fix_all,
    MODEL_DOCTOR_UL_items,
    VIEW3D_PT_model_doctor,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.model_doctor = PointerProperty(type=DoctorState)


def unregister():
    del bpy.types.Scene.model_doctor
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
