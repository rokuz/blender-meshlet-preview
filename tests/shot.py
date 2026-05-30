"""Launch Blender GUI, build meshlets, OpenGL-render the viewport, then quit.

    blender --python tests/shot.py -- /abs/out.png [MODE]

Relies on the extension being installed+enabled in user preferences. An OpenGL
viewport render runs the overlay draw handler and avoids the splash screen.
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/meshlet_shot.png"
MODE = argv[1] if len(argv) > 1 else 'PARTITION'


def run():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.2)
    obj = bpy.context.active_object

    st = bpy.context.scene.meshlet_preview
    st.max_vertices = 64
    st.max_triangles = 124
    st.cone_weight = 0.25
    st.view_mode = MODE
    st.show_overlay = True
    st.overlay_alpha = 0.9

    scene = bpy.context.scene
    scene.render.filepath = OUT
    scene.render.image_settings.file_format = 'PNG'
    scene.render.resolution_x = 900
    scene.render.resolution_y = 700

    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    space = area.spaces.active
    space.shading.type = 'SOLID'
    space.overlay.show_overlays = True

    with bpy.context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.meshlet.recalculate()
        bpy.ops.view3d.view_axis(type='FRONT')
        bpy.ops.view3d.view_selected()
        bpy.ops.render.opengl(write_still=True, view_context=True)

    print("WROTE", OUT, os.path.exists(OUT))
    bpy.ops.wm.quit_blender()


run()
