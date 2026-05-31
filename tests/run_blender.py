"""Run the unittest suite inside Blender and exit with a real status code.

    blender --background --python tests/run_blender.py

Discovers every tests/test_*.py. Tests guarded with ``skipUnless(HAS_BPY)`` run
here because bpy is available; the native tests run too. Exits 0 on success,
1 on any failure/error so CI and local runs get a usable result.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

suite = unittest.TestLoader().discover(HERE, pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)

sys.stderr.flush()
sys.stdout.flush()
# os._exit avoids Blender swallowing the status code on shutdown.
os._exit(0 if result.wasSuccessful() else 1)
