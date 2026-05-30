"""Background: build a dense mesh and save it, so the GUI screenshot pass can
open it (opening a file suppresses the splash screen)."""
import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.2)
bpy.ops.wm.save_as_mainfile(filepath="/tmp/ml.blend")
print("saved /tmp/ml.blend")
