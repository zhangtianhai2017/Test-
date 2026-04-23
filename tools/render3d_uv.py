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

    Filters out limb vertices (T-pose arms reach x=+-45 on this NPC) by
    only keeping vertices within `max_torso_radius` of the body's vertical
    axis in XZ.
    """
    near = body_vertices[(body_vertices[:, 1] > y_level - y_halfband) &
                          (body_vertices[:, 1] < y_level + y_halfband)]
    if len(near) > 0:
        r = np.sqrt(near[:, 0] ** 2 + near[:, 2] ** 2)
        near = near[r < max_torso_radius]
    if len(near) < n_samples // 4:
        # Not enough torso vertices in this band: fall back to anything in
        # the y window so we still get a ring (will be approximate).
        near = body_vertices[(body_vertices[:, 1] > y_level - y_halfband) &
                              (body_vertices[:, 1] < y_level + y_halfband)]

    theta = np.arctan2(near[:, 0], near[:, 2])
    targets = np.linspace(-np.pi, np.pi, n_samples, endpoint=False)
    ring = []
    for t in targets:
        d = np.abs(np.mod(theta - t + np.pi, 2 * np.pi) - np.pi)
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
                    u_side: float, band_offset: float = 0.6
                    ) -> o3d.geometry.TriangleMesh:
    """Slim vertical ribbon at the side of the hip that bridges front and
    back waist-lines (the side-tie knot area of a tie-side bikini)."""
    # find a body vertex near (u_side, y_center)
    theta = u_side * np.pi
    y_center = (y_lo_world + y_hi_world) / 2
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
    half_w = 0.6
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


def build_strap_meshes(body_mesh: o3d.geometry.TriangleMesh, g,
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
    #    edge (the arc that does NOT pass through the front).
    cup_outer_u = g.top_inner_u + 2 * g.top_half_u
    band_y = v_to_y(g.top_center_v)
    band_h = max(1.2, 1.5 + 2.0 * g.top_back_coverage)   # thin: 1.5-3.5 cm
    ring = _body_ring(V, band_y, y_halfband=3.0, n_samples=96)
    back_band = _build_band_mesh(ring, band_h, offset=0.5,
                                  u_from=cup_outer_u, u_to=-cup_outer_u)
    straps.append(("top_back_band", back_band))

    # 2) Bottom waist string — thin ring at the average of front/back tops.
    #    Asymmetric waists (high-front + thong-back) rely on the side ties
    #    to bridge the height difference; keep the band itself uniformly
    #    thin so it reads as a string, not a wide belt.
    y_front = v_to_y(g.bot_front_top_v)
    y_back  = v_to_y(g.bot_back_top_v)
    band_y2 = (y_front + y_back) / 2
    band_h2 = 1.5
    ring2 = _body_ring(V, band_y2, y_halfband=3.0, n_samples=96)
    waist_band = _build_band_mesh(ring2, band_h2, offset=0.5)
    straps.append(("waist_band", waist_band))

    # 3) Side ties — slim vertical ribbon on each hip spanning the v-range
    #    between front and back waist-lines (visible bridge for tie-side
    #    bikinis).
    y_side_lo = min(y_front, y_back) - 0.8
    y_side_hi = max(y_front, y_back) + 0.8
    for u_side, name in [(0.5, "side_tie_R"), (-0.5, "side_tie_L")]:
        tie = _build_tie_mesh(V, y_side_lo, y_side_hi, u_side)
        straps.append((name, tie))

    return straps


def build_fabric_shell(body_mesh: o3d.geometry.TriangleMesh, body_uvs: np.ndarray,
                       polys_uv: list[list[tuple[float, float]]],
                       offset: float = 0.3) -> o3d.geometry.TriangleMesh:
    """Build a thin fabric shell from the body's triangles that fall inside
    any Genome UV polygon.

    Each such triangle gets offset outward along its vertex normals by
    `offset` (cm) so the shell reads as a physical layer of fabric sitting
    above the skin rather than paint on the skin. The shell mesh carries
    the same triangle-UV layout as the body, so it can reuse the bikini
    texture directly.

    Args:
        body_mesh: original body TriangleMesh (with vertex_normals).
        body_uvs:  (3*NT, 2) cylindrical UVs already in [0, 1] range, same
                   order as body.triangle_uvs.
        polys_uv:  list of closed polygons in Genome UV coords (u in [-1, 1],
                   v in [0, 1]).
        offset:    outward displacement in the same units as the mesh (cm).
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

    # A triangle is "fabric" if ALL THREE of its per-vertex UVs are inside
    # at least one polygon. We union the results across polygons.
    inside_any = np.zeros(len(pts_g), dtype=bool)
    for poly in polys_uv:
        if len(poly) < 3:
            continue
        path = Path(np.asarray(poly, dtype=np.float32))
        inside_any |= path.contains_points(pts_g)

    tri_inside = inside_any.reshape(-1, 3).all(axis=1)
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
    shell.compute_vertex_normals()

    # Per-triangle UVs for the kept triangles, in body-texture coords.
    sel_flat = np.where(tri_inside.repeat(3))[0]
    shell_uvs = body_uvs[sel_flat]
    shell.triangle_uvs = o3d.utility.Vector2dVector(shell_uvs)
    return shell


# --------------------------------------------------------------------------

def _color_from_genome(g) -> tuple[float, float, float, float]:
    from verify_ga_uv import _color as vc
    r, gg, b = vc(g)
    return (r, gg, b, 1.0)


def _skin_only_texture() -> Image.Image:
    """Uniform skin-tone texture for the body layer, with no bikini polygons
    painted on. The bikini is drawn as a separate 3D shell on top."""
    return Image.new("RGB", (TEX_W, TEX_H), SKIN_RGB)


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
            shell_tex_np = np.array(texture_pil.convert("RGB"))
            shell_mat = o3d.visualization.rendering.MaterialRecord()
            shell_mat.shader = "defaultLit"
            shell_mat.albedo_img = o3d.geometry.Image(shell_tex_np)
            # matte fabric: a bit rougher than skin, no metallic
            shell_mat.base_roughness = 0.85
            shell_mat.base_metallic = 0.0
            scene.add_geometry("fabric_shell", shell, shell_mat)

    # ---- straps (closed-loop geometry) ----
    if genome is not None and y_crotch is not None and y_neck is not None:
        strap_mat = o3d.visualization.rendering.MaterialRecord()
        strap_mat.shader = "defaultLit"
        strap_mat.base_color = _color_from_genome(genome)
        strap_mat.base_roughness = 0.85
        strap_mat.base_metallic = 0.0
        for name, strap in build_strap_meshes(mesh, genome, y_crotch, y_neck):
            if len(strap.vertices) > 0:
                scene.add_geometry(f"strap_{name}", strap, strap_mat)

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
