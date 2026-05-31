"""GUI: open /tmp/ml.blend (no splash), build meshlets, window-screenshot, quit.

    blender /tmp/ml.blend --python tests/screenshot.py -- /abs/out.png MODE

A window screenshot is used because viewport draw handlers (our overlay) do not
run during an OpenGL render.
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/meshlet_shot.png"
MODE = argv[1] if len(argv) > 1 else 'PARTITION'

bpy.context.preferences.view.show_splash = False

obj = bpy.data.objects.get("Icosphere") or bpy.context.view_layer.objects[0]
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

st = bpy.context.scene.meshlet_preview
st.max_vertices = 64
st.max_triangles = 124
st.cone_weight = 0.25
st.view_mode = MODE
st.show_overlay = True
st.overlay_alpha = 0.9
for tok in argv:                       # optional float token -> sliver threshold
    try:
        st.sliver_threshold = float(tok)
        break
    except ValueError:
        pass

_area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
_region = next(r for r in _area.regions if r.type == 'WINDOW')
_space = _area.spaces.active
_space.shading.type = 'SOLID'

_view = next((a for a in argv if a in {'FRONT', 'TOP', 'RIGHT', 'LEFT', 'BACK', 'BOTTOM'}),
             'FRONT')
with bpy.context.temp_override(area=_area, region=_region, space_data=_space):
    bpy.ops.meshlet.recalculate()
    bpy.ops.view3d.view_axis(type=_view)
    bpy.ops.view3d.view_selected()

# Optional: highlight the meshlet under the viewport center (wireframe path).
if "PICK" in argv:
    from bpy_extras import view3d_utils
    from bl_ext.user_default import meshlet_preview as mp
    draw, ops = mp.draw, mp.ops
    rv3d = _space.region_3d
    center = (_region.width / 2.0, _region.height / 2.0)
    origin = view3d_utils.region_2d_to_origin_3d(_region, rv3d, center)
    direction = view3d_utils.region_2d_to_vector_3d(_region, rv3d, center)
    dg = bpy.context.evaluated_depsgraph_get()
    hit, loc, _n, idx, hobj, mat = bpy.context.scene.ray_cast(dg, origin, direction)
    if hit and hobj is not None:
        m = ops._hit_to_meshlet(hobj, idx, loc, mat, hobj.original.name, dg)
        if m is not None:
            draw.set_selected(hobj.original.name, m)
            print("selected meshlet", m)

# Clean, chrome-free framing for documentation images.
if "CLEAN" in argv:
    _space.overlay.show_overlays = False          # hide grid / gizmos (our overlay stays)
    with bpy.context.temp_override(area=_area, region=_region, space_data=_space):
        bpy.ops.screen.screen_full_area(use_hide_panels=True)

_n = {"i": 0}


def tick():
    _n["i"] += 1
    for a in bpy.context.screen.areas:
        a.tag_redraw()
    if _n["i"] < 3:
        return 0.3
    bpy.ops.screen.screenshot(filepath=OUT)
    print("WROTE", OUT)
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=0.8)
