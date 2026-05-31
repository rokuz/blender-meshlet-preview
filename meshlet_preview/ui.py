"""Sidebar (N-panel) UI for the Meshlet Preview addon."""

import bpy

from . import draw, meshopt


class VIEW3D_PT_meshlet_preview(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Meshlet"
    bl_label = "Meshlet Preview"

    def draw(self, context):
        layout = self.layout
        st = context.scene.meshlet_preview

        if not meshopt.is_available():
            box = layout.box()
            box.alert = True
            box.label(text="meshoptimizer library not found", icon='ERROR')
            box.label(text="Build: python3 native/build_wheel.py")
            return

        obj = context.active_object

        col = layout.column(align=True)
        col.label(text="Meshlet Parameters:")
        col.prop(st, "max_vertices")
        col.prop(st, "max_triangles")
        col.prop(st, "cone_weight")
        col.prop(st, "optimize_first")
        col.prop(st, "sliver_threshold")

        row = layout.row()
        row.scale_y = 1.4
        row.operator("meshlet.recalculate", icon='MOD_REMESH')

        layout.separator()

        col = layout.column(align=True)
        col.label(text="Visualization:")
        col.prop(st, "view_mode", text="")
        row = col.row(align=True)
        row.prop(st, "show_overlay", toggle=True)
        row.prop(st, "overlay_alpha", text="Opacity", slider=True)
        col.prop(st, "show_degenerate")

        self._draw_legend(layout, st.view_mode)

        stats = draw.get_stats(obj.name) if obj else None
        if stats:
            row = layout.row(align=True)
            row.operator("meshlet.pick", icon='EYEDROPPER')
            sub = row.row(align=True)
            sub.enabled = draw.get_selected(obj.name) >= 0
            sub.operator("meshlet.deselect", text="", icon='X')

            self._draw_selected(layout, draw.get_selected_info(obj.name))
            self._draw_stats(layout, stats)
            layout.operator("meshlet.clear", icon='TRASH', text="Clear Overlay")
        elif obj and obj.type == 'MESH':
            layout.label(text="Press the button to build meshlets.", icon='INFO')
        else:
            layout.label(text="Select a mesh object.", icon='INFO')

    def _draw_legend(self, layout, mode):
        box = layout.box()
        if mode == 'PARTITION':
            box.label(text="Each color = one meshlet", icon='COLOR')
        elif mode == 'FILL':
            box.label(text="green = full · red = wasteful", icon='COLOR')
        elif mode == 'CONE':
            box.label(text="green = tight cone · red = uncullable", icon='COLOR')
        elif mode == 'OVERDRAW':
            box.label(text="green = ~1.0 · red = high overdraw", icon='COLOR')
        elif mode == 'ACMR':
            box.label(text="green = good order · red = cache misses", icon='COLOR')
        elif mode == 'GEOMETRY':
            box.label(text="green = clean · red = slivers / stringy", icon='COLOR')

    def _draw_selected(self, layout, info):
        if not info:
            return
        box = layout.box()
        box.label(text=f"Meshlet #{info['id']}", icon='RESTRICT_SELECT_OFF')
        col = box.column(align=True)
        col.label(text=f"Vertices: {info['vertices']}")
        col.label(text=f"Triangles: {info['triangles']}")
        col.label(text=f"Fill: {info['fill'] * 100:.0f}%")
        cone = "wide" if info['cone_cutoff'] >= 0.999 else "ok"
        col.label(text=f"Cone cutoff: {info['cone_cutoff']:.2f}  ({cone})")
        col.label(text=f"ACMR: {info['acmr']:.2f}   Overdraw: {info['overdraw']:.2f}")
        col.label(text=f"Compactness: {info['compactness']:.2f}")
        if info['degenerate']:
            col.label(text=f"Degenerate tris: {info['degenerate']}", icon='ERROR')

    def _draw_stats(self, layout, stats):
        box = layout.box()
        box.label(text="Statistics:", icon='INFO')
        col = box.column(align=True)
        col.label(text=f"Meshlets: {stats['meshlet_count']}")
        col.label(text=f"Triangles: {stats['triangle_count']}")
        col.label(text=f"Avg fill: {stats['avg_fill'] * 100:.0f}%  "
                       f"(min {stats['min_fill'] * 100:.0f}%)")
        col.label(text=f"Wide cones: {stats['wide_cone_pct']:.0f}%")
        col.label(text=f"Compactness: avg {stats['avg_compactness']:.2f} "
                       f"min {stats['min_compactness']:.2f}")
        if stats['degenerate_tris']:
            col.label(text=f"Degenerate: {stats['degenerate_tris']} tris "
                           f"in {stats['degenerate_meshlets']} meshlets", icon='ERROR')
        else:
            col.label(text="Degenerate: none", icon='CHECKMARK')
        col.separator()
        col.label(text=f"ACMR: {stats['global_acmr']:.2f}   "
                       f"ATVR: {stats['global_atvr']:.2f}")
        col.label(text=f"Overdraw: {stats['global_overdraw']:.2f}   "
                       f"Overfetch: {stats['global_overfetch']:.2f}")


def register():
    bpy.utils.register_class(VIEW3D_PT_meshlet_preview)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_meshlet_preview)
