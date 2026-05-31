"""ctypes binding to the bundled meshoptimizer shim (``mp_shim.cpp``).

The native library is delivered as a platform wheel (``meshopt_preview_native``)
bundled by the extension; ``meshopt_buildMeshlets`` and the analyzers are not
exposed by the public PyPI ``meshoptimizer`` package, which is why we ship our
own thin shim. The library is loaded through ctypes, so it is independent of the
host Python ABI.

The single entry point is :func:`build`, which runs the whole pipeline (build
meshlets -> per-meshlet bounds and analyzers -> global stats) in one native call
and returns a :class:`MeshletResult`.
"""

from __future__ import annotations

import ctypes
import os

try:
    import numpy as _np
except Exception:  # numpy is bundled with Blender, but stay usable without it.
    _np = None


class _MPResult(ctypes.Structure):
    _fields_ = [
        ("meshlet_count", ctypes.c_uint),
        ("triangle_count", ctypes.c_uint),
        ("vertex_counts", ctypes.POINTER(ctypes.c_uint)),
        ("triangle_counts", ctypes.POINTER(ctypes.c_uint)),
        ("cone_cutoff", ctypes.POINTER(ctypes.c_float)),
        ("cone_axis", ctypes.POINTER(ctypes.c_float)),
        ("center", ctypes.POINTER(ctypes.c_float)),
        ("radius", ctypes.POINTER(ctypes.c_float)),
        ("acmr", ctypes.POINTER(ctypes.c_float)),
        ("overdraw", ctypes.POINTER(ctypes.c_float)),
        ("degenerate_counts", ctypes.POINTER(ctypes.c_uint)),
        ("compactness", ctypes.POINTER(ctypes.c_float)),
        ("tri_meshlet", ctypes.POINTER(ctypes.c_uint)),
        ("tri_indices", ctypes.POINTER(ctypes.c_uint)),
        ("tri_degenerate", ctypes.POINTER(ctypes.c_ubyte)),
        ("global_acmr", ctypes.c_float),
        ("global_atvr", ctypes.c_float),
        ("global_overdraw", ctypes.c_float),
        ("global_overfetch", ctypes.c_float),
        ("total_degenerate", ctypes.c_uint),
    ]


class MeshletError(RuntimeError):
    pass


class MeshletResult:
    """Plain container of per-meshlet metrics and draw buffers.

    Arrays are numpy arrays when numpy is available, otherwise Python lists.
    Per-meshlet arrays have length ``meshlet_count``; ``cone_axis`` and
    ``center`` are flattened ``meshlet_count * 3``. ``tri_meshlet`` has length
    ``triangle_count`` and ``tri_indices`` has length ``triangle_count * 3``.
    """

    __slots__ = (
        "meshlet_count", "triangle_count",
        "vertex_counts", "triangle_counts", "cone_cutoff", "cone_axis",
        "center", "radius", "acmr", "overdraw",
        "degenerate_counts", "compactness",
        "tri_meshlet", "tri_indices", "tri_degenerate",
        "global_acmr", "global_atvr", "global_overdraw", "global_overfetch",
        "total_degenerate",
    )


_lib = None


def _candidate_paths():
    """Yield possible shared-library locations, most preferred first."""
    # 1. A local development build next to the source tree. Preferred so that
    #    running from source always uses the freshly compiled library rather
    #    than a possibly-stale installed wheel. (Absent in an installed add-on.)
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("libmeshopt_preview.dylib", "libmeshopt_preview.so",
                 "meshopt_preview.dll"):
        yield os.path.join(here, "..", "native", "build", name)
        yield os.path.join(here, name)
    # 2. The bundled wheel package, importable once Blender installs the wheel.
    try:
        import meshopt_preview_native  # type: ignore
        yield meshopt_preview_native.library_path()
    except Exception:
        pass


def _load():
    global _lib
    if _lib is not None:
        return _lib
    last_err = None
    for path in _candidate_paths():
        if not path or not os.path.exists(path):
            continue
        try:
            lib = ctypes.CDLL(path)
        except OSError as exc:
            last_err = exc
            continue
        lib.mp_build.restype = ctypes.POINTER(_MPResult)
        lib.mp_build.argtypes = [
            ctypes.POINTER(ctypes.c_float), ctypes.c_uint,
            ctypes.POINTER(ctypes.c_uint), ctypes.c_uint,
            ctypes.c_uint, ctypes.c_uint, ctypes.c_float, ctypes.c_int,
            ctypes.c_float,
        ]
        lib.mp_free_result.restype = None
        lib.mp_free_result.argtypes = [ctypes.POINTER(_MPResult)]
        lib.mp_version.restype = ctypes.c_int
        lib.mp_version.argtypes = []
        _lib = lib
        return _lib
    raise MeshletError(
        "Could not load the meshoptimizer native library. "
        "Build it with 'python3 native/build_wheel.py'. "
        f"Last error: {last_err}")


def is_available():
    try:
        _load()
        return True
    except MeshletError:
        return False


def version():
    """meshoptimizer version as major*1000 + minor*10 + patch (e.g. 220)."""
    return _load().mp_version()


def _copy_uint(ptr, n):
    if n == 0:
        return _np.empty(0, dtype=_np.uint32) if _np is not None else []
    if _np is not None:
        return _np.ctypeslib.as_array(ptr, shape=(n,)).astype(_np.uint32, copy=True)
    return list(ptr[:n])


def _copy_float(ptr, n):
    if n == 0:
        return _np.empty(0, dtype=_np.float32) if _np is not None else []
    if _np is not None:
        return _np.ctypeslib.as_array(ptr, shape=(n,)).astype(_np.float32, copy=True)
    return list(ptr[:n])


def _copy_u8(ptr, n):
    if n == 0:
        return _np.empty(0, dtype=_np.uint8) if _np is not None else []
    if _np is not None:
        return _np.ctypeslib.as_array(ptr, shape=(n,)).astype(_np.uint8, copy=True)
    return list(ptr[:n])


def _as_float_ptr(positions):
    """Return (ptr, count) for a flat sequence of float3 positions."""
    if _np is not None:
        arr = _np.ascontiguousarray(positions, dtype=_np.float32).ravel()
        return arr.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), arr.size, arr
    buf = (ctypes.c_float * len(positions))(*positions)
    return buf, len(buf), buf


def _as_uint_ptr(indices):
    if _np is not None:
        arr = _np.ascontiguousarray(indices, dtype=_np.uint32).ravel()
        return arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint)), arr.size, arr
    buf = (ctypes.c_uint * len(indices))(*indices)
    return buf, len(buf), buf


def build(positions, indices, max_vertices=64, max_triangles=124,
          cone_weight=0.0, optimize_first=True, sliver_quality=0.02):
    """Split a triangle mesh into meshlets and analyze it.

    ``positions`` is a flat sequence of float3 vertex coordinates (length
    ``vertex_count * 3``); ``indices`` is a flat triangle-list index buffer.
    ``sliver_quality`` is the scale-invariant triangle-quality threshold below
    which a triangle is flagged degenerate (0 = equilateral .. 1 worst).
    Returns a :class:`MeshletResult`.
    """
    lib = _load()

    max_triangles = int(max_triangles)
    if max_triangles % 4 != 0:  # meshoptimizer requires divisibility by 4.
        max_triangles += 4 - (max_triangles % 4)
    max_vertices = max(3, min(255, int(max_vertices)))
    max_triangles = max(4, min(512, max_triangles))

    pos_ptr, pos_count, _pos_keep = _as_float_ptr(positions)
    idx_ptr, idx_count, _idx_keep = _as_uint_ptr(indices)
    vertex_count = pos_count // 3

    if idx_count < 3 or vertex_count == 0:
        raise MeshletError("Mesh has no triangles to process.")

    res_ptr = lib.mp_build(
        pos_ptr, ctypes.c_uint(vertex_count),
        idx_ptr, ctypes.c_uint(idx_count),
        ctypes.c_uint(max_vertices), ctypes.c_uint(max_triangles),
        ctypes.c_float(cone_weight), ctypes.c_int(1 if optimize_first else 0),
        ctypes.c_float(sliver_quality))

    if not res_ptr:
        raise MeshletError("Meshlet building failed (allocation or degenerate input).")

    try:
        r = res_ptr.contents
        mc = int(r.meshlet_count)
        tc = int(r.triangle_count)

        out = MeshletResult()
        out.meshlet_count = mc
        out.triangle_count = tc
        out.vertex_counts = _copy_uint(r.vertex_counts, mc)
        out.triangle_counts = _copy_uint(r.triangle_counts, mc)
        out.cone_cutoff = _copy_float(r.cone_cutoff, mc)
        out.cone_axis = _copy_float(r.cone_axis, mc * 3)
        out.center = _copy_float(r.center, mc * 3)
        out.radius = _copy_float(r.radius, mc)
        out.acmr = _copy_float(r.acmr, mc)
        out.overdraw = _copy_float(r.overdraw, mc)
        out.degenerate_counts = _copy_uint(r.degenerate_counts, mc)
        out.compactness = _copy_float(r.compactness, mc)
        out.tri_meshlet = _copy_uint(r.tri_meshlet, tc)
        out.tri_indices = _copy_uint(r.tri_indices, tc * 3)
        out.tri_degenerate = _copy_u8(r.tri_degenerate, tc)
        out.global_acmr = float(r.global_acmr)
        out.global_atvr = float(r.global_atvr)
        out.global_overdraw = float(r.global_overdraw)
        out.global_overfetch = float(r.global_overfetch)
        out.total_degenerate = int(r.total_degenerate)
        return out
    finally:
        lib.mp_free_result(res_ptr)
