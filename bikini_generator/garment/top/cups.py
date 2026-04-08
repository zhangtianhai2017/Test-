"""Cup shape generators for bikini tops.

Each generator returns a GarmentPatch positioned on the body.
Parametric functions map (u, v) -> (x, y, z) on the breast surface.
"""

import numpy as np
from ..patch import GarmentPatch
from ...body.landmarks import get_landmarks
from ...config import BODY


def _breast_surface(x_sign: float, u: float, v: float, depth: float = 1.0) -> np.ndarray:
    """Map (u,v) in [0,1]x[0,1] to a point on/near the breast surface.

    u: latitude (0=top, 1=bottom)
    v: longitude (0=inner, 1=outer)

    Coordinates calibrated to real ZBrush body mesh.
    """
    lm = get_landmarks()
    side = "left" if x_sign < 0 else "right"
    apex = lm[f"{side}_breast_apex"]
    outer = lm[f"{side}_breast_outer"]
    inner = lm[f"{side}_breast_inner"]

    # Breast center and radii from real landmarks
    cx = apex[0]
    cy = apex[1]
    cz_base = (inner[2] + outer[2]) / 2  # base Z (on ribcage)

    r_lateral = abs(outer[0] - inner[0]) / 2  # half-width
    r_vertical = 0.04  # approximate vertical extent
    r_forward = apex[2] - cz_base  # projection depth

    theta = u * np.pi * 0.6  # latitude angle
    phi = (v - 0.5) * np.pi * 0.8  # longitude angle

    r_scale = 1.0 + depth * 0.3
    x = cx + r_lateral * r_scale * np.sin(theta) * np.sin(phi) * x_sign
    y = cy + r_vertical * r_scale * np.cos(theta) * 0.5 - r_vertical * (1 - np.cos(theta)) * 0.3
    z = cz_base + (r_forward + 0.005) * r_scale * np.sin(theta) * np.cos(phi)

    return np.array([x, y, z])


def triangle_cup(side: str = "left", coverage: float = 0.7, nu: int = 20, nv: int = 20) -> GarmentPatch:
    """Classic triangle bikini cup."""
    x_sign = -1.0 if side == "left" else 1.0
    landmarks = get_landmarks()

    def func(u, v):
        # Triangle shape: width narrows toward top
        width_scale = 1.0 - u * (1.0 - 0.1)  # narrow at top
        v_adj = 0.5 + (v - 0.5) * width_scale * coverage
        return _breast_surface(x_sign, u, v_adj)

    patch = GarmentPatch.from_parametric(
        f"cup_{side}_triangle", func, (0.05, 0.95), (0.05, 0.95), nu, nv
    )

    # Anchor: top center vertex (strap attachment)
    top_center = nu // 2
    apex_name = f"{side}_breast_apex"
    patch.anchor_vertex_ids = [0, nv - 1, top_center]
    patch.anchor_body_positions = [
        landmarks[f"{side}_breast_inner"],
        landmarks[f"{side}_breast_outer"],
        landmarks[apex_name] + np.array([0, 0.06, 0]),
    ]
    patch.material_name = f"cup_{side}"
    return patch


def round_cup(side: str = "left", coverage: float = 0.8, nu: int = 24, nv: int = 24) -> GarmentPatch:
    """Full round cup with underwire shape."""
    x_sign = -1.0 if side == "left" else 1.0
    landmarks = get_landmarks()

    def func(u, v):
        v_adj = 0.5 + (v - 0.5) * coverage
        return _breast_surface(x_sign, u, v_adj, depth=1.2)

    patch = GarmentPatch.from_parametric(
        f"cup_{side}_round", func, (0.0, 1.0), (0.0, 1.0), nu, nv
    )
    patch.anchor_vertex_ids = [0, nv - 1]
    patch.anchor_body_positions = [
        landmarks[f"{side}_breast_inner"],
        landmarks[f"{side}_breast_outer"],
    ]
    patch.material_name = f"cup_{side}"
    return patch


def bandeau_cup(side: str = "left", coverage: float = 0.6, nu: int = 16, nv: int = 24) -> GarmentPatch:
    """Bandeau (strapless) style — wider, less tall."""
    x_sign = -1.0 if side == "left" else 1.0
    landmarks = get_landmarks()

    def func(u, v):
        # Bandeau: less vertical coverage, more horizontal
        u_adj = 0.25 + u * 0.5 * coverage
        v_adj = 0.5 + (v - 0.5) * 1.1  # wider
        return _breast_surface(x_sign, u_adj, v_adj, depth=0.8)

    patch = GarmentPatch.from_parametric(
        f"cup_{side}_bandeau", func, (0.0, 1.0), (0.0, 1.0), nu, nv
    )
    # Bandeau: anchor along the band (bottom edge + sides)
    bottom_ids = list(range((nu - 1) * nv, nu * nv))
    side_ids = [0, nv - 1, (nu - 1) * nv, nu * nv - 1]
    band_y = landmarks[f"{side}_underbust"][1]
    patch.anchor_vertex_ids = side_ids
    patch.anchor_body_positions = [
        landmarks[f"{side}_breast_inner"],
        landmarks[f"{side}_breast_outer"],
        landmarks[f"{side}_underbust"],
        landmarks[f"{side}_underbust"] + np.array([x_sign * 0.04, 0, -0.02]),
    ]
    patch.material_name = f"cup_{side}"
    return patch


def scallop_cup(side: str = "left", coverage: float = 0.75, nu: int = 24, nv: int = 24) -> GarmentPatch:
    """Cup with scalloped/wavy edge."""
    x_sign = -1.0 if side == "left" else 1.0
    landmarks = get_landmarks()

    def func(u, v):
        # Add scallop to edges
        edge_wave = 0.008 * np.sin(v * np.pi * 6) * (1 - u)  # waves on top edge
        v_adj = 0.5 + (v - 0.5) * coverage
        pos = _breast_surface(x_sign, u, v_adj)
        pos[2] += edge_wave
        pos[1] += edge_wave * 0.5
        return pos

    patch = GarmentPatch.from_parametric(
        f"cup_{side}_scallop", func, (0.05, 0.95), (0.05, 0.95), nu, nv
    )
    patch.anchor_vertex_ids = [0, nv - 1]
    patch.anchor_body_positions = [
        landmarks[f"{side}_breast_inner"],
        landmarks[f"{side}_breast_outer"],
    ]
    patch.material_name = f"cup_{side}"
    return patch


def cone_cup(side: str = "left", coverage: float = 0.7, sharpness: float = 0.6,
             nu: int = 20, nv: int = 20) -> GarmentPatch:
    """Conical/pointed cup shape."""
    x_sign = -1.0 if side == "left" else 1.0
    landmarks = get_landmarks()

    def func(u, v):
        v_adj = 0.5 + (v - 0.5) * coverage
        pos = _breast_surface(x_sign, u, v_adj)
        # Add conical projection toward apex
        apex_factor = (1 - u) * (1 - abs(v - 0.5) * 2)
        pos[2] += sharpness * 0.03 * apex_factor
        return pos

    patch = GarmentPatch.from_parametric(
        f"cup_{side}_cone", func, (0.05, 0.95), (0.05, 0.95), nu, nv
    )
    patch.anchor_vertex_ids = [0, nv - 1]
    patch.anchor_body_positions = [
        landmarks[f"{side}_breast_inner"],
        landmarks[f"{side}_breast_outer"],
    ]
    patch.material_name = f"cup_{side}"
    return patch


# Registry of all cup generators
CUP_STYLES = {
    "triangle": triangle_cup,
    "round": round_cup,
    "bandeau": bandeau_cup,
    "scallop": scallop_cup,
    "cone": cone_cup,
}
