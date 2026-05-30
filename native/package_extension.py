#!/usr/bin/env python3
"""Assemble the installable extension zip from the wheels currently present in
``meshlet_preview/wheels/``.

The committed manifest only references the single locally-built wheel so that
``blender --command extension build`` works during development. For a release we
build one native wheel per platform (see the CI workflow), drop them all into
``meshlet_preview/wheels/`` and run this script: it rewrites the ``wheels`` and
``platforms`` arrays to match what is actually present and writes
``dist/<id>-<version>.zip``. No Blender install required.
"""

from __future__ import annotations

import os
import re
import sys
import zipfile

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    print("This script needs Python 3.11+ (tomllib).", file=sys.stderr)
    raise

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
PKG = os.path.join(PROJECT, "meshlet_preview")
WHEELS = os.path.join(PKG, "wheels")
MANIFEST = os.path.join(PKG, "blender_manifest.toml")
DIST = os.path.join(PROJECT, "dist")

# meshoptimizer wheel platform tag -> Blender extension platform id.
_PLATFORM_MAP = (
    ("macosx_", "_arm64", "macos-arm64"),
    ("macosx_", "_x86_64", "macos-x64"),
    ("manylinux", "_aarch64", "linux-arm64"),
    ("manylinux", "_x86_64", "linux-x64"),
    ("linux_", "aarch64", "linux-arm64"),
    ("linux_", "x86_64", "linux-x64"),
    ("win_", "arm64", "windows-arm64"),
    ("win_", "amd64", "windows-x64"),
)


def _platform_for_wheel(name: str):
    tag = name[:-4]  # strip .whl
    plat = tag.split("-")[-1]  # last segment is the platform tag
    for prefix, suffix, blender_id in _PLATFORM_MAP:
        if prefix in plat and suffix in plat:
            return blender_id
    return None


def _replace_array(text: str, key: str, items: list[str]) -> str:
    body = "".join(f'  "{it}",\n' for it in items)
    new = f"{key} = [\n{body}]"
    pattern = re.compile(rf"^{re.escape(key)}\s*=\s*\[.*?\]", re.DOTALL | re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(new, text, count=1)
    return text.rstrip() + "\n\n" + new + "\n"


def main():
    with open(MANIFEST, "rb") as fh:
        meta = tomllib.load(fh)
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        text = fh.read()

    wheels = sorted(f for f in os.listdir(WHEELS) if f.endswith(".whl"))
    if not wheels:
        raise SystemExit("No wheels in meshlet_preview/wheels/ — run build_wheel.py first.")

    platforms = []
    wheel_refs = []
    for w in wheels:
        plat = _platform_for_wheel(w)
        wheel_refs.append(f"./wheels/{w}")
        if plat and plat not in platforms:
            platforms.append(plat)
        print(f"  {w} -> {plat}")

    text = _replace_array(text, "platforms", sorted(platforms))
    text = _replace_array(text, "wheels", wheel_refs)

    os.makedirs(DIST, exist_ok=True)
    zip_name = f"{meta['id']}-{meta['version']}.zip"
    zip_path = os.path.join(DIST, zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("blender_manifest.toml", text)
        for root, dirs, files in os.walk(PKG):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                if fn == "blender_manifest.toml" or fn.endswith(".pyc"):
                    continue
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, PKG)
                zf.write(full, arc)

    print(f"Wrote {os.path.relpath(zip_path, PROJECT)} "
          f"({len(wheels)} wheel(s), platforms: {', '.join(sorted(platforms))})")


if __name__ == "__main__":
    main()
