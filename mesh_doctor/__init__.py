"""Mesh Doctor: catch the tells of generated, scripted and unfinished geometry."""

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from . import checks, fixes

SEVERITY_ICON = {checks.ERROR: "CANCEL", checks.WARNING: "ERROR", checks.INFO: "INFO"}


class CheckItem(bpy.types.PropertyGroup):
    object: StringProperty()
    code: StringProperty()
    severity: StringProperty()
    message: StringProperty()
    fix: StringProperty()


class DoctorState(bpy.types.PropertyGroup):
    items: CollectionProperty(type=CheckItem)
    index: IntProperty()
    selected_only: BoolProperty(
        name="Selected Only", default=False,
        description="Check only the selected objects")
    show_info: BoolProperty(
        name="Show Suggestions", default=True,
        description="Also list INFO-level suggestions, not just warnings")
    scanned: BoolProperty()


def _visible_items(state):
    return [i for i in state.items if state.show_info or i.severity != checks.INFO]


def run_scan(context):
    state = context.scene.mesh_doctor
    context.view_layer.update()  # world matrices must reflect fixes just applied
    objs = context.selected_objects if state.selected_only else context.scene.objects
    found = checks.scan(objs, bpy.data.texts, bpy.data.materials, bpy.data.images)
    state.items.clear()
    for f in found:
        item = state.items.add()
        item.object, item.code, item.severity = f.object, f.code, f.severity
        item.message, item.fix = f.message, f.fix
    state.index = 0
    state.scanned = True
    return found


class MESH_DOCTOR_OT_scan(bpy.types.Operator):
    bl_idname = "mesh_doctor.scan"
    bl_label = "Scan"
    bl_description = "Check the scene (or selection) for common problems"

    def execute(self, context):
        found = run_scan(context)
        warn = sum(1 for f in found if f.severity != checks.INFO)
        self.report({"INFO"}, f"{warn} warning(s), {len(found) - warn} suggestion(s)")
        return {"FINISHED"}


class MESH_DOCTOR_OT_select(bpy.types.Operator):
    bl_idname = "mesh_doctor.select"
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


class MESH_DOCTOR_OT_fix(bpy.types.Operator):
    bl_idname = "mesh_doctor.fix"
    bl_label = "Fix"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty()
    fix: StringProperty()

    @classmethod
    def description(cls, context, props):
        label = fixes.FIXES.get(props.fix, ("Fix",))[0]
        return f"{label} on {props.name}"

    def execute(self, context):
        obj = bpy.data.objects.get(self.name)
        if obj is None or self.fix not in fixes.FIXES:
            return {"CANCELLED"}
        label, fn, _ = fixes.FIXES[self.fix]
        try:
            fn(context, obj)
        except fixes.FixError as e:
            self.report({"WARNING"}, str(e))
            return {"CANCELLED"}
        run_scan(context)
        self.report({"INFO"}, f"{label}: {obj.name}")
        return {"FINISHED"}


class MESH_DOCTOR_OT_fix_all(bpy.types.Operator):
    bl_idname = "mesh_doctor.fix_all"
    bl_label = "Fix All Safe"
    bl_description = ("Recalculate normals, apply scale and smooth shading everywhere "
                      "they were flagged. Merging, bevels and UVs are left for you to "
                      "decide")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        state = context.scene.mesh_doctor
        done, skipped = 0, []
        todo = [(i.object, i.fix) for i in state.items
                if i.fix and fixes.FIXES[i.fix][2]]
        for name, key in todo:
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            try:
                fixes.FIXES[key][1](context, obj)
                done += 1
            except fixes.FixError as e:
                skipped.append(str(e))
        run_scan(context)
        msg = f"Applied {done} fix(es)"
        if skipped:
            msg += f", skipped {len(skipped)}: {skipped[0]}"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class MESH_DOCTOR_UL_items(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop, index):
        row = layout.row(align=True)
        title = checks.TITLES.get(item.code, item.code)
        label = f"{title}  ·  {item.object}" if item.object else title
        row.label(text=label, icon=SEVERITY_ICON.get(item.severity, "DOT"))
        if item.object:
            row.operator("mesh_doctor.select", text="", icon="RESTRICT_SELECT_OFF",
                         emboss=False).name = item.object
        if item.fix:
            op = row.operator("mesh_doctor.fix", text="", icon="MODIFIER")
            op.name, op.fix = item.object, item.fix

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        show_info = data.show_info
        flags = [self.bitflag_filter_item if show_info or i.severity != checks.INFO else 0
                 for i in items]
        return flags, []


class VIEW3D_PT_mesh_doctor(bpy.types.Panel):
    bl_label = "Mesh Doctor"
    bl_idname = "VIEW3D_PT_mesh_doctor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mesh Doctor"

    def draw(self, context):
        layout = self.layout
        state = context.scene.mesh_doctor

        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("mesh_doctor.scan", icon="VIEWZOOM")
        row.operator("mesh_doctor.fix_all", icon="BRUSH_DATA")
        row = layout.row(align=True)
        row.prop(state, "selected_only")
        row.prop(state, "show_info")

        if not state.scanned:
            layout.label(text="Press Scan to check this scene.")
            return
        visible = _visible_items(state)
        if not visible:
            layout.label(text="No problems found.", icon="CHECKMARK")
            return

        warn = sum(1 for i in state.items if i.severity != checks.INFO)
        layout.label(text=f"{warn} warning(s), {len(state.items) - warn} suggestion(s)")
        layout.template_list("MESH_DOCTOR_UL_items", "", state, "items", state, "index",
                             rows=8)

        if 0 <= state.index < len(state.items):
            item = state.items[state.index]
            box = layout.box()
            col = box.column(align=True)
            col.label(text=checks.TITLES.get(item.code, item.code),
                      icon=SEVERITY_ICON.get(item.severity, "DOT"))
            if item.object:
                col.label(text=item.object, icon="OBJECT_DATA")
            for line in _wrap(item.message, max(20, int(context.region.width / 7))):
                col.label(text=line)
            if item.fix:
                op = box.operator("mesh_doctor.fix", text=fixes.FIXES[item.fix][0],
                                  icon="MODIFIER")
                op.name, op.fix = item.object, item.fix


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
    MESH_DOCTOR_OT_scan,
    MESH_DOCTOR_OT_select,
    MESH_DOCTOR_OT_fix,
    MESH_DOCTOR_OT_fix_all,
    MESH_DOCTOR_UL_items,
    VIEW3D_PT_mesh_doctor,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mesh_doctor = PointerProperty(type=DoctorState)


def unregister():
    del bpy.types.Scene.mesh_doctor
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
