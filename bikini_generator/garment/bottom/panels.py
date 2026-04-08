"""Bottom panel generators for bikini bottoms.

Front and back panels with various shapes and coverage levels.
All panels anchor at both hip (top) and crotch (bottom) edges.
"""

import numpy as np
from ..patch import GarmentPatch
from ...body.landmarks import get_landmarks
from ...config import BODY


def _body_surface_bottom(u: float, v: float, is_front: bool = True) -> np.ndarray:
    """Map (u,v) to a point on the lower body surface.

    u: vertical (0=hip, 1=crotch)
    v: horizontal (0=left, 1=right)

    Calibrated to real ZBrush body mesh landmarks.
    Front and back panels both extend fully to crotch_center at u=1
    so they connect seamlessly at the bottom.
    """
    lm = get_landmarks()
    crotch_center = lm["crotch_center"]

    if is_front:
        top_point = lm["hip_front"]
        # At u=1 both front and back converge to crotch_center
        bottom_point = crotch_center + np.array([0, 0, 0.008])  # slightly forward
    else:
        top_point = lm["hip_back"]
        bottom_point = crotch_center + np.array([0, 0, -0.008])  # slightly backward

    y_top = top_point[1]
    y_bottom = bottom_point[1]
    y = y_top + u * (y_bottom - y_top)

    hip_half_width = abs(lm["hip_left"][0]) * 0.35
    crotch_half_width = 0.03
    half_width = hip_half_width + u * (crotch_half_width - hip_half_width)

    x = (v - 0.5) * 2 * half_width

    if is_front:
        z_top = top_point[2]
        z_bottom = bottom_point[2]
        z_base = z_top + u * (z_bottom - z_top)
        belly = 0.006 * np.sin(u * np.pi) * (1 - abs(v - 0.5) * 2)
        z = z_base + belly
    else:
        z_top = top_point[2]
        z_bottom = bottom_point[2]
        z_base = z_top + u * (z_bottom - z_top)
        butt_curve = -0.012 * np.sin(u * np.pi * 0.8) * (1 - abs(v - 0.5) * 1.5)
        z = z_base + butt_curve

    return np.array([x, y, z])


def _anchor_panel(patch: GarmentPatch, nv: int, nu: int, is_front: bool):
    """Add standard anchoring: top edge at hips + bottom edge at crotch."""
    lm = get_landmarks()

    # Top edge anchors (first row of vertices)
    top_left = 0
    top_right = nv - 1
    top_center = nv // 2

    # Bottom edge anchors (last row of vertices)
    bottom_left = (nu - 1) * nv
    bottom_right = nu * nv - 1
    bottom_center = (nu - 1) * nv + nv // 2

    crotch_c = lm["crotch_center"]

    if is_front:
        patch.anchor_vertex_ids = [top_left, top_right, top_center,
                                   bottom_left, bottom_right, bottom_center]
        patch.anchor_body_positions = [
            lm["hip_left"] + np.array([0.06, 0, 0.04]),
            lm["hip_right"] + np.array([-0.06, 0, 0.04]),
            lm["hip_front"],
            crotch_c + np.array([-0.02, 0, 0.008]),
            crotch_c + np.array([0.02, 0, 0.008]),
            crotch_c + np.array([0, 0, 0.008]),
        ]
    else:
        patch.anchor_vertex_ids = [top_left, top_right, top_center,
                                   bottom_left, bottom_right, bottom_center]
        patch.anchor_body_positions = [
            lm["hip_left"] + np.array([0.06, 0, -0.04]),
            lm["hip_right"] + np.array([-0.06, 0, -0.04]),
            lm["hip_back"],
            crotch_c + np.array([-0.02, 0, -0.008]),
            crotch_c + np.array([0.02, 0, -0.008]),
            crotch_c + np.array([0, 0, -0.008]),
        ]


# --- Front panels ---

def classic_front(coverage: float = 0.7, rise: float = 0.5,
                  nu: int = 20, nv: int = 20) -> GarmentPatch:
    """Classic triangle front panel."""
    def func(u, v):
        width_factor = 1.0 - u * (1.0 - 0.2) * (1 - coverage * 0.3)
        v_adj = 0.5 + (v - 0.5) * width_factor * coverage
        u_adj = u  # full range hip to crotch
        return _body_surface_bottom(u_adj, v_adj, is_front=True)

    patch = GarmentPatch.from_parametric("bottom_front_classic", func, (0, 1), (0, 1), nu, nv)
    _anchor_panel(patch, nv, nu, is_front=True)
    patch.material_name = "bottom"
    return patch


def v_front(coverage: float = 0.5, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """V-shaped front panel — lower, more daring cut."""
    def func(u, v):
        v_center_dist = abs(v - 0.5) * 2
        u_offset = 0.2 * (1 - v_center_dist)
        u_adj = u_offset + u * (1 - u_offset)  # full range to crotch
        width_factor = coverage * (0.4 + 0.6 * (1 - u * 0.5))
        v_adj = 0.5 + (v - 0.5) * width_factor
        return _body_surface_bottom(u_adj, v_adj, is_front=True)

    patch = GarmentPatch.from_parametric("bottom_front_v", func, (0, 1), (0, 1), nu, nv)
    _anchor_panel(patch, nv, nu, is_front=True)
    patch.material_name = "bottom"
    return patch


def high_cut_front(coverage: float = 0.6, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """High-cut front — leg openings cut high on the hip."""
    def func(u, v):
        side_cut = (abs(v - 0.5) * 2) ** 1.5
        u_adj = u * (1.0 - side_cut * 0.15)  # full range, sides cut higher
        width_factor = coverage * (1 - u * 0.4)
        v_adj = 0.5 + (v - 0.5) * width_factor
        return _body_surface_bottom(u_adj, v_adj, is_front=True)

    patch = GarmentPatch.from_parametric("bottom_front_highcut", func, (0, 1), (0, 1), nu, nv)
    _anchor_panel(patch, nv, nu, is_front=True)
    patch.material_name = "bottom"
    return patch


def ruched_front(coverage: float = 0.6, nu: int = 24, nv: int = 24) -> GarmentPatch:
    """Ruched/gathered front panel with fabric bunching."""
    def func(u, v):
        v_adj = 0.5 + (v - 0.5) * coverage
        pos = _body_surface_bottom(u, v_adj, is_front=True)  # full range
        ruch = 0.004 * np.sin(u * np.pi * 8) * np.sin(v * np.pi * 3)
        pos[2] += ruch
        return pos

    patch = GarmentPatch.from_parametric("bottom_front_ruched", func, (0, 1), (0, 1), nu, nv)
    _anchor_panel(patch, nv, nu, is_front=True)
    patch.material_name = "bottom"
    return patch


def skirt_front(coverage: float = 0.8, nu: int = 24, nv: int = 32) -> GarmentPatch:
    """Mini skirt overlay — wraps around front with flare."""
    lm = get_landmarks()

    def func(u, v):
        flare = 1.0 + u * 0.4
        v_adj = 0.5 + (v - 0.5) * coverage * flare
        u_adj = u  # full range
        pos = _body_surface_bottom(u_adj, v_adj, is_front=True)
        pos[2] += u * 0.015
        return pos

    patch = GarmentPatch.from_parametric("bottom_front_skirt", func, (0, 1), (0, 1), nu, nv)
    # Skirt: anchor entire top edge (it's a waistband)
    top_ids = list(range(nv))
    bottom_center = (nu - 1) * nv + nv // 2
    patch.anchor_vertex_ids = top_ids + [bottom_center]
    patch.anchor_body_positions = []
    top_y = lm["hip_front"][1]
    for i in range(nv):
        x = (i / (nv - 1) - 0.5) * 0.3
        patch.anchor_body_positions.append(np.array([x, top_y, lm["hip_front"][2]]))
    patch.anchor_body_positions.append(lm["crotch_front"])
    patch.material_name = "bottom"
    return patch


# --- Back panels ---

def classic_back(coverage: float = 0.6, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """Classic back panel — moderate coverage."""
    def func(u, v):
        width_factor = coverage * (1.0 - u * 0.3)
        v_adj = 0.5 + (v - 0.5) * width_factor
        return _body_surface_bottom(u, v_adj, is_front=False)

    patch = GarmentPatch.from_parametric("bottom_back_classic", func, (0, 1), (0, 1), nu, nv)
    _anchor_panel(patch, nv, nu, is_front=False)
    patch.material_name = "bottom"
    return patch


def thong_back(nu: int = 16, nv: int = 10) -> GarmentPatch:
    """Thong back — minimal coverage."""
    def func(u, v):
        width = 0.08 * (1 - u * 0.7)
        v_adj = 0.5 + (v - 0.5) * width / 0.16
        return _body_surface_bottom(u, v_adj, is_front=False)

    patch = GarmentPatch.from_parametric("bottom_back_thong", func, (0, 1), (0, 1), nu, nv)
    _anchor_panel(patch, nv, nu, is_front=False)
    patch.material_name = "bottom"
    return patch


def brazilian_back(coverage: float = 0.4, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """Brazilian back — moderate-to-low coverage."""
    def func(u, v):
        width_factor = coverage * (1.0 - u * 0.5)
        v_adj = 0.5 + (v - 0.5) * width_factor
        pos = _body_surface_bottom(u, v_adj, is_front=False)
        if abs(v - 0.5) < 0.2:
            pos[2] -= 0.003 * np.sin(u * np.pi * 4)
        return pos

    patch = GarmentPatch.from_parametric("bottom_back_brazilian", func, (0, 1), (0, 1), nu, nv)
    _anchor_panel(patch, nv, nu, is_front=False)
    patch.material_name = "bottom"
    return patch


def full_back(coverage: float = 0.9, nu: int = 20, nv: int = 24) -> GarmentPatch:
    """Full coverage back panel."""
    def func(u, v):
        v_adj = 0.5 + (v - 0.5) * coverage
        return _body_surface_bottom(u, v_adj, is_front=False)

    patch = GarmentPatch.from_parametric("bottom_back_full", func, (0, 1), (0, 1), nu, nv)
    _anchor_panel(patch, nv, nu, is_front=False)
    patch.material_name = "bottom"
    return patch


FRONT_STYLES = {
    "classic": classic_front,
    "v_shape": v_front,
    "high_cut": high_cut_front,
    "ruched": ruched_front,
    "skirt": skirt_front,
}

BACK_STYLES = {
    "classic": classic_back,
    "thong": thong_back,
    "brazilian": brazilian_back,
    "full": full_back,
}
