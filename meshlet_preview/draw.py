"""Meshlet result cache and the 3D-viewport GPU overlay.

Results from the recalculate operator are cached here in memory (keyed by object
name) and drawn as a non-destructive, depth-tested triangle overlay. Colors are
computed per meshlet for the active view mode and rebuilt lazily inside the draw
callback (the only place a GPU context is guaranteed).
"""

import colorsys

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

# obj_name -> _Entry
_cache = {}
_handle = None
_shader = None
_wire_shader = None


class _Entry:
    __slots__ = (
        "coords", "tri_meshlet",
        "vertex_counts", "triangle_counts", "cone_cutoff", "acmr", "overdraw",
        "max_vertices", "max_triangles", "stats",
        "batch", "batch_key",
        "tri_lookup", "selected", "wire_batch", "wire_key",
    )

    def __init__(self):
        self.batch = None
        self.batch_key = None
        self.tri_lookup = None
        self.selected = -1
        self.wire_batch = None
        self.wire_key = None


# --------------------------------------------------------------------------- #
# Cache management (called from the operator / UI)
# --------------------------------------------------------------------------- #

def set_result(obj_name, coords, tri_meshlet, result, max_vertices, max_triangles,
               tri_lookup=None):
    """Store a meshopt result and precompute the summary statistics."""
    e = _Entry()
    e.tri_lookup = tri_lookup
    e.coords = np.ascontiguousarray(coords, dtype=np.float32).reshape(-1, 3)
    e.tri_meshlet = np.ascontiguousarray(tri_meshlet, dtype=np.uint32)
    e.vertex_counts = np.asarray(result.vertex_counts, dtype=np.float32)
    e.triangle_counts = np.asarray(result.triangle_counts, dtype=np.float32)
    e.cone_cutoff = np.asarray(result.cone_cutoff, dtype=np.float32)
    e.acmr = np.asarray(result.acmr, dtype=np.float32)
    e.overdraw = np.asarray(result.overdraw, dtype=np.float32)
    e.max_vertices = float(max_vertices)
    e.max_triangles = float(max_triangles)

    fill = np.maximum(e.vertex_counts / e.max_vertices,
                      e.triangle_counts / e.max_triangles)
    wide = np.count_nonzero(e.cone_cutoff >= 0.999)
    e.stats = {
        "meshlet_count": result.meshlet_count,
        "triangle_count": result.triangle_count,
        "avg_fill": float(fill.mean()) if len(fill) else 0.0,
        "min_fill": float(fill.min()) if len(fill) else 0.0,
        "wide_cone_pct": (100.0 * wide / result.meshlet_count)
                         if result.meshlet_count else 0.0,
        "global_acmr": result.global_acmr,
        "global_atvr": result.global_atvr,
        "global_overdraw": result.global_overdraw,
        "global_overfetch": result.global_overfetch,
    }
    e.batch = None
    e.batch_key = None
    _cache[obj_name] = e


def get_stats(obj_name):
    e = _cache.get(obj_name)
    return e.stats if e else None


def has_result(obj_name):
    return obj_name in _cache


def clear(obj_name):
    _cache.pop(obj_name, None)
    tag_redraw_all()


def clear_all():
    _cache.clear()
    tag_redraw_all()


def invalidate_batches():
    for e in _cache.values():
        e.batch = None
        e.batch_key = None


def get_lookup(obj_name):
    e = _cache.get(obj_name)
    return e.tri_lookup if e else None


def set_selected(obj_name, meshlet_id):
    """Select a meshlet (or -1 to clear) and refresh the viewport."""
    e = _cache.get(obj_name)
    if e is None:
        return
    meshlet_id = int(meshlet_id)
    if meshlet_id == e.selected:
        return
    e.selected = meshlet_id
    e.wire_batch = None
    e.wire_key = None
    tag_redraw_all()


def get_selected(obj_name):
    e = _cache.get(obj_name)
    return e.selected if e else -1


def get_selected_info(obj_name):
    """Per-meshlet metrics for the selected meshlet, or None."""
    e = _cache.get(obj_name)
    if e is None or e.selected < 0 or e.selected >= len(e.vertex_counts):
        return None
    m = e.selected
    vc = float(e.vertex_counts[m])
    tc = float(e.triangle_counts[m])
    return {
        "id": m,
        "vertices": int(vc),
        "triangles": int(tc),
        "fill": max(vc / e.max_vertices, tc / e.max_triangles),
        "cone_cutoff": float(e.cone_cutoff[m]),
        "acmr": float(e.acmr[m]),
        "overdraw": float(e.overdraw[m]),
    }


# --------------------------------------------------------------------------- #
# Color maps (vectorized, per meshlet)
# --------------------------------------------------------------------------- #

def _heat(bad):
    """Map badness in [0,1] to green -> yellow -> red. Returns (n,3)."""
    bad = np.clip(bad, 0.0, 1.0)
    r = np.minimum(1.0, 2.0 * bad)
    g = np.minimum(1.0, 2.0 * (1.0 - bad))
    b = np.full_like(bad, 0.12)
    return np.stack([r, g, b], axis=1)


def _partition_colors(n):
    """Distinct, stable color per meshlet id using the golden-ratio hue walk."""
    cols = np.empty((n, 3), dtype=np.float32)
    h = 0.0
    for i in range(n):
        h = (h + 0.61803398875) % 1.0
        cols[i] = colorsys.hsv_to_rgb(h, 0.65, 0.95)
    return cols


def _meshlet_colors(entry, mode):
    """Per-meshlet RGB (n,3) for the given view mode."""
    if mode == 'PARTITION':
        return _partition_colors(len(entry.cone_cutoff))
    if mode == 'FILL':
        fill = np.maximum(entry.vertex_counts / entry.max_vertices,
                          entry.triangle_counts / entry.max_triangles)
        return _heat(1.0 - fill)
    if mode == 'CONE':
        return _heat(entry.cone_cutoff)
    if mode == 'OVERDRAW':
        return _heat(entry.overdraw - 1.0)            # 1.0 good -> 2.0 worst
    if mode == 'ACMR':
        return _heat((entry.acmr - 0.5) / 2.0)        # 0.5 best -> 2.5 worst
    return _partition_colors(len(entry.cone_cutoff))


def _build_batch(entry, mode, alpha, shader):
    mcolors = _meshlet_colors(entry, mode)                 # (m,3)
    tri_rgb = mcolors[entry.tri_meshlet]                   # (tris,3)
    a = np.full((len(tri_rgb), 1), float(alpha), dtype=np.float32)
    tri_rgba = np.concatenate([tri_rgb.astype(np.float32), a], axis=1)
    vert_rgba = np.repeat(tri_rgba, 3, axis=0)             # (tris*3,4)
    return batch_for_shader(shader, 'TRIS',
                            {"pos": entry.coords, "color": vert_rgba})


# --------------------------------------------------------------------------- #
# Draw handler
# --------------------------------------------------------------------------- #

def _get_shader():
    global _shader
    if _shader is None:
        _shader = gpu.shader.from_builtin('FLAT_COLOR')
    return _shader


def _get_wire_shader():
    global _wire_shader
    if _wire_shader is None:
        _wire_shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    return _wire_shader


def _build_wire_batch(entry, shader):
    """Line batch of the edges of the selected meshlet's triangles."""
    idx = np.nonzero(entry.tri_meshlet == entry.selected)[0]
    if len(idx) == 0:
        return None
    base = idx * 3
    c0 = entry.coords[base]
    c1 = entry.coords[base + 1]
    c2 = entry.coords[base + 2]
    lines = np.empty((len(idx) * 6, 3), dtype=np.float32)
    lines[0::6], lines[1::6] = c0, c1   # edge 0-1
    lines[2::6], lines[3::6] = c1, c2   # edge 1-2
    lines[4::6], lines[5::6] = c2, c0   # edge 2-0
    return batch_for_shader(shader, 'LINES', {"pos": lines})


def _draw_selection(context):
    """Second pass: bright wireframe over any selected meshlets."""
    selected = [(n, e) for n, e in _cache.items() if e.selected is not None and e.selected >= 0]
    if not selected:
        return

    region = context.region
    shader = _get_wire_shader()
    shader.bind()
    if region is not None:
        shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", 2.5)
    shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))

    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    for name, entry in selected:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        if entry.wire_batch is None or entry.wire_key != entry.selected:
            entry.wire_batch = _build_wire_batch(entry, shader)
            entry.wire_key = entry.selected
        if entry.wire_batch is None:
            continue
        gpu.matrix.push()
        try:
            gpu.matrix.multiply_matrix(obj.matrix_world)
            entry.wire_batch.draw(shader)
        finally:
            gpu.matrix.pop()


def _draw():
    if not _cache:
        return
    context = bpy.context
    st = getattr(context.scene, "meshlet_preview", None)
    if st is None or not st.show_overlay:
        return

    view_layer = context.view_layer
    shader = _get_shader()
    key = (st.view_mode, round(st.overlay_alpha, 3))

    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(False)
    gpu.state.face_culling_set('NONE')
    try:
        for name, entry in list(_cache.items()):
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            try:
                if not obj.visible_get(view_layer=view_layer):
                    continue
            except Exception:
                pass
            if entry.batch is None or entry.batch_key != key:
                entry.batch = _build_batch(entry, st.view_mode, st.overlay_alpha, shader)
                entry.batch_key = key

            gpu.matrix.push()
            try:
                gpu.matrix.multiply_matrix(obj.matrix_world)
                shader.bind()
                entry.batch.draw(shader)
            finally:
                gpu.matrix.pop()

        _draw_selection(context)
    finally:
        gpu.state.depth_mask_set(True)
        gpu.state.blend_set('NONE')


def tag_redraw_all():
    wm = bpy.context.window_manager
    if not wm:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def register():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw, (), 'WINDOW', 'POST_VIEW')


def unregister():
    global _handle, _shader, _wire_shader
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    _cache.clear()
    _shader = None
    _wire_shader = None
