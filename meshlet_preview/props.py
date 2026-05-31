"""Property definitions for the Meshlet Preview addon."""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
)
from bpy.types import PropertyGroup

from . import draw


def _redraw(self, context):
    draw.tag_redraw_all()


def _view_mode_changed(self, context):
    # The cached GPU batch is colored for a specific view mode; drop it so the
    # draw handler rebuilds it with the new colors.
    draw.invalidate_batches()
    draw.tag_redraw_all()


VIEW_MODE_ITEMS = (
    ('PARTITION', "Meshlet Partition",
     "Distinct color per meshlet so you can see the actual triangle clusters"),
    ('FILL', "Fill Efficiency",
     "How full each meshlet is versus the vertex/triangle caps; "
     "under-filled meshlets waste GPU warps"),
    ('CONE', "Cone Culling",
     "Normal-cone tightness; wide cones (red) can't be backface-cluster-culled"),
    ('OVERDRAW', "Overdraw",
     "Per-meshlet overdraw ratio from the software rasterizer; higher is worse"),
    ('ACMR', "Vertex Cache (ACMR)",
     "Per-meshlet average cache miss ratio; higher means poorer triangle ordering"),
    ('GEOMETRY', "Geometry Quality",
     "Red where a meshlet contains degenerate/sliver triangles or is spatially "
     "stringy (low compactness)"),
)


class MeshletPreviewSettings(PropertyGroup):
    max_vertices: IntProperty(
        name="Max Vertices",
        description="Maximum vertices per meshlet (GPU mesh-shader limit, <= 255)",
        default=64, min=3, soft_max=128, max=255,
    )
    max_triangles: IntProperty(
        name="Max Triangles",
        description="Maximum triangles per meshlet (rounded up to a multiple of 4, <= 512)",
        default=124, min=4, soft_max=256, max=512,
    )
    cone_weight: FloatProperty(
        name="Cone Weight",
        description="Balance between compact clusters (0) and tight backface-culling "
                    "cones (1)",
        default=0.25, min=0.0, max=1.0, subtype='FACTOR',
    )
    optimize_first: BoolProperty(
        name="Optimize Order First",
        description="Reorder triangles for vertex-cache and overdraw locality before "
                    "clustering; makes the cache/overdraw stats meaningful",
        default=True,
    )
    sliver_threshold: FloatProperty(
        name="Sliver Threshold",
        description="Triangle-quality cutoff for the Geometry Quality view; "
                    "triangles below this (slivers / near-zero area) are flagged "
                    "degenerate (0 = equilateral .. raise to catch thinner slivers)",
        default=0.02, min=0.0, max=0.5, precision=3, subtype='FACTOR',
    )

    view_mode: EnumProperty(
        name="View",
        description="Which meshlet metric to color the overlay by",
        items=VIEW_MODE_ITEMS,
        default='PARTITION',
        update=_view_mode_changed,
    )
    show_overlay: BoolProperty(
        name="Show Overlay",
        description="Draw the meshlet color overlay in the 3D viewport",
        default=True,
        update=_redraw,
    )
    overlay_alpha: FloatProperty(
        name="Opacity",
        description="Overlay opacity over the shaded mesh",
        default=0.75, min=0.0, max=1.0, subtype='FACTOR',
        update=_redraw,
    )


def register():
    bpy.utils.register_class(MeshletPreviewSettings)
    bpy.types.Scene.meshlet_preview = bpy.props.PointerProperty(
        type=MeshletPreviewSettings)


def unregister():
    del bpy.types.Scene.meshlet_preview
    bpy.utils.unregister_class(MeshletPreviewSettings)
