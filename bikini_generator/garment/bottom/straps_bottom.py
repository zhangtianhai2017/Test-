"""Waist/hip strap generators for bikini bottoms.

Straps connect front and back panels by going over the hips,
holding the bottom together as a wearable garment.
"""

import numpy as np
from ..patch import GarmentPatch
from ...body.landmarks import get_landmarks
from ...config import BODY


def _strip_between(
    name: str,
    start: np.ndarray,
    end: np.ndarray,
    width: float,
    waypoints: list[np.ndarray] | None = None,
    n_length: int = 16,
    n_width: int = 4,
) -> GarmentPatch:
    """Create a strip mesh between points, optionally through waypoints."""
    points = [start]
    if waypoints:
        points.extend(waypoints)
    points.append(end)

    # Piecewise linear path
    path_points = []
    for i in range(len(points) - 1):
        n_seg = max(2, n_length // (len(points) - 1))
        for t in np.linspace(0, 1, n_seg, endpoint=(i == len(points) - 2)):
            path_points.append(points[i] * (1 - t) + points[i + 1] * t)

    path = np.array(path_points)
    n_seg = len(path)

    verts = []
    uvs = []
    for i in range(n_seg):
        if i == 0:
            tangent = path[min(1, n_seg - 1)] - path[0]
        elif i == n_seg - 1:
            tangent = path[-1] - path[max(0, -2)]
        else:
            tangent = path[i + 1] - path[i - 1]
        tlen = np.linalg.norm(tangent)
        if tlen > 1e-8:
            tangent = tangent / tlen

        up = np.array([0, 1, 0])
        if abs(np.dot(tangent, up)) > 0.9:
            up = np.array([0, 0, 1])
        side = np.cross(tangent, up)
        slen = np.linalg.norm(side)
        if slen > 1e-8:
            side = side / slen

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
    patch.anchor_vertex_ids = list(range(n_width)) + list(range((n_seg - 1) * n_width, n_seg * n_width))
    patch.anchor_body_positions = [start] * n_width + [end] * n_width
    return patch


def _get_panel_side_points(lm):
    """Get the side edge points where front/back panels end.

    Returns (left_front, left_back, right_front, right_back) positions.
    These are at the top edge of the panels, at hip height.
    """
    hip_y = lm["hip_front"][1]
    # Front panel top-left/right edges
    front_half_w = abs(lm["hip_left"][0]) * 0.35 * 0.7  # match panel coverage
    back_half_w = abs(lm["hip_left"][0]) * 0.35 * 0.6

    left_front = np.array([-front_half_w, hip_y, lm["hip_front"][2]])
    right_front = np.array([front_half_w, hip_y, lm["hip_front"][2]])
    left_back = np.array([-back_half_w, hip_y, lm["hip_back"][2]])
    right_back = np.array([back_half_w, hip_y, lm["hip_back"][2]])

    return left_front, left_back, right_front, right_back


def side_tie_straps(width: float = 0.008) -> list[GarmentPatch]:
    """Side-tie strings connecting front and back panels over the hips."""
    lm = get_landmarks()
    left_front, left_back, right_front, right_back = _get_panel_side_points(lm)

    straps = []
    # Left side: front panel edge → hip → back panel edge
    left_hip = lm["hip_left"] * 0.6 + np.array([0, lm["hip_front"][1], 0]) * 0.4
    left_hip[1] = lm["hip_front"][1]  # keep at hip height
    straps.append(_strip_between(
        "bottom_strap_left_tie", left_front, left_back,
        width, waypoints=[left_hip], n_length=20,
    ))

    # Right side
    right_hip = lm["hip_right"] * 0.6 + np.array([0, lm["hip_front"][1], 0]) * 0.4
    right_hip[1] = lm["hip_front"][1]
    straps.append(_strip_between(
        "bottom_strap_right_tie", right_front, right_back,
        width, waypoints=[right_hip], n_length=20,
    ))
    return straps


def waistband(width: float = 0.02) -> list[GarmentPatch]:
    """Full waistband encircling the hips, connecting front and back."""
    lm = get_landmarks()
    hip_y = lm["hip_front"][1] + 0.01

    # Build a path: front center → right hip → back center → left hip → front center
    n_points = 32
    angles = np.linspace(0, 2 * np.pi, n_points, endpoint=True)

    # Elliptical path around body at hip height
    rx = abs(lm["hip_left"][0]) * 0.55  # X radius
    rz_front = lm["hip_front"][2] + 0.01  # front Z
    rz_back = abs(lm["hip_back"][2]) + 0.01  # back Z

    path = []
    for a in angles:
        x = rx * np.sin(a)
        rz = rz_front if np.cos(a) > 0 else rz_back
        z = rz * np.cos(a)
        path.append(np.array([x, hip_y, z]))

    path = np.array(path)
    n_seg = len(path)
    n_w = 4

    verts = []
    uvs = []
    for i in range(n_seg):
        up = np.array([0, 1, 0])
        for j in range(n_w):
            v_off = (j / (n_w - 1) - 0.5) * width
            verts.append(path[i] + up * v_off)
            uvs.append([i / (n_seg - 1), j / (n_w - 1)])

    verts = np.array(verts)
    uvs = np.array(uvs)

    faces = []
    for i in range(n_seg - 1):
        for j in range(n_w - 1):
            v0 = i * n_w + j
            v1 = v0 + 1
            v2 = (i + 1) * n_w + j
            v3 = v2 + 1
            faces.append([v0, v2, v1])
            faces.append([v1, v2, v3])

    patch = GarmentPatch(
        name="bottom_waistband",
        vertices=verts,
        faces=np.array(faces, dtype=np.int32),
        uvs=uvs,
    )
    patch.compute_normals()
    patch.anchor_vertex_ids = list(range(len(verts)))
    patch.anchor_body_positions = [verts[i].copy() for i in range(len(verts))]
    return [patch]


def chain_straps(width: float = 0.004) -> list[GarmentPatch]:
    """Thin chain-like side straps connecting front and back."""
    return side_tie_straps(width=width)


def multi_strap_sides(width: float = 0.005) -> list[GarmentPatch]:
    """Multiple thin straps on each side (3 per side)."""
    lm = get_landmarks()
    left_front, left_back, right_front, right_back = _get_panel_side_points(lm)

    straps = []
    for side_name, s_front, s_back, hip_lm in [
        ("left", left_front, left_back, "hip_left"),
        ("right", right_front, right_back, "hip_right"),
    ]:
        for i, offset_y in enumerate([-0.01, 0.0, 0.01]):
            hip = lm[hip_lm] * 0.6 + np.array([0, lm["hip_front"][1], 0]) * 0.4
            hip[1] = lm["hip_front"][1] + offset_y
            sf = s_front.copy()
            sb = s_back.copy()
            sf[1] += offset_y
            sb[1] += offset_y
            straps.append(_strip_between(
                f"bottom_strap_{side_name}_{i}",
                sf, sb, width, waypoints=[hip], n_length=20,
            ))
    return straps


BOTTOM_STRAP_STYLES = {
    "side_tie": side_tie_straps,
    "waistband": waistband,
    "chain": chain_straps,
    "multi_strap": multi_strap_sides,
}
