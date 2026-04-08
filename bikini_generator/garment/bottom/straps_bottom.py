"""Waist/hip strap generators for bikini bottoms.

Straps connect front and back panels by arcing around the body
surface at hip height, holding the bottom together.
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
            tangent = path[-1] - path[max(0, n_seg - 2)]
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


def _hip_arc_waypoints(lm, side, n_points=5):
    """Generate waypoints that arc around the body surface at hip height.

    Creates a smooth path from front to back, staying outside the body.
    The arc follows an elliptical cross-section at hip height.
    """
    hip_y = lm["hip_front"][1]
    x_sign = -1.0 if side == "left" else 1.0

    # Body ellipse radii at hip height
    rx = abs(lm[f"hip_{side}"][0]) * 0.5  # half hip width
    rz_front = lm["hip_front"][2] + 0.015  # stay outside body surface
    rz_back = abs(lm["hip_back"][2]) + 0.015

    waypoints = []
    for i in range(n_points):
        t = (i + 1) / (n_points + 1)
        angle = t * np.pi  # 0=front, pi=back
        x = x_sign * rx * np.sin(angle)
        rz = rz_front if np.cos(angle) > 0 else rz_back
        z = rz * np.cos(angle)
        waypoints.append(np.array([x, hip_y, z]))

    return waypoints


def _get_panel_side_points(lm):
    """Get the side edge points where front/back panels end."""
    hip_y = lm["hip_front"][1]
    front_half_w = abs(lm["hip_left"][0]) * 0.35 * 0.7
    back_half_w = abs(lm["hip_left"][0]) * 0.35 * 0.6

    left_front = np.array([-front_half_w, hip_y, lm["hip_front"][2] + 0.005])
    right_front = np.array([front_half_w, hip_y, lm["hip_front"][2] + 0.005])
    left_back = np.array([-back_half_w, lm["hip_back"][1], lm["hip_back"][2] - 0.005])
    right_back = np.array([back_half_w, lm["hip_back"][1], lm["hip_back"][2] - 0.005])

    return left_front, left_back, right_front, right_back


def side_tie_straps(width: float = 0.018) -> list[GarmentPatch]:
    """Side-tie strings connecting front and back panels around the hips."""
    lm = get_landmarks()
    left_front, left_back, right_front, right_back = _get_panel_side_points(lm)

    straps = []
    for side, sf, sb in [("left", left_front, left_back), ("right", right_front, right_back)]:
        waypoints = _hip_arc_waypoints(lm, side, n_points=4)
        straps.append(_strip_between(
            f"bottom_strap_{side}_tie", sf, sb,
            width, waypoints=waypoints, n_length=24,
        ))
    return straps


def waistband(width: float = 0.02) -> list[GarmentPatch]:
    """Full waistband encircling the hips."""
    lm = get_landmarks()
    hip_y = lm["hip_front"][1] + 0.005

    n_points = 36
    angles = np.linspace(0, 2 * np.pi, n_points, endpoint=True)

    rx = abs(lm["hip_left"][0]) * 0.5
    rz_front = lm["hip_front"][2] + 0.015
    rz_back = abs(lm["hip_back"][2]) + 0.015

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


def chain_straps(width: float = 0.01) -> list[GarmentPatch]:
    """Thin chain-like side straps connecting front and back."""
    return side_tie_straps(width=width)


def multi_strap_sides(width: float = 0.012) -> list[GarmentPatch]:
    """Multiple thin straps on each side (3 per side)."""
    lm = get_landmarks()
    left_front, left_back, right_front, right_back = _get_panel_side_points(lm)

    straps = []
    for side, sf, sb in [("left", left_front, left_back), ("right", right_front, right_back)]:
        for i, offset_y in enumerate([-0.012, 0.0, 0.012]):
            sf2 = sf.copy(); sf2[1] += offset_y
            sb2 = sb.copy(); sb2[1] += offset_y
            waypoints = _hip_arc_waypoints(lm, side, n_points=4)
            for wp in waypoints:
                wp[1] += offset_y
            straps.append(_strip_between(
                f"bottom_strap_{side}_{i}",
                sf2, sb2, width, waypoints=waypoints, n_length=24,
            ))
    return straps


BOTTOM_STRAP_STYLES = {
    "side_tie": side_tie_straps,
    "waistband": waistband,
    "chain": chain_straps,
    "multi_strap": multi_strap_sides,
}
