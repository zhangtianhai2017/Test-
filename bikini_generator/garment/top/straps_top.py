"""Strap generators for bikini tops.

Straps connect cups to body anchor points (shoulders, neck, back).
Each strap is a thin strip mesh following a spline path.
"""

import numpy as np
from ..patch import GarmentPatch
from ...body.landmarks import get_landmarks


def _spline_strip(
    name: str,
    points: list[np.ndarray],
    width: float = 0.01,
    n_length: int = 16,
    n_width: int = 4,
) -> GarmentPatch:
    """Create a strip mesh along a series of control points (Catmull-Rom-ish)."""
    # Simple piecewise linear interpolation with smoothing
    total_points = []
    for i in range(len(points) - 1):
        for t in np.linspace(0, 1, n_length // (len(points) - 1), endpoint=(i == len(points) - 2)):
            total_points.append(points[i] * (1 - t) + points[i + 1] * t)

    path = np.array(total_points)
    n_seg = len(path)

    # Compute tangent and perpendicular at each point
    verts = []
    uvs = []
    for i in range(n_seg):
        if i == 0:
            tangent = path[1] - path[0]
        elif i == n_seg - 1:
            tangent = path[-1] - path[-2]
        else:
            tangent = path[i + 1] - path[i - 1]
        tangent = tangent / (np.linalg.norm(tangent) + 1e-8)

        up = np.array([0, 1, 0])
        if abs(np.dot(tangent, up)) > 0.9:
            up = np.array([0, 0, 1])
        side = np.cross(tangent, up)
        side = side / (np.linalg.norm(side) + 1e-8)

        for j in range(n_width):
            v = (j / (n_width - 1) - 0.5) * width
            verts.append(path[i] + side * v)
            uvs.append([i / (n_seg - 1), j / (n_width - 1)])

    verts = np.array(verts)
    uvs = np.array(uvs)

    faces = []
    for i in range(n_seg - 1):
        for j in range(n_width - 1):
            v0 = i * n_width + j
            v1 = v0 + 1
            v2 = (i + 1) * n_width + j
            v3 = v2 + 1
            faces.append([v0, v2, v1])
            faces.append([v1, v2, v3])

    patch = GarmentPatch(
        name=name,
        vertices=verts,
        faces=np.array(faces, dtype=np.int32),
        uvs=uvs,
    )
    patch.compute_normals()

    # Anchor first and last ring
    patch.anchor_vertex_ids = list(range(n_width)) + list(range((n_seg - 1) * n_width, n_seg * n_width))
    patch.anchor_body_positions = (
        [path[0]] * n_width + [path[-1]] * n_width
    )
    return patch


def over_shoulder_straps(width: float = 0.018) -> list[GarmentPatch]:
    """Classic over-the-shoulder straps (left and right)."""
    lm = get_landmarks()
    straps = []
    for side in ["left", "right"]:
        apex = lm[f"{side}_breast_apex"] + np.array([0, 0.03, 0])
        shoulder = lm[f"{side}_shoulder"]
        mid = (apex + shoulder) / 2 + np.array([0, 0.02, 0.01])
        back = lm["spine_upper"] + np.array([0.05 if side == "right" else -0.05, 0, 0])

        straps.append(_spline_strip(
            f"strap_{side}_shoulder",
            [apex, mid, shoulder, back],
            width=width,
        ))
    return straps


def halter_strap(width: float = 0.015) -> list[GarmentPatch]:
    """Halter neck strap — cups connect around back of neck at shoulder height."""
    lm = get_landmarks()
    # Halter goes up to shoulder height, then wraps behind the neck
    shoulder_y = (lm["left_shoulder"][1] + lm["right_shoulder"][1]) / 2
    neck_back_z = lm["neck_back"][2]
    straps = []
    for side in ["left", "right"]:
        sign = -1 if side == "left" else 1
        apex = lm[f"{side}_breast_apex"] + np.array([0, 0.03, 0])
        shoulder = lm[f"{side}_shoulder"]
        # Route: cup → shoulder area → behind neck (at shoulder height)
        neck_wrap = np.array([sign * 0.03, shoulder_y + 0.02, neck_back_z + 0.02])
        neck_center = np.array([0, shoulder_y + 0.02, neck_back_z])
        straps.append(_spline_strip(
            f"strap_{side}_halter",
            [apex, shoulder, neck_wrap, neck_center],
            width=width,
            n_length=20,
        ))
    return straps


def cross_back_straps(width: float = 0.015) -> list[GarmentPatch]:
    """Cross-back straps: left cup → right back, right cup → left back."""
    lm = get_landmarks()
    straps = []
    for side, cross_side in [("left", "right"), ("right", "left")]:
        sign = -1 if side == "left" else 1
        cross_sign = -1 if cross_side == "left" else 1
        outer = lm[f"{side}_breast_outer"] + np.array([0, 0.02, 0])
        shoulder = lm[f"{side}_shoulder"]
        back = lm["spine_upper"] + np.array([cross_sign * 0.06, -0.02, 0])

        straps.append(_spline_strip(
            f"strap_{side}_crossback",
            [outer, shoulder, back],
            width=width,
        ))
    return straps


def multi_strap_web(width: float = 0.01) -> list[GarmentPatch]:
    """Multi-strap web: 3 thin straps per side creating a web pattern."""
    lm = get_landmarks()
    straps = []
    for side in ["left", "right"]:
        sign = -1 if side == "left" else 1
        apex = lm[f"{side}_breast_apex"] + np.array([0, 0.03, 0])
        outer = lm[f"{side}_breast_outer"] + np.array([0, 0.02, 0])
        shoulder = lm[f"{side}_shoulder"]
        back = lm["spine_upper"] + np.array([sign * 0.04, 0, 0])

        # Web_a: cup apex → shoulder (inner path)
        mid_a = (apex + shoulder) / 2 + np.array([0, 0.015, 0.01])
        straps.append(_spline_strip(f"strap_{side}_web_a", [apex, mid_a, shoulder], width))
        # Web_b: cup outer → shoulder (outer path)
        straps.append(_spline_strip(f"strap_{side}_web_b", [outer, shoulder], width))
        # Web_c: cup apex → shoulder → back
        straps.append(_spline_strip(f"strap_{side}_web_c", [apex, shoulder, back], width))
    return straps


def no_straps() -> list[GarmentPatch]:
    """Strapless — relies on band tension and friction."""
    return []


def back_band(width: float = 0.025) -> list[GarmentPatch]:
    """Back band connecting left and right cups around the back."""
    lm = get_landmarks()
    left_outer = lm["left_breast_outer"] + np.array([0, -0.02, 0])
    right_outer = lm["right_breast_outer"] + np.array([0, -0.02, 0])
    left_rib = lm["left_ribcage"]
    right_rib = lm["right_ribcage"]
    back = lm["spine_mid"]

    strap = _spline_strip(
        "strap_back_band",
        [right_outer, right_rib, back, left_rib, left_outer],
        width=width,
        n_length=32,
    )
    return [strap]


STRAP_STYLES = {
    "over_shoulder": over_shoulder_straps,
    "halter": halter_strap,
    "cross_back": cross_back_straps,
    "multi_web": multi_strap_web,
    "strapless": no_straps,
}

BAND_STYLES = {
    "back_band": back_band,
    "none": lambda: [],
}
