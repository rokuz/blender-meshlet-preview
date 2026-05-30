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

        # Map each triangle (by its sorted vertex-index triple) to its meshlet,
        # so a viewport click can be resolved to a meshlet.
        tri = np.sort(np.asarray(result.tri_indices, dtype=np.int64).reshape(-1, 3), axis=1)
        meshlets = np.asarray(result.tri_meshlet, dtype=np.int64)
        tri_lookup = {(int(a), int(b), int(c)): int(m)
                      for (a, b, c), m in zip(tri, meshlets)}

        draw.set_result(obj.name, coords, result.tri_meshlet, result,
                        st.max_vertices, max_tri, tri_lookup=tri_lookup)
        draw.tag_redraw_all()

        self.report(
            {'INFO'},
            f"{result.meshlet_count} meshlets, {result.triangle_count} tris, "
            f"ACMR {result.global_acmr:.2f}, overdraw {result.global_overdraw:.2f}")
        return {'FINISHED'}


def _point_in_triangle(p, a, b, c):
    """Barycentric point-in-triangle test on the triangle's plane (mathutils)."""
    v0 = c - a
    v1 = b - a
    v2 = p - a
    d00 = v0.dot(v0)
    d01 = v0.dot(v1)
    d11 = v1.dot(v1)
    d20 = v2.dot(v0)
    d21 = v2.dot(v1)
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-12:
        return False
    u = (d11 * d20 - d01 * d21) / denom
    v = (d00 * d21 - d01 * d20) / denom
    return u >= -1e-4 and v >= -1e-4 and (u + v) <= 1.0 + 1e-4


def _hit_to_meshlet(obj, poly_index, location, matrix, obj_name):
    """Resolve a ray-cast hit (evaluated object + polygon + point) to a meshlet."""
    lookup = draw.get_lookup(obj_name)
    if lookup is None:
        return None
    mesh = obj.to_mesh()
    try:
        polys = mesh.polygons
        if poly_index < 0 or poly_index >= len(polys):
            return None
        verts = list(polys[poly_index].vertices)
        if len(verts) == 3:
            return lookup.get(tuple(sorted(verts)))

        # n-gon: find the loop triangle (Blender's triangulation, same one
        # meshoptimizer saw) that contains the hit point.
        mesh.calc_loop_triangles()
        loc_local = matrix.inverted() @ location
        fallback = None
        for lt in mesh.loop_triangles:
            if lt.polygon_index != poly_index:
                continue
            vi = lt.vertices
            key = tuple(sorted(vi))
            if fallback is None:
                fallback = lookup.get(key)
            a, b, c = (mesh.vertices[vi[0]].co, mesh.vertices[vi[1]].co,
                       mesh.vertices[vi[2]].co)
            if _point_in_triangle(loc_local, a, b, c):
                return lookup.get(key)
        return fallback
    finally:
        obj.to_mesh_clear()


class MESHLET_OT_pick(bpy.types.Operator):
    bl_idname = "meshlet.pick"
    bl_label = "Pick Meshlet"
    bl_description = ("Click meshlets in the viewport to highlight them as a "
                      "wireframe; click empty space to deselect, Esc to finish")
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and obj is not None and draw.has_result(obj.name))

    def invoke(self, context, event):
        self._obj_name = context.active_object.name
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(
            "Meshlet pick: Left-click a meshlet  |  Esc / Right-click to finish")
        context.window.cursor_modal_set('EYEDROPPER')
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        context.workspace.status_text_set(None)
        context.window.cursor_modal_restore()

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self._finish(context)
            return {'CANCELLED'}

        # Let the user keep navigating the viewport while picking.
        if (event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
                or event.type.startswith('NUMPAD')):
            return {'PASS_THROUGH'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Ignore clicks outside the 3D region (e.g. on the sidebar).
            if context.region is None or context.region.type != 'WINDOW':
                return {'PASS_THROUGH'}
            self._pick(context, event)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def _pick(self, context, event):
        from bpy_extras import view3d_utils

        region = context.region
        rv3d = context.region_data
        if rv3d is None:
            return
        coord = (event.mouse_region_x, event.mouse_region_y)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

        depsgraph = context.evaluated_depsgraph_get()
        hit, location, _normal, index, obj, matrix = context.scene.ray_cast(
            depsgraph, origin, direction)

        if not hit or obj is None:
            draw.set_selected(self._obj_name, -1)
            return
        name = obj.original.name
        if not draw.has_result(name):
            draw.set_selected(self._obj_name, -1)
            return
        meshlet = _hit_to_meshlet(obj, index, location, matrix, name)
        draw.set_selected(name, meshlet if meshlet is not None else -1)


class MESHLET_OT_deselect(bpy.types.Operator):
    bl_idname = "meshlet.deselect"
    bl_label = "Deselect Meshlet"
    bl_description = "Clear the highlighted meshlet"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and draw.get_selected(obj.name) >= 0

    def execute(self, context):
        draw.set_selected(context.active_object.name, -1)
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


_classes = (MESHLET_OT_recalculate, MESHLET_OT_pick, MESHLET_OT_deselect,
            MESHLET_OT_clear)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
