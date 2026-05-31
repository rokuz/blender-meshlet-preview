"""Screenshot the Meshlet Preview N-panel (sidebar) with a meshlet selected.

    blender <file>.blend --python tests/shot_panel.py -- /abs/out.png

Relies on the extension being installed+enabled.
"""
import sys

import bpy
from bpy_extras import view3d_utils

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/panel.png"

bpy.context.preferences.view.show_splash = False

obj = next(o for o in bpy.context.view_layer.objects if o.type == 'MESH')
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

st = bpy.context.scene.meshlet_preview
st.max_vertices = 64
st.max_triangles = 124
st.cone_weight = 0.25
st.view_mode = 'CONE'
st.show_overlay = True
st.overlay_alpha = 0.85

area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
space = area.spaces.active
space.shading.type = 'SOLID'
space.show_region_ui = True          # open the N sidebar

with bpy.context.temp_override(area=area, region=region, space_data=space):
    bpy.ops.meshlet.recalculate()
    bpy.ops.view3d.view_axis(type='FRONT')
    bpy.ops.view3d.view_selected()
    # Select the meshlet under the viewport centre so the panel shows details.
    rv3d = space.region_3d
    c = (region.width / 2.0, region.height / 2.0)
    org = view3d_utils.region_2d_to_origin_3d(region, rv3d, c)
    d = view3d_utils.region_2d_to_vector_3d(region, rv3d, c)
    dg = bpy.context.evaluated_depsgraph_get()
    from bl_ext.user_default import meshlet_preview as mp
    hit, loc, _n, idx, hobj, mat = bpy.context.scene.ray_cast(dg, org, d)
    if hit and hobj is not None:
        m = mp.ops._hit_to_meshlet(hobj, idx, loc, mat, hobj.original.name, dg)
        if m is not None:
            mp.draw.set_selected(hobj.original.name, m)
    # Maximize the 3D area but keep its header + panels (clean, no Outliner).
    bpy.ops.screen.screen_full_area(use_hide_panels=False)

_n = {"i": 0}


def tick():
    _n["i"] += 1
    a = next(x for x in bpy.context.screen.areas if x.type == 'VIEW_3D')
    ui = next((r for r in a.regions if r.type == 'UI'), None)
    if ui is not None:
        try:
            ui.active_panel_category = "Meshlet"   # switch to our tab
        except Exception:
            pass
    a.tag_redraw()
    if _n["i"] < 3:
        return 0.3
    bpy.ops.screen.screenshot(filepath=OUT)
    print("WROTE", OUT)
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=0.8)
