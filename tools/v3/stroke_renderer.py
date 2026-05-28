"""
v3 Stroke Renderer — turn a list[Stroke] + body mesh into a PNG.

Strategy:
  For each Stroke:
    1. Sample its Bezier path at N UV points
    2. Map each (u, v) → 3D world point on body via _body_point_at()
    3. Build a _arc_tube along the 3D polyline with width / 2 radius
    4. Color with palette[stroke.color_id]
  Composite all stroke meshes + body mesh
  Render single front view with OffscreenRenderer

This bypasses the full v2 render pipeline (build_fabric_shell /
polish_shell / build_strap_meshes) — those are coupled to the
genome / Garment representation. v3 strokes are body-anchored ribbons,
which is a simpler geometry that the same primitive helpers can serve.

Limitations of this v0:
  - tension is honored only as a normal-offset multiplier (no real drape physics)
  - width is set as tube radius (mid value); start/end taper not implemented
  - material / decoration mixes ignored (color only)
  - lighting / material settings are the v2 defaults

For Phase A1+A2 these are fine; for Phase A3 RL training they are
sufficient — the judge sees front-view images.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

# guarantee tools/ on path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Open3D may be missing in some test envs; import lazily so the schema
# files remain importable in lighter contexts.
def _lazy_o3d():
    import open3d as o3d  # noqa: E402
    return o3d


from v3.stroke_schema import Anchor, Stroke, DEFAULT_ANCHOR_UV, MAX_STROKES  # noqa: E402


# ─── palette ──────────────────────────────────────────────────────────

def default_palette(n: int = 256) -> np.ndarray:
    """A 256-color HSL grid covering the wheel.

    Layout:
      - first 16 colors: hand-picked anchor colors (CSS-named approximations)
      - rest: CIELAB-uniform sampling stand-in (HSL grid as proxy)
    """
    anchor = np.array([
        [0.95, 0.92, 0.88],   # ivory
        [0.10, 0.10, 0.12],   # black
        [0.85, 0.85, 0.85],   # silver
        [0.10, 0.20, 0.55],   # navy
        [0.95, 0.25, 0.45],   # hot pink
        [0.98, 0.50, 0.10],   # orange
        [0.10, 0.65, 0.40],   # emerald
        [0.50, 0.10, 0.20],   # burgundy
        [0.95, 0.95, 0.20],   # neon yellow
        [0.80, 0.60, 0.55],   # nude
        [0.75, 0.50, 0.55],   # dusty rose
        [0.60, 0.70, 0.55],   # sage
        [0.55, 0.40, 0.55],   # mauve
        [0.95, 0.55, 0.40],   # coral
        [0.50, 0.85, 0.75],   # mint
        [0.65, 0.55, 0.45],   # taupe
    ], dtype=np.float32)
    out = np.zeros((n, 3), dtype=np.float32)
    out[:len(anchor)] = anchor
    # rest: HSL grid covering hue × saturation × lightness
    grid_n = n - len(anchor)
    if grid_n > 0:
        # try to factor into roughly cubic
        sn = max(2, int(round(grid_n ** (1 / 3))))
        ln = max(2, int(round(grid_n ** (1 / 3))))
        hn = max(2, int(math.ceil(grid_n / (sn * ln))))
        idx = len(anchor)
        for h in range(hn):
            for s in range(sn):
                for L in range(ln):
                    if idx >= n:
                        break
                    out[idx] = _hsl_to_rgb(h / hn, 0.4 + 0.6 * s / max(1, sn - 1),
                                            0.3 + 0.5 * L / max(1, ln - 1))
                    idx += 1
    return out


def _hsl_to_rgb(h: float, s: float, L: float) -> np.ndarray:
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h, L, s)
    return np.array([r, g, b], dtype=np.float32)


# Use the proper named palette from v3/palette.py if available, else fall
# back to the in-file HSL approximation.
try:
    from v3.palette import rgb_array as _palette_rgb_array
    PALETTE = _palette_rgb_array()
except ImportError:
    PALETTE = default_palette(256)


# ─── anchor resolution ────────────────────────────────────────────────

def resolve_anchor_uv_for_mesh(body_mesh) -> dict[Anchor, tuple[float, float]]:
    """Anchor UV positions tuned to the actual body mesh extents.

    For now we reuse DEFAULT_ANCHOR_UV (already calibrated near typical
    body proportions). Future: use anatomy.detect() to derive precise
    Y levels per anchor.
    """
    return dict(DEFAULT_ANCHOR_UV)


def uv_to_3d(body_vertices: np.ndarray, u: float, v: float,
              y_min: float, y_max: float) -> np.ndarray:
    """Map (u ∈ [0,1], v ∈ [0,1]) → 3D world point on body surface.

    u: anti-clockwise around body, 0 = back center, 0.5 = front center.
    v: 0 = ankles, 1 = top of head.
    """
    from render3d_uv import _body_point_at  # avoid circular at module load
    # convert our u ∈ [0,1] (front=0.5) into the project's u
    # (project's _body_point_at uses target = u * pi, so u=0 = back,
    #  u=1 = front from one side around)
    # Use a u remap: project's u=0.5 sits at front. Stroke schema
    # uses u=0.5 = front too. So we can pass it through directly.
    y_world = y_min + v * (y_max - y_min)
    return _body_point_at(body_vertices, u, y_world)


# ─── stroke → mesh ─────────────────────────────────────────────────────

def stroke_to_mesh(stroke: Stroke,
                    body_vertices: np.ndarray,
                    y_min: float, y_max: float,
                    anchor_uv: dict[Anchor, tuple[float, float]],
                    n_samples: int = 16,
                    surface_offset_cm: float = 0.4):
    """Build a tube mesh along the stroke's 3D path on the body."""
    from render3d_uv import _arc_tube
    o3d = _lazy_o3d()

    path_uv = stroke.sample_path(n_samples=n_samples, anchor_uv=anchor_uv)
    pts_3d = []
    for u, v in path_uv:
        p = uv_to_3d(body_vertices, u, v, y_min, y_max)
        # push slightly out along XZ radial direction for visibility
        r = math.hypot(p[0], p[2])
        if r > 1e-3:
            offset = surface_offset_cm * (1.0 - 0.6 * (1 - stroke.tension))
            p = p + np.array([p[0] / r * offset, 0.0, p[2] / r * offset])
        pts_3d.append(p)
    pts_3d = np.asarray(pts_3d, dtype=np.float64)

    # tube radius = mean width / 2 in cm, with a visibility floor.
    # Body mesh is ~170 cm tall, rendered at 720 px → ~4 px/cm.
    # A 3 cm-wide tube is ~12 px which is hard to see on a 480-wide image.
    # Boost radius 2x for legibility (matches v2's rendering convention).
    radius = max(0.6, 1.0 * float(np.mean(stroke.width_profile)))
    tube = _arc_tube(pts_3d, radius=radius, sides=8)
    if len(tube.vertices) == 0:
        return tube

    # color
    rgb = PALETTE[max(0, min(255, stroke.color_id))]
    colors = np.tile(rgb, (len(tube.vertices), 1))
    tube.vertex_colors = o3d.utility.Vector3dVector(colors)
    tube.compute_vertex_normals()
    return tube


def design_to_meshes(strokes: list[Stroke],
                      body_mesh,
                      anchor_uv: dict[Anchor, tuple[float, float]] = None
                      ) -> list:
    """Turn a list of strokes into a list of 3D meshes (one per stroke)."""
    if anchor_uv is None:
        anchor_uv = resolve_anchor_uv_for_mesh(body_mesh)
    V = np.asarray(body_mesh.vertices)
    y_min, y_max = np.percentile(V[:, 1], [2, 98])
    meshes = []
    for s in strokes:
        m = stroke_to_mesh(s, V, y_min, y_max, anchor_uv)
        if len(m.vertices) > 0:
            meshes.append(m)
    return meshes


# ─── render to PNG ────────────────────────────────────────────────────

def render_design_png(strokes: list[Stroke],
                       out_path: str,
                       body_mesh=None,
                       W: int = 480, H: int = 720,
                       view: str = "front",
                       skin_rgb: tuple[float, float, float] = (0.90, 0.78, 0.74)):
    """Render a design (list of strokes) to a PNG.

    view: "front" | "three_quarter" | "back"
    """
    o3d = _lazy_o3d()
    from render3d_uv import load_body_mesh

    if body_mesh is None:
        body_mesh = load_body_mesh()

    stroke_meshes = design_to_meshes(strokes, body_mesh)

    # set up offscreen renderer
    R = o3d.visualization.rendering.OffscreenRenderer(W, H)
    R.scene.set_background([0.92, 0.92, 0.94, 1.0])
    R.scene.scene.set_sun_light(
        direction=[-0.4, -0.6, -0.7],
        color=[1.0, 1.0, 1.0], intensity=80_000)
    R.scene.scene.enable_sun_light(True)
    R.scene.scene.enable_indirect_light(True)
    R.scene.scene.set_indirect_light_intensity(28_000)

    # body material — neutral skin
    mat_body = o3d.visualization.rendering.MaterialRecord()
    mat_body.base_color = list(skin_rgb) + [1.0]
    mat_body.shader = "defaultLit"

    # stroke material — vertex-colored
    mat_stroke = o3d.visualization.rendering.MaterialRecord()
    mat_stroke.base_color = [1.0, 1.0, 1.0, 1.0]
    mat_stroke.shader = "defaultLit"

    R.scene.add_geometry("body", body_mesh, mat_body)
    for i, m in enumerate(stroke_meshes):
        R.scene.add_geometry(f"stroke_{i}", m, mat_stroke)

    # camera framing
    V = np.asarray(body_mesh.vertices)
    y_lo, y_hi = float(np.percentile(V[:, 1], 2)), float(np.percentile(V[:, 1], 98))
    body_h = y_hi - y_lo
    target_y = y_lo + 0.55 * body_h
    center = [0.0, target_y, 0.0]
    az = {"front": 0, "three_quarter": 45, "side": 90, "back": 180}.get(view, 0)
    az_r = math.radians(az)
    el_r = 0.0
    fov = 60.0
    radius = body_h * 0.55 / math.tan(math.radians(fov / 2.0))
    eye = [center[0] + math.sin(az_r) * math.cos(el_r) * radius,
           center[1] + math.sin(el_r) * radius,
           center[2] + math.cos(az_r) * math.cos(el_r) * radius]
    R.setup_camera(fov, center, eye, [0.0, 1.0, 0.0])

    img = R.render_to_image()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    o3d.io.write_image(out_path, img, 9)
    return out_path


# ─── 2D UV sketch (GPU-free fallback for smoke) ───────────────────────

def render_uv_sketch(strokes: list[Stroke],
                      out_path: str,
                      W: int = 480, H: int = 720,
                      anchor_uv: dict = None,
                      title: str | None = None):
    """Fallback 2D renderer — draws strokes in body UV space.

    Useful when GPU/EGL is contested (vLLM holding most of A6000)
    and the Open3D OffscreenRenderer crashes. Information equivalent
    to the 3D render for smoke validation: shows stroke topology and
    color in the body's cylindrical UV layout.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    if anchor_uv is None:
        anchor_uv = DEFAULT_ANCHOR_UV

    fig, ax = plt.subplots(figsize=(W / 100, H / 100), dpi=100)

    # Body schematic — front view in UV (u ∈ [0.1, 0.9] is "front of body")
    body_color = (0.92, 0.85, 0.82)
    # head
    ax.add_patch(mpatches.Ellipse((0.5, 0.90), 0.14, 0.10, color=body_color))
    # torso
    ax.add_patch(mpatches.Rectangle((0.30, 0.42), 0.40, 0.42, color=body_color))
    # arms (small)
    ax.add_patch(mpatches.Rectangle((0.18, 0.55), 0.08, 0.28, color=body_color, alpha=0.6))
    ax.add_patch(mpatches.Rectangle((0.74, 0.55), 0.08, 0.28, color=body_color, alpha=0.6))
    # legs
    ax.add_patch(mpatches.Rectangle((0.32, 0.05), 0.15, 0.40, color=body_color, alpha=0.8))
    ax.add_patch(mpatches.Rectangle((0.53, 0.05), 0.15, 0.40, color=body_color, alpha=0.8))

    # Anchor dots (light)
    for a, (u, v) in anchor_uv.items():
        ax.scatter([u], [v], s=14, c='gray', alpha=0.4, marker='+')

    # Strokes: each as a colored polyline with thickness ~ width
    for i, s in enumerate(strokes):
        path = s.sample_path(n_samples=32, anchor_uv=anchor_uv)
        us = [p[0] for p in path]
        vs = [p[1] for p in path]
        c = PALETTE[max(0, min(255, s.color_id))]
        # width in cm → linewidth in pt; visible scale
        lw = max(1.0, float(np.mean(s.width_profile)) * 1.5)
        ax.plot(us, vs, color=tuple(c), linewidth=lw, alpha=0.92,
                 solid_capstyle='round')

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect('auto')
    ax.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(['back', 'side R', 'front', 'side L', 'back'], fontsize=7)
    ax.set_yticks([])
    if title:
        ax.set_title(title, fontsize=9)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    plt.savefig(out_path, bbox_inches='tight', dpi=100)
    plt.close(fig)
    return out_path


# ─── smoke ────────────────────────────────────────────────────────────

def _smoke():
    """Render the two hand-crafted reference designs to PNG."""
    print("─── stroke_renderer smoke ───")
    from v3.stroke_schema import (
        example_classical_bikini, example_avant_garde_harness,
    )
    from render3d_uv import load_body_mesh

    body = load_body_mesh()
    out_root = "/mnt/c/Users/Administrator/Test-/tools/output/2026-05-27/p17_renderer_smoke"

    for name, fn in [
        ("classical_bikini", example_classical_bikini),
        ("avant_garde_harness", example_avant_garde_harness),
    ]:
        strokes = fn()
        out = os.path.join(out_root, f"{name}.png")
        render_design_png(strokes, out, body_mesh=body)
        size = os.path.getsize(out)
        print(f"  ✓ {name}: {out}  ({size:,} bytes)")
    print(f"\nAll PNGs in {out_root}")


if __name__ == "__main__":
    _smoke()
