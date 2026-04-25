"""Render side-by-side: raw fabric shell vs. polished shell.

For visual validation of garment_polish — confirms that interior smoothing,
boundary projection and cup-dome offset actually do their jobs.
"""
from __future__ import annotations

import os, sys, argparse
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

import numpy as np
from PIL import Image
import open3d as o3d

sys.path.insert(0, os.path.dirname(__file__))
from verify_ga_uv import genome_polygons
from render3d_uv import (
    cylindrical_uvs, torso_anchors, genome_to_texture,
    load_body_mesh, build_fabric_shell, build_binding_mesh,
    build_strap_meshes, _apply_weave_shade_to_texture,
)
from garment_polish import polish_shell
from seed_loader import load_seed, seed_to_genome


def _setup_scene(W: int, H: int):
    R = o3d.visualization.rendering.OffscreenRenderer(W, H)
    R.scene.set_background([0.92, 0.92, 0.92, 1.0])
    R.scene.scene.set_sun_light(
        [-0.4, -0.6, -0.8], [1.0, 1.0, 1.0], 75000)
    R.scene.scene.enable_sun_light(True)
    return R


def _frame_camera(R, mesh, zoom: str = "full"):
    """zoom in {"full","chest"} — chest tightly frames the bikini area."""
    bb = mesh.get_axis_aligned_bounding_box()
    c = bb.get_center().copy()
    extent = max(bb.get_extent())
    if zoom == "chest":
        # Frame just the upper torso so cup detail is large in frame.
        max_b = bb.get_max_bound()
        min_b = bb.get_min_bound()
        height = max_b[1] - min_b[1]
        c[1] = min_b[1] + 0.78 * height       # upper chest
        extent = 0.32 * height
    eye = c + np.array([0.0, 0.0, extent * 1.6])
    R.scene.camera.look_at(c.tolist(), eye.tolist(), [0, 1, 0])


def render_shell(genome, polish: bool, W=440, H=720, zoom: str = "full"):
    body = load_body_mesh()
    body_uvs = cylindrical_uvs(body)
    body.triangle_uvs = o3d.utility.Vector2dVector(body_uvs)
    polys_uv = genome_polygons(genome)
    yc, yn = torso_anchors(body)
    shell = build_fabric_shell(body, body_uvs, polys_uv, offset=0.3)
    if polish:
        shell = polish_shell(shell, body, polys_uv, yc, yn)

    R = _setup_scene(W, H)
    body_mat = o3d.visualization.rendering.MaterialRecord()
    body_mat.shader = "defaultLit"
    skin = (np.ones((4, 4, 3), dtype=np.uint8) * np.array([225, 188, 165], dtype=np.uint8))
    body_mat.albedo_img = o3d.geometry.Image(skin)
    body_mat.base_roughness = 0.65
    R.scene.add_geometry("body", body, body_mat)

    if len(shell.vertices) > 0:
        tex = _apply_weave_shade_to_texture(genome_to_texture(genome))
        shell_mat = o3d.visualization.rendering.MaterialRecord()
        shell_mat.shader = "defaultLit"
        shell_mat.albedo_img = o3d.geometry.Image(np.array(tex.convert("RGB")))
        shell_mat.base_roughness = 0.95 - 0.65 * float(genome.fabric_sheen)
        shell_mat.base_metallic = float(genome.fabric_metallic)
        R.scene.add_geometry("shell", shell, shell_mat)

        bind = build_binding_mesh(shell, offset=0.05, thickness=0.40)  # 4 mm FOE
        if len(bind.vertices) > 0:
            bm = o3d.visualization.rendering.MaterialRecord()
            bm.shader = "defaultLit"
            bm.base_roughness = 0.7
            R.scene.add_geometry("binding", bind, bm)

    _frame_camera(R, body, zoom=zoom)
    img = R.render_to_image()
    arr = np.asarray(img)
    return Image.fromarray(arr), shell


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seed")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    g = seed_to_genome(load_seed(args.seed))
    # 2x2: raw/full | polished/full
    #      raw/chest | polished/chest
    raw_full, raw_shell = render_shell(g, polish=False, zoom="full")
    pol_full, pol_shell = render_shell(g, polish=True, zoom="full")
    raw_chest, _ = render_shell(g, polish=False, zoom="chest", W=440, H=440)
    pol_chest, _ = render_shell(g, polish=True, zoom="chest", W=440, H=440)

    out_path = args.out or os.path.join(os.path.dirname(__file__),
                                          "output", f"polish_compare_{args.seed}.png")

    from PIL import ImageDraw
    Wf, Hf = raw_full.size
    Wc, Hc = raw_chest.size
    sheet = Image.new("RGB", (Wf * 2 + 8, Hf + Hc + 80), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    d.text((10, 10), f"RAW shell  ({len(raw_shell.vertices)} verts)  full body", fill=(255, 220, 100))
    d.text((Wf + 18, 10), f"POLISHED shell  ({len(pol_shell.vertices)} verts)  full body", fill=(150, 230, 150))
    sheet.paste(raw_full, (0, 30))
    sheet.paste(pol_full, (Wf + 8, 30))
    d.text((10, Hf + 40), "RAW — chest detail (look at jagged edges + nipple bumps)", fill=(255, 220, 100))
    d.text((Wf + 18, Hf + 40), "POLISHED — smoothed cup, FOE-style 4 mm rim", fill=(150, 230, 150))
    sheet.paste(raw_chest, ((Wf - Wc) // 2, Hf + 60))
    sheet.paste(pol_chest, (Wf + 8 + (Wf - Wc) // 2, Hf + 60))
    sheet.save(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
