#!/usr/bin/env python3
"""Compile the meshoptimizer shim into a shared library and package it as a
platform wheel that the Blender extension bundles.

Run with any Python 3 (it only shells out to the C++ compiler):

    python3 native/build_wheel.py

The resulting wheel is written to ``meshlet_preview/wheels/``. Because the
library is loaded through ctypes (not the CPython C-API) the wheel is tagged
``py3-none-<platform>`` and works across Python versions on that platform.
"""

from __future__ import annotations

import base64
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import zipfile

NAME = "meshopt_preview_native"
# Track the bundled meshoptimizer release. Bumping this on every native change
# is important: Blender's wheel manager keys on the wheel filename/version, so a
# same-named wheel with new contents would NOT be reinstalled. Bump on shim
# changes too.
VERSION = "1.1.1"

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
# meshoptimizer is a git submodule (native/meshoptimizer); its sources live in src/.
MESHOPT_DIR = os.path.join(HERE, "meshoptimizer", "src")
SHIM = os.path.join(HERE, "mp_shim.cpp")
BUILD = os.path.join(HERE, "build")
WHEELS = os.path.join(PROJECT, "meshlet_preview", "wheels")


def _platform_info():
    """Return (lib_filename, wheel_platform_tag) for the current host."""
    sysname = platform.system()
    machine = platform.machine().lower()
    if sysname == "Darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
        minos = "11_0" if arch == "arm64" else "10_13"
        return "libmeshopt_preview.dylib", f"macosx_{minos}_{arch}"
    if sysname == "Linux":
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
        # linux_<arch> is the conservative tag; rename to manylinux for PyPI-style hosts.
        return "libmeshopt_preview.so", f"linux_{arch}"
    if sysname == "Windows":
        return "meshopt_preview.dll", "win_amd64"
    raise SystemExit(f"Unsupported platform: {sysname}")


def _sources():
    cpp = [os.path.join(MESHOPT_DIR, f)
           for f in sorted(os.listdir(MESHOPT_DIR)) if f.endswith(".cpp")]
    cpp.append(SHIM)
    return cpp


def _compile(lib_name: str) -> str:
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, lib_name)
    sources = _sources()
    sysname = platform.system()

    if sysname == "Windows":
        # MSVC: build object files then link a DLL.
        objs = []
        for src in sources:
            obj = os.path.join(BUILD, os.path.splitext(os.path.basename(src))[0] + ".obj")
            subprocess.run(["cl", "/nologo", "/O2", "/EHsc", "/c", src,
                            "/Fo" + obj], check=True)
            objs.append(obj)
        subprocess.run(["link", "/nologo", "/DLL", "/OUT:" + out, *objs], check=True)
        return out

    cxx = os.environ.get("CXX", "c++")
    # Default symbol visibility keeps the extern "C" mp_* entry points exported.
    cmd = [cxx, "-O2", "-std=c++11", "-fPIC", "-shared"]
    if sysname == "Darwin":
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
        cmd += ["-arch", arch, "-mmacosx-version-min=11.0",
                "-install_name", "@rpath/" + lib_name]
    cmd += sources + ["-o", out]
    subprocess.run(cmd, check=True)
    return out


def _record_line(arcname: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{arcname},sha256={digest},{len(data)}"


def _build_wheel(lib_path: str, lib_name: str, plat_tag: str) -> str:
    os.makedirs(WHEELS, exist_ok=True)
    dist_info = f"{NAME}-{VERSION}.dist-info"
    tag = f"py3-none-{plat_tag}"
    wheel_name = f"{NAME}-{VERSION}-{tag}.whl"
    wheel_path = os.path.join(WHEELS, wheel_name)

    with open(lib_path, "rb") as fh:
        lib_data = fh.read()

    init_py = (
        '"""Native meshoptimizer shim for the Meshlet Preview addon.\n\n'
        'Use ``library_path()`` to locate the bundled shared library and load\n'
        'it with ctypes."""\n'
        "import os\n\n"
        f"_LIB = {lib_name!r}\n\n"
        "def library_path():\n"
        "    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _LIB)\n"
    )
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {NAME}\n"
        f"Version: {VERSION}\n"
        "Summary: meshoptimizer native shim for the Blender Meshlet Preview addon\n"
        "License: MIT\n"
        "Requires-Python: >=3.8\n"
    )
    wheel_meta = (
        "Wheel-Version: 1.0\n"
        "Generator: meshlet_preview_build (0.1)\n"
        "Root-Is-Purelib: false\n"
        f"Tag: {tag}\n"
    )

    members = [
        (f"{NAME}/__init__.py", init_py.encode()),
        (f"{NAME}/{lib_name}", lib_data),
        (f"{dist_info}/METADATA", metadata.encode()),
        (f"{dist_info}/WHEEL", wheel_meta.encode()),
    ]

    record_lines = [_record_line(arc, data) for arc, data in members]
    record_arc = f"{dist_info}/RECORD"
    record_lines.append(f"{record_arc},,")
    record_data = ("\n".join(record_lines) + "\n").encode()
    members.append((record_arc, record_data))

    # Remove stale wheels for this package before writing the fresh one.
    for old in os.listdir(WHEELS):
        if old.startswith(f"{NAME}-") and old.endswith(".whl"):
            os.remove(os.path.join(WHEELS, old))

    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, data in members:
            zf.writestr(arc, data)

    return wheel_path


def main():
    lib_name, plat_tag = _platform_info()
    print(f"Compiling {lib_name} for {plat_tag} ...")
    lib_path = _compile(lib_name)
    wheel_path = _build_wheel(lib_path, lib_name, plat_tag)
    print(f"Wrote {os.path.relpath(wheel_path, PROJECT)}")


if __name__ == "__main__":
    main()
