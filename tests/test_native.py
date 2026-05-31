"""Unit tests for the native meshoptimizer shim + ctypes wrapper.

These need no Blender; run with the project's interpreter:

    python3 -m unittest discover -s tests -v
"""
import math
import os
import sys
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Import meshopt.py directly (not via the bpy-dependent package __init__).
sys.path.insert(0, os.path.join(PROJECT, "meshlet_preview"))

import meshopt  # noqa: E402

requires_lib = unittest.skipUnless(
    meshopt.is_available(),
    "native meshoptimizer library not built (run native/build_wheel.py)")


def grid(n):
    """An n x n quad grid on the XY plane -> 2*n*n triangles."""
    positions = []
    for j in range(n + 1):
        for i in range(n + 1):
            positions += [i / n, j / n, math.sin(i * 0.5) * 0.1]
    indices = []
    row = n + 1
    for j in range(n):
        for i in range(n):
            a = j * row + i
            indices += [a, a + 1, a + row, a + 1, a + row + 1, a + row]
    return positions, indices


@requires_lib
class TestMeshletBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pos, cls.idx = grid(40)
        cls.nverts = len(cls.pos) // 3
        cls.r = meshopt.build(cls.pos, cls.idx, max_vertices=64,
                              max_triangles=124, cone_weight=0.25)

    def test_version(self):
        self.assertGreaterEqual(meshopt.version(), 220)

    def test_triangle_count_preserved(self):
        self.assertEqual(self.r.triangle_count, len(self.idx) // 3)

    def test_meshlets_produced(self):
        self.assertGreater(self.r.meshlet_count, 0)

    def test_indices_in_range(self):
        self.assertLess(max(int(x) for x in self.r.tri_indices), self.nverts)

    def test_meshlet_ids_valid(self):
        self.assertLess(max(int(m) for m in self.r.tri_meshlet), self.r.meshlet_count)

    def test_per_meshlet_arrays_sized(self):
        for arr in (self.r.vertex_counts, self.r.triangle_counts,
                    self.r.cone_cutoff, self.r.acmr, self.r.overdraw,
                    self.r.degenerate_counts, self.r.compactness):
            self.assertEqual(len(arr), self.r.meshlet_count)

    def test_clean_grid_has_no_degenerate(self):
        self.assertEqual(self.r.total_degenerate, 0)

    def test_global_stats_present(self):
        self.assertGreater(self.r.global_acmr, 0.0)
        self.assertGreaterEqual(self.r.global_overdraw, 1.0)


@requires_lib
class TestDegenerateDetection(unittest.TestCase):
    # One healthy triangle + one zero-area (collinear) triangle.
    POS = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0,
           0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 2.0, 0.0, 0.0]
    IDX = [0, 1, 2, 3, 4, 5]

    def test_zero_area_triangle_flagged(self):
        r = meshopt.build(self.POS, self.IDX, optimize_first=False)
        self.assertEqual(r.total_degenerate, 1)
        self.assertEqual(sum(int(x) for x in r.tri_degenerate), 1)

    def test_threshold_zero_disables_detection(self):
        r = meshopt.build(self.POS, self.IDX, optimize_first=False,
                          sliver_quality=0.0)
        self.assertEqual(r.total_degenerate, 0)

    def test_higher_threshold_flags_more(self):
        # A mildly thin (but non-zero-area) triangle is clean at a strict
        # threshold and flagged at a lenient one.
        pos = [0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        idx = [0, 1, 2]
        self.assertEqual(meshopt.build(pos, idx, sliver_quality=0.02).total_degenerate, 0)
        self.assertEqual(meshopt.build(pos, idx, sliver_quality=0.5).total_degenerate, 1)


@requires_lib
class TestInputValidation(unittest.TestCase):
    def test_too_few_indices_raises(self):
        with self.assertRaises(meshopt.MeshletError):
            meshopt.build([0.0, 0.0, 0.0], [0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
