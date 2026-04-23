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


# --------------------------------------------------------------------------
# Texture rasterization — Genome -> PIL.Image
# --------------------------------------------------------------------------

def _uv_to_px(poly_uv: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Map (u in [-1,1], v in [0,1]) to PIL pixel coords (0..W, 0..H).

    v=0 (hip/groin) is at the bottom of the image so the vertical layout
    reads naturally from bottom to top like a world map.
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


def _draw_pattern_into(layer: Image.Image, poly_px, pattern: str):
    """Draw a semi-transparent white pattern across the polygon's bbox.
    Caller composites the layer against the polygon mask afterwards."""
    draw = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = _poly_bbox_px(poly_px)
    overlay = (255, 255, 255, 140)  # 55% alpha

    if pattern == "stripe":
        n = 10
        stripe_h = max(1, (y1 - y0) // (n * 2))
        for i in range(n):
            cy = y0 + (i + 0.5) * (y1 - y0) / n
            draw.rectangle([x0, cy - stripe_h / 2, x1, cy + stripe_h / 2],
                           fill=overlay)
    elif pattern == "polka":
        rng = np.random.default_rng(0)
        r = max(3, (x1 - x0) // 40)
        for _ in range(40):
            cx = rng.uniform(x0, x1)
            cy = rng.uniform(y0, y1)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=overlay)
    elif pattern == "checker":
        n = 10
        dx = max(2, (x1 - x0) // n)
        dy = max(2, (y1 - y0) // n)
        for i in range(n):
            for j in range(n):
                if (i + j) % 2 == 0:
                    draw.rectangle(
                        [x0 + i * dx, y0 + j * dy,
                         x0 + (i + 1) * dx, y0 + (j + 1) * dy],
                        fill=overlay,
                    )


def genome_to_texture(g: Genome) -> Image.Image:
    """Rasterize a Genome's UV polygons into a texture PNG (1024x512 RGBA)."""
    img = Image.new("RGBA", (TEX_W, TEX_H), SKIN_RGB + (255,))
    draw = ImageDraw.Draw(img, "RGBA")

    r, gr, b = _color(g)
    color_rgba = (int(r * 255), int(gr * 255), int(b * 255), 255)

    for poly_uv in genome_polygons(g):
        poly_px = _uv_to_px(poly_uv)
        if len(set(poly_px)) < 3:
            continue
        draw.polygon(poly_px, fill=color_rgba, outline=(35, 35, 35, 255))
        if g.pattern != "solid":
            mask = Image.new("L", (TEX_W, TEX_H), 0)
            ImageDraw.Draw(mask).polygon(poly_px, fill=255)
            ovl = Image.new("RGBA", (TEX_W, TEX_H), (0, 0, 0, 0))
            _draw_pattern_into(ovl, poly_px, g.pattern)
            img = Image.composite(ovl, img, mask).convert("RGBA")
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
    mesh.compute_vertex_normals()
    return mesh


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
# Offscreen rendering
# --------------------------------------------------------------------------

def render_mesh(renderer, mesh: o3d.geometry.TriangleMesh,
                texture_pil: Image.Image) -> np.ndarray:
    """Apply the texture and render a single frame. Returns HxWx3 uint8."""
    tex_np = np.array(texture_pil.convert("RGB"))
    o3d_tex = o3d.geometry.Image(tex_np)

    mat = o3d.visualization.rendering.MaterialRecord()
    mat.shader = "defaultLit"
    mat.albedo_img = o3d_tex
    mat.base_roughness = 0.7
    mat.base_metallic = 0.0

    scene = renderer.scene
    scene.clear_geometry()
    scene.add_geometry("body", mesh, mat)
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
        img = render_mesh(renderer, mesh, tex)
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
        ax.set_title(
            f"{label}\npat={g.pattern} inner_u={g.top_inner_u:.2f} "
            f"back={g.top_back_coverage:.2f}\nrise={g.bot_front_top_v:.2f}",
            fontsize=8,
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
