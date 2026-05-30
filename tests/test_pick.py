"""Headless test of the meshlet picking path:

    blender --background --python tests/test_pick.py
"""
import os
import sys

import bpy
from mathutils import Vector

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

import meshlet_preview  # noqa: E402
from meshlet_preview import draw, ops  # noqa: E402


def main():
    print("=== meshlet pick test ===")
    # Reset first (disables any installed copy of the extension), then register
    # this source tree so there is exactly one set of classes.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    meshlet_preview.register()

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.2)
    obj = bpy.context.active_object
    bpy.context.view_layer.objects.active = obj

    with bpy.context.temp_override(active_object=obj, object=obj,
                                   selected_objects=[obj]):
        assert bpy.ops.meshlet.recalculate() == {'FINISHED'}

    stats = draw.get_stats(obj.name)
    lookup = draw.get_lookup(obj.name)
    print(f"meshlets={stats['meshlet_count']} triangles={stats['triangle_count']} "
          f"lookup_entries={len(lookup)}")
    assert lookup and len(lookup) == stats["triangle_count"], "lookup must cover all tris"
    assert all(0 <= m < stats["meshlet_count"] for m in lookup.values())

    # Manual selection round-trips through the cache + per-meshlet info.
    draw.set_selected(obj.name, 5)
    assert draw.get_selected(obj.name) == 5
    info = draw.get_selected_info(obj.name)
    print("selected info:", info)
    assert info["id"] == 5 and info["triangles"] > 0
    draw.set_selected(obj.name, -1)
    assert draw.get_selected_info(obj.name) is None

    # Full pick path: ray_cast the sphere from above and resolve to a meshlet.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _n, index, hobj, matrix = bpy.context.scene.ray_cast(
        depsgraph, Vector((0.0, 0.0, 5.0)), Vector((0.0, 0.0, -1.0)))
    print("ray hit:", hit, "poly:", index, "obj:", hobj.original.name if hobj else None)
    assert hit and hobj is not None
    meshlet = ops._hit_to_meshlet(hobj, index, location, matrix, hobj.original.name)
    print("hit -> meshlet:", meshlet)
    assert meshlet is not None and 0 <= meshlet < stats["meshlet_count"]

    meshlet_preview.unregister()
    print("=== PASS ===")


if __name__ == "__main__":
    main()
