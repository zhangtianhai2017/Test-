"""
Export a Genome -> game-ready garment mesh (glTF .glb).

This is the **bake / export** stage that bridges the GA's parametric
output and what an engine like Unreal or Unity can actually load:
the GA gives us 44 numbers + a UV layout, and this module turns them
into a self-contained .glb file with:

  - a single mesh: fabric shell (body triangles offset outward) + straps
    + binding (rim around the fabric edge), all merged into one primitive;
  - per-vertex UVs sharing one square albedo texture: the cylindrical
    bake from genome_to_texture for the shell, plus a small "trim" patch
    in the bottom of the texture for straps / binding / hardware;
  - a PBR-metallic-roughness material driven by Genome fields:
       baseColorTexture = the baked albedo
       metallicFactor   = genome.fabric_metallic
       roughnessFactor  = 1.0 - genome.fabric_sheen
       alphaCutoff      = (1 if fully opaque else 0.5)
  - per-vertex normals.

What a fully production-ready exporter would also output, but is
out of scope for this prototype — see docs/bikini-game-export-pipeline.md
for the long version:
  - separate normal / roughness / occlusion textures (we only bake albedo);
  - skinning weights transferred from the body skeleton;
  - Chaos Cloth simulation parameters (max-distance, backstop, stiffness)
    as vertex paints;
  - LOD chain;
  - collision body authoring;
  - Atlas-packed UV layout (we currently reuse the body cylinder UV for
    the shell, which has wasted-area issues for thin straps).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

import numpy as np
from PIL import Image
import open3d as o3d
import trimesh

sys.path.insert(0, os.path.dirname(__file__))
from verify_ga_uv import genome_polygons
from render3d_uv import (
    cylindrical_uvs, torso_anchors, genome_to_texture,
    load_body_mesh, build_fabric_shell, build_binding_mesh,
    build_strap_meshes,
)
from garment_polish import polish_shell
from seed_loader import load_seed, seed_to_genome


# Within the merged texture, the bottom TRIM_HEIGHT pixels hold a solid
# trim color. Strap / binding / hardware vertices all use UV (0.5, 0.99)
# which lands in that strip; shell vertices keep cylindrical UVs but with
# v rescaled into [0, 1 - TRIM_FRAC] so they don't sample into the trim.
TEX_W, TEX_H_BAKE = 1024, 512
TRIM_HEIGHT = 16
TEX_H = TEX_H_BAKE + TRIM_HEIGHT
TRIM_FRAC = TRIM_HEIGHT / TEX_H


def _trim_color(g) -> tuple[int, int, int]:
    """Pick a solid-color trim pixel for straps / binding.
    trim_color_mode in [0..1]: 0 = blend with primary, 1 = strong contrast."""
    import colorsys
    rgb_p = colorsys.hls_to_rgb(g.hue, g.lightness, g.saturation)
    if g.trim_color_mode > 0.5:
        # contrast: invert lightness so straps pop
        rgb = colorsys.hls_to_rgb(g.hue, 1.0 - g.lightness, g.saturation)
    else:
        rgb = rgb_p
    return tuple(int(c * 255) for c in rgb)


def _build_albedo(g) -> Image.Image:
    """1024 x 528 albedo: top 512 = cylindrical fabric bake, bottom 16 = trim."""
    bake = genome_to_texture(g)        # 1024 x 512
    if bake.size != (TEX_W, TEX_H_BAKE):
        bake = bake.resize((TEX_W, TEX_H_BAKE))
    full = Image.new("RGB", (TEX_W, TEX_H), _trim_color(g))
    full.paste(bake.convert("RGB"), (0, 0))
    return full


def _o3d_to_arrays(m: o3d.geometry.TriangleMesh):
    V = np.asarray(m.vertices, dtype=np.float64)
    F = np.asarray(m.triangles, dtype=np.int64)
    return V, F


def _shell_uvs_to_atlas(shell_uvs_per_corner: np.ndarray) -> np.ndarray:
    """Map cylindrical (u,v) -> atlas (u, v') where v' = v * (1 - TRIM_FRAC).
    Input is per-triangle-corner (3*Ntri, 2)."""
    out = shell_uvs_per_corner.copy()
    out[:, 1] *= (1.0 - TRIM_FRAC)
    return out


def _per_corner_to_per_vertex(verts: np.ndarray, faces: np.ndarray,
                               corner_uvs: np.ndarray
                               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """An o3d shell carries UVs per triangle CORNER (3*Ntri, 2). To turn
    into a glTF primitive with one UV per vertex we duplicate every vertex
    and rebuild the face index. Acceptable since the shell is only ~hundreds
    of triangles."""
    nt = len(faces)
    new_V = np.empty((nt * 3, 3), dtype=np.float64)
    new_F = np.empty((nt, 3), dtype=np.int64)
    new_UV = np.empty((nt * 3, 2), dtype=np.float32)
    for ti, (a, b, c) in enumerate(faces):
        new_V[3*ti + 0] = verts[a]
        new_V[3*ti + 1] = verts[b]
        new_V[3*ti + 2] = verts[c]
        new_UV[3*ti + 0] = corner_uvs[3*ti + 0]
        new_UV[3*ti + 1] = corner_uvs[3*ti + 1]
        new_UV[3*ti + 2] = corner_uvs[3*ti + 2]
        new_F[ti] = [3*ti, 3*ti + 1, 3*ti + 2]
    return new_V, new_F, new_UV


def export_genome_to_glb(g, out_path: str,
                         body_mesh: o3d.geometry.TriangleMesh | None = None,
                         shell_offset: float = 0.3,
                         polish: bool = True,
                         verbose: bool = True) -> dict:
    """Bake one Genome to a single .glb file. Returns stats dict.

    polish=True applies garment_polish.polish_shell which (a) flattens
    nipple bumps with Taubin smoothing, (b) snaps the jagged shell
    boundary onto the smooth Genome polygon, and (c) re-offsets so the
    cup region forms a molded dome.
    """
    if body_mesh is None:
        body_mesh = load_body_mesh()
    body_uvs = cylindrical_uvs(body_mesh)        # per-corner, (3*Ntri, 2)
    body_mesh.triangle_uvs = o3d.utility.Vector2dVector(body_uvs)

    polys_uv = genome_polygons(g)
    yc, yn = torso_anchors(body_mesh)
    shell = build_fabric_shell(body_mesh, body_uvs, polys_uv, offset=shell_offset)
    if polish and len(np.asarray(shell.triangles)) > 0:
        shell = polish_shell(shell, body_mesh, polys_uv, yc, yn)
    shell_corner_uvs = np.asarray(shell.triangle_uvs)

    # Binding ~ fold-over-elastic: industry standard 1" or 5/8" FOE folds
    # in half so it covers ~10-12 mm on each face. Our 'thickness' is the
    # rim width visible along the boundary -> 0.40 cm matches a 1" FOE
    # folded at the seam allowance (Yarnspirations / Brother USA).
    bind = build_binding_mesh(shell, offset=0.05, thickness=0.40)
    straps = build_strap_meshes(body_mesh, g, yc, yn)

    # ---- Stage 1: SHELL ----
    sV, sF = _o3d_to_arrays(shell)
    if len(sF) == 0:
        raise RuntimeError("Empty fabric shell — Genome polygons produced no triangles.")
    atlas_uvs = _shell_uvs_to_atlas(shell_corner_uvs)
    sV, sF, sUV = _per_corner_to_per_vertex(sV, sF, atlas_uvs)

    # ---- Stage 2: BINDING + STRAPS — flat trim UV ----
    extra_meshes = [("binding", bind)] + straps
    accumV, accumF, accumUV = [sV], [sF], [sUV]
    voff = sV.shape[0]
    for name, m in extra_meshes:
        V, F = _o3d_to_arrays(m)
        if len(V) == 0:
            continue
        UV = np.full((len(V), 2), [0.5, 1.0 - TRIM_HEIGHT * 0.5 / TEX_H],
                     dtype=np.float32)
        accumV.append(V)
        accumF.append(F + voff)
        accumUV.append(UV)
        voff += len(V)

    V = np.concatenate(accumV, axis=0)
    F = np.concatenate(accumF, axis=0)
    UV = np.concatenate(accumUV, axis=0)

    # Recompute vertex normals on the merged mesh.
    tri = trimesh.Trimesh(vertices=V, faces=F, process=False)
    tri.fix_normals()
    N = np.asarray(tri.vertex_normals)

    albedo = _build_albedo(g)
    material = trimesh.visual.material.PBRMaterial(
        name="fabric",
        baseColorTexture=albedo,
        baseColorFactor=(1.0, 1.0, 1.0, float(g.fabric_opacity)),
        metallicFactor=float(g.fabric_metallic),
        roughnessFactor=float(np.clip(1.0 - g.fabric_sheen, 0.05, 1.0)),
        doubleSided=True,
    )
    visual = trimesh.visual.TextureVisuals(uv=UV, material=material)
    out = trimesh.Trimesh(vertices=V, faces=F, vertex_normals=N, visual=visual,
                          process=False)

    # Embed manufacturing latent state as glTF extras["manufacturing_state"].
    # SKU IDs only — keeps payload small (well under the 64 KB practical
    # limit some glTF importers have). Engine-side LUT can resolve to
    # full catalog dicts. UnsupportedArchetypeV1 falls back to no-extras.
    try:
        from garment_state import (genome_to_garment, validate_garment,
                                     UnsupportedArchetypeV1)
        try:
            garment = validate_garment(genome_to_garment(g))
            out.metadata["extras"] = {
                "manufacturing_state": garment.sku_summary()
            }
        except UnsupportedArchetypeV1 as exc:
            out.metadata["extras"] = {
                "manufacturing_state_error": str(exc),
            }
    except Exception:
        # garment_state not available yet — proceed without extras
        pass

    out.export(out_path)

    stats = {
        "out_path": out_path,
        "vertices": int(len(V)),
        "triangles": int(len(F)),
        "shell_tris": int(len(sF)),
        "extra_tris": int(len(F) - len(sF)),
        "albedo_size": albedo.size,
        "metallic": float(g.fabric_metallic),
        "roughness": float(np.clip(1.0 - g.fabric_sheen, 0.05, 1.0)),
        "opacity": float(g.fabric_opacity),
        "filesize_kb": int(os.path.getsize(out_path) // 1024),
    }
    if verbose:
        print("--- export_genome_to_glb ---")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", help="seed name under assets/seeds/ — e.g. composite_floral")
    ap.add_argument("--out", default=None,
                    help="output .glb path. Default: tools/output/glb/<seed>.glb")
    ap.add_argument("--offset", type=float, default=0.3,
                    help="fabric shell offset from body (cm). Default 0.3")
    ap.add_argument("--no-polish", action="store_true",
                    help="skip garment_polish (smoothing, boundary snap, "
                         "cup dome) — use to compare raw shell vs. polished.")
    args = ap.parse_args()

    seed = load_seed(args.seed)
    g = seed_to_genome(seed)
    out = args.out or os.path.join(os.path.dirname(__file__),
                                    "output", "glb", f"{args.seed}.glb")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    t0 = time.time()
    export_genome_to_glb(g, out, shell_offset=args.offset,
                         polish=not args.no_polish)
    print(f"exported in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
