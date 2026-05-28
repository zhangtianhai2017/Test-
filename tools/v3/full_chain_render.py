"""
v3 → full v2 chain rendering. The proper renderer that produces REAL
fabric (not just tubes).

Pipeline (calls v2's existing chain unchanged):

    tokens (list[Panel|Stroke])
        ↓ tokens_to_garment
    Garment object
        ↓ validate_garment           ← H1-H4 hard constraints
    Garment (possibly with dropped pieces)
        ↓ .flatten_polygons()
    list[list[(u,v)]] in v2 Genome UV space
        ↓ build_fabric_shell(body, body_uvs, polys)
    fabric shell mesh on body
        ↓ polish_shell               ← smooth, snap to boundary
    polished shell mesh
        ↓ apply_wrinkles             ← visual softness
    wrinkled shell mesh
        ↓ build_binding_mesh         ← fabric edge binding
    binding mesh
        + stroke meshes (via _arc_tube)
        ↓ composite + Open3D OffscreenRenderer
    PNG

This is THE rendering pipeline v3 should always use going forward.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import open3d as o3d

from render3d_uv import (
    load_body_mesh, cylindrical_uvs, torso_anchors,
    build_fabric_shell, build_binding_mesh, apply_wrinkles,
)
from garment_polish import polish_shell  # may live in a different file
# fallback import path
try:
    from garment_polish import polish_shell
except ImportError:
    from render3d_uv import polish_shell

from garment_state import validate_garment

from v3.stroke_schema import Panel, Stroke
from v3.tokens_to_garment import tokens_to_garment
from v3.stroke_renderer import design_to_meshes  # for stroke tubes
try:
    from v3.palette import rgb_array as _palette_rgb_array
    PALETTE_RGB = _palette_rgb_array()
except ImportError:
    PALETTE_RGB = None


# ─── shared, persistent renderer ──────────────────────────────────────

# The OffscreenRenderer is held alive at module scope so we can render
# many designs in one process without each crashing on EGL init. Use
# scene.clear_geometry() between designs.
_RENDERER = None
_BODY_MESH = None
_BODY_UVS = None


def _get_renderer(W: int, H: int):
    global _RENDERER
    if _RENDERER is None:
        R = o3d.visualization.rendering.OffscreenRenderer(W, H)
        R.scene.set_background([0.92, 0.92, 0.94, 1.0])
        R.scene.scene.set_sun_light(
            direction=[-0.4, -0.6, -0.7],
            color=[1.0, 1.0, 1.0], intensity=80_000)
        R.scene.scene.enable_sun_light(True)
        R.scene.scene.enable_indirect_light(True)
        R.scene.scene.set_indirect_light_intensity(28_000)
        _RENDERER = R
    return _RENDERER


def _get_body():
    """Lazy load body mesh + cached UVs."""
    global _BODY_MESH, _BODY_UVS
    if _BODY_MESH is None:
        _BODY_MESH = load_body_mesh()
        _BODY_UVS = cylindrical_uvs(_BODY_MESH)
        _BODY_MESH.triangle_uvs = o3d.utility.Vector2dVector(_BODY_UVS)
    return _BODY_MESH, _BODY_UVS


# ─── color helpers ────────────────────────────────────────────────────

def _shell_color_from_tokens(tokens) -> tuple[float, float, float]:
    """Pick the dominant panel color (mean over panels)."""
    if PALETTE_RGB is None:
        return (0.85, 0.55, 0.45)
    panel_colors = [PALETTE_RGB[t.color_id] for t in tokens
                    if isinstance(t, Panel)]
    if not panel_colors:
        return (0.85, 0.55, 0.45)
    return tuple(np.mean(panel_colors, axis=0).tolist())


# ─── main render entrypoint ──────────────────────────────────────────

def render_design_3d(tokens,
                      out_path: str,
                      W: int = 480, H: int = 720,
                      view: str = "front",
                      skin_rgb: tuple[float, float, float] = (0.90, 0.78, 0.74),
                      fabric_offset_cm: float = 0.4,
                      smooth_iters: int = 2,
                      wrinkle_amp: float = 0.04,
                      binding_offset_cm: float = 0.15,
                      binding_thickness_cm: float = 0.5,
                      verbose: bool = False):
    """Render a list of Panel/Stroke tokens to a PNG via the full v2 chain."""

    body, body_uvs = _get_body()
    R = _get_renderer(W, H)

    # 1. tokens → Garment
    g = tokens_to_garment(tokens)
    g = validate_garment(g)
    polys = g.flatten_polygons()
    if verbose:
        print(f"  Garment: {len(g.pieces)} pieces → "
              f"{len(polys)} polygons (incl. mirrors), "
              f"archetype={g.archetype}")

    # 2. v2 fabric shell
    shell = build_fabric_shell(body, body_uvs, polys,
                                offset=fabric_offset_cm)
    if verbose:
        print(f"  fabric_shell: {len(shell.vertices)} verts, "
              f"{len(shell.triangles)} tris")

    # 3. polish (smoothing + boundary snap)
    if len(shell.vertices) > 0:
        try:
            yc, yn = torso_anchors(body)
            shell = polish_shell(
                shell, body, polys, yc, yn,
                smooth_iters=smooth_iters,
                boundary_snap=True,
                min_offset=0.15,
                cup_extra_offset=0.0,
                genome=None,
                cup_dome_depth_cm=0.0,
            )
        except TypeError:
            # signature mismatch; fall back to minimal call
            try:
                shell = polish_shell(shell, body, polys, yc, yn,
                                       smooth_iters=smooth_iters)
            except Exception as e:
                if verbose:
                    print(f"  polish_shell skipped: {e}")
        except Exception as e:
            if verbose:
                print(f"  polish_shell skipped: {e}")

    # 4. wrinkles
    if len(shell.vertices) > 0 and wrinkle_amp > 0:
        try:
            apply_wrinkles(shell, amplitude=wrinkle_amp)
        except Exception as e:
            if verbose:
                print(f"  apply_wrinkles skipped: {e}")

    # 5. binding mesh (sewn fabric edges)
    binding = o3d.geometry.TriangleMesh()
    if len(shell.vertices) > 0:
        try:
            binding = build_binding_mesh(
                shell, offset=binding_offset_cm,
                thickness=binding_thickness_cm)
        except Exception as e:
            if verbose:
                print(f"  binding skipped: {e}")

    # 6. shell + binding color from dominant panel
    shell_rgb = _shell_color_from_tokens(tokens)
    if len(shell.vertices) > 0:
        cs = np.tile(shell_rgb, (len(shell.vertices), 1))
        shell.vertex_colors = o3d.utility.Vector3dVector(cs)
        shell.compute_vertex_normals()
    if len(binding.vertices) > 0:
        # binding slightly darker
        bc = tuple(c * 0.7 for c in shell_rgb)
        cb = np.tile(bc, (len(binding.vertices), 1))
        binding.vertex_colors = o3d.utility.Vector3dVector(cb)
        binding.compute_vertex_normals()

    # 7. strokes (straps/harness) — keep v3 arc_tube path
    stroke_meshes = design_to_meshes(
        [t for t in tokens if isinstance(t, Stroke)], body)

    # 8. assemble scene
    R.scene.clear_geometry()
    mat_body = o3d.visualization.rendering.MaterialRecord()
    mat_body.base_color = list(skin_rgb) + [1.0]
    mat_body.shader = "defaultLit"
    R.scene.add_geometry("body", body, mat_body)

    mat_fabric = o3d.visualization.rendering.MaterialRecord()
    mat_fabric.base_color = [1.0, 1.0, 1.0, 1.0]
    mat_fabric.shader = "defaultLit"
    if len(shell.vertices) > 0:
        R.scene.add_geometry("shell", shell, mat_fabric)
    if len(binding.vertices) > 0:
        R.scene.add_geometry("binding", binding, mat_fabric)
    for i, sm in enumerate(stroke_meshes):
        R.scene.add_geometry(f"stroke_{i}", sm, mat_fabric)

    # 9. camera
    V = np.asarray(body.vertices)
    y_lo, y_hi = float(np.percentile(V[:, 1], 2)), float(np.percentile(V[:, 1], 98))
    body_h = y_hi - y_lo
    target_y = y_lo + 0.55 * body_h
    center = [0.0, target_y, 0.0]
    az = {"front": 0, "three_quarter": 45, "side": 90, "back": 180}.get(view, 0)
    fov = 60.0
    radius = body_h * 0.55 / math.tan(math.radians(fov / 2.0))
    az_r = math.radians(az)
    eye = [center[0] + math.sin(az_r) * radius,
           center[1],
           center[2] + math.cos(az_r) * radius]
    R.setup_camera(fov, center, eye, [0.0, 1.0, 0.0])

    img = R.render_to_image()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    o3d.io.write_image(out_path, img, 9)
    return out_path


# ─── smoke ────────────────────────────────────────────────────────────

def _smoke():
    """Render a hand-crafted bikini via the full v2 chain."""
    from v3.stroke_schema import Panel, Stroke, Anchor

    print("─── full_chain_render smoke ───")

    tokens = [
        # Left cup
        Panel(
            boundary_uv=[(0.32, 0.78), (0.48, 0.78), (0.50, 0.68),
                          (0.40, 0.65), (0.30, 0.68), (0.32, 0.75)],
            anchors=[Anchor.SHOULDER_L, Anchor.STERNUM, Anchor.UNDERBUST],
            color_id=4, fabric_id="F_ECONYL_PLAIN_LIGHT",
        ),
        # Bottom front (spans centerline)
        Panel(
            boundary_uv=[(0.30, 0.50), (0.70, 0.50), (0.65, 0.42),
                          (0.55, 0.38), (0.45, 0.38), (0.35, 0.42)],
            anchors=[Anchor.HIP_L, Anchor.HIP_R],
            color_id=4, fabric_id="F_ECONYL_PLAIN_LIGHT",
        ),
        # Shoulder straps
        Stroke(start_anchor=Anchor.SHOULDER_L, end_anchor=Anchor.UNDERBUST,
                width_profile=(1.5, 1.5, 1.5), color_id=4),
        Stroke(start_anchor=Anchor.SHOULDER_R, end_anchor=Anchor.UNDERBUST,
                width_profile=(1.5, 1.5, 1.5), color_id=4, is_end=True),
    ]
    out = "tools/output/2026-05-28/p28_full_chain/test_bikini_navy.png"
    render_design_3d(tokens, out, verbose=True)
    print(f"  ✓ rendered ({os.path.getsize(out):,} bytes) → {out}")


if __name__ == "__main__":
    _smoke()
