"""Waist/hip strap generators for bikini bottoms."""

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
        n_seg = n_length // (len(points) - 1)
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
    patch.anchor_vertex_ids = list(range(n_width)) + list(range((n_seg - 1) * n_width, n_seg * n_width))
    patch.anchor_body_positions = [start] * n_width + [end] * n_width
    return patch


def side_tie_straps(width: float = 0.008) -> list[GarmentPatch]:
    """Simple side-tie strings at the hips."""
    lm = get_landmarks()
    straps = []
    for side in ["left", "right"]:
        front = lm[f"hip_{side}"] + np.array([0, 0.02, 0.05])
        hip = lm[f"hip_{side}"] + np.array([0, 0.02, 0])
        back = lm[f"hip_{side}"] + np.array([0, 0.02, -0.05])
        straps.append(_strip_between(
            f"bottom_strap_{side}_tie", front, back,
            width, waypoints=[hip],
        ))
    return straps


def waistband(width: float = 0.025) -> list[GarmentPatch]:
    """Full waistband encircling the hips."""
    lm = get_landmarks()
    points = [
        lm["hip_front"] + np.array([0, 0.02, 0]),
        lm["hip_right"] + np.array([0, 0.02, 0]),
        lm["hip_back"] + np.array([0, 0.02, 0]),
        lm["hip_left"] + np.array([0, 0.02, 0]),
        lm["hip_front"] + np.array([0, 0.02, 0]),  # close loop
    ]

    path = []
    n_per_seg = 8
    for i in range(len(points) - 1):
        for t in np.linspace(0, 1, n_per_seg, endpoint=(i == len(points) - 2)):
            path.append(points[i] * (1 - t) + points[i + 1] * t)

    path = np.array(path)
    n_seg = len(path)

    verts = []
    uvs = []
    for i in range(n_seg):
        tangent = path[(i + 1) % n_seg] - path[(i - 1) % n_seg]
        tangent = tangent / (np.linalg.norm(tangent) + 1e-8)

        # "up" is radially outward from body center at this height
        center = np.array([0, path[i][1], 0])
        outward = path[i] - center
        outward[1] = 0
        outward = outward / (np.linalg.norm(outward) + 1e-8)

        up = np.array([0, 1, 0])
        for j in range(4):
            v_off = (j / 3 - 0.5) * width
            verts.append(path[i] + up * v_off)
            uvs.append([i / (n_seg - 1), j / 3])

    verts = np.array(verts)
    uvs = np.array(uvs)
    n_width = 4

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
        name="bottom_waistband",
        vertices=verts,
        faces=np.array(faces, dtype=np.int32),
        uvs=uvs,
    )
    patch.compute_normals()
    # Anchor all vertices (it's a band)
    patch.anchor_vertex_ids = list(range(len(verts)))
    patch.anchor_body_positions = [verts[i].copy() for i in range(len(verts))]
    return [patch]


def chain_straps(width: float = 0.004) -> list[GarmentPatch]:
    """Thin chain-like side straps."""
    return side_tie_straps(width=width)


def multi_strap_sides(width: float = 0.005) -> list[GarmentPatch]:
    """Multiple thin straps on each side (3 per side)."""
    lm = get_landmarks()
    straps = []
    for side in ["left", "right"]:
        for offset_y in [-0.01, 0.0, 0.01]:
            front = lm[f"hip_{side}"] + np.array([0, 0.02 + offset_y, 0.05])
            back = lm[f"hip_{side}"] + np.array([0, 0.02 + offset_y, -0.05])
            hip = lm[f"hip_{side}"] + np.array([0, 0.02 + offset_y, 0])
            straps.append(_strip_between(
                f"bottom_strap_{side}_{offset_y:.2f}",
                front, back, width, waypoints=[hip],
            ))
    return straps


BOTTOM_STRAP_STYLES = {
    "side_tie": side_tie_straps,
    "waistband": waistband,
    "chain": chain_straps,
    "multi_strap": multi_strap_sides,
}
