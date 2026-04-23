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
        near = body_vertices[(body_vertices[:, 1] > y_level - y_halfband) &
                              (body_vertices[:, 1] < y_level + y_halfband)]

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

    # 5) Halter neck strap — a curved tube from the inner-top of each cup
    #    up over the BACK of the neck. Controlled by g.top_neck_strap.
    if g.top_neck_strap > 0.15:
        strap_r = 0.15 + 0.25 * g.top_neck_strap     # ~1.5 to 4 mm radius
        cup_top_v = g.top_center_v + g.top_half_v
        u_inner_halter = 0.03 + 0.05 * g.top_inner_u
        y_start = v_to_y(cup_top_v)
        anchor_R = _body_point_at(V, u_inner_halter, y_start)
        anchor_L = _body_point_at(V, -u_inner_halter, y_start)
        # go up to the neck area and around to the back
        y_neck_top = y_neck + 12.0
        # midpoint behind the neck (z < 0)
        neck_mid = np.array([0.0, y_neck_top, -8.0])
        # simple 3-segment polyline per side: anchor -> forward-upper point
        # -> neck back midpoint, for each cup. They meet at neck_mid.
        up_R = anchor_R + np.array([0.0, 6.0, 0.0]) + np.array([anchor_R[0] * 0.1, 0, 0])
        up_L = anchor_L + np.array([0.0, 6.0, 0.0]) + np.array([anchor_L[0] * 0.1, 0, 0])
        halter_R = _arc_tube(np.array([anchor_R, up_R, neck_mid]), radius=strap_r)
        halter_L = _arc_tube(np.array([anchor_L, up_L, neck_mid]), radius=strap_r)
        straps.append(("halter_R", halter_R))
        straps.append(("halter_L", halter_L))

    # 6) Shoulder straps — two tubes from outer-top of each cup up to the
    #    shoulder (where they'd meet the back band in reality). Controlled
    #    by g.top_shoulder_strap.
    if g.top_shoulder_strap > 0.15:
        strap_r = 0.15 + 0.22 * g.top_shoulder_strap
        cup_top_v = g.top_center_v + g.top_half_v
        u_outer = g.top_inner_u + 2 * g.top_half_u
        y_start = v_to_y(cup_top_v)
        y_shoulder = y_neck + 8.0                    # just below shoulder cap
        for u_s, name in [(u_outer, "shoulder_R"), (-u_outer, "shoulder_L")]:
            anchor = _body_point_at(V, u_s, y_start)
            # shoulder end: slightly outward of anchor, up at shoulder height,
            # and on the TOP of the shoulder (y slightly forward in z)
            shoulder_end = _body_point_at(V, u_s * 0.6, y_shoulder)
            strap = _arc_tube(np.array([anchor, shoulder_end]), radius=strap_r)
            straps.append((name, strap))

    return straps


def build_fabric_shell(body_mesh: o3d.geometry.TriangleMesh, body_uvs: np.ndarray,
                       polys_uv: list[list[tuple[float, float]]],
                       offset: float = 0.3,
                       max_torso_radius: float = 20.0,
                       ) -> o3d.geometry.TriangleMesh:
    """Build a thin fabric shell from the body's triangles that fall inside
    any Genome UV polygon. Each such triangle gets offset outward along its
    vertex normals by `offset` (cm). Carries the body's triangle-UV layout
    so it can reuse the bikini texture.

    Triangles on the T-pose arms are excluded by a torso-radius filter —
    arm and torso side vertices share the same cylindrical u so without
    this filter a wide bandeau's shell extends onto the forearms.
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

    # Also require the triangle's centroid to be on the torso, not on an
    # arm. On this T-pose mesh torso stays under r_xz ~18 cm; arms run out
    # to ~45 cm at identical Y and cylindrical u, so without this filter a
    # bandeau's shell would paint onto the forearms.
    tri_xz = V[T][:, :, [0, 2]].mean(axis=1)
    tri_r = np.sqrt(tri_xz[:, 0] ** 2 + tri_xz[:, 1] ** 2)
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


# Cache once — same weave for every genome.
_FABRIC_NORMAL_CACHE = None
_WEAVE_SHADE_CACHE = None

def _get_fabric_normal() -> np.ndarray:
    global _FABRIC_NORMAL_CACHE
    if _FABRIC_NORMAL_CACHE is None:
        _FABRIC_NORMAL_CACHE = _fabric_normal_map()
    return _FABRIC_NORMAL_CACHE

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
            apply_wrinkles(shell, amplitude=0.06)

            # bake the weave shade into the albedo so the thread pattern
            # shows even if the renderer ignores the normal map
            shaded_tex = _apply_weave_shade_to_texture(texture_pil)
            shell_tex_np = np.array(shaded_tex.convert("RGB"))
            shell_mat = o3d.visualization.rendering.MaterialRecord()
            shell_mat.shader = "defaultLit"
            shell_mat.albedo_img = o3d.geometry.Image(shell_tex_np)
            try:
                shell_mat.normal_img = o3d.geometry.Image(_get_fabric_normal())
            except AttributeError:
                pass
            shell_mat.base_roughness = 0.85
            shell_mat.base_metallic = 0.0
            scene.add_geometry("fabric_shell", shell, shell_mat)

            # edge binding — small raised rim around the shell border
            binding = build_binding_mesh(shell, offset=0.05, thickness=0.15)
            if len(binding.vertices) > 0:
                from verify_ga_uv import _color as _color_fn
                r, g, b = _color_fn(genome) if genome is not None else (0.3, 0.3, 0.3)
                # darker, slightly saturated version of the fabric color
                bind_mat = o3d.visualization.rendering.MaterialRecord()
                bind_mat.shader = "defaultLit"
                bind_mat.base_color = (r * 0.55, g * 0.55, b * 0.55, 1.0)
                bind_mat.base_roughness = 0.6
                bind_mat.base_metallic = 0.0
                scene.add_geometry("fabric_binding", binding, bind_mat)

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
