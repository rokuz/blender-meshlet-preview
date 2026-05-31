"""Integration tests that run inside Blender (require ``bpy``).

Run via the in-Blender runner so they get a real exit code:

    blender --background --python tests/run_blender.py

When collected by a plain ``python -m unittest`` (no bpy) they are skipped.
"""
import os
import sys
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

try:
    import bpy
    HAS_BPY = True
except Exception:
    HAS_BPY = False


@unittest.skipUnless(HAS_BPY, "requires Blender (bpy)")
class AddonTestCase(unittest.TestCase):
    """Registers this source tree fresh per test for full isolation."""

    def setUp(self):
        import meshlet_preview
        self.addon = meshlet_preview
        from meshlet_preview import draw
        self.draw = draw
        # Factory reset disables any installed copy; register the source after.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        meshlet_preview.register()
        self.addCleanup(meshlet_preview.unregister)

    def add_sphere(self, subdivisions=4):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=1.2)
        obj = bpy.context.active_object
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        return obj

    def add_cube(self):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        return obj

    def recalc(self, obj):
        with bpy.context.temp_override(active_object=obj, object=obj,
                                       selected_objects=[obj]):
            return bpy.ops.meshlet.recalculate()


class TestOperator(AddonTestCase):
    def test_registers_scene_property(self):
        self.assertTrue(hasattr(bpy.types.Scene, "meshlet_preview"))

    def test_recalculate_finishes(self):
        obj = self.add_sphere()
        self.assertEqual(self.recalc(obj), {'FINISHED'})

    def test_stats_match_mesh(self):
        obj = self.add_sphere()
        self.recalc(obj)
        stats = self.draw.get_stats(obj.name)
        self.assertIsNotNone(stats)
        self.assertGreater(stats["meshlet_count"], 0)
        # An ico sphere is all triangles.
        self.assertEqual(stats["triangle_count"], len(obj.data.polygons))
        self.assertTrue(0.0 <= stats["avg_fill"] <= 1.0)
        self.assertEqual(stats["degenerate_tris"], 0)

    def test_all_view_mode_colormaps(self):
        obj = self.add_sphere()
        self.recalc(obj)
        entry = self.draw._cache[obj.name]
        n = self.draw.get_stats(obj.name)["meshlet_count"]
        for mode in ('PARTITION', 'FILL', 'CONE', 'OVERDRAW', 'ACMR', 'GEOMETRY'):
            cols = self.draw._meshlet_colors(entry, mode)
            self.assertEqual(cols.shape, (n, 3), mode)
            self.assertGreaterEqual(cols.min(), 0.0, mode)
            self.assertLessEqual(cols.max(), 1.0, mode)

    def test_poll_false_without_mesh(self):
        # No active object -> the operator must not be runnable.
        self.assertFalse(bpy.ops.meshlet.recalculate.poll())


class TestPicking(AddonTestCase):
    def test_lookup_covers_all_triangles(self):
        obj = self.add_sphere()
        self.recalc(obj)
        lookup = self.draw.get_lookup(obj.name)
        stats = self.draw.get_stats(obj.name)
        self.assertEqual(len(lookup), stats["triangle_count"])
        self.assertTrue(all(0 <= m < stats["meshlet_count"] for m in lookup.values()))

    def test_selection_roundtrip(self):
        obj = self.add_sphere()
        self.recalc(obj)
        self.draw.set_selected(obj.name, 3)
        self.assertEqual(self.draw.get_selected(obj.name), 3)
        info = self.draw.get_selected_info(obj.name)
        self.assertEqual(info["id"], 3)
        self.assertGreater(info["triangles"], 0)
        self.draw.set_selected(obj.name, -1)
        self.assertIsNone(self.draw.get_selected_info(obj.name))

    def test_raycast_resolves_meshlet(self):
        from mathutils import Vector
        from meshlet_preview import ops
        obj = self.add_sphere()
        self.recalc(obj)
        dg = bpy.context.evaluated_depsgraph_get()
        hit, loc, _n, idx, hobj, mat = bpy.context.scene.ray_cast(
            dg, Vector((0.0, 0.0, 5.0)), Vector((0.0, 0.0, -1.0)))
        self.assertTrue(hit)
        m = ops._hit_to_meshlet(hobj, idx, loc, mat, hobj.original.name)
        self.assertIsNotNone(m)
        self.assertTrue(0 <= m < self.draw.get_stats(obj.name)["meshlet_count"])

    def test_ngon_face_resolves_meshlet(self):
        # A cube has quad (n-gon) faces -> exercises the n-gon pick branch.
        from mathutils import Vector
        from meshlet_preview import ops
        obj = self.add_cube()
        self.recalc(obj)
        dg = bpy.context.evaluated_depsgraph_get()
        hit, loc, _n, idx, hobj, mat = bpy.context.scene.ray_cast(
            dg, Vector((0.3, 0.2, 5.0)), Vector((0.0, 0.0, -1.0)))
        self.assertTrue(hit)
        self.assertGreater(len(hobj.to_mesh().polygons[idx].vertices), 3)
        hobj.to_mesh_clear()
        m = ops._hit_to_meshlet(hobj, idx, loc, mat, hobj.original.name)
        self.assertIsNotNone(m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
