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

_area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
_region = next(r for r in _area.regions if r.type == 'WINDOW')
_space = _area.spaces.active
_space.shading.type = 'SOLID'

with bpy.context.temp_override(area=_area, region=_region, space_data=_space):
    bpy.ops.meshlet.recalculate()
    bpy.ops.view3d.view_axis(type='FRONT')
    bpy.ops.view3d.view_selected()

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
