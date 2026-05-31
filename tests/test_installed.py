"""System test of the *installed* extension: the native library must load from
the bundled wheel and the operator must run. Skipped unless the extension is
installed in the Blender that runs this.

    blender --background --python tests/run_blender.py
"""
import unittest

try:
    import bpy
    HAS_BPY = True
except Exception:
    HAS_BPY = False

MODULE = "bl_ext.user_default.meshlet_preview"


@unittest.skipUnless(HAS_BPY, "requires Blender (bpy)")
class TestInstalledExtension(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import addon_utils
        bpy.ops.wm.read_factory_settings(use_empty=True)
        addon_utils.enable(MODULE, default_set=False, persistent=False)
        if not hasattr(bpy.types.Scene, "meshlet_preview"):
            raise unittest.SkipTest(f"{MODULE} is not installed")
        cls._enabled = True

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_enabled", False):
            import addon_utils
            addon_utils.disable(MODULE, default_set=False)

    def test_native_library_comes_from_wheel(self):
        import meshopt_preview_native
        path = meshopt_preview_native.library_path()
        self.assertIn("site-packages", path)
        self.assertTrue(path.endswith((".dylib", ".so", ".dll")))

    def test_operator_runs_via_installed_addon(self):
        bpy.ops.mesh.primitive_monkey_add()
        obj = bpy.context.active_object
        obj.modifiers.new("subsurf", 'SUBSURF').levels = 2
        bpy.context.view_layer.objects.active = obj
        with bpy.context.temp_override(active_object=obj, object=obj,
                                       selected_objects=[obj]):
            self.assertEqual(bpy.ops.meshlet.recalculate(), {'FINISHED'})
        draw = __import__(MODULE, fromlist=["draw"]).draw
        self.assertGreater(draw.get_stats(obj.name)["meshlet_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
