"""Standalone smoke test for the meshoptimizer shim (no Blender required)."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "meshlet_preview"))
import meshopt  # noqa: E402


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
            b = a + 1
            c = a + row
            d = c + 1
            indices += [a, b, c, b, d, c]
    return positions, indices


def main():
    print("meshoptimizer version:", meshopt.version())
    pos, idx = grid(40)
    vcount = len(pos) // 3
    print(f"input: {vcount} verts, {len(idx) // 3} tris")

    r = meshopt.build(pos, idx, max_vertices=64, max_triangles=124,
                      cone_weight=0.25, optimize_first=True)

    print(f"meshlets: {r.meshlet_count}")
    print(f"output triangles: {r.triangle_count} (input {len(idx) // 3})")
    assert r.triangle_count == len(idx) // 3, "triangle count must be preserved"
    print(f"first meshlet: verts={int(r.vertex_counts[0])} "
          f"tris={int(r.triangle_counts[0])} "
          f"cone_cutoff={float(r.cone_cutoff[0]):.3f} "
          f"acmr={float(r.acmr[0]):.3f} overdraw={float(r.overdraw[0]):.3f}")
    print(f"global: acmr={r.global_acmr:.3f} atvr={r.global_atvr:.3f} "
          f"overdraw={r.global_overdraw:.3f} overfetch={r.global_overfetch:.3f}")

    # All triangle indices must be in range.
    mx = max(int(x) for x in r.tri_indices)
    assert mx < vcount, f"index {mx} out of range {vcount}"
    # Every triangle maps to a valid meshlet id.
    assert max(int(m) for m in r.tri_meshlet) < r.meshlet_count
    # A clean grid has no degenerate triangles.
    print(f"degenerate (grid): {r.total_degenerate}")
    assert r.total_degenerate == 0

    degenerate_case()
    print("OK")


def degenerate_case():
    """One healthy triangle + one zero-area (collinear) triangle."""
    pos = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0,
           0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 2.0, 0.0, 0.0]
    idx = [0, 1, 2, 3, 4, 5]
    r = meshopt.build(pos, idx, max_vertices=64, max_triangles=124,
                      optimize_first=False)
    bad = [int(x) for x in r.tri_degenerate]
    print(f"degenerate (sliver case): total={r.total_degenerate} flags={bad}")
    assert r.total_degenerate == 1, r.total_degenerate
    assert sum(bad) == 1


if __name__ == "__main__":
    main()
