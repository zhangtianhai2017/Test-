# assets/

Drop the human body mesh here. `tools/render3d_uv.py` scans this folder for
the first `.obj` file it can find (alphabetical order) and uses it as the
body.

Recommended name: `body.obj` or `smpl_female.obj`.

## Requirements

- `.obj` format (triangulated or quad; Open3D handles both)
- Y-axis up, facing +Z by default (see `--body-orient` flag if yours differs)
- Roughly centered around the origin; scale doesn't matter, the script
  normalizes it

## Ignored

Any `.mtl` file or companion textures in this folder are **ignored** — the
bikini texture is generated per-genome from the UV-unwrap GA output and
applied with a cylindrical UV reprojection, so whatever native UV layout
the mesh ships with is not used.
