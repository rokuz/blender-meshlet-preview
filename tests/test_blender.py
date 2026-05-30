"""Headless functional test: run inside Blender with

    blender --background --python tests/test_blender.py

It registers the addon from source (using the local native/build library via
meshopt.py's dev fallback), builds meshlets on a generated mesh through the
operator, and verifies the cache and statistics.
"""
import os
import sys

import bpy

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

import meshlet_preview  # noqa: E402
from meshlet_preview import draw, meshopt  # noqa: E402


def main():
    print("=== meshlet_preview headless test ===")
    print("meshoptimizer available:", meshopt.is_available(),
          "version:", meshopt.version() if meshopt.is_available() else "n/a")

    # Reset first (disables any installed copy), then register this source tree.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    meshlet_preview.register()

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.0)
    obj = bpy.context.active_object
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    me = obj.data
    print(f"mesh: {len(me.vertices)} verts, {len(me.polygons)} polys")

    st = bpy.context.scene.meshlet_preview
    st.max_vertices = 64
    st.max_triangles = 124
    st.cone_weight = 0.25

    with bpy.context.temp_override(active_object=obj, object=obj,
                                   selected_objects=[obj]):
        res = bpy.ops.meshlet.recalculate()
    print("operator result:", res)
    assert res == {'FINISHED'}, res

    stats = draw.get_stats(obj.name)
    assert stats is not None, "no stats cached"
    print("stats:", stats)
    assert stats["meshlet_count"] > 0
    assert stats["triangle_count"] == len(me.polygons)  # ico sphere is all tris
    assert 0.0 <= stats["avg_fill"] <= 1.0
    assert stats["global_acmr"] > 0.0

    # Cycle every view mode and rebuild colors to exercise the colormaps.
    entry = draw._cache[obj.name]
    for mode in ('PARTITION', 'FILL', 'CONE', 'OVERDRAW', 'ACMR'):
        cols = draw._meshlet_colors(entry, mode)
        assert cols.shape == (stats["meshlet_count"], 3), (mode, cols.shape)
        assert cols.min() >= 0.0 and cols.max() <= 1.0, mode
    print("all view-mode colormaps OK")

    meshlet_preview.unregister()
    print("=== PASS ===")


if __name__ == "__main__":
    main()
