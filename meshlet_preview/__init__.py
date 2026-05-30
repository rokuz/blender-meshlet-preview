"""Meshlet Preview — split a mesh into meshlets with meshoptimizer and visualize
GPU rendering problems (partition, fill efficiency, cone culling, overdraw and
vertex-cache behaviour) as a non-destructive 3D viewport overlay.
"""

from . import draw, ops, props, ui

# Submodules with register()/unregister(); order matters: draw installs the GPU
# handler, props depends on draw for its update callbacks, ui/ops depend on props.
_modules = (draw, props, ops, ui)


def register():
    for mod in _modules:
        mod.register()


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
