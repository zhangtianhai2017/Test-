"""Bottom panel generators for bikini bottoms.

Front and back panels with various shapes and coverage levels.
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
    """
    lm = get_landmarks()

    # Real landmark coordinates
    if is_front:
        top_point = lm["hip_front"]
        bottom_point = lm["crotch_front"]
    else:
        top_point = lm["hip_back"]
        bottom_point = lm["crotch_back"]

    y_top = top_point[1]
    y_bottom = bottom_point[1]
    y = y_top + u * (y_bottom - y_top)

    # Width: from real hip landmarks, narrows to crotch
    hip_half_width = abs(lm["hip_left"][0]) * 0.4  # don't use full hip width for panels
    crotch_half_width = 0.04
    half_width = hip_half_width + u * (crotch_half_width - hip_half_width)

    x = (v - 0.5) * 2 * half_width

    # Z depth from real landmarks
    if is_front:
        z_top = top_point[2]
        z_bottom = bottom_point[2]
        z_base = z_top + u * (z_bottom - z_top)
        belly = 0.008 * np.sin(u * np.pi) * (1 - abs(v - 0.5) * 2)
        z = z_base + belly
    else:
        z_top = top_point[2]
        z_bottom = bottom_point[2]
        z_base = z_top + u * (z_bottom - z_top)
        butt_curve = -0.015 * np.sin(u * np.pi * 0.8) * (1 - abs(v - 0.5) * 1.5)
        z = z_base + butt_curve

    return np.array([x, y, z])


def classic_front(coverage: float = 0.7, rise: float = 0.5,
                  nu: int = 20, nv: int = 20) -> GarmentPatch:
    """Classic triangle front panel."""
    lm = get_landmarks()

    def func(u, v):
        # Triangle: narrows toward bottom
        width_factor = 1.0 - u * (1.0 - 0.3) * (1 - coverage * 0.3)
        v_adj = 0.5 + (v - 0.5) * width_factor * coverage
        u_adj = u * (0.5 + rise * 0.5)
        return _body_surface_bottom(u_adj, v_adj, is_front=True)

    patch = GarmentPatch.from_parametric("bottom_front_classic", func, (0, 1), (0, 1), nu, nv)

    # Anchor top edge (waistband attachment points)
    top_ids = list(range(nv))
    patch.anchor_vertex_ids = [0, nv - 1, nv // 2]
    patch.anchor_body_positions = [
        lm["hip_left"] + np.array([0, 0.02, 0.05]),
        lm["hip_right"] + np.array([0, 0.02, 0.05]),
        lm["hip_front"],
    ]
    patch.material_name = "bottom"
    return patch


def v_front(coverage: float = 0.5, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """V-shaped front panel — lower, more daring cut."""
    lm = get_landmarks()

    def func(u, v):
        # V-shape: top edge dips down in center
        v_center_dist = abs(v - 0.5) * 2
        u_offset = 0.3 * (1 - v_center_dist)  # dips more at center
        u_adj = (u_offset + u * (1 - u_offset)) * 0.6
        width_factor = coverage * (0.4 + 0.6 * (1 - u * 0.5))
        v_adj = 0.5 + (v - 0.5) * width_factor
        return _body_surface_bottom(u_adj, v_adj, is_front=True)

    patch = GarmentPatch.from_parametric("bottom_front_v", func, (0, 1), (0, 1), nu, nv)
    patch.anchor_vertex_ids = [0, nv - 1]
    patch.anchor_body_positions = [
        lm["hip_left"] + np.array([0, 0, 0.05]),
        lm["hip_right"] + np.array([0, 0, 0.05]),
    ]
    patch.material_name = "bottom"
    return patch


def high_cut_front(coverage: float = 0.6, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """High-cut front — leg openings cut high on the hip."""
    lm = get_landmarks()

    def func(u, v):
        # Side edges curve inward aggressively
        side_cut = (abs(v - 0.5) * 2) ** 1.5
        u_adj = u * (0.7 + side_cut * 0.3)
        width_factor = coverage * (1 - u * 0.4)
        v_adj = 0.5 + (v - 0.5) * width_factor
        return _body_surface_bottom(u_adj, v_adj, is_front=True)

    patch = GarmentPatch.from_parametric("bottom_front_highcut", func, (0, 1), (0, 1), nu, nv)
    patch.anchor_vertex_ids = [0, nv - 1, nv // 2]
    patch.anchor_body_positions = [
        lm["hip_left"] + np.array([0, 0.04, 0.03]),
        lm["hip_right"] + np.array([0, 0.04, 0.03]),
        lm["hip_front"] + np.array([0, 0.04, 0]),
    ]
    patch.material_name = "bottom"
    return patch


def ruched_front(coverage: float = 0.6, nu: int = 24, nv: int = 24) -> GarmentPatch:
    """Ruched/gathered front panel with fabric bunching."""
    lm = get_landmarks()

    def func(u, v):
        v_adj = 0.5 + (v - 0.5) * coverage
        pos = _body_surface_bottom(u * 0.6, v_adj, is_front=True)
        # Add ruching bumps
        ruch = 0.004 * np.sin(u * np.pi * 8) * np.sin(v * np.pi * 3)
        pos[2] += ruch
        return pos

    patch = GarmentPatch.from_parametric("bottom_front_ruched", func, (0, 1), (0, 1), nu, nv)
    patch.anchor_vertex_ids = [0, nv - 1]
    patch.anchor_body_positions = [
        lm["hip_left"] + np.array([0, 0, 0.05]),
        lm["hip_right"] + np.array([0, 0, 0.05]),
    ]
    patch.material_name = "bottom"
    return patch


def skirt_front(coverage: float = 0.8, nu: int = 24, nv: int = 32) -> GarmentPatch:
    """Mini skirt overlay — wraps around front with flare."""
    lm = get_landmarks()

    def func(u, v):
        # Wider than normal panels, with flare at bottom
        flare = 1.0 + u * 0.4
        v_adj = 0.5 + (v - 0.5) * coverage * flare
        u_adj = u * 0.5  # less vertical travel
        pos = _body_surface_bottom(u_adj, v_adj, is_front=True)
        # Drape outward at bottom
        pos[2] += u * 0.02
        return pos

    patch = GarmentPatch.from_parametric("bottom_front_skirt", func, (0, 1), (0, 1), nu, nv)
    patch.anchor_vertex_ids = list(range(nv))  # entire top edge anchored
    top_y = BODY.hip_height + 0.02
    for i in range(nv):
        patch.anchor_body_positions.append(
            np.array([(i / (nv - 1) - 0.5) * 0.3, top_y, 0.10])
        )
    patch.material_name = "bottom"
    return patch


# --- Back panels ---

def classic_back(coverage: float = 0.6, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """Classic back panel — moderate coverage."""
    lm = get_landmarks()

    def func(u, v):
        width_factor = coverage * (1.0 - u * 0.3)
        v_adj = 0.5 + (v - 0.5) * width_factor
        return _body_surface_bottom(u * 0.6, v_adj, is_front=False)

    patch = GarmentPatch.from_parametric("bottom_back_classic", func, (0, 1), (0, 1), nu, nv)
    patch.anchor_vertex_ids = [0, nv - 1]
    patch.anchor_body_positions = [
        lm["hip_left"] + np.array([0, 0.02, -0.05]),
        lm["hip_right"] + np.array([0, 0.02, -0.05]),
    ]
    patch.material_name = "bottom"
    return patch


def thong_back(nu: int = 16, nv: int = 10) -> GarmentPatch:
    """Thong back — minimal coverage."""
    lm = get_landmarks()

    def func(u, v):
        # Narrow strip that tapers
        width = 0.08 * (1 - u * 0.7)
        v_adj = 0.5 + (v - 0.5) * width / 0.16
        return _body_surface_bottom(u * 0.6, v_adj, is_front=False)

    patch = GarmentPatch.from_parametric("bottom_back_thong", func, (0, 1), (0, 1), nu, nv)
    patch.anchor_vertex_ids = [0, nv - 1]
    patch.anchor_body_positions = [
        lm["hip_left"] + np.array([0, 0, -0.05]),
        lm["hip_right"] + np.array([0, 0, -0.05]),
    ]
    patch.material_name = "bottom"
    return patch


def brazilian_back(coverage: float = 0.4, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """Brazilian back — moderate-to-low coverage."""
    lm = get_landmarks()

    def func(u, v):
        width_factor = coverage * (1.0 - u * 0.5)
        v_adj = 0.5 + (v - 0.5) * width_factor
        pos = _body_surface_bottom(u * 0.6, v_adj, is_front=False)
        # Slight ruching at center
        if abs(v - 0.5) < 0.2:
            pos[2] -= 0.003 * np.sin(u * np.pi * 4)
        return pos

    patch = GarmentPatch.from_parametric("bottom_back_brazilian", func, (0, 1), (0, 1), nu, nv)
    patch.anchor_vertex_ids = [0, nv - 1]
    patch.anchor_body_positions = [
        lm["hip_left"] + np.array([0, 0, -0.05]),
        lm["hip_right"] + np.array([0, 0, -0.05]),
    ]
    patch.material_name = "bottom"
    return patch


def full_back(coverage: float = 0.9, nu: int = 20, nv: int = 24) -> GarmentPatch:
    """Full coverage back panel."""
    lm = get_landmarks()

    def func(u, v):
        v_adj = 0.5 + (v - 0.5) * coverage
        return _body_surface_bottom(u * 0.55, v_adj, is_front=False)

    patch = GarmentPatch.from_parametric("bottom_back_full", func, (0, 1), (0, 1), nu, nv)
    patch.anchor_vertex_ids = [0, nv - 1, nv // 2]
    patch.anchor_body_positions = [
        lm["hip_left"] + np.array([0, 0.02, -0.05]),
        lm["hip_right"] + np.array([0, 0.02, -0.05]),
        lm["hip_back"],
    ]
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
