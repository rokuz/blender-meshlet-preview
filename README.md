# Meshlet Preview

A Blender extension that splits a mesh into **meshlets** with
[meshoptimizer](https://github.com/zeux/meshoptimizer) and previews them in the
3D viewport, so a modeller can see and fix the things that hurt GPU
mesh-shading / cluster-culling performance.

Built for **Blender 5.1.2** (Python 3.13); the manifest declares
`blender_version_min = 4.2.0`.

## What it shows

Pick a metric in the **Meshlet** sidebar panel (`N` → *Meshlet*) and the overlay
recolors live. Tune the parameters and press **Build / Recalculate Meshlets** to
re-split after editing the mesh.

| View mode | What it reveals |
|-----------|-----------------|
| **Meshlet Partition** | The actual triangle clusters (one color each). Long/stringy clusters cluster poorly. |
| **Fill Efficiency** | How full each meshlet is vs the vertex/triangle caps. Red = under-filled = wasted GPU warps. |
| **Cone Culling** | Normal-cone tightness. Red = wide/uncullable cone (can't be backface-cluster-culled). |
| **Overdraw** | Per-meshlet overdraw ratio from meshoptimizer's software rasterizer. |
| **Vertex Cache (ACMR)** | Per-meshlet average cache miss ratio (triangle ordering quality). |
| **Geometry Quality** | Red where a meshlet has degenerate/sliver triangles (scale-invariant quality below the *Sliver Threshold*) or is spatially stringy (low compactness). Picking it outlines the offending triangles in red. |

The panel also reports global statistics: meshlet count, average/min fill,
percentage of wide cones, degenerate-triangle count, average/min compactness,
ACMR, ATVR, overdraw and overfetch.

The overlay is **non-destructive** — it is drawn with the `gpu` module and never
modifies your mesh data. It evaluates modifiers, so the preview matches what
actually gets rendered.

### Inspecting a single meshlet

Press **Pick Meshlet** and click a meshlet in the viewport: it is outlined as a
white wireframe and the panel shows that meshlet's vertex/triangle counts, fill,
cone cutoff, ACMR and overdraw. Click empty space to deselect, `Esc` or
right-click to finish picking (you can still orbit/zoom while picking).

## Installation

### From a release (recommended)

1. Download `meshlet_preview-<version>.zip` from the
   [**Releases**](../../releases) page. The zip bundles the native library for
   macOS (Apple Silicon + Intel), Windows x64 and Linux x64 — Blender picks the
   one for your platform automatically.
2. In Blender: **Edit → Preferences → Add-ons** (Blender 5.x: the *Get
   Extensions* / *Add-ons* tab) → the **▾** menu (top-right) → **Install from
   Disk…** → pick the zip.
   - Or simply **drag-and-drop the zip into the Blender window**.
3. Enable **Meshlet Preview** if it isn't already, then open the 3D viewport
   sidebar (`N`) and switch to the **Meshlet** tab.

Requires Blender 4.2 or newer (developed against 5.1.2). When prompted, allow
the bundled Python wheel to be installed — that is the meshoptimizer library.

### From source

```sh
python3 native/build_wheel.py        # compile the native wheel for this OS
python3 native/package_extension.py  # -> dist/meshlet_preview-<version>.zip
```

then install `dist/meshlet_preview-<version>.zip` as above. The source build only
contains the wheel for your current platform.

## Releases (CI)

Pushing a `v*` tag (e.g. `git tag v0.1.0 && git push origin v0.1.0`) triggers
`.github/workflows/release.yml`, which builds the native wheel on macOS arm64,
macOS x64, Windows x64 and Linux x64 runners, runs `native/package_extension.py`
to assemble a single multi-platform zip, and publishes it as a GitHub release.
You can also run the workflow manually (*Actions → Build & Release → Run
workflow*) to get the zip as a build artifact without releasing.

## How it is built

meshoptimizer's public PyPI package does **not** expose the meshlet builder, so
this project vendors the meshoptimizer MIT C source (`native/meshoptimizer/`)
plus a thin C ABI shim (`native/mp_shim.cpp`) that runs the whole pipeline in one
call. It is compiled to a shared library and called from Python via `ctypes`
(`meshlet_preview/meshopt.py`), so it is independent of Blender's Python ABI.

The library is delivered as a platform **wheel** bundled by the extension —
the supported way to ship native code to
[extensions.blender.org](https://extensions.blender.org/).

### Build the native wheel

```sh
python3 native/build_wheel.py
```

This compiles the shared library for the current OS/arch and writes a wheel into
`meshlet_preview/wheels/`. Run it on each platform you want to support, collect
the wheels into `meshlet_preview/wheels/`, then `native/package_extension.py`
rewrites the manifest's `wheels`/`platforms` lists to match and builds the zip.
CI does exactly this across all platforms (see *Releases* above).

### Build / install the extension

```sh
# Build the installable .zip
blender --command extension build --source-dir meshlet_preview --output-dir dist

# Or install straight into Blender
blender --command extension install-file --repo user_default --enable \
    dist/meshlet_preview-0.1.0.zip
```

To remove it again: *Edit → Preferences → Get Extensions → Meshlet Preview →
Remove*, or `blender --command extension remove ...`.

## Tests

```sh
# Native library only (no Blender)
python3 native/test_shim.py

# Inside Blender, from source
blender --background --python tests/test_blender.py

# The installed extension (wheel-provided native lib)
blender --background --python tests/test_installed.py

# Visual: render each view mode to a PNG (GUI)
blender --background --python tests/make_scene.py
blender /tmp/ml.blend --python tests/screenshot.py -- /tmp/ms_CONE.png CONE
```

## Layout

```
meshlet_preview/            the extension (uploadable to extensions.blender.org)
  blender_manifest.toml
  __init__.py               registration
  props.py                  parameters + view-mode enum
  ops.py                    build / clear operators
  ui.py                     N-panel
  draw.py                   result cache, colormaps, GPU overlay
  meshopt.py                ctypes binding to the native shim
  wheels/                   bundled native wheel(s)
native/
  meshoptimizer/            vendored MIT source (v0.22)
  mp_shim.cpp               C ABI shim over meshoptimizer
  build_wheel.py            compiles the lib and packages the wheel
tests/
```

## Licenses

Addon code: GPL-3.0-or-later. Bundled meshoptimizer: MIT (see
`native/meshoptimizer/LICENSE.meshoptimizer.txt`).
