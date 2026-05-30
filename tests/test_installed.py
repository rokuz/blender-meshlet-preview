"""Verify the *installed* extension works end-to-end (wheel-provided native lib).

    blender --background --python tests/test_installed.py
"""
import addon_utils
import bpy

MODULE = "bl_ext.user_default.meshlet_preview"


def main():
    print("=== installed extension test ===")

    enabled = [m.__name__ for m in addon_utils.modules()
               if m.__name__.endswith("meshlet_preview")]
    print("found addon modules:", enabled)

    # Reset to an empty scene first; this also disables the session's addons,
    # so enable the extension afterwards.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable(MODULE, default_set=False, persistent=False)
    assert hasattr(bpy.types.Scene, "meshlet_preview"), "addon failed to register"

    # The native shim must come from the bundled wheel, not the source fallback.
    import meshopt_preview_native
    print("native package:", meshopt_preview_native.__file__)
    print("library:", meshopt_preview_native.library_path())

    mp = __import__(MODULE, fromlist=["meshopt"]).meshopt
    print("meshoptimizer available:", mp.is_available(), "version:", mp.version())

    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.active_object
    # Subdivide so there are enough triangles for several meshlets.
    mod = obj.modifiers.new("subsurf", 'SUBSURF')
    mod.levels = 2

    bpy.context.view_layer.objects.active = obj
    st = bpy.context.scene.meshlet_preview
    st.view_mode = 'CONE'

    with bpy.context.temp_override(active_object=obj, object=obj,
                                   selected_objects=[obj]):
        res = bpy.ops.meshlet.recalculate()
    print("operator result:", res)
    assert res == {'FINISHED'}

    draw = __import__(MODULE, fromlist=["draw"]).draw
    stats = draw.get_stats(obj.name)
    print("stats:", stats)
    assert stats and stats["meshlet_count"] > 0
    print("=== PASS ===")


if __name__ == "__main__":
    main()
