"""Operators: build/recalculate meshlets and clear the overlay."""

import bpy
import numpy as np

from . import draw, meshopt


def _round_max_triangles(value):
    value = int(value)
    if value % 4:
        value += 4 - (value % 4)
    return max(4, min(512, value))


class MESHLET_OT_recalculate(bpy.types.Operator):
    bl_idname = "meshlet.recalculate"
    bl_label = "Build / Recalculate Meshlets"
    bl_description = ("Split the active mesh into meshlets with meshoptimizer and "
                      "update the viewport overlay and statistics")
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        if not meshopt.is_available():
            self.report({'ERROR'},
                        "meshoptimizer native library not found. Build it with "
                        "'python3 native/build_wheel.py'.")
            return {'CANCELLED'}

        obj = context.active_object
        st = context.scene.meshlet_preview

        # Evaluate modifiers so the preview matches what gets rendered.
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        try:
            mesh.calc_loop_triangles()
            nv = len(mesh.vertices)
            tris = mesh.loop_triangles
            nt = len(tris)
            if nv == 0 or nt == 0:
                self.report({'ERROR'}, "Mesh has no triangles to process.")
                return {'CANCELLED'}

            co = np.empty(nv * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", co)
            idx = np.empty(nt * 3, dtype=np.int32)
            tris.foreach_get("vertices", idx)
        finally:
            eval_obj.to_mesh_clear()

        max_tri = _round_max_triangles(st.max_triangles)
        try:
            result = meshopt.build(
                co, idx.astype(np.uint32),
                max_vertices=st.max_vertices,
                max_triangles=max_tri,
                cone_weight=st.cone_weight,
                optimize_first=st.optimize_first)
        except meshopt.MeshletError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        # Expand to per-triangle-corner positions in object-local space.
        coords = co.reshape(-1, 3)[result.tri_indices]
        draw.set_result(obj.name, coords, result.tri_meshlet, result,
                        st.max_vertices, max_tri)
        draw.tag_redraw_all()

        self.report(
            {'INFO'},
            f"{result.meshlet_count} meshlets, {result.triangle_count} tris, "
            f"ACMR {result.global_acmr:.2f}, overdraw {result.global_overdraw:.2f}")
        return {'FINISHED'}


class MESHLET_OT_clear(bpy.types.Operator):
    bl_idname = "meshlet.clear"
    bl_label = "Clear Meshlet Overlay"
    bl_description = "Remove the cached meshlet overlay for the active object"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and draw.has_result(obj.name)

    def execute(self, context):
        draw.clear(context.active_object.name)
        return {'FINISHED'}


_classes = (MESHLET_OT_recalculate, MESHLET_OT_clear)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
