"""
3D preview renderer for the UV-unwrap bikini GA.

Loads a body mesh from assets/*.obj, discards its native UV, computes a
cylindrical UV (u = atan2(x, z) / pi, v = normalized height) so the
Genome's "world map" polygons line up with body landmarks, rasterizes
each Genome into a texture via PIL, and renders the textured body with
Open3D's OffscreenRenderer in CPU mode.

Outputs:
    tools/output/ga_3d_render.png             2x5 grid of 3D renders
    tools/output/ga_3d_textures/genome_*.png  per-genome flat textures

Run: `python3 tools/render3d_uv.py`
"""

from __future__ import annotations

import glob
import os
import math
import sys
import time

# OPEN3D_CPU_RENDERING must be set before importing open3d
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

import numpy as np
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt

import open3d as o3d

# Reuse everything from the UV verifier
sys.path.insert(0, os.path.dirname(__file__))
from verify_ga_uv import (
    Genome,
    LANDMARKS_V,
    _color,
    genome_polygons,
    make_parents,
    run_ga,
)
import random


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ROOT, "assets")
OUT_DIR = os.path.join(ROOT, "tools", "output")
TEX_DIR = os.path.join(OUT_DIR, "ga_3d_textures")

TEX_W, TEX_H = 1024, 512        # texture resolution (2:1 for u:v)
RENDER_W, RENDER_H = 384, 576   # per-genome render resolution
SEED = 42
N_OFFSPRING = 8
SKIN_RGB = (243, 217, 192)      # fallback skin tone for the uncovered area

# Fabric weave: number of thread cycles across the U and V texture axes.
# Chosen so cells read as fabric but aren't so fine they alias to noise at
# the render resolution. U wraps ~90cm (body circumference) so 64 threads
# -> ~1.4cm each; V spans ~90cm so 32 threads keeps cells square-ish.
WEAVE_U_THREADS = 140
WEAVE_V_THREADS = 70


# --------------------------------------------------------------------------
# Texture rasterization — Genome -> PIL.Image
# --------------------------------------------------------------------------

def _uv_to_px(poly_uv: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Map (u in [-1,1], v in [0,1]) to PIL pixel coords (0..W, 0..H).

    v=0 (hip/groin) is at the IMAGE BOTTOM (y = (1-v)*H). Open3D's
    UV sampling uses the OpenGL convention (v=0 at the image bottom),
    so this flip is correct and required to make poly-paint match
    shell-sample. Verified empirically: cup at v=0.75 paints at pixel
    rows 82-190 and Open3D reads it from row 128 — GREEN. Inverting
    to y=v*H (no flip) shifted cup to pixel rows 333-435 while Open3D
    still read row 128 → cup turned skin-toned.
    """
    out = []
    for u, v in poly_uv:
        x = (u + 1.0) * 0.5 * TEX_W
        y = (1.0 - v) * TEX_H
        out.append((int(round(x)), int(round(y))))
    return out


def _poly_bbox_px(poly_px: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs = [p[0] for p in poly_px]
    ys = [p[1] for p in poly_px]
    return min(xs), min(ys), max(xs), max(ys)


def _draw_pattern_into(layer: Image.Image, poly_px, pattern: str,
                       primary_rgba: tuple[int, int, int, int],
                       secondary_rgba: tuple[int, int, int, int],
                       scale: float = 0.5,
                       angle: float = 0.0):
    """Draw an overlay pattern into `layer`, clipped later by the polygon
    mask. `primary_rgba` is the fabric base color (already painted under);
    `secondary_rgba` is the accent color for two-colour prints. `scale` in
    [0,1] scales motif size; `angle` in [0,1] maps to 0..180 deg rotation.
    """
    draw = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = _poly_bbox_px(poly_px)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    # motif size scales from ~10px at 0 to ~60px at 1
    motif = max(6, int(10 + 50 * scale))
    acc = secondary_rgba[:3] + (170,)
    acc_dim = (max(0, acc[0] - 50), max(0, acc[1] - 50),
                max(0, acc[2] - 50), 200)
    white = (255, 255, 255, 130)

    if pattern == "stripe":
        n = max(4, int(20 / (0.4 + scale)))
        sh = max(1, h // (n * 2))
        for i in range(n):
            cy = y0 + (i + 0.5) * h / n
            draw.rectangle([x0, cy - sh, x1, cy + sh], fill=acc)
    elif pattern == "polka":
        rng = np.random.default_rng(0)
        r = max(2, motif // 5)
        count = max(10, (w * h) // (motif * motif * 3))
        for _ in range(count):
            cx = rng.uniform(x0, x1)
            cy = rng.uniform(y0, y1)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=white)
    elif pattern == "checker":
        n = max(4, int(14 / (0.3 + scale)))
        dx = max(2, w // n); dy = max(2, h // n)
        for i in range(n):
            for j in range(n):
                if (i + j) % 2 == 0:
                    draw.rectangle(
                        [x0 + i * dx, y0 + j * dy,
                         x0 + (i + 1) * dx, y0 + (j + 1) * dy], fill=acc)
    elif pattern == "gingham":
        n = max(5, int(12 / (0.3 + scale)))
        dx = max(2, w // n); dy = max(2, h // n)
        light = acc[:3] + (90,)
        dark = acc[:3] + (170,)
        for i in range(n):
            for j in range(n):
                xx = x0 + i * dx; yy = y0 + j * dy
                if i % 2 == 1 and j % 2 == 1:
                    draw.rectangle([xx, yy, xx + dx, yy + dy], fill=dark)
                elif i % 2 == 1 or j % 2 == 1:
                    draw.rectangle([xx, yy, xx + dx, yy + dy], fill=light)
    elif pattern == "chevron":
        n = max(4, int(10 / (0.3 + scale)))
        band_h = h / n
        zig_w = max(6, motif)
        for i in range(n):
            if i % 2 == 0:
                y = y0 + i * band_h
                for xx in range(int(x0), int(x1) + zig_w, zig_w):
                    draw.polygon([
                        (xx, y + band_h),
                        (xx + zig_w / 2, y),
                        (xx + zig_w, y + band_h),
                    ], fill=acc)
    elif pattern == "floral":
        rng = np.random.default_rng(0)
        # clamp motif size to fit the bbox so rng.uniform's low<high always
        r_big = max(2, min(motif // 3, (min(w, h) - 2) // 3))
        r_small = max(1, r_big // 3)
        count = max(6, (w * h) // max(1, motif * motif * 3))
        for _ in range(count):
            lo_x, hi_x = x0 + r_big, x1 - r_big
            lo_y, hi_y = y0 + r_big, y1 - r_big
            if hi_x <= lo_x or hi_y <= lo_y:
                break
            cx = rng.uniform(lo_x, hi_x)
            cy = rng.uniform(lo_y, hi_y)
            for k in range(5):
                a = 2 * np.pi * k / 5
                px = cx + r_big * np.cos(a)
                py = cy + r_big * np.sin(a)
                draw.ellipse([px - r_small, py - r_small,
                               px + r_small, py + r_small], fill=acc)
            draw.ellipse([cx - r_small, cy - r_small,
                           cx + r_small, cy + r_small], fill=acc_dim)
    elif pattern == "tropical":
        rng = np.random.default_rng(0)
        r = max(6, motif // 2)
        count = max(3, (w * h) // (motif * motif * 6))
        for _ in range(count):
            cx = rng.uniform(x0, x1); cy = rng.uniform(y0, y1)
            # palm-leaf-like ellipse
            angle_deg = rng.uniform(0, 180)
            bbox = [cx - r, cy - r * 0.5, cx + r, cy + r * 0.5]
            draw.ellipse(bbox, fill=acc)
    elif pattern == "leopard":
        rng = np.random.default_rng(0)
        r = max(2, motif // 5)
        count = max(25, (w * h) // (motif * motif))
        for _ in range(count):
            cx = rng.uniform(x0, x1); cy = rng.uniform(y0, y1)
            rr = r * rng.uniform(0.7, 1.3)
            draw.ellipse([cx - rr, cy - rr * 0.8,
                           cx + rr, cy + rr * 0.8], fill=acc)
            if rng.random() < 0.6:
                draw.ellipse([cx - rr * 0.4, cy - rr * 0.3,
                               cx + rr * 0.4, cy + rr * 0.3], fill=acc_dim)
    elif pattern == "tie_dye":
        # radial blend of acc toward the polygon center
        tile = np.zeros((h, w, 4), dtype=np.uint8)
        yy, xx = np.indices((h, w))
        d = np.sqrt((xx - w / 2) ** 2 + (yy - h / 2) ** 2)
        d /= max(d.max(), 1)
        mix = np.clip(1 - d, 0, 1) ** 1.5
        tile[..., 0] = acc[0]; tile[..., 1] = acc[1]; tile[..., 2] = acc[2]
        tile[..., 3] = (mix * 200).astype(np.uint8)
        layer.paste(Image.fromarray(tile), (x0, y0), Image.fromarray(tile))
    elif pattern == "ombre":
        # vertical gradient: top = 0 alpha, bottom = strong secondary
        tile = np.zeros((h, w, 4), dtype=np.uint8)
        tile[..., 0] = acc[0]; tile[..., 1] = acc[1]; tile[..., 2] = acc[2]
        tile[..., 3] = np.linspace(0, 220, h, dtype=np.uint8)[:, None]
        layer.paste(Image.fromarray(tile), (x0, y0), Image.fromarray(tile))
    elif pattern == "herringbone":
        bh = max(4, motif // 3); bw = bh * 3
        for j, y in enumerate(range(int(y0), int(y1), bh)):
            tilt = bh // 2 if j % 2 == 0 else -bh // 2
            for x in range(int(x0), int(x1), bw):
                draw.polygon([(x, y), (x + bw, y + tilt),
                               (x + bw, y + tilt + bh), (x, y + bh)],
                              fill=acc)
    elif pattern == "pinstripe":
        # Very thin vertical stripes
        n = max(20, int(50 / (0.3 + scale)))
        sw = max(1, w // (n * 4))
        for i in range(n):
            cx = x0 + (i + 0.5) * w / n
            draw.rectangle([cx - sw, y0, cx + sw, y1], fill=acc)
    elif pattern == "mesh":
        # See-through grid pattern: thin lines forming squares
        n = max(8, int(20 / (0.3 + scale)))
        line_w = max(1, motif // 10)
        for i in range(n + 1):
            xx = x0 + i * w / n
            draw.line([(xx, y0), (xx, y1)], fill=acc, width=line_w)
        for j in range(int(h / (w / n)) + 1):
            yy = y0 + j * w / n
            draw.line([(x0, yy), (x1, yy)], fill=acc, width=line_w)
    elif pattern == "lace":
        # Fine repeating floral-like dots in a diagonal grid
        s = max(6, motif // 2)
        r = max(2, s // 4)
        for j in range(int(h / s) + 2):
            yy = y0 + j * s
            x_off = (s // 2) if j % 2 else 0
            for i in range(int(w / s) + 2):
                cx = x0 + i * s + x_off
                draw.ellipse([cx - r, yy - r, cx + r, yy + r], fill=acc)
                # surrounding petals
                for k in range(4):
                    ang = np.pi * k / 2
                    px = cx + int(r * 1.8 * np.cos(ang))
                    py = yy + int(r * 1.8 * np.sin(ang))
                    draw.ellipse([px - 1, py - 1, px + 1, py + 1], fill=acc_dim)
    elif pattern == "snake":
        # Snakeskin: small diamond scales
        rng = np.random.default_rng(1)
        s = max(4, motif // 3)
        for j in range(int(h / s) + 1):
            yy = y0 + j * s
            x_off = (s // 2) if j % 2 else 0
            for i in range(int(w / s) + 1):
                cx = x0 + i * s + x_off
                d = s // 2
                sh = acc if rng.random() < 0.7 else acc_dim
                draw.polygon([(cx, yy - d), (cx + d, yy),
                               (cx, yy + d), (cx - d, yy)], fill=sh)
    elif pattern == "zebra":
        # Irregular vertical stripes alternating
        rng = np.random.default_rng(2)
        x = x0
        sw_lo = max(2, motif // 3); sw_hi = max(sw_lo + 1, motif)
        gap_lo = max(2, motif // 4); gap_hi = max(gap_lo + 1, motif // 2)
        while x < x1:
            sw = rng.integers(sw_lo, sw_hi)
            draw.rectangle([x, y0, min(x1, x + sw), y1], fill=acc)
            x += sw + rng.integers(gap_lo, gap_hi)
    elif pattern == "color_block_v":
        # Vertical split: left half acc, right half stays primary
        mid = x0 + w // 2
        draw.rectangle([x0, y0, mid, y1], fill=acc)
    elif pattern == "color_block_h":
        # Horizontal split
        mid = y0 + h // 2
        draw.rectangle([x0, y0, x1, mid], fill=acc)
    elif pattern == "color_block_diag":
        # Diagonal triangle fill
        draw.polygon([(x0, y0), (x1, y0), (x0, y1)], fill=acc)
    elif pattern == "houndstooth":
        # Broken check: tight diamond + rectangle alternation
        s = max(4, motif // 3)
        for j in range(int(h / s) + 1):
            yy = y0 + j * s
            for i in range(int(w / s) + 1):
                cx = x0 + i * s
                if (i + j) % 2 == 0:
                    draw.polygon([(cx, yy), (cx + s, yy),
                                   (cx + s // 2, yy + s)], fill=acc)
                else:
                    draw.rectangle([cx, yy, cx + s // 2, yy + s], fill=acc_dim)
    elif pattern == "argyle":
        # Diamond grid
        s = max(8, motif)
        for j in range(int(h / s) + 2):
            yy = y0 + j * s
            for i in range(int(w / s) + 2):
                cx = x0 + i * s + (s // 2 if j % 2 else 0)
                d = s // 2
                if (i + j) % 2 == 0:
                    draw.polygon([(cx, yy - d), (cx + d, yy),
                                   (cx, yy + d), (cx - d, yy)], fill=acc)
    elif pattern == "watercolor":
        # Multiple soft blobs of secondary color
        rng = np.random.default_rng(3)
        n = max(4, (w * h) // (motif * motif * 8))
        for _ in range(n):
            cx = rng.uniform(x0, x1); cy = rng.uniform(y0, y1)
            rr = motif * rng.uniform(0.6, 1.6)
            soft = acc[:3] + (90,)
            draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=soft)
    elif pattern == "geo_diamond":
        # Sharp diamond grid (different from argyle: filled & outlined)
        s = max(8, motif)
        for j in range(int(h / s) + 1):
            yy = y0 + j * s
            for i in range(int(w / s) + 1):
                cx = x0 + i * s + (s // 2 if j % 2 else 0)
                d = s // 2
                if (i + j) % 3 == 0:
                    draw.polygon([(cx, yy - d), (cx + d, yy),
                                   (cx, yy + d), (cx - d, yy)],
                                  fill=acc, outline=acc_dim)
    elif pattern == "damask":
        # Stylized floral medallion repeating
        s = max(20, motif * 2)
        for j in range(int(h / s) + 1):
            yy = y0 + j * s + s // 2
            for i in range(int(w / s) + 1):
                cx = x0 + i * s + s // 2 + (s // 2 if j % 2 else 0)
                # 4-petal flower
                for k in range(4):
                    ang = np.pi * k / 2
                    px = cx + int(s // 3 * np.cos(ang))
                    py = yy + int(s // 3 * np.sin(ang))
                    pr = s // 5
                    draw.ellipse([px - pr, py - pr, px + pr, py + pr],
                                  fill=acc)
                draw.ellipse([cx - 3, yy - 3, cx + 3, yy + 3], fill=acc_dim)


def genome_to_texture(g: Genome,
                       polys_override: list[list[tuple[float, float]]] | None = None
                       ) -> Image.Image:
    """Rasterize a Genome's UV polygons into a texture PNG (1024x512 RGBA).

    `polys_override` (added 2026-05-23): when supplied, draws THESE
    polygons instead of `genome_polygons(g)`. Required when the shell
    is built from `garm.flatten_polygons()` (outfit -> garment path),
    because the genome-based polygons differ in shape — notably the
    front_bottom in `genome_polygons` has a V-notch at the top center
    that the garment trapezoid doesn't, so shell verts in that notch
    region sample skin-color from the painted texture and render as
    bare skin. Passing the garment polygons here aligns texture paint
    with shell mesh extent."""
    from verify_ga_uv import _secondary_color
    img = Image.new("RGBA", (TEX_W, TEX_H), SKIN_RGB + (255,))
    draw = ImageDraw.Draw(img, "RGBA")

    r, gr, b = _color(g)
    primary_rgba = (int(r * 255), int(gr * 255), int(b * 255), 255)
    r2, g2, b2 = _secondary_color(g)
    secondary_rgba = (int(r2 * 255), int(g2 * 255), int(b2 * 255), 255)

    polys_to_draw = (polys_override if polys_override is not None
                      else genome_polygons(g))
    for poly_uv in polys_to_draw:
        poly_px = _uv_to_px(poly_uv)
        if len(set(poly_px)) < 3:
            continue
        draw.polygon(poly_px, fill=primary_rgba, outline=(35, 35, 35, 255))
        if g.pattern != "solid":
            mask = Image.new("L", (TEX_W, TEX_H), 0)
            ImageDraw.Draw(mask).polygon(poly_px, fill=255)
            # Build the pattern on top of a solid-primary base so the
            # accent alpha blends over the primary color instead of
            # wiping it out when mask-composited.
            base = Image.new("RGBA", (TEX_W, TEX_H), primary_rgba)
            accent = Image.new("RGBA", (TEX_W, TEX_H), (0, 0, 0, 0))
            _draw_pattern_into(accent, poly_px, g.pattern,
                                primary_rgba, secondary_rgba,
                                scale=g.pattern_scale, angle=g.pattern_angle)
            combined = Image.alpha_composite(base, accent)
            img = Image.composite(combined, img, mask).convert("RGBA")
            draw = ImageDraw.Draw(img, "RGBA")
    # Paint a skin-tone safe band at the top and bottom of the texture.
    # Body vertices whose genome v clamps to 0 (legs) or 1 (head) end up
    # sampling near the image edges; without these bands they'd pick up
    # the extreme rows of whatever polygon happened to touch v=0/1.
    margin = 18
    draw.rectangle([0, 0, TEX_W, margin], fill=SKIN_RGB + (255,))
    draw.rectangle([0, TEX_H - margin, TEX_W, TEX_H], fill=SKIN_RGB + (255,))
    return img


# --------------------------------------------------------------------------
# Body mesh — load and re-UV with a cylindrical "world map" projection
# --------------------------------------------------------------------------

def load_body_mesh() -> o3d.geometry.TriangleMesh:
    objs = sorted(glob.glob(os.path.join(ASSETS_DIR, "*.obj")))
    if not objs:
        raise SystemExit(
            f"No .obj found in {ASSETS_DIR}. Drop a body mesh there and re-run."
        )
    path = objs[0]
    print(f"loading body mesh: {path}")
    mesh = o3d.io.read_triangle_mesh(path)
    # We re-UV cylindrically, so the native triangle_uvs and textures
    # are intentionally discarded.
    mesh.triangle_uvs = o3d.utility.Vector2dVector(np.zeros((0, 2)))
    mesh.textures = []
    # UE exports split vertices at every UV/material seam (132k vertices
    # for 95k triangles) — every triangle ends up an island with no shared
    # edges. Merge near-coincident vertices so the shell extraction and
    # boundary-edge detection in build_binding_mesh work properly.
    mesh.merge_close_vertices(eps=1e-3)
    mesh.compute_vertex_normals()
    return mesh


def torso_anchors(mesh: o3d.geometry.TriangleMesh) -> tuple[float, float]:
    """Return (y_crotch, y_neck) for this body mesh, computed with the same
    empirical fractions used by cylindrical_uvs. Exposed so the strap
    builders can place bands at the same body heights as the UV texture.
    """
    V = np.asarray(mesh.vertices)
    y_min, y_max = np.percentile(V[:, 1], [2, 98])
    body_height = y_max - y_min
    return y_min + 0.337 * body_height, y_min + 0.939 * body_height


def cylindrical_uvs(mesh: o3d.geometry.TriangleMesh) -> np.ndarray:
    """Compute per-triangle, per-vertex UVs by projecting the body onto a
    cylinder. Returns a (num_triangles*3, 2) float array.

    Convention: Y up, +Z front. u = atan2(x, z)/pi gives u=0 at the front
    center, u=+/-1 at the back seam. v is normalized height within the
    torso range so the bikini area fills the texture.
    """
    V = np.asarray(mesh.vertices)
    T = np.asarray(mesh.triangles)

    y = V[:, 1]
    # Remap v so Genome landmarks align with body anthropometrics.
    # Genome's LANDMARKS_V: bust=0.78, hip=0.22. Body anthropometrics:
    # bust ~= 73% of stature, hip ~= 46%. Two-point linear fit:
    #   y(v) = (0.354 + 0.482 * v) * stature
    # So v=0 anchors below the crotch, v=1 anchors around the clavicle.
    # Head/leg vertices clamp to 0/1 and sample skin rows of the texture.
    # Two-point linear fit so Genome v=0.76 (top_center_v in make_parents)
    # lands on this mesh's actual breast peak, and v=0.22 (front-panel top)
    # lands on the hip. For this UE NPC the peaks sit at y~130 and y~77;
    # that yields y_crotch=0.337*H, y_neck=0.939*H (see breast-peak probe).
    y_min, y_max = np.percentile(y, [2, 98])
    body_height = y_max - y_min
    y_crotch = y_min + 0.337 * body_height
    y_neck   = y_min + 0.939 * body_height

    # azimuth: atan2(x, z), +Z forward -> u=0 at front
    theta = np.arctan2(V[:, 0], V[:, 2])   # [-pi, pi]
    u = theta / np.pi                       # [-1, 1]
    v = np.clip((y - y_crotch) / (y_neck - y_crotch), 0.0, 1.0)

    # No seam unwrap: triangles that straddle u=+/-1 will get a distorted
    # strip ("candy stripe") across the back of the body because their
    # three UVs interpolate across the whole texture width. That's OK —
    # the camera frames the front, the back artifact is invisible, and
    # we avoid the worse bug of UVs clamping to the fabric pixels at
    # u=0/1 when the default sampler is CLAMP (no REPEAT in Open3D's
    # defaultLit Material).
    tri_u = u[T]                            # (NT, 3)
    tri_v = v[T]                            # (NT, 3)
    uvs = np.stack([tri_u, tri_v], axis=-1).reshape(-1, 2)
    uvs[:, 0] = (uvs[:, 0] + 1.0) * 0.5      # [-1, 1] -> [0, 1]
    return uvs


# --------------------------------------------------------------------------
# 3D strap meshes — closed-loop geometry so each bikini looks like it's
# actually held on the body (Path B in the stay-on discussion).
#
# Each strap is a ribbon generated by sampling the body surface at a fixed
# y, offsetting the sampled points outward along their radial direction in
# the XZ plane, then extruding up/down by the strap thickness.
# --------------------------------------------------------------------------

def _body_ring(body_vertices: np.ndarray, y_level: float, y_halfband: float,
               n_samples: int = 96, max_torso_radius: float = 25.0,
               ) -> np.ndarray:
    """Sample the body's cross-section at y=y_level as a ring of points.

    At bust level the T-pose arm-root sits at the same Y and nearly the
    same theta as the torso side, so a naive "vertex with closest angle"
    pick may land on the arm root and push the back band onto the arm.
    To avoid that: among vertices within an angular tolerance of each
    target, pick the one with the SMALLEST XZ-plane radius — guaranteed
    to be the torso surface, not an arm.
    """
    near = body_vertices[(body_vertices[:, 1] > y_level - y_halfband) &
                          (body_vertices[:, 1] < y_level + y_halfband)]
    if len(near) > 0:
        r = np.sqrt(near[:, 0] ** 2 + near[:, 2] ** 2)
        near = near[r < max_torso_radius]
    if len(near) < n_samples // 4:
        # Bug fix: the previous fallback dropped the radius filter, which
        # let arm vertices into the ring at chest/bust level (T-pose arms
        # share Y with the upper chest). That dragged the back band onto
        # the arms. Instead, widen the Y window — keeping the radius
        # filter — until we have enough torso samples.
        for grow in (1.5, 2.0, 3.0):
            near = body_vertices[(body_vertices[:, 1] > y_level - y_halfband * grow) &
                                  (body_vertices[:, 1] < y_level + y_halfband * grow)]
            r = np.sqrt(near[:, 0] ** 2 + near[:, 2] ** 2)
            near = near[r < max_torso_radius]
            if len(near) >= n_samples // 4:
                break

    theta = np.arctan2(near[:, 0], near[:, 2])
    r_xz = np.sqrt(near[:, 0] ** 2 + near[:, 2] ** 2)
    targets = np.linspace(-np.pi, np.pi, n_samples, endpoint=False)
    angle_tol = 0.12  # rad; ~7 deg window around each target
    ring = []
    for t in targets:
        d = np.abs(np.mod(theta - t + np.pi, 2 * np.pi) - np.pi)
        close = np.where(d < angle_tol)[0]
        if len(close) > 0:
            idx = close[np.argmin(r_xz[close])]
        else:
            idx = int(np.argmin(d))
        ring.append([near[idx, 0], y_level, near[idx, 2]])
    return np.array(ring, dtype=np.float32)


def _build_band_mesh(ring: np.ndarray, band_thickness: float, offset: float,
                      u_from: float | None = None,
                      u_to: float | None = None,
                      ) -> o3d.geometry.TriangleMesh:
    """Turn a ring of body surface points into a ribbon mesh that sits just
    off the body. If u_from/u_to are given we clip to that arc.

    ring is expected to be sorted by cylindrical angle theta in [-pi, pi].
    For a full ring (u_from=u_to=None) the closing edge between index N-1
    and 0 is also emitted. For a clipped arc, only consecutive ACTIVE
    vertices generate triangles — no jump across the inactive gap.
    """
    N = len(ring)
    thetas = np.arctan2(ring[:, 0], ring[:, 2])

    if u_from is None and u_to is None:
        active = np.ones(N, dtype=bool)
        full_ring = True
    else:
        t_from = u_from * np.pi
        t_to = u_to * np.pi
        if t_from <= t_to:
            active = (thetas >= t_from) & (thetas <= t_to)
        else:
            active = (thetas >= t_from) | (thetas <= t_to)
        full_ring = False

    if active.sum() < 2:
        return o3d.geometry.TriangleMesh()

    # radial offset outward in XZ, then split into lower / upper rings
    radial = np.stack([ring[:, 0], np.zeros(N), ring[:, 2]], axis=1)
    r_len = np.linalg.norm(radial, axis=1, keepdims=True)
    r_unit = radial / np.maximum(r_len, 1e-6)
    outer_ring = ring + r_unit * offset

    lower = outer_ring.copy(); lower[:, 1] -= band_thickness / 2
    upper = outer_ring.copy(); upper[:, 1] += band_thickness / 2
    verts = np.empty((2 * N, 3), dtype=np.float32)
    verts[0::2] = lower
    verts[1::2] = upper

    faces = []
    # emit a quad only if BOTH endpoints are active (skips jumps across the
    # inactive arc for partial rings)
    for i in range(N - 1):
        if active[i] and active[i + 1]:
            b0, t0, b1, t1 = 2 * i, 2 * i + 1, 2 * (i + 1), 2 * (i + 1) + 1
            faces.append([b0, t0, t1])
            faces.append([b0, t1, b1])
    # closing edge for full ring
    if full_ring and active[N - 1] and active[0]:
        b0, t0, b1, t1 = 2 * (N - 1), 2 * (N - 1) + 1, 0, 1
        faces.append([b0, t0, t1])
        faces.append([b0, t1, b1])
    # closing edge for arc that wraps the seam (first-and-last both active
    # even though arc goes through the back)
    if (not full_ring) and active[N - 1] and active[0]:
        # only close if the inactive gap sits in the middle of the index
        # array (i.e., there are inactive points in between); otherwise
        # closing would duplicate an existing seam
        if (~active).any():
            b0, t0, b1, t1 = 2 * (N - 1), 2 * (N - 1) + 1, 0, 1
            faces.append([b0, t0, t1])
            faces.append([b0, t1, b1])

    if not faces:
        return o3d.geometry.TriangleMesh()

    faces = np.array(faces, dtype=np.int32)
    tri = o3d.geometry.TriangleMesh()
    tri.vertices = o3d.utility.Vector3dVector(verts.astype(np.float64))
    tri.triangles = o3d.utility.Vector3iVector(faces)
    tri.compute_vertex_normals()
    return tri


def _build_tie_mesh(body_vertices: np.ndarray, y_lo_world: float, y_hi_world: float,
                    u_side: float, band_offset: float = 0.6,
                    half_width_cm: float = 0.6
                    ) -> o3d.geometry.TriangleMesh:
    """Slim vertical ribbon at the side of the hip that bridges front and
    back waist-lines (the side-tie knot area of a tie-side bikini, or the
    structural side seam of any bottom that has both front and back
    panels). half_width_cm controls the visible band thickness."""
    theta = u_side * np.pi
    near = body_vertices[(body_vertices[:, 1] > y_lo_world - 1) &
                          (body_vertices[:, 1] < y_hi_world + 1)]
    if len(near) < 4:
        return o3d.geometry.TriangleMesh()
    nt = np.arctan2(near[:, 0], near[:, 2])
    d = np.abs(np.mod(nt - theta + np.pi, 2 * np.pi) - np.pi)
    idx = int(np.argmin(d))
    p = near[idx]
    rxz = np.array([p[0], 0, p[2]]); rxz /= max(np.linalg.norm(rxz), 1e-6)
    p_out = p + rxz * band_offset
    half_w = half_width_cm
    # vertices: four corners of a slim vertical rectangle facing outward
    tangent = np.array([-rxz[2], 0, rxz[0]]) * half_w
    v0 = p_out + tangent; v0[1] = y_lo_world
    v1 = p_out - tangent; v1[1] = y_lo_world
    v2 = p_out - tangent; v2[1] = y_hi_world
    v3 = p_out + tangent; v3[1] = y_hi_world
    verts = np.array([v0, v1, v2, v3], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    tri = o3d.geometry.TriangleMesh()
    tri.vertices = o3d.utility.Vector3dVector(verts)
    tri.triangles = o3d.utility.Vector3iVector(faces)
    tri.compute_vertex_normals()
    return tri


def _body_point_at(body_vertices: np.ndarray, u: float, y_level: float,
                    y_tol: float = 3.0, angle_tol: float = 0.12,
                    max_torso_radius: float = 22.0) -> np.ndarray:
    """Find a point on the torso surface at (u, y_level). Same idea as
    _body_ring but returns a single XYZ."""
    near = body_vertices[(body_vertices[:, 1] > y_level - y_tol) &
                          (body_vertices[:, 1] < y_level + y_tol)]
    if len(near) > 0:
        r = np.sqrt(near[:, 0] ** 2 + near[:, 2] ** 2)
        near = near[r < max_torso_radius]
    if len(near) < 3:
        near = body_vertices[(body_vertices[:, 1] > y_level - y_tol) &
                              (body_vertices[:, 1] < y_level + y_tol)]
    if len(near) == 0:
        # y_level fell outside the mesh entirely — clamp to nearest available
        # row so callers always get a valid anchor back.
        y_min, y_max = float(body_vertices[:, 1].min()), float(body_vertices[:, 1].max())
        y_clamped = float(np.clip(y_level, y_min + 0.5, y_max - 0.5))
        near = body_vertices[np.abs(body_vertices[:, 1] - y_clamped) < y_tol * 2]
        if len(near) == 0:
            # last-resort: return the single closest vertex by absolute y distance
            return body_vertices[int(np.argmin(np.abs(body_vertices[:, 1] - y_level)))].astype(np.float64)
    theta = np.arctan2(near[:, 0], near[:, 2])
    r_xz = np.sqrt(near[:, 0] ** 2 + near[:, 2] ** 2)
    target = u * np.pi
    d = np.abs(np.mod(theta - target + np.pi, 2 * np.pi) - np.pi)
    close = np.where(d < angle_tol)[0]
    if len(close) > 0:
        idx = close[np.argmin(r_xz[close])]
    else:
        idx = int(np.argmin(d))
    return near[idx].astype(np.float64)


def _tube_between(p0: np.ndarray, p1: np.ndarray, radius: float = 0.25,
                   sides: int = 6) -> o3d.geometry.TriangleMesh:
    """Build a narrow N-sided prism from p0 to p1."""
    p0 = np.asarray(p0, dtype=np.float64)
    p1 = np.asarray(p1, dtype=np.float64)
    axis = p1 - p0
    length = float(np.linalg.norm(axis))
    if length < 1e-4:
        return o3d.geometry.TriangleMesh()
    axis_u = axis / length
    # pick a reference vector not parallel to axis
    ref = np.array([0.0, 1.0, 0.0]) if abs(axis_u[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    n1 = np.cross(axis_u, ref); n1 /= np.linalg.norm(n1)
    n2 = np.cross(axis_u, n1)

    verts, faces = [], []
    for i in range(sides):
        a = 2 * np.pi * i / sides
        dir = np.cos(a) * n1 + np.sin(a) * n2
        verts.append(p0 + dir * radius)
        verts.append(p1 + dir * radius)
    for i in range(sides):
        a0, b0 = 2 * i, 2 * i + 1
        a1, b1 = 2 * ((i + 1) % sides), 2 * ((i + 1) % sides) + 1
        faces.append([a0, b0, b1])
        faces.append([a0, b1, a1])
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(np.array(verts))
    mesh.triangles = o3d.utility.Vector3iVector(np.array(faces, dtype=np.int32))
    mesh.compute_vertex_normals()
    return mesh


def _arc_tube(points: np.ndarray, radius: float = 0.25, sides: int = 6
              ) -> o3d.geometry.TriangleMesh:
    """A swept tube through a sequence of points (polyline)."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 2:
        return o3d.geometry.TriangleMesh()
    mesh = o3d.geometry.TriangleMesh()
    for i in range(len(pts) - 1):
        seg = _tube_between(pts[i], pts[i + 1], radius=radius, sides=sides)
        mesh += seg
    mesh.compute_vertex_normals()
    return mesh


def _build_torus(major_r: float, minor_r: float, major_seg: int = 24,
                  minor_seg: int = 10) -> o3d.geometry.TriangleMesh:
    try:
        return o3d.geometry.TriangleMesh.create_torus(
            torus_radius=major_r, tube_radius=minor_r,
            radial_resolution=major_seg, tubular_resolution=minor_seg,
        )
    except Exception:
        verts, faces = [], []
        for i in range(major_seg):
            a = 2 * np.pi * i / major_seg
            for j in range(minor_seg):
                b = 2 * np.pi * j / minor_seg
                x = (major_r + minor_r * np.cos(b)) * np.cos(a)
                y = minor_r * np.sin(b)
                z = (major_r + minor_r * np.cos(b)) * np.sin(a)
                verts.append([x, y, z])
        for i in range(major_seg):
            for j in range(minor_seg):
                ni = (i + 1) % major_seg
                nj = (j + 1) % minor_seg
                a = i * minor_seg + j
                b = ni * minor_seg + j
                c = ni * minor_seg + nj
                d = i * minor_seg + nj
                faces += [[a, b, c], [a, c, d]]
        m = o3d.geometry.TriangleMesh()
        m.vertices = o3d.utility.Vector3dVector(np.array(verts))
        m.triangles = o3d.utility.Vector3iVector(np.array(faces, dtype=np.int32))
        return m


def _place_at(mesh: o3d.geometry.TriangleMesh, center: np.ndarray,
               normal: np.ndarray) -> o3d.geometry.TriangleMesh:
    """Translate mesh so it sits at `center` with its Y axis aligned to
    `normal` (used for orienting torus / bow flat against the body)."""
    out = o3d.geometry.TriangleMesh(mesh)
    # rotate Y-axis to align with normal
    y = np.array([0.0, 1.0, 0.0])
    n = normal / max(np.linalg.norm(normal), 1e-6)
    axis = np.cross(y, n)
    s = np.linalg.norm(axis)
    if s > 1e-6:
        axis /= s
        angle = np.arccos(np.clip(np.dot(y, n), -1, 1))
        R = o3d.geometry.get_rotation_matrix_from_axis_angle(axis * angle)
        out.rotate(R, center=(0, 0, 0))
    out.translate(center)
    return out


def _build_oring_meshes(g, body_vertices, y_crotch, y_neck, v_to_y):
    """One torus per strap junction: at the center-gore, at each hip."""
    if g.has_oring < 0.5:
        return []
    size = 0.25 + 0.8 * g.oring_size  # cm major radius 0.25..1.05
    minor = 0.12 * size
    anchors = []
    # center front gore
    y = v_to_y(g.top_center_v)
    anchors.append(("front_gore", 0.0, y))
    # hips at the side ties
    y_front = v_to_y(g.bot_front_top_v)
    y_back = v_to_y(g.bot_back_top_v)
    hip_y = (y_front + y_back) / 2
    for u in (0.5, -0.5):
        anchors.append(("hip", u, hip_y))
    out = []
    for name, u, yy in anchors:
        p = _body_point_at(body_vertices, u, yy)
        rxz = np.array([p[0], 0.0, p[2]])
        rxz /= max(np.linalg.norm(rxz), 1e-6)
        # torus sits on surface, facing outward
        torus = _build_torus(size, minor)
        mesh = _place_at(torus, p + rxz * (minor + 0.3), rxz)
        mesh.compute_vertex_normals()
        out.append((f"oring_{name}_{u:.1f}", mesh))
    return out


def _build_bow_mesh(g, body_vertices, v_to_y):
    """A small bow at the center front. Two triangles + a center knot."""
    if g.has_bow < 0.5:
        return []
    size = 0.8 + 3.2 * g.bow_size   # wingspan 0.8..4.0 cm
    y = v_to_y(g.top_center_v)
    p = _body_point_at(body_vertices, 0.0, y)
    rxz = np.array([p[0], 0.0, p[2]]); rxz /= max(np.linalg.norm(rxz), 1e-6)
    tangent = np.array([-rxz[2], 0, rxz[0]])  # horizontal
    up = np.array([0.0, 1.0, 0.0])
    out = p + rxz * 0.4
    h = size * 0.45

    def wing(dir_sign: int):
        outer = out + tangent * dir_sign * size
        verts = np.array([
            out, outer + up * h, outer - up * h,
            out + tangent * dir_sign * size * 0.3 + up * h * 0.15,
        ])
        faces = np.array([[0, 1, 2], [0, 1, 3], [0, 3, 2]], dtype=np.int32)
        m = o3d.geometry.TriangleMesh()
        m.vertices = o3d.utility.Vector3dVector(verts)
        m.triangles = o3d.utility.Vector3iVector(faces)
        m.compute_vertex_normals()
        return m

    knot = o3d.geometry.TriangleMesh.create_sphere(size * 0.22)
    knot.translate(out)
    knot.compute_vertex_normals()
    return [("bow_R", wing(+1)), ("bow_L", wing(-1)), ("bow_knot", knot)]


def _build_fringe_meshes(g, body_vertices, v_to_y):
    """Hanging short tassels along the bottom panel's leg opening.

    Anchor band runs along the LEG OPENING (lower edge of the front
    bottom piece), not the waistline — fringe hangs from the hem like a
    skirt fringe. Length capped to 6 cm so the strands stay above the
    knees regardless of g.fringe_length."""
    if g.has_fringe < 0.5:
        return []
    length = max(2.0, min(6.0, 1.0 + 4.0 * g.fringe_length))
    y_front = v_to_y(g.bot_front_top_v)
    y_back = v_to_y(g.bot_back_top_v)
    # Hem of the front panel — leg opening sits a few cm below the
    # panel's top edge. We approximate by going halfway between front_top
    # and the crotch-y reference.
    band_y = min(y_front, y_back) - 4.0
    us = np.linspace(-0.30, 0.30, 9)
    out = o3d.geometry.TriangleMesh()
    for u in us:
        anchor = _body_point_at(body_vertices, float(u), band_y)
        rxz = np.array([anchor[0], 0.0, anchor[2]])
        rxz /= max(np.linalg.norm(rxz), 1e-6)
        p0 = anchor + rxz * 0.3
        p1 = p0 - np.array([0.0, length, 0.0])
        seg = _tube_between(p0, p1, radius=0.10, sides=5)
        out += seg
    out.compute_vertex_normals()
    return [("fringes", out)]


def _build_beads_meshes(g, body_vertices, v_to_y):
    """Small beads along the top band."""
    if g.has_beads < 0.5:
        return []
    y = v_to_y(g.top_center_v)
    cup_outer_u = g.top_inner_u + 2 * g.top_half_u
    us = np.linspace(cup_outer_u + 0.02, 1.0, 6)
    us = np.concatenate([us, -us])
    out = o3d.geometry.TriangleMesh()
    for u in us:
        p = _body_point_at(body_vertices, float(u), y)
        rxz = np.array([p[0], 0.0, p[2]])
        rxz /= max(np.linalg.norm(rxz), 1e-6)
        bead = o3d.geometry.TriangleMesh.create_sphere(0.28)
        bead.translate(p + rxz * 0.35)
        out += bead
    out.compute_vertex_normals()
    return [("beads", out)]


def _build_shell_mesh(g, body_vertices, v_to_y):
    """A shell-like charm hanging from the center gore."""
    if g.has_shell < 0.5:
        return []
    y = v_to_y(g.top_center_v) - 2.5
    p = _body_point_at(body_vertices, 0.0, y)
    rxz = np.array([p[0], 0.0, p[2]])
    rxz /= max(np.linalg.norm(rxz), 1e-6)
    # a flattened sphere cap as a quick shell approximation
    shell = o3d.geometry.TriangleMesh.create_sphere(0.85)
    shell.scale(1.0, center=(0, 0, 0))
    verts = np.asarray(shell.vertices)
    verts[:, 2] *= 0.3          # flatten along world-z ~ anchor normal
    shell.vertices = o3d.utility.Vector3dVector(verts)
    shell = _place_at(shell, p + rxz * 0.8, rxz)
    shell.compute_vertex_normals()
    return [("shell", shell)]


def _build_strap_meshes_legacy(body_mesh: o3d.geometry.TriangleMesh, g,
                       y_crotch: float, y_neck: float
                       ) -> list[tuple[str, o3d.geometry.TriangleMesh]]:
    """Build 3D strap/band meshes for a Genome. Returns list of (name, mesh).

    Uses the same (y_crotch, y_neck) anchors as the cylindrical UV so strap
    positions match the textured-panel positions.
    """
    V = np.asarray(body_mesh.vertices)
    straps = []

    def v_to_y(v: float) -> float:
        return y_crotch + v * (y_neck - y_crotch)

    # 1) Top back band — horizontal ring at bust level, reaching from the
    #    right cup's outer edge, around the back, to the left cup's outer
    #    edge (the arc that does NOT pass through the front). Tighter
    #    torso-radius filter (20cm) so the arm-root at x~21 is excluded.
    cup_outer_u = g.top_inner_u + 2 * g.top_half_u
    band_y = v_to_y(g.top_center_v)
    band_h = max(1.2, 1.5 + 2.0 * g.top_back_coverage)   # thin: 1.5-3.5 cm
    ring = _body_ring(V, band_y, y_halfband=3.0, n_samples=96,
                      max_torso_radius=20.0)
    back_band = _build_band_mesh(ring, band_h, offset=0.5,
                                  u_from=cup_outer_u, u_to=-cup_outer_u)
    straps.append(("top_back_band", back_band))

    # 1b) Underbust band — the support elastic running the FULL ring at
    #     the bottom of the cup. This is what mechanically holds a
    #     real bra/bikini top up; without it the garment looks like
    #     adhesive tape on the chest. Generic: any genome with cup_v
    #     above a basic bust line gets one. Continuous around the body.
    underbust_v = max(0.05, g.top_center_v - g.top_half_v - 0.02)
    underbust_y = v_to_y(underbust_v)
    underbust_ring = _body_ring(V, underbust_y, y_halfband=2.5, n_samples=96,
                                  max_torso_radius=20.0)
    underbust_band = _build_band_mesh(underbust_ring,
                                        band_thickness=1.2,
                                        offset=0.55)
    straps.append(("underbust_band", underbust_band))

    # 1c) Crotch gusset — a tube tracing the inseam from front pubic
    #     anchor over the perineum to the back-buttock anchor. Real
    #     swimwear has this as a separate fabric piece that bridges the
    #     front and back bottoms. The path goes UP into the body's
    #     crotch concavity, not straight through space — we sample the
    #     body surface at a small array of u values along the path so
    #     the tube hugs the body. Width scales with bot_front/back_half_u
    #     so thongs get a thin string and one-pieces get a visible strip.
    gusset_radius = max(0.32,
                          min(g.bot_front_half_u, g.bot_back_half_u) * 4.0)
    # Sample the body along an arc from front (u=0) to back (u=1) at the
    # crotch line, lifted slightly above y_crotch where the legs actually
    # meet the pelvis. Using only torso vertices via _body_point_at's
    # built-in radius filter keeps the path off the legs.
    inseam_y = y_crotch + 1.0
    n_pts = 7
    inseam_path = []
    for k in range(n_pts):
        t = k / (n_pts - 1)
        u = t * 1.0      # front=0, back=1
        # Y rises slightly toward the back so the path mounts the buttock
        y_k = inseam_y + 0.8 * t
        try:
            p = _body_point_at(V, u, y_k, max_torso_radius=18.0)
            inseam_path.append(p)
        except Exception:
            pass
    if len(inseam_path) >= 2:
        gusset = _arc_tube(np.array(inseam_path), radius=gusset_radius)
        # Suppress for any Genome where the bottom panels are too small
        # to need a gusset — thongs / Brazilian / cheeky cuts. With
        # bot_back_half_u < 0.13 the back panel is barely there and the
        # gusset reads as off-body debris. Threshold based on visible
        # back coverage only (not is_one_piece) so a high-cut maillot
        # still gets a gusset, but a string bikini doesn't.
        if g.bot_back_half_u >= 0.13:
            straps.append(("gusset", gusset))

    # 2) Bottom waist string — thin ring at the average of front/back tops.
    #    Asymmetric waists (high-front + thong-back) rely on the side ties
    #    to bridge the height difference; keep the band itself uniformly
    #    thin so it reads as a string, not a wide belt.
    #
    #    SUPPRESSION RULE: a one-piece (top_back_coverage > 0.7 AND
    #    bot_front_top_v overlaps the bust panel) doesn't need a waist
    #    tie because the front and back are already continuous fabric.
    #    Drawing a waist tie on a one-piece reads as fabric debris.
    y_front = v_to_y(g.bot_front_top_v)
    y_back  = v_to_y(g.bot_back_top_v)
    is_one_piece = (g.top_back_coverage > 0.7
                    and g.bot_front_top_v > g.top_center_v - g.top_half_v - 0.15)
    if not is_one_piece:
        band_y2 = (y_front + y_back) / 2
        band_h2 = 1.5
        ring2 = _body_ring(V, band_y2, y_halfband=3.0, n_samples=96)
        waist_band = _build_band_mesh(ring2, band_h2, offset=0.5)
        straps.append(("waist_band", waist_band))

    # 3) Side ties — slim vertical ribbon on each hip spanning the v-range
    #    between front and back waist-lines (visible bridge for tie-side
    #    bikinis). One-pieces don't have side ties either.
    if not is_one_piece:
        y_side_lo = min(y_front, y_back) - 0.8
        y_side_hi = max(y_front, y_back) + 0.8
        for u_side, name in [(0.5, "side_tie_R"), (-0.5, "side_tie_L")]:
            tie = _build_tie_mesh(V, y_side_lo, y_side_hi, u_side)
            straps.append((name, tie))

    # 4) Tie dangles — hanging "tail" tubes off the side ties. Length
    #    scales with g.bot_tie_dangle. Drawn as a thin tube going straight
    #    down from the hip.
    if g.bot_tie_dangle > 0.15:
        dangle_len = 2.0 + 14.0 * g.bot_tie_dangle   # cm, up to ~16cm
        for u_side, name in [(0.5, "dangle_R"), (-0.5, "dangle_L")]:
            anchor = _body_point_at(V, u_side, (y_side_lo + y_side_hi) / 2)
            rxz = np.array([anchor[0], 0.0, anchor[2]])
            rxz /= max(np.linalg.norm(rxz), 1e-6)
            p0 = anchor + rxz * 0.6
            p1 = p0 - np.array([0.0, dangle_len, 0.0])
            dangle = _tube_between(p0, p1, radius=0.15, sides=5)
            straps.append((name, dangle))

    # 5) Halter neck strap — two short tubes rising from the cup inner-top
    #    and converging at the sternal notch / base of the neck in FRONT
    #    of the body. The "wrap behind the neck" part is implied — we
    #    don't render past the neck base because any arc over the top
    #    would have to cross the head/chin from a front camera view
    #    (straight-line tube between front-chest and behind-neck passes
    #    through the jaw around y = neck_top - 3).
    if g.top_neck_strap > 0.15:
        strap_r = 0.15 + 0.25 * g.top_neck_strap     # ~1.5 to 4 mm radius
        cup_top_v = g.top_center_v + g.top_half_v
        u_inner_halter = 0.03 + 0.05 * g.top_inner_u
        y_start = v_to_y(cup_top_v)
        anchor_R = _body_point_at(V, u_inner_halter, y_start)
        anchor_L = _body_point_at(V, -u_inner_halter, y_start)
        # Meeting point: at the base of the neck, slightly in front so
        # the tube stays above the body surface and never crosses the
        # chin / jaw. y_neck is our "v=1 anchor" (upper chest height);
        # the actual neck base sits just below it.
        meeting = _body_point_at(V, 0.0, y_neck - 4.0) \
                  + np.array([0.0, 0.0, 0.4])
        # Optional mid-control point to bend the tube gracefully toward
        # the sternal notch instead of a straight line from cup to neck.
        mid_R = 0.5 * (anchor_R + meeting) + np.array([0.0, 1.0, 0.5])
        mid_L = 0.5 * (anchor_L + meeting) + np.array([0.0, 1.0, 0.5])
        halter_R = _arc_tube(np.array([anchor_R, mid_R, meeting]),
                              radius=strap_r)
        halter_L = _arc_tube(np.array([anchor_L, mid_L, meeting]),
                              radius=strap_r)
        straps.append(("halter_R", halter_R))
        straps.append(("halter_L", halter_L))

    # Hardware / trim (Batch 2) — torus O-rings, bow, fringes, beads, shell.
    straps.extend(_build_oring_meshes(g, V, y_crotch, y_neck, v_to_y))
    straps.extend(_build_bow_mesh(g, V, v_to_y))
    straps.extend(_build_fringe_meshes(g, V, v_to_y))
    straps.extend(_build_beads_meshes(g, V, v_to_y))
    straps.extend(_build_shell_mesh(g, V, v_to_y))

    # 5b) Bar-tack reinforcements — small dense knot of stitching where a
    #     shoulder/halter strap meets a cup edge. Real swimwear has this
    #     so the strap doesn't tear out under load. We approximate as a
    #     tiny ellipsoid (radius ~3 mm) at each cup-top anchor point.
    if g.top_shoulder_strap > 0.15 or g.top_neck_strap > 0.15:
        cup_top_v = g.top_center_v + g.top_half_v
        u_outer = g.top_inner_u + 2 * g.top_half_u
        u_inner = 0.03 + 0.05 * g.top_inner_u
        for tag, u in (("OR", u_outer), ("OL", -u_outer),
                          ("IR", u_inner), ("IL", -u_inner)):
            try:
                anc = _body_point_at(V, u, v_to_y(cup_top_v),
                                       max_torso_radius=18.0)
                tack = o3d.geometry.TriangleMesh.create_sphere(
                    radius=0.30, resolution=8)
                tack.translate(anc.tolist())
                tack.compute_vertex_normals()
                straps.append((f"bartack_{tag}", tack))
            except Exception:
                pass

    # 6) Shoulder straps — anatomically routed from cup top (front) over
    #    the actual ACROMION (shoulder peak detected from the mesh) to
    #    the SCAPULA (back of shoulder). Anchors come from anatomy.detect
    #    so the strap respects real human shoulder topology instead of
    #    relying on a constant "+4 cm up" guess that pushed straps into
    #    the chin / ear region. Generic across body meshes.
    if g.top_shoulder_strap > 0.15:
        try:
            from anatomy import (detect as _detect_anatomy,
                                  front_clavicle_point as _front_clav,
                                  back_scapula_point as _back_scap)
            _L = _detect_anatomy(body_mesh)
        except Exception:
            _L = None

        strap_r = 0.15 + 0.22 * g.top_shoulder_strap
        cup_top_v = g.top_center_v + g.top_half_v
        u_outer = g.top_inner_u + 2 * g.top_half_u
        y_front = v_to_y(cup_top_v)
        for u_s, side, name in [(u_outer, "R", "shoulder_R"),
                                   (-u_outer, "L", "shoulder_L")]:
            P0 = _body_point_at(V, u_s, y_front)            # front cup top
            if _L is not None:
                # Clamp the cup-top start point's Y so it doesn't push
                # above acromion. If the cup polygon extended into the
                # neck region (one-piece) the front anchor still
                # belongs at chest height where a real shoulder strap
                # is sewn to the cup.
                P0 = P0.copy()
                if P0[1] > _L.y_acromion - 2.0:
                    P0[1] = _L.y_acromion - 2.0
                P_clav = _front_clav(body_mesh, _L, side)
                # Shoulder ridge apex = directly above acromion at the
                # acromion lateral position, pulled IN toward neck so
                # the strap can't fly out onto the deltoid.
                P_ridge = np.array([
                    P_clav[0] * 0.65,           # 35% inward toward neck
                    min(_L.y_acromion + 1.5,
                         _L.y_neck_base - 1.0),  # never breach neck base
                    P_clav[2] * 0.4,            # nudged forward
                ], dtype=np.float64)
                P_scap = _back_scap(body_mesh, _L, side)
                # Back endpoint: inboard of scapula, at chest band level
                P_back_anchor = np.array([
                    P_scap[0] * 0.7,
                    v_to_y(g.top_center_v),
                    P_scap[2] * 0.7,
                ], dtype=np.float64)
                strap = _arc_tube(
                    np.array([P0, P_clav, P_ridge, P_scap, P_back_anchor]),
                    radius=strap_r)
            else:
                # Fallback: original constant-offset behavior
                ridge = P0 + np.array([-0.25 * P0[0], 4.0, 0.4])
                u_back = (u_s + 1.0) if u_s < 0 else (u_s - 1.0)
                P2 = _body_point_at(V, u_back, v_to_y(g.top_center_v))
                if P2[2] > 0:
                    P2 = P2 * np.array([1.0, 1.0, -1.0])
                mid_back = ridge + np.array([0.0, -1.0, -3.0])
                strap = _arc_tube(np.array([P0, ridge, mid_back, P2]),
                                    radius=strap_r)
            straps.append((name, strap))

    return straps


def build_fabric_shell(body_mesh: o3d.geometry.TriangleMesh, body_uvs: np.ndarray,
                       polys_uv: list[list[tuple[float, float]]],
                       offset: float = 0.3,
                       max_torso_radius: float = 20.0,
                       body_deployment=None,
                       ) -> o3d.geometry.TriangleMesh:
    """Build a thin fabric shell from the body's triangles that fall inside
    any Genome UV polygon. Each such triangle gets offset outward along its
    vertex normals by `offset` (cm). Carries the body's triangle-UV layout
    so it can reuse the bikini texture.

    Triangles on the T-pose arms are excluded by a torso-radius filter —
    arm and torso side vertices share the same cylindrical u so without
    this filter a wide bandeau's shell extends onto the forearms.

    `body_deployment`: optional BodyDeployment from garment_state.
    When provided, every triangle's centroid is classified by
    deployment.classify_xyz and rejected if its region is in the
    intersection of must_clear across all PatternPieces. This is the
    cascade-aware filter that pulls the latent state's BodyMapping
    into the renderer — replaces the legacy hard-coded Y filters.
    """
    from matplotlib.path import Path

    V = np.asarray(body_mesh.vertices)
    T = np.asarray(body_mesh.triangles)
    if not body_mesh.has_vertex_normals():
        body_mesh.compute_vertex_normals()
    N = np.asarray(body_mesh.vertex_normals)

    # Convert body UVs from the texture-space [0,1] back to Genome [-1,1]
    # for point-in-polygon tests.
    pts_g = body_uvs.copy()
    pts_g[:, 0] = pts_g[:, 0] * 2.0 - 1.0

    # Mandatory anatomy filter — runs BEFORE the polygon test so no
    # polygon (no matter how wide it is in UV) can ever collect a
    # triangle whose vertices live in arms, legs, head, or neck.
    # This replaces the earlier SHELL_UV_MARGIN / CUP_V_THRESHOLD
    # heuristics (those were band-aids on the polygon side; this is
    # the structural fix on the candidate-set side).  Identical bug
    # pattern manifested as the armpit-to-side-chest bridge AND the
    # inner-knee bridge -- both vanish here.
    from anatomy import detect as _detect_anatomy_for_classifier
    from body_region_classifier import (classify_vertices,
                                          classify_triangles_strict)
    _LM_for_filter = _detect_anatomy_for_classifier(body_mesh)
    _vert_regions = classify_vertices(V, _LM_for_filter)
    _torso_tri_mask = classify_triangles_strict(_vert_regions, T)

    # A triangle is "fabric" if ALL THREE of its per-vertex UVs are inside
    # at least one polygon. We union the results across polygons.
    inside_any = np.zeros(len(pts_g), dtype=bool)
    for poly in polys_uv:
        if len(poly) < 3:
            continue
        p = np.asarray(poly, dtype=np.float32)
        path = Path(p)
        inside_any |= path.contains_points(pts_g)

    tri_inside = inside_any.reshape(-1, 3).all(axis=1)
    # Enforce the anatomy classifier as a hard intersection -- triangles
    # outside the torso region are unconditionally rejected.
    tri_inside &= _torso_tri_mask

    # Also require the triangle's centroid to be on the torso, not on an
    # arm. On this T-pose mesh torso stays under r_xz ~18 cm; arms run out
    # to ~45 cm at identical Y and cylindrical u, so without this filter a
    # bandeau's shell would paint onto the forearms.
    tri_xz = V[T][:, :, [0, 2]].mean(axis=1)
    tri_r = np.sqrt(tri_xz[:, 0] ** 2 + tri_xz[:, 1] ** 2)
    tri_y = V[T][:, :, 1].mean(axis=1)

    # Anatomy-aware filtering: when a BodyDeployment is supplied, the
    # filter comes from the latent state (intersection of must_clear
    # across all pieces). Otherwise fall back to a coarse Y/radius cap
    # via anatomy.detect — kept for backward compatibility with callers
    # that don't yet pass the deployment.
    try:
        from anatomy import detect as _detect_anatomy
        _L = _detect_anatomy(body_mesh)
        tri_inside &= tri_y < (_L.y_neck_base + 1.0)

        # ---- BodyDeployment-driven must_clear rejection ----
        # NOTE 2026-05-23: previously applied globally as
        #   forbidden = INTERSECTION of must_clear across pieces
        # and any triangle in that region was rejected. That double-gated
        # with body_region_classifier (which is already applied as a hard
        # mask above) AND used a stricter "pelvis vs legs" definition
        # from garment_state.deploy_to_body — which classified the
        # bikini-bottom fabric-bearing zone as 'legs', killing every
        # bottom panel. Disabled. body_region_classifier (torso + new
        # pelvis region, 2026-05-23) is the single source of truth for
        # which body triangles are fabric-safe.
        if body_deployment is not None and body_deployment.classify_xyz is not None:
            pass
        # Per-Y radius cap. Below axilla: torso ~16-17 cm wide.
        # Between axilla and acromion: that's the upper chest / shoulder
        # cap region — radius ~ deltoid (19.9). Between acromion and neck:
        # narrows toward the neck — use deltoid as upper bound but the
        # body's own radius will be smaller anyway.
        cap = np.where(tri_y < _L.y_axilla,
                        max(_L.waist_radius_xz, _L.axilla_radius_xz) + 0.5,
                        _L.deltoid_radius_xz + 0.4)
        tri_inside &= tri_r < cap
    except Exception:
        # Fallback to constant max_torso_radius
        tri_inside &= tri_r < max_torso_radius

    if not tri_inside.any():
        return o3d.geometry.TriangleMesh()

    sel_tris = T[tri_inside]
    used_verts = np.unique(sel_tris)
    remap = np.full(V.shape[0], -1, dtype=np.int64)
    remap[used_verts] = np.arange(used_verts.shape[0])
    new_tris = remap[sel_tris]

    new_verts = V[used_verts] + N[used_verts] * offset

    shell = o3d.geometry.TriangleMesh()
    shell.vertices = o3d.utility.Vector3dVector(new_verts.astype(np.float64))
    shell.triangles = o3d.utility.Vector3iVector(new_tris.astype(np.int32))

    # UE-exported OBJs duplicate vertices at UV / material seams, so after
    # remapping every triangle is an isolated island (no shared edges).
    # Merge near-coincident vertices so interior edges actually get shared,
    # otherwise the boundary-edge detection used by build_binding_mesh
    # would pick up every triangle-edge and render as pebbled fins.
    shell.merge_close_vertices(eps=1e-3)
    shell.compute_vertex_normals()

    # Per-triangle UVs for the kept triangles, in body-texture coords.
    sel_flat = np.where(tri_inside.repeat(3))[0]
    shell_uvs = body_uvs[sel_flat]
    shell.triangle_uvs = o3d.utility.Vector2dVector(shell_uvs)
    return shell


def _pseudo_noise_3d(pts: np.ndarray, octaves: int = 2, seed: int = 0
                     ) -> np.ndarray:
    """Cheap trig-based pseudo-noise for wrinkle displacement — no need
    for a Perlin library. Returns values in approximately [-1, 1]."""
    rng = np.random.default_rng(seed)
    total = np.zeros(len(pts), dtype=np.float64)
    norm = 0.0
    for i in range(octaves):
        # ~0.20, 0.40 rad/cm -> wavelengths ~31cm and ~16cm (few wrinkles)
        freq = 0.20 * (2.0 ** i)
        amp = 1.0 / (2 ** i)
        phase = rng.uniform(0, 2 * np.pi, 3)
        total += amp * (np.sin(pts[:, 0] * freq + phase[0])
                        * np.cos(pts[:, 1] * freq * 1.1 + phase[1])
                        * np.sin(pts[:, 2] * freq * 0.9 + phase[2]))
        norm += amp
    return total / norm


def apply_wrinkles(shell: o3d.geometry.TriangleMesh, amplitude: float = 0.06
                   ) -> None:
    """Displace shell vertices along their normals by low-frequency noise
    so the fabric has subtle drape/wrinkles. Amplitude in cm (~0.6 mm)."""
    if len(shell.vertices) == 0:
        return
    if not shell.has_vertex_normals():
        shell.compute_vertex_normals()
    V = np.asarray(shell.vertices)
    N = np.asarray(shell.vertex_normals)
    noise = _pseudo_noise_3d(V)
    V_new = V + N * noise[:, None] * amplitude
    shell.vertices = o3d.utility.Vector3dVector(V_new)
    shell.compute_vertex_normals()


def build_binding_mesh(shell: o3d.geometry.TriangleMesh,
                        offset: float = 0.08, thickness: float = 0.25,
                        width_along_normal: bool = True
                        ) -> o3d.geometry.TriangleMesh:
    """Small raised rim along the shell's boundary edges — reads as the
    binding/piping stitched onto the edge of a real bikini. Each boundary
    edge becomes a thin vertical ribbon rising by `thickness` cm above the
    shell surface.
    """
    from collections import Counter

    if len(shell.vertices) == 0:
        return o3d.geometry.TriangleMesh()
    if not shell.has_vertex_normals():
        shell.compute_vertex_normals()

    V = np.asarray(shell.vertices)
    N = np.asarray(shell.vertex_normals)
    T = np.asarray(shell.triangles)

    # Boundary edges: appear in exactly one triangle
    all_edges = np.concatenate([
        T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]],
    ], axis=0)
    sorted_edges = np.sort(all_edges, axis=1)
    counter = Counter(map(tuple, sorted_edges))
    boundary = [e for e, c in counter.items() if c == 1]
    if not boundary:
        return o3d.geometry.TriangleMesh()

    verts = []
    faces = []
    for (i0, i1) in boundary:
        p0 = V[i0] + N[i0] * offset
        p1 = V[i1] + N[i1] * offset
        u0 = V[i0] + N[i0] * (offset + thickness)
        u1 = V[i1] + N[i1] * (offset + thickness)
        base = len(verts)
        verts.extend([p0, p1, u1, u0])
        # two triangles per quad, both winding orders to avoid backface cull
        faces.append([base, base + 1, base + 2])
        faces.append([base, base + 2, base + 3])
        faces.append([base, base + 2, base + 1])
        faces.append([base, base + 3, base + 2])

    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(np.asarray(verts))
    mesh.triangles = o3d.utility.Vector3iVector(np.asarray(faces, dtype=np.int32))
    mesh.compute_vertex_normals()
    return mesh


# --------------------------------------------------------------------------

def _color_from_genome(g) -> tuple[float, float, float, float]:
    from verify_ga_uv import _color as vc
    r, gg, b = vc(g)
    return (r, gg, b, 1.0)


def _skin_only_texture() -> Image.Image:
    """Uniform skin-tone texture for the body layer, with no bikini polygons
    painted on. The bikini is drawn as a separate 3D shell on top."""
    return Image.new("RGB", (TEX_W, TEX_H), SKIN_RGB)


def _fabric_normal_map(w: int = TEX_W, h: int = TEX_H,
                       u_threads: int = WEAVE_U_THREADS,
                       v_threads: int = WEAVE_V_THREADS) -> np.ndarray:
    """Plain-weave tangent-space normal map.

    Simulates threads going over/under on a checkerboard pattern: in each
    cell, either the horizontal thread crosses over the vertical (so the
    bump is horizontal) or vice versa. The normal is derived from a small
    height map via numpy gradients. Returns uint8 HxWx3 in XYZ -> RGB
    tangent-space convention (x right, y up, z out).
    """
    us = np.linspace(0, 2 * np.pi * u_threads, w, endpoint=False)
    vs = np.linspace(0, 2 * np.pi * v_threads, h, endpoint=False)
    U, V = np.meshgrid(us, vs)

    # Which cell we're in (checkerboard of warp vs. weft)
    cell_u = (us / np.pi).astype(int)
    cell_v = (vs / np.pi).astype(int)
    CU, CV = np.meshgrid(cell_u, cell_v)
    over_weft = ((CU + CV) % 2) == 0          # True => horizontal thread on top

    # Height map: smooth bump along the "on-top" thread's length
    h_horiz = 0.5 + 0.5 * np.cos(V)           # ridges run along U (horizontal)
    h_vert  = 0.5 + 0.5 * np.cos(U)           # ridges run along V (vertical)
    height = np.where(over_weft, h_horiz, h_vert) * 0.9
    # small overall dip between the two threads to read as a weave gap
    height += 0.1 * (np.sin(U * 0.5) * np.sin(V * 0.5))

    # Gradients -> normal (x=u axis, y=v axis, z out)
    dv, du = np.gradient(height)               # np.gradient on (H, W) -> (dy, dx)
    strength = 3.0                              # scales bump intensity
    nx = -du * strength
    ny = -dv * strength
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= length
    ny /= length
    nz /= length

    # Tangent-space encoding: store (x, y, z) -> [0, 1] -> [0, 255]
    normal = np.stack([
        (nx * 0.5 + 0.5),
        (ny * 0.5 + 0.5),
        (nz * 0.5 + 0.5),
    ], axis=-1)
    return (normal * 255).clip(0, 255).astype(np.uint8)


def _weave_shade_overlay(w: int = TEX_W, h: int = TEX_H,
                         u_threads: int = WEAVE_U_THREADS,
                         v_threads: int = WEAVE_V_THREADS) -> np.ndarray:
    """Grayscale multiplicative overlay baked into the albedo so the weave
    reads even if the renderer ignores the normal map.

    Darkens cells where one thread dips, brightens cells where it rises.
    Values in [0.80, 1.10] so the base color stays dominant.
    """
    us = np.linspace(0, 2 * np.pi * u_threads, w, endpoint=False)
    vs = np.linspace(0, 2 * np.pi * v_threads, h, endpoint=False)
    U, V = np.meshgrid(us, vs)
    cell_u = (us / np.pi).astype(int)
    cell_v = (vs / np.pi).astype(int)
    CU, CV = np.meshgrid(cell_u, cell_v)
    over_weft = ((CU + CV) % 2) == 0
    h_horiz = 0.5 + 0.5 * np.cos(V)
    h_vert  = 0.5 + 0.5 * np.cos(U)
    height = np.where(over_weft, h_horiz, h_vert)
    # Subtle shade multiplier in [0.90, 1.05] — readable as fabric weave
    # without dominating the base pattern (stripe/polka/checker).
    return (0.90 + 0.15 * height).astype(np.float32)


def _crinkle_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Hunza G signature crinkle — densely crumpled fabric. Builds a height
    map from 5-octave pseudo-noise and converts to a tangent-space normal.
    """
    rng = np.random.default_rng(7)
    yy, xx = np.indices((h, w)).astype(np.float32)
    height = np.zeros_like(xx)
    norm = 0.0
    for i in range(5):
        fx = 0.06 * (2.0 ** i)
        fy = 0.04 * (2.0 ** i)
        phx, phy = rng.uniform(0, 2 * np.pi, 2)
        amp = 1.0 / (1.7 ** i)
        height += amp * np.sin(xx * fx + phx) * np.cos(yy * fy + phy)
        norm += amp
    height /= norm
    dv, du = np.gradient(height)
    s = 8.0
    nx = -du * s; ny = -dv * s; nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= length; ny /= length; nz /= length
    normal = np.stack([(nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)], axis=-1)
    return (normal * 255).clip(0, 255).astype(np.uint8)


def _ribbed_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Strong vertical ribs (rib-knit look)."""
    xs = np.linspace(0, 2 * np.pi * 80, w)
    height = 0.5 + 0.5 * np.cos(xs)[None, :] * np.ones((h, 1))
    du, dv = np.gradient(height, axis=1), np.gradient(height, axis=0)
    s = 6.0
    nx = -du * s; ny = -dv * s; nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= length; ny /= length; nz /= length
    normal = np.stack([(nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)], axis=-1)
    return (normal * 255).clip(0, 255).astype(np.uint8)


def _mesh_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Open grid, like sports mesh / fishnet (coarser lattice, sharper)."""
    xs = np.linspace(0, 2 * np.pi * 90, w)
    ys = np.linspace(0, 2 * np.pi * 45, h)
    U, V = np.meshgrid(xs, ys)
    height = (np.cos(U) + np.cos(V)) * 0.5
    dv, du = np.gradient(height)
    s = 7.0
    nx = -du * s; ny = -dv * s; nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= length; ny /= length; nz /= length
    normal = np.stack([(nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)], axis=-1)
    return (normal * 255).clip(0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Extended fabric weaves.  Each returns an HxWx3 uint8 tangent-space
# normal map in the same convention as the originals (x=u, y=v, z=out).
# ---------------------------------------------------------------------------

def _height_to_normal(height: np.ndarray, strength: float) -> np.ndarray:
    dv, du = np.gradient(height)
    nx = -du * strength
    ny = -dv * strength
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx /= length; ny /= length; nz /= length
    normal = np.stack([(nx * 0.5 + 0.5), (ny * 0.5 + 0.5), (nz * 0.5 + 0.5)], axis=-1)
    return (normal * 255).clip(0, 255).astype(np.uint8)


def _velvet_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Velvet pile — micro-random bumps biased along V (pile direction).
    Soft, dense, mostly subtle."""
    rng = np.random.default_rng(11)
    height = 0.0
    yy, xx = np.indices((h, w)).astype(np.float32)
    for i in range(3):
        fx = 0.45 * (2.0 ** i)
        fy = 0.85 * (2.0 ** i)        # finer along v (pile)
        amp = 1.0 / (2.0 ** i)
        phx, phy = rng.uniform(0, 2 * np.pi, 2)
        height = height + amp * np.sin(xx * fx + phx) * np.sin(yy * fy + phy)
    height = height * 0.6              # stronger pile read
    return _height_to_normal(height, strength=4.0)


def _crochet_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Regular hexagonal-ish open lattice — deep dark holes between
    bright thread bundles.  Reads as crochet/macrame."""
    cell = 28
    yy, xx = np.indices((h, w)).astype(np.float32)
    # offset rows for a brick-like layout (close to hex)
    row = (yy // cell).astype(int)
    cx = (xx + (row % 2) * (cell / 2)) % cell - cell / 2
    cy = (yy % cell) - cell / 2
    r2 = (cx * cx) / ((cell / 2) ** 2) + (cy * cy) / ((cell / 2) ** 2)
    # height: ring-shaped thread bundle around each cell, deep dip in centre
    rim = np.exp(-((r2 - 0.55) ** 2) * 18.0)
    hole = -np.exp(-r2 * 4.0) * 1.4
    height = rim + hole
    return _height_to_normal(height, strength=6.0)


def _shiny_knit_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Fine horizontal rib bands, narrower than 'ribbed', for shiny knit
    (Missoni-ish space-dye)."""
    ys = np.linspace(0, 2 * np.pi * 220, h)
    height = (0.5 + 0.5 * np.cos(ys))[:, None] * np.ones((1, w))
    return _height_to_normal(height, strength=4.0)


def _foam_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """EVA foam — nearly featureless flat surface (foam cup)."""
    rng = np.random.default_rng(3)
    height = rng.normal(scale=0.04, size=(h, w))   # imperceptible micro-roughness
    return _height_to_normal(height, strength=0.6)


def _sequined_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Tile pattern of small raised discs."""
    tile = 16
    yy, xx = np.indices((h, w)).astype(np.float32)
    cx = (xx % tile) - tile / 2
    cy = (yy % tile) - tile / 2
    r2 = cx * cx + cy * cy
    disc = np.exp(-r2 / (tile * 0.6))           # raised plateau
    edge = np.exp(-((np.sqrt(r2) - tile * 0.35) ** 2) / 4.0) * 0.7
    height = disc + edge
    return _height_to_normal(height, strength=5.0)


def _seersucker_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Puckered alternating stripes — sand-grain rough between flat
    stripes, looks like seersucker or sand-washed fabric."""
    stripe = 26
    xs = (np.arange(w) // stripe) % 2
    puckered_cols = xs.astype(np.float32)[None, :].repeat(h, axis=0)
    rng = np.random.default_rng(17)
    pucker = rng.normal(scale=1.0, size=(h, w)) * puckered_cols * 0.35
    flat   = (1.0 - puckered_cols) * 0.0
    height = pucker + flat
    return _height_to_normal(height, strength=4.0)


def _lace_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Dense organic lacework — overlapping floral motifs with holes."""
    rng = np.random.default_rng(23)
    yy, xx = np.indices((h, w)).astype(np.float32)
    height = np.zeros_like(xx)
    for _ in range(120):                          # place 120 floral nodes
        cx = rng.uniform(0, w); cy = rng.uniform(0, h)
        r = rng.uniform(10, 24)
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        # ring (thread) + petal lobes
        ring = np.exp(-((d2 - r * r) ** 2) / (r * r * 8))
        height = height + ring
    # subtractive grid of micro-holes
    holes = np.cos(xx / 4.0) * np.cos(yy / 4.0)
    height = height - 0.25 * (holes > 0.7)
    return _height_to_normal(height, strength=3.5)


def _fishnet_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Wide-open diamond mesh — sharper / larger than sports mesh."""
    period = 26
    yy, xx = np.indices((h, w)).astype(np.float32)
    # diagonal stripes both directions
    a = np.cos((xx + yy) * 2 * np.pi / period)
    b = np.cos((xx - yy) * 2 * np.pi / period)
    height = np.maximum(a, b)                      # raised threads
    # dig holes where neither thread lies (deep cells)
    height = np.where(height < 0.0, height - 0.6, height)
    return _height_to_normal(height, strength=8.0)


def _neoprene_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Rubber-coated nylon — uniform low micro-grain, slightly stronger
    so the wetsuit feel reads at viewing distance."""
    rng = np.random.default_rng(41)
    height = rng.normal(scale=0.22, size=(h, w))
    from scipy.ndimage import gaussian_filter
    height = gaussian_filter(height, sigma=0.6)
    return _height_to_normal(height, strength=2.2)


def _slub_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Linen-like slub — irregular horizontal thickness variations.
    Bumped strength so the linen texture reads clearly."""
    rng = np.random.default_rng(53)
    rows = rng.normal(scale=0.9, size=(h, 1))
    cols = 0.5 + 0.5 * np.cos(np.linspace(0, 2 * np.pi * 30, w))[None, :]
    height = rows * cols
    return _height_to_normal(height, strength=4.5)


def _terry_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Terry loops — dense small loops (towel-like)."""
    rng = np.random.default_rng(67)
    yy, xx = np.indices((h, w)).astype(np.float32)
    height = np.zeros_like(xx)
    for _ in range(800):                           # many small loops
        cx = rng.uniform(0, w); cy = rng.uniform(0, h)
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        height = height + np.exp(-d2 / 14.0)
    return _height_to_normal(height, strength=2.5)


def _jacquard_normal_map(w: int = TEX_W, h: int = TEX_H) -> np.ndarray:
    """Decorative woven motif — interlocked diamond bumps + flat negative."""
    period = 60
    yy, xx = np.indices((h, w)).astype(np.float32)
    diamond = np.abs(((xx % period) - period / 2)) + np.abs(((yy % period) - period / 2))
    motif = np.clip(period / 2 - diamond, 0, None) / (period / 2)
    # secondary fine ribbing inside the motif
    ribs = 0.4 * np.cos(xx * 0.3) * np.cos(yy * 0.3)
    height = motif + 0.3 * ribs * motif
    return _height_to_normal(height, strength=4.0)


# ---------------------------------------------------------------------------


# Cache once — same weave for every genome.
_NORMAL_CACHE: dict[str, np.ndarray] = {}
_WEAVE_SHADE_CACHE = None


_WEAVE_BUILDERS = {
    "plain":       lambda: _fabric_normal_map(),
    "crinkle":     lambda: _crinkle_normal_map(),
    "ribbed":      lambda: _ribbed_normal_map(),
    "mesh":        lambda: _mesh_normal_map(),
    "velvet":      lambda: _velvet_normal_map(),
    "crochet":     lambda: _crochet_normal_map(),
    "shiny_knit":  lambda: _shiny_knit_normal_map(),
    "foam":        lambda: _foam_normal_map(),
    "sequined":    lambda: _sequined_normal_map(),
    "seersucker":  lambda: _seersucker_normal_map(),
    "lace":        lambda: _lace_normal_map(),
    "fishnet":     lambda: _fishnet_normal_map(),
    "neoprene":    lambda: _neoprene_normal_map(),
    "slub":        lambda: _slub_normal_map(),
    "terry":       lambda: _terry_normal_map(),
    "jacquard":    lambda: _jacquard_normal_map(),
}


def _get_fabric_normal(weave: str = "plain") -> np.ndarray:
    if weave not in _NORMAL_CACHE:
        builder = _WEAVE_BUILDERS.get(weave, _WEAVE_BUILDERS["plain"])
        _NORMAL_CACHE[weave] = builder()
    return _NORMAL_CACHE[weave]

def _get_weave_shade() -> np.ndarray:
    global _WEAVE_SHADE_CACHE
    if _WEAVE_SHADE_CACHE is None:
        _WEAVE_SHADE_CACHE = _weave_shade_overlay()
    return _WEAVE_SHADE_CACHE


def _apply_weave_shade_to_texture(tex: Image.Image) -> Image.Image:
    """Multiply the Genome's albedo texture by the weave shade overlay so
    the fabric carries a visible thread pattern even without a working
    normal map."""
    arr = np.asarray(tex.convert("RGB"), dtype=np.float32)
    shade = _get_weave_shade()[..., None]
    out = np.clip(arr * shade, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def render_mesh(renderer, mesh: o3d.geometry.TriangleMesh,
                texture_pil: Image.Image, genome=None,
                y_crotch: float | None = None, y_neck: float | None = None,
                body_uvs: np.ndarray | None = None,
                polys_uv: list | None = None,
                ) -> np.ndarray:
    """Render the body + bikini as layered 3D geometry.

    When `body_uvs` and `polys_uv` are supplied we build a fabric shell
    out of the body triangles that fall inside the Genome's UV polygons,
    offset 3 mm outward. The body itself is rendered in plain skin tone
    so the bikini reads as an actual garment layer rather than paint on
    skin. The straps (back band, waist string, side ties) add closed-loop
    geometry holding the shell on.

    If `body_uvs, polys_uv` are None, falls back to the old UV-decal
    approach (full texture painted on the body) for backward compat.
    """
    scene = renderer.scene
    scene.clear_geometry()

    use_shell = body_uvs is not None and polys_uv is not None

    # ---- body layer ----
    body_tex_np = np.array(
        (_skin_only_texture() if use_shell else texture_pil).convert("RGB")
    )
    body_mat = o3d.visualization.rendering.MaterialRecord()
    body_mat.shader = "defaultLit"
    body_mat.albedo_img = o3d.geometry.Image(body_tex_np)
    body_mat.base_roughness = 0.65
    body_mat.base_metallic = 0.0
    scene.add_geometry("body", mesh, body_mat)

    # ---- bikini fabric shell ----
    if use_shell:
        shell = build_fabric_shell(mesh, body_uvs, polys_uv, offset=0.3)
        if len(shell.vertices) > 0:
            # heavier fabric -> stiffer, less wiggle; lighter -> more drape
            wr_amp = 0.04 + 0.10 * (1.0 - getattr(genome, "fabric_weight", 0.5))
            apply_wrinkles(shell, amplitude=wr_amp)

            # bake the weave shade into the albedo so the thread pattern
            # shows even if the renderer ignores the normal map
            shaded_tex = _apply_weave_shade_to_texture(texture_pil)
            shell_tex_np = np.array(shaded_tex.convert("RGB"))
            shell_mat = o3d.visualization.rendering.MaterialRecord()
            shell_mat.shader = "defaultLit"
            shell_mat.albedo_img = o3d.geometry.Image(shell_tex_np)
            try:
                weave = getattr(genome, "fabric_weave", "plain") if genome else "plain"
                shell_mat.normal_img = o3d.geometry.Image(_get_fabric_normal(weave))
            except AttributeError:
                pass
            # sheen -> roughness: matte (0.95) ... satin (0.30)
            sheen = getattr(genome, "fabric_sheen", 0.3) if genome else 0.3
            shell_mat.base_roughness = 0.95 - 0.65 * sheen
            # lurex / foil shine
            shell_mat.base_metallic = getattr(genome, "fabric_metallic", 0.0)
            scene.add_geometry("fabric_shell", shell, shell_mat)

            # edge binding — small raised rim around the shell border
            binding = build_binding_mesh(shell, offset=0.05, thickness=0.15)
            if len(binding.vertices) > 0:
                from verify_ga_uv import _trim_color
                r, g, b = _trim_color(genome) if genome is not None else (0.3, 0.3, 0.3)
                bind_mat = o3d.visualization.rendering.MaterialRecord()
                bind_mat.shader = "defaultLit"
                bind_mat.base_color = (r, g, b, 1.0)
                bind_mat.base_roughness = 0.55
                bind_mat.base_metallic = shell_mat.base_metallic * 0.6
                scene.add_geometry("fabric_binding", binding, bind_mat)

    # ---- straps + hardware ----
    if genome is not None and y_crotch is not None and y_neck is not None:
        strap_mat = o3d.visualization.rendering.MaterialRecord()
        strap_mat.shader = "defaultLit"
        strap_mat.base_color = _color_from_genome(genome)
        strap_mat.base_roughness = 0.85
        strap_mat.base_metallic = 0.0

        # Metallic hardware material — used for O-rings, bow knot, beads,
        # shell. Color / metallic_factor come from the hardware_metal gene.
        hw_color = {
            "none":      (0.75, 0.75, 0.75, 1.0),
            "gold":      (1.00, 0.83, 0.28, 1.0),
            "silver":    (0.92, 0.92, 0.95, 1.0),
            "rose_gold": (0.92, 0.72, 0.66, 1.0),
            "pearl":     (0.96, 0.94, 0.88, 1.0),
            "chrome":    (0.85, 0.85, 0.90, 1.0),
        }.get(getattr(genome, "hardware_metal", "gold"), (0.9, 0.9, 0.9, 1.0))
        hw_mat = o3d.visualization.rendering.MaterialRecord()
        hw_mat.shader = "defaultLit"
        hw_mat.base_color = hw_color
        hw_mat.base_roughness = 0.25 if genome.hardware_metal != "pearl" else 0.45
        hw_mat.base_metallic = 0.9 if genome.hardware_metal not in ("pearl", "none") else 0.15

        metal_prefixes = ("oring_", "bow_knot", "beads", "shell")
        for name, strap in build_strap_meshes(mesh, genome, y_crotch, y_neck):
            if len(strap.vertices) == 0:
                continue
            is_metal = any(name.startswith(p) for p in metal_prefixes)
            scene.add_geometry(f"strap_{name}", strap,
                               hw_mat if is_metal else strap_mat)

    fit_camera(renderer, mesh)
    img = renderer.render_to_image()
    return np.asarray(img)


def make_renderer(w: int, h: int):
    renderer = o3d.visualization.rendering.OffscreenRenderer(w, h)
    scene = renderer.scene
    scene.set_background([0.94, 0.94, 0.96, 1.0])
    scene.scene.set_sun_light(
        direction=[-0.3, -0.7, -0.5],
        color=[1.0, 1.0, 1.0],
        intensity=80_000,
    )
    scene.scene.enable_sun_light(True)
    scene.scene.enable_indirect_light(True)
    scene.scene.set_indirect_light_intensity(30_000)
    return renderer


def fit_camera(renderer, mesh: o3d.geometry.TriangleMesh):
    """Frame the torso from the front."""
    V = np.asarray(mesh.vertices)
    y_lo, y_hi = np.percentile(V[:, 1], [2, 98])
    y_top = y_lo + 0.95 * (y_hi - y_lo)
    y_bot = y_lo + 0.20 * (y_hi - y_lo)
    center = np.array([0.0, (y_top + y_bot) / 2.0, 0.0], dtype=np.float32)
    height = float(y_top - y_bot)
    fov_deg = 35.0
    dist = (height * 0.55) / np.tan(np.deg2rad(fov_deg / 2.0))
    eye = np.array([0.0, center[1], dist], dtype=np.float32)
    up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    renderer.setup_camera(fov_deg, center, eye, up)


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(TEX_DIR, exist_ok=True)

    mesh = load_body_mesh()
    uvs = cylindrical_uvs(mesh)
    mesh.triangle_uvs = o3d.utility.Vector2dVector(uvs)
    y_crotch, y_neck = torso_anchors(mesh)

    renderer = make_renderer(RENDER_W, RENDER_H)

    rng = random.Random(SEED)
    pa, pb = make_parents()
    offspring = run_ga(pa, pb, N_OFFSPRING, rng)
    genomes = [("Parent A", pa), ("Parent B", pb)]
    genomes += [(f"Child {i+1}", g) for i, g in enumerate(offspring)]

    renders = []
    for label, g in genomes:
        t0 = time.time()
        tex = genome_to_texture(g)
        tag = label.lower().replace(" ", "_")
        tex.save(os.path.join(TEX_DIR, f"genome_{tag}.png"))
        from verify_ga_uv import genome_polygons
        polys = genome_polygons(g)
        img = render_mesh(renderer, mesh, tex, genome=g,
                          y_crotch=y_crotch, y_neck=y_neck,
                          body_uvs=uvs, polys_uv=polys)
        renders.append((label, img, g))
        print(f"  rendered {label} in {time.time() - t0:.1f}s")

    # 2x5 grid
    cols = 5
    rows = (len(renders) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.6, rows * 3.6),
                             facecolor="white")
    axes = np.array(axes).reshape(-1)
    for i, (label, img, g) in enumerate(renders):
        ax = axes[i]
        ax.imshow(img)
        from fitness import evaluate as _evaluate_fit
        fit = _evaluate_fit(g)
        hw_bits = []
        if g.has_oring >= 0.5: hw_bits.append(f"O-ring({g.hardware_metal})")
        if g.has_bow >= 0.5: hw_bits.append("bow")
        if g.has_fringe >= 0.5: hw_bits.append("fringe")
        if g.has_beads >= 0.5: hw_bits.append("beads")
        if g.has_shell >= 0.5: hw_bits.append("shell")
        hw_str = ", ".join(hw_bits) if hw_bits else "no hardware"
        ax.set_title(
            f"{label}  {g.style_archetype}  pat={g.pattern}\n"
            f"{hw_str}\n"
            f"weave={g.fabric_weave} sheen={g.fabric_sheen:.2f} "
            f"met={g.fabric_metallic:.2f}\n"
            f"fit: P={fit['proportion']:.2f} H={fit['harmony']:.2f} "
            f"E={fit['emphasis']:.2f} R={fit['rhythm']:.2f}  "
            f"overall={fit['overall']:.2f}",
            fontsize=5.5,
        )
        ax.axis("off")
    for j in range(len(renders), len(axes)):
        axes[j].axis("off")
    fig.suptitle("Bikini GA — 3D preview on uploaded body mesh",
                 fontsize=12, y=0.995)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "ga_3d_render.png")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# build_strap_meshes_v2 — driven by Garment latent state instead of raw Genome
# ---------------------------------------------------------------------------

def _build_strap_meshes_garment(body_mesh,
                           garment,
                           genome,
                           y_crotch: float, y_neck: float,
                           body_deployment=None):
    """Garment-driven sibling of build_strap_meshes. Iterates over
    garment.connectors / .accessories / .attachments to decide which
    sub-meshes to build, picks SKU width / size from CONNECTORS catalog,
    and routes each strap by its Connector.path_policy. Reuses all the
    existing geometry primitives (_arc_tube / _build_band_mesh /
    _build_tie_mesh / _body_ring / _body_point_at) so visual output is
    near-identical to v1 when fed the same Genome.

    Returns list[(name, mesh)] same shape as build_strap_meshes for
    drop-in compatibility.
    """
    V = np.asarray(body_mesh.vertices)
    g = genome
    straps: list[tuple[str, o3d.geometry.TriangleMesh]] = []

    def v_to_y(v: float) -> float:
        return y_crotch + v * (y_neck - y_crotch)

    # Build a dict of garment connectors by id for quick lookup, and
    # group attachments by component_id.
    # Accountability rule (cascade-aware): when a BodyDeployment is
    # supplied, only connectors / accessories that survived
    # deploy_to_body's anchor resolution stay in the build set. This
    # is what kills the "floating in space, attached to nothing"
    # problem at the latent-state layer.
    if body_deployment is not None:
        valid_c = body_deployment.valid_connector_ids
        valid_a = body_deployment.valid_accessory_ids
        conns = [c for c in garment.connectors if c.id in valid_c]
        accs = [a for a in garment.accessories if a.id in valid_a]
    else:
        conns = list(garment.connectors)
        accs = list(garment.accessories)
    conn_by_id = {c.id: c for c in conns}
    acc_by_id = {a.id: a for a in accs}
    # Replace garment lookups inside this function with the filtered
    # local copies to keep the rest of the function's logic intact.
    class _filtered:
        connectors = conns
        accessories = accs
        archetype = garment.archetype
        attachments = garment.attachments
        seams = garment.seams
        pieces = garment.pieces
    garment = _filtered()
    atts_for: dict[str, list] = {}
    for att in garment.attachments:
        atts_for.setdefault(att.component_id, []).append(att)

    # Resolve anatomy anchors once.
    try:
        from anatomy import (detect as _detect_anatomy,
                              front_clavicle_point as _front_clav,
                              back_scapula_point as _back_scap)
        L = _detect_anatomy(body_mesh)
    except Exception:
        L = None

    def _anchor_xyz(anchor_name: str) -> np.ndarray | None:
        if L is None:
            return None
        if anchor_name == "front_clavicle_R":
            return _front_clav(body_mesh, L, "R")
        if anchor_name == "front_clavicle_L":
            return _front_clav(body_mesh, L, "L")
        if anchor_name == "back_scapula_R":
            return _back_scap(body_mesh, L, "R")
        if anchor_name == "back_scapula_L":
            return _back_scap(body_mesh, L, "L")
        if anchor_name == "neck_base_back":
            return np.array([0.0, L.y_neck_base - 1.0, -3.0],
                              dtype=np.float64)
        if anchor_name == "neck_base_front":
            return np.array([0.0, L.y_neck_base - 1.0, 3.0],
                              dtype=np.float64)
        if anchor_name == "sternum":
            return np.array([0.0, v_to_y(g.top_center_v), 5.0],
                              dtype=np.float64)
        if anchor_name == "navel":
            return np.array([0.0, v_to_y(0.5), 6.0], dtype=np.float64)
        if anchor_name == "hip_R":
            return _body_point_at(V, +0.5, v_to_y(g.bot_back_top_v))
        if anchor_name == "hip_L":
            return _body_point_at(V, -0.5, v_to_y(g.bot_back_top_v))
        return None

    # ---- Components are emitted ONLY when the manufacturing latent
    # state actually contains them. Anything missing a Connector +
    # Attachment chain is presumed structurally invalid (= a piece
    # floating in space disconnected from any anchor) and gets dropped.
    cup_outer_u = g.top_inner_u + 2 * g.top_half_u

    # 1) Top back band — continuous fabric ribbon. Belongs on bandeau
    # / bralette / one-piece. Triangle-string-halter uses a thin string
    # at chest level instead (emitted in section 5).
    if garment.archetype in ("bandeau_back_band", "bralette_shoulder_strap",
                                "one_piece_maillot"):
        band_y = v_to_y(g.top_center_v)
        band_h = max(1.2, 1.5 + 2.0 * g.top_back_coverage)
        ring = _body_ring(V, band_y, y_halfband=3.0, n_samples=96,
                           max_torso_radius=20.0)
        back_band = _build_band_mesh(ring, band_h, offset=0.5,
                                       u_from=cup_outer_u, u_to=-cup_outer_u)
        straps.append(("top_back_band", back_band))

    # 1b) Underbust band — gated on existence in garment.connectors
    has_underbust = any(c.kind == "underbust_elastic"
                         for c in garment.connectors)
    if has_underbust:
        underbust_v = max(0.05, g.top_center_v - g.top_half_v - 0.02)
        underbust_y = v_to_y(underbust_v)
        underbust_ring = _body_ring(V, underbust_y, y_halfband=2.5,
                                      n_samples=96, max_torso_radius=20.0)
        ub_thickness = next((c.width_cm for c in garment.connectors
                              if c.kind == "underbust_elastic"), 1.5)
        underbust_band = _build_band_mesh(underbust_ring,
                                            band_thickness=ub_thickness,
                                            offset=0.55)
        straps.append(("underbust_band", underbust_band))

    # 1c) Crotch gusset — removed. The earlier `_arc_tube` from u=0 to
    # u=1.0 traced a half-circle around the torso at crotch height,
    # producing a horizontal-bar-with-a-loop artifact between the thighs
    # in front views (front-segment visible, side-segment off-screen,
    # back-segment hidden behind the body). Real swimwear gussets are
    # internal fabric panels, not a strap around the hips — the
    # front_bottom + back_bottom PatternPieces already meet visibly at
    # the inseam without any extra surface geometry.

    # 2) Waist string — only emit when garment.connectors carries a
    # waist_elastic. Without it, the waist band was floating fabric
    # belonging to nothing.
    has_waist = any(c.kind == "waist_elastic" for c in garment.connectors)
    if has_waist:
        y_front = v_to_y(g.bot_front_top_v)
        y_back  = v_to_y(g.bot_back_top_v)
        band_y2 = (y_front + y_back) / 2
        ring2 = _body_ring(V, band_y2, y_halfband=3.0, n_samples=96)
        waist_band = _build_band_mesh(ring2, 1.5, offset=0.5)
        straps.append(("waist_band", waist_band))

    # 3) Hip-side connector — a thin cord / ribbon / elastic strap
    # holding the front and back bottom panels together at the hip.
    # Optional style element: rendered only when an outfit slot
    # (side_tie / hip_strap) routed a connector to hip_R / hip_L.
    # Width comes from the strap library entry's width_cm so cords
    # stay thin (3mm), ribbons wider (15mm), sport elastic widest (25mm).
    tie_atts = [a for a in garment.attachments
                if a.target_kind == "anatomy_anchor"
                and a.anatomy_anchor in ("hip_R", "hip_L")
                and a.component_kind == "connector"]
    conn_by_id = {c.id: c for c in garment.connectors}
    if tie_atts:
        y_front = v_to_y(g.bot_front_top_v)
        y_back  = v_to_y(g.bot_back_top_v)
        y_side_lo = min(y_front, y_back) - 0.8
        y_side_hi = max(y_front, y_back) + 0.8
        for att in tie_atts:
            u_side = +0.5 if att.anatomy_anchor == "hip_R" else -0.5
            name = "side_tie_R" if att.anatomy_anchor == "hip_R" else "side_tie_L"
            c = conn_by_id.get(att.component_id)
            half_w = max(0.15, (c.width_cm if c is not None else 1.2) * 0.5)
            tie = _build_tie_mesh(V, y_side_lo, y_side_hi, u_side,
                                    half_width_cm=half_w)
            straps.append((name, tie))

    # 4) Tie dangles — these are decorative tails of the side tie. The
    # garment latent state doesn't model dangles as separate Connectors;
    # they're a property of the side tie ribbon. We emit them only if a
    # side tie connector exists AND Genome.bot_tie_dangle is set.
    if tie_atts and g.bot_tie_dangle > 0.15:
        dangle_len = 2.0 + 14.0 * g.bot_tie_dangle
        for att in tie_atts:
            u_side = +0.5 if att.anatomy_anchor == "hip_R" else -0.5
            name = "dangle_R" if att.anatomy_anchor == "hip_R" else "dangle_L"
            try:
                anchor = _body_point_at(V, u_side,
                                          (v_to_y(g.bot_front_top_v)
                                           + v_to_y(g.bot_back_top_v)) / 2)
                rxz = np.array([anchor[0], 0.0, anchor[2]])
                rxz /= max(np.linalg.norm(rxz), 1e-6)
                p0 = anchor + rxz * 0.6
                p1 = p0 - np.array([0.0, dangle_len, 0.0])
                dangle = _tube_between(p0, p1, radius=0.15, sides=5)
                straps.append((name, dangle))
            except Exception:
                pass

    # 5) Back-closure tie string — only for archetypes that use a
    # behind-back tie at chest level. The string anchors at the cup
    # outer-top (where it would be sewn to the cup edge in real life),
    # passes through the scapula left/right (anatomy-resolved
    # back_scapula_R/L), and meets at the other cup edge.
    #
    # This is the anatomy-aware attachment routing requested in step 3:
    # control points come from named anatomy anchors + UV-derived cup
    # corners, not from a generic _body_ring walk.
    back_tie_atts = [a for a in garment.attachments
                     if a.target_kind == "anatomy_anchor"
                     and a.anatomy_anchor in ("back_scapula_R", "back_scapula_L")
                     and a.component_kind == "connector"
                     and any(c.id == a.component_id and c.kind == "tie_string"
                              for c in garment.connectors)]
    if back_tie_atts and garment.archetype == "triangle_string_halter":
        try:
            band_y = v_to_y(g.top_center_v)
            cup_outer_u = g.top_inner_u + 2 * g.top_half_u
            # Right-side anchor: cup_outer in 3D at chest band height.
            cup_R = _body_point_at(V, +cup_outer_u, band_y,
                                     max_torso_radius=20.0)
            cup_L = _body_point_at(V, -cup_outer_u, band_y,
                                     max_torso_radius=20.0)
            # Anatomy-resolved scapula points (anatomy module returns
            # body-surface vertices on the back at acromion height).
            scap_R = _anchor_xyz("back_scapula_R") if L is not None else \
                      _body_point_at(V, +0.85, band_y, max_torso_radius=20.0)
            scap_L = _anchor_xyz("back_scapula_L") if L is not None else \
                      _body_point_at(V, -0.85, band_y, max_torso_radius=20.0)
            # Center-back midpoint, drop slightly forward of the spine
            # so the string visibly contacts the body.
            back_center = np.array([
                0.0,
                band_y,
                min(scap_R[2], scap_L[2]) - 0.4,
            ], dtype=np.float64)
            # Pull scapula control points slightly toward the center
            # so the arc doesn't bow out laterally past the body.
            ctrl_R = scap_R * np.array([0.85, 1.0, 1.0]) \
                      + np.array([0.0, 0.0, -0.5])
            ctrl_L = scap_L * np.array([0.85, 1.0, 1.0]) \
                      + np.array([0.0, 0.0, -0.5])
            arc_pts = [cup_R, ctrl_R, back_center, ctrl_L, cup_L]
            tie_r = next((c.width_cm * 0.5 for c in garment.connectors
                            if any(a.component_id == c.id
                                   and a.anatomy_anchor in (
                                       "back_scapula_R", "back_scapula_L")
                                   for a in garment.attachments)),
                          0.25)
            back_tie = _arc_tube(np.array(arc_pts), radius=max(0.18, tie_r))
            straps.append(("back_tie_string", back_tie))
        except Exception:
            pass

    # 5b) Halter neck strap — driven by a halter connector + its attachment
    halter_conns = [c for c in garment.connectors if c.kind == "halter_strap"]
    if halter_conns:
        c = halter_conns[0]
        strap_r = max(0.15, c.width_cm * 0.5)
        cup_top_v = g.top_center_v + g.top_half_v
        u_inner_halter = 0.03 + 0.05 * g.top_inner_u
        y_start = v_to_y(cup_top_v)
        try:
            anchor_R = _body_point_at(V, u_inner_halter, y_start)
            anchor_L = _body_point_at(V, -u_inner_halter, y_start)
            meeting = (_anchor_xyz("neck_base_back")
                        if L is not None
                        else _body_point_at(V, 0.0, y_neck - 4.0)
                              + np.array([0.0, 0.0, 0.4]))
            mid_R = 0.5 * (anchor_R + meeting) + np.array([0.0, 1.0, 0.5])
            mid_L = 0.5 * (anchor_L + meeting) + np.array([0.0, 1.0, 0.5])
            halter_R = _arc_tube(np.array([anchor_R, mid_R, meeting]),
                                   radius=strap_r)
            halter_L = _arc_tube(np.array([anchor_L, mid_L, meeting]),
                                   radius=strap_r)
            straps.append(("halter_R", halter_R))
            straps.append(("halter_L", halter_L))
        except Exception:
            pass

    # 6) O-rings — at strap junctions when a connector kind=o_ring exists
    rings = [c for c in garment.connectors if c.kind == "o_ring"]
    if rings:
        # Reuse v1 helper but with our SKU radius.
        for c in rings:
            radius_cm = c.diameter_cm * 0.5
            cup_top_v = g.top_center_v + g.top_half_v
            u_outer = g.top_inner_u + 2 * g.top_half_u
            y_top = v_to_y(cup_top_v)
            for u_s, side in ((u_outer, "R"), (-u_outer, "L")):
                try:
                    anc = _body_point_at(V, u_s, y_top, max_torso_radius=18.0)
                    ring = _build_torus(anc, radius_cm, tube_radius=0.08)
                    straps.append((f"oring_{side}", ring))
                except Exception:
                    pass

    # 7) Shoulder straps — driven by shoulder_strap connector + anatomy anchors
    sh_conns = [c for c in garment.connectors if c.kind == "shoulder_strap"]
    if sh_conns and g.top_shoulder_strap > 0.15:
        c = sh_conns[0]
        strap_r = max(0.15, c.width_cm * 0.5)
        cup_top_v = g.top_center_v + g.top_half_v
        u_outer = g.top_inner_u + 2 * g.top_half_u
        y_front = v_to_y(cup_top_v)
        for u_s, side, name in [(u_outer, "R", "shoulder_R"),
                                   (-u_outer, "L", "shoulder_L")]:
            try:
                P0 = _body_point_at(V, u_s, y_front)
                if L is not None:
                    if P0[1] > L.y_acromion - 2.0:
                        P0 = P0.copy(); P0[1] = L.y_acromion - 2.0
                    P_clav = _front_clav(body_mesh, L, side)
                    P_ridge = np.array([
                        P_clav[0] * 0.65,
                        min(L.y_acromion + 1.5, L.y_neck_base - 1.0),
                        P_clav[2] * 0.4,
                    ], dtype=np.float64)
                    P_scap = _back_scap(body_mesh, L, side)
                    P_back_anchor = np.array([
                        P_scap[0] * 0.7, v_to_y(g.top_center_v), P_scap[2] * 0.7,
                    ], dtype=np.float64)
                    strap = _arc_tube(
                        np.array([P0, P_clav, P_ridge, P_scap, P_back_anchor]),
                        radius=strap_r)
                else:
                    ridge = P0 + np.array([-0.25 * P0[0], 4.0, 0.4])
                    u_back = (u_s + 1.0) if u_s < 0 else (u_s - 1.0)
                    P2 = _body_point_at(V, u_back, v_to_y(g.top_center_v))
                    if P2[2] > 0:
                        P2 = P2 * np.array([1.0, 1.0, -1.0])
                    mid_back = ridge + np.array([0.0, -1.0, -3.0])
                    strap = _arc_tube(np.array([P0, ridge, mid_back, P2]),
                                       radius=strap_r)
                straps.append((name, strap))
            except Exception:
                pass

    # 8) Bar-tacks — at cup-top junctions when shoulder/halter exists
    if g.top_shoulder_strap > 0.15 or g.top_neck_strap > 0.15:
        cup_top_v = g.top_center_v + g.top_half_v
        u_outer = g.top_inner_u + 2 * g.top_half_u
        u_inner = 0.03 + 0.05 * g.top_inner_u
        for tag, u in (("OR", u_outer), ("OL", -u_outer),
                        ("IR", u_inner), ("IL", -u_inner)):
            try:
                anc = _body_point_at(V, u, v_to_y(cup_top_v),
                                       max_torso_radius=18.0)
                tack = o3d.geometry.TriangleMesh.create_sphere(
                    radius=0.30, resolution=8)
                tack.translate(anc.tolist())
                tack.compute_vertex_normals()
                straps.append((f"bartack_{tag}", tack))
            except Exception:
                pass

    # 9) Accessories — bow / shell_charm / pendant / fringe / beads / tassel /
    #    ring_charm. Each maps to one of the existing _build_*_mesh helpers
    #    (which take Genome) — we forward to those.
    for acc in garment.accessories:
        if acc.kind == "bow":
            straps.extend(_build_bow_mesh(g, V, v_to_y))
        elif acc.kind == "fringe":
            straps.extend(_build_fringe_meshes(g, V, v_to_y))
        elif acc.kind == "beads":
            straps.extend(_build_beads_meshes(g, V, v_to_y))
        elif acc.kind == "shell_charm":
            straps.extend(_build_shell_mesh(g, V, v_to_y))

    # 10) Body jewelry (v2 — bracelets, necklaces, earrings, anklets,
    # body chains). Each library entry resolves through BodyDeployment to
    # a 3D anchor (wrist_R / earlobe_R / ankle_R / neck_front / belly_button)
    # and then routes to a small mesh primitive. No geometry if the
    # deployment didn't resolve the entry's anchors.
    if body_deployment is not None:
        straps.extend(_build_body_jewelry_meshes(body_mesh, garment,
                                                    body_deployment))

    return straps


def build_strap_meshes(body_mesh: o3d.geometry.TriangleMesh, g,
                        y_crotch: float, y_neck: float,
                        body_deployment=None):
    """Public dispatcher. Builds the manufacturing Garment latent state
    from the Genome and routes to the garment-driven sub-mesh builder.

    body_deployment (optional): a BodyDeployment from
    garment_state.deploy_to_body. When supplied, accountability rules
    apply — connectors / accessories without resolved attachments are
    skipped at strap-build time. The dispatcher computes one internally
    if not provided.
    """
    try:
        from garment_state import (genome_to_garment, validate_garment,
                                     deploy_to_body, validate_deployment,
                                     UnsupportedArchetypeV1)
        try:
            garment = validate_garment(genome_to_garment(g))
            if body_deployment is None:
                body_deployment = validate_deployment(
                    garment, deploy_to_body(garment, body_mesh))
            return _build_strap_meshes_garment(body_mesh, garment, g,
                                                  y_crotch, y_neck,
                                                  body_deployment)
        except UnsupportedArchetypeV1:
            return _build_strap_meshes_legacy(body_mesh, g, y_crotch, y_neck)
    except Exception:
        return _build_strap_meshes_legacy(body_mesh, g, y_crotch, y_neck)


# ---------------------------------------------------------------------------
# build_seam_lines_for_garment — auto seam-line geometry from PatternPiece
#   tagging. Each shell triangle is labeled by the polygon its centroid
#   falls inside; adjacent triangles with different labels share a seam
#   edge, which gets a thin tube along it. Removes the need to bake fake
#   stitch lines into the albedo.
# ---------------------------------------------------------------------------

def build_seam_lines_for_garment(shell: o3d.geometry.TriangleMesh,
                                   garment,
                                   offset: float = 0.05,
                                   tube_radius: float = 0.12,
                                   ) -> o3d.geometry.TriangleMesh:
    """Compute piece-tag boundary edges on the shell and return a thin
    tube mesh tracing each seam edge.

    Tagging rule: a triangle's piece_id is the first PatternPiece (in
    garment.pieces order) whose polygon contains the triangle's UV
    centroid. polygon_uv lives in Genome UV space [-1,1] x [0,1]; we
    derive the triangle's centroid from per-corner UVs already attached
    to the shell (shell.triangle_uvs).
    """
    from matplotlib.path import Path

    F = np.asarray(shell.triangles)
    if len(F) == 0 or not shell.has_triangle_uvs():
        return o3d.geometry.TriangleMesh()
    UV = np.asarray(shell.triangle_uvs)         # per-corner, (3*Ntri, 2)
    V = np.asarray(shell.vertices)
    if not shell.has_vertex_normals():
        shell.compute_vertex_normals()
    N = np.asarray(shell.vertex_normals)

    # Per-triangle UV centroid in Genome [-1,1] x [0,1].
    n_tri = len(F)
    tri_uv = UV.reshape(n_tri, 3, 2).mean(axis=1)
    tri_uv_g = tri_uv.copy()
    tri_uv_g[:, 0] = tri_uv_g[:, 0] * 2.0 - 1.0

    # Build (piece_id, Path) list including mirrored shell pieces.
    polys: list[tuple[str, "Path"]] = []
    for piece in garment.pieces:
        if piece.layer_role != "shell":
            continue
        polys.append((piece.id,
                       Path(np.asarray(piece.polygon_uv, dtype=np.float32))))
        if piece.count == 2 and piece.mirror_axis == "u":
            mirror = [(-u, v) for (u, v) in piece.polygon_uv]
            polys.append((piece.id + "_mirror",
                           Path(np.asarray(mirror, dtype=np.float32))))

    # Tag triangles. First-match wins (garment.pieces order = priority).
    tri_piece: list[str | None] = [None] * n_tri
    for piece_id, path in polys:
        inside = path.contains_points(tri_uv_g)
        for i in np.where(inside)[0]:
            if tri_piece[i] is None:
                tri_piece[i] = piece_id

    # Build edge -> [(triangle_idx)] map; only triangles with a tag count.
    edge_to_tris: dict[tuple[int, int], list[int]] = {}
    for ti, (a, b, c) in enumerate(F):
        if tri_piece[ti] is None:
            continue
        for u, v in ((a, b), (b, c), (c, a)):
            e = (int(min(u, v)), int(max(u, v)))
            edge_to_tris.setdefault(e, []).append(ti)

    # Seam edge: shared by ≥2 triangles whose piece tags differ.
    # _mirror suffix is collapsed to base id so left/right of same piece
    # don't get a fake seam down the center.
    def _base(pid: str | None) -> str | None:
        if pid is None:
            return None
        return pid[: -len("_mirror")] if pid.endswith("_mirror") else pid

    seam_edges: list[tuple[int, int]] = []
    for edge, tris in edge_to_tris.items():
        if len(tris) < 2:
            continue
        pids = {_base(tri_piece[ti]) for ti in tris}
        pids.discard(None)
        if len(pids) >= 2:
            seam_edges.append(edge)

    if not seam_edges:
        return o3d.geometry.TriangleMesh()

    # Build thin tubes along each seam edge, offset slightly outward
    # along the average vertex normal so the tube sits proud of the shell.
    out_meshes: list[o3d.geometry.TriangleMesh] = []
    for u, v in seam_edges:
        p0 = V[u] + N[u] * offset
        p1 = V[v] + N[v] * offset
        if np.linalg.norm(p1 - p0) < 0.05:
            continue
        tube = _tube_between(p0, p1, radius=tube_radius, sides=4)
        out_meshes.append(tube)
    if not out_meshes:
        return o3d.geometry.TriangleMesh()

    merged = out_meshes[0]
    for m in out_meshes[1:]:
        merged += m
    merged.compute_vertex_normals()
    return merged


# ---------------------------------------------------------------------------
# v2 body jewelry — bracelets, necklaces, earrings, anklets, body chains.
# Built from library entries (kind=body_jewelry) routed via the
# corresponding anatomy_anchor in the BodyDeployment.
# ---------------------------------------------------------------------------

def _bracelet_mesh(anchor_xyz: np.ndarray, side_sign: int,
                    diameter_cm: float = 6.5,
                    tube_r: float = 0.20) -> o3d.geometry.TriangleMesh:
    """Bracelet = torus around the arm, axis aligned with the arm
    direction. For a T-pose body that's the X axis, so the torus
    naturally has its axis = X. _build_torus default axis is Y; we
    rotate to align with X."""
    torus = _build_torus(major_r=diameter_cm * 0.5,
                          minor_r=tube_r, major_seg=24, minor_seg=8)
    # Rotate Y axis -> X axis (pi/2 around Z)
    R = torus.get_rotation_matrix_from_xyz((0.0, 0.0, np.pi / 2))
    torus.rotate(R, center=(0.0, 0.0, 0.0))
    torus.translate(anchor_xyz.tolist())
    torus.compute_vertex_normals()
    return torus


def _anklet_mesh(anchor_xyz: np.ndarray,
                  diameter_cm: float = 8.5,
                  tube_r: float = 0.18) -> o3d.geometry.TriangleMesh:
    """Anklet = torus around the leg, axis = Y (legs are vertical)."""
    torus = _build_torus(major_r=diameter_cm * 0.5,
                          minor_r=tube_r, major_seg=24, minor_seg=8)
    torus.translate(anchor_xyz.tolist())
    torus.compute_vertex_normals()
    return torus


def _necklace_choker_mesh(anchor_xyz: np.ndarray,
                            radius_cm: float = 7.0,
                            tube_r: float = 0.15) -> o3d.geometry.TriangleMesh:
    """Choker = small torus around the neck, axis = Y. Anchored at
    neck_front, but the torus is centered slightly behind so it wraps
    the neck cylinder."""
    torus = _build_torus(major_r=radius_cm,
                          minor_r=tube_r, major_seg=24, minor_seg=6)
    # Pull center slightly back from neck_front anchor
    center = anchor_xyz + np.array([0.0, 0.0, -3.0])
    torus.translate(center.tolist())
    torus.compute_vertex_normals()
    return torus


def _necklace_pendant_mesh(anchor_xyz: np.ndarray,
                             chain_radius_cm: float = 8.0,
                             pendant_size_cm: float = 1.2,
                             tube_r: float = 0.10
                             ) -> o3d.geometry.TriangleMesh:
    """Pendant necklace = thin loop around neck + small drop at the
    front center of the chain, dropped chain_radius_cm/4 below."""
    chain = _build_torus(major_r=chain_radius_cm,
                          minor_r=tube_r, major_seg=28, minor_seg=5)
    center = anchor_xyz + np.array([0.0, 0.0, -3.0])
    chain.translate(center.tolist())
    drop = o3d.geometry.TriangleMesh.create_sphere(
        radius=pendant_size_cm * 0.5, resolution=10)
    drop.translate((anchor_xyz + np.array([0.0, -3.0, 1.0])).tolist())
    out = chain + drop
    out.compute_vertex_normals()
    return out


def _earring_drop_mesh(anchor_xyz: np.ndarray,
                        length_cm: float = 2.5
                        ) -> o3d.geometry.TriangleMesh:
    """Drop earring = small sphere at earlobe + a slim cylinder hanging
    below."""
    stud = o3d.geometry.TriangleMesh.create_sphere(radius=0.25, resolution=8)
    stud.translate(anchor_xyz.tolist())
    drop = o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.15, height=length_cm, resolution=8)
    # cylinder default axis is Z; rotate to Y (vertical hanging) and
    # translate down from the earlobe.
    R = drop.get_rotation_matrix_from_xyz((np.pi / 2, 0.0, 0.0))
    drop.rotate(R, center=(0.0, 0.0, 0.0))
    drop.translate((anchor_xyz + np.array([0.0, -length_cm * 0.5 - 0.4, 0.0])).tolist())
    out = stud + drop
    out.compute_vertex_normals()
    return out


def _earring_stud_mesh(anchor_xyz: np.ndarray,
                        size_cm: float = 0.6) -> o3d.geometry.TriangleMesh:
    stud = o3d.geometry.TriangleMesh.create_sphere(
        radius=size_cm * 0.5, resolution=10)
    stud.translate(anchor_xyz.tolist())
    stud.compute_vertex_normals()
    return stud


def _body_chain_waist_mesh(belly_anchor: np.ndarray,
                             waist_circumference_cm: float = 75.0,
                             tube_r: float = 0.15
                             ) -> o3d.geometry.TriangleMesh:
    """Waist body chain = thin horizontal torus around the body at
    belly_button height, axis = Y."""
    radius = waist_circumference_cm / (2 * np.pi)
    torus = _build_torus(major_r=radius, minor_r=tube_r,
                          major_seg=36, minor_seg=5)
    # Center at the body's central axis at belly button height
    torus.translate((0.0, float(belly_anchor[1]), 0.0))
    torus.compute_vertex_normals()
    return torus


def _body_chain_belly_mesh(belly_anchor: np.ndarray,
                             tube_r: float = 0.12
                             ) -> o3d.geometry.TriangleMesh:
    """Belly body chain = waist loop + a thin vertical drop chain from
    the waist to the navel."""
    waist = _body_chain_waist_mesh(belly_anchor + np.array([0.0, 4.0, 0.0]),
                                      waist_circumference_cm=75.0,
                                      tube_r=tube_r)
    drop = o3d.geometry.TriangleMesh.create_cylinder(
        radius=tube_r, height=4.5, resolution=8)
    R = drop.get_rotation_matrix_from_xyz((np.pi / 2, 0.0, 0.0))
    drop.rotate(R, center=(0.0, 0.0, 0.0))
    drop.translate((belly_anchor + np.array([0.0, 1.5, 0.5])).tolist())
    out = waist + drop
    out.compute_vertex_normals()
    return out


def _build_body_jewelry_meshes(body_mesh, garment, body_deployment
                                  ) -> list[tuple[str, o3d.geometry.TriangleMesh]]:
    """Walk garment.accessories looking for body_jewelry kinds and emit
    geometry per the corresponding library entry."""
    if body_deployment is None:
        return []
    try:
        from library_data import LIBRARY
    except Exception:
        return []

    out: list[tuple[str, o3d.geometry.TriangleMesh]] = []
    for acc in garment.accessories:
        entry = LIBRARY.get(acc.id)
        if entry is None or entry.kind != "body_jewelry":
            continue
        if acc.id not in body_deployment.valid_accessory_ids:
            continue
        # find the resolved anchor 3D position from any of the entry's anatomy_hints
        anchor_xyz = None
        for att in garment.attachments:
            if (att.component_kind == "accessory" and att.component_id == acc.id
                    and att.id in body_deployment.resolved_anchors):
                p = body_deployment.resolved_anchors[att.id]
                if p is None:
                    continue
                anchor_xyz = np.array(p, dtype=np.float64)
                break
        if anchor_xyz is None:
            continue

        form = entry.jewelry_form
        diam = float(entry.local_params_schema.get(
            "diameter_cm", (5.0, 10.0, acc.size_cm))[2])
        if form == "bracelet_chain" or form == "bracelet_beaded":
            side = +1 if anchor_xyz[0] > 0 else -1
            mesh = _bracelet_mesh(anchor_xyz, side_sign=side,
                                    diameter_cm=diam, tube_r=0.20)
            out.append((f"jewelry_{entry.id}", mesh))
        elif form == "necklace_choker":
            mesh = _necklace_choker_mesh(anchor_xyz, radius_cm=7.0,
                                            tube_r=0.15)
            out.append((f"jewelry_{entry.id}", mesh))
        elif form == "necklace_pendant":
            chain_r = float(entry.local_params_schema.get(
                "chain_length_cm", (40.0, 55.0, 45.0))[2]) / (2 * np.pi)
            mesh = _necklace_pendant_mesh(anchor_xyz, chain_radius_cm=chain_r,
                                             pendant_size_cm=1.4)
            out.append((f"jewelry_{entry.id}", mesh))
        elif form == "earring_drop":
            length = float(entry.local_params_schema.get(
                "length_cm", (1.5, 4.0, 2.5))[2])
            mesh = _earring_drop_mesh(anchor_xyz, length_cm=length)
            out.append((f"jewelry_{entry.id}_R", mesh))
            # Mirror to the other earlobe by negating X
            mirror = _earring_drop_mesh(
                np.array([-anchor_xyz[0], anchor_xyz[1], anchor_xyz[2]]),
                length_cm=length)
            out.append((f"jewelry_{entry.id}_L", mirror))
        elif form == "earring_stud":
            size = float(entry.local_params_schema.get(
                "size_cm", (0.4, 1.0, 0.6))[2])
            out.append((f"jewelry_{entry.id}_R",
                          _earring_stud_mesh(anchor_xyz, size_cm=size)))
            out.append((f"jewelry_{entry.id}_L",
                          _earring_stud_mesh(np.array([-anchor_xyz[0], anchor_xyz[1], anchor_xyz[2]]),
                                              size_cm=size)))
        elif form == "body_chain_waist":
            length = float(entry.local_params_schema.get(
                "length_cm", (60.0, 90.0, 75.0))[2])
            mesh = _body_chain_waist_mesh(anchor_xyz,
                                            waist_circumference_cm=length)
            out.append((f"jewelry_{entry.id}", mesh))
        elif form == "body_chain_belly":
            mesh = _body_chain_belly_mesh(anchor_xyz)
            out.append((f"jewelry_{entry.id}", mesh))
        elif form in ("anklet_chain", "anklet_charm"):
            side = +1 if anchor_xyz[0] > 0 else -1
            mesh = _anklet_mesh(anchor_xyz, diameter_cm=diam, tube_r=0.15)
            out.append((f"jewelry_{entry.id}_R", mesh))
            mirror = _anklet_mesh(
                np.array([-anchor_xyz[0], anchor_xyz[1], anchor_xyz[2]]),
                diameter_cm=diam, tube_r=0.15)
            out.append((f"jewelry_{entry.id}_L", mirror))
    return out
