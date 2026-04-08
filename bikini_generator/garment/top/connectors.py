"""Connectors between bikini top cups.

These bridge the left and right cups at the center (sternum area).
"""

import numpy as np
from ..patch import GarmentPatch
from ...body.landmarks import get_landmarks


def _make_strip(
    name: str,
    start: np.ndarray,
    end: np.ndarray,
    width: float,
    n_length: int = 10,
    n_width: int = 4,
    curve_offset: np.ndarray | None = None,
) -> GarmentPatch:
    """Create a strip/band mesh between two points."""
    direction = end - start
    length = np.linalg.norm(direction)
    forward = direction / length

    # Find perpendicular directions
    up = np.array([0, 1, 0])
    if abs(np.dot(forward, up)) > 0.9:
        up = np.array([0, 0, 1])
    side = np.cross(forward, up)
    side = side / np.linalg.norm(side)

    def func(u, v):
        t = u
        pos = start + direction * t
        if curve_offset is not None:
            # Quadratic bezier curve outward
            blend = 4 * t * (1 - t)  # peaks at 0.5
            pos = pos + curve_offset * blend
        lateral = (v - 0.5) * width
        pos = pos + side * lateral
        return pos

    patch = GarmentPatch.from_parametric(name, func, (0, 1), (0, 1), n_length, n_width)
    return patch


def string_connector(width: float = 0.005) -> GarmentPatch:
    """Thin string between cups."""
    lm = get_landmarks()
    start = lm["right_breast_inner"]
    end = lm["left_breast_inner"]
    return _make_strip("connector_string", start, end, width, n_length=8, n_width=3)


def band_connector(width: float = 0.03) -> GarmentPatch:
    """Wide band between cups."""
    lm = get_landmarks()
    start = lm["right_breast_inner"]
    end = lm["left_breast_inner"]
    return _make_strip("connector_band", start, end, width, n_length=10, n_width=6)


def ring_connector(radius: float = 0.015, n: int = 16) -> GarmentPatch:
    """Decorative ring/O-ring at center."""
    lm = get_landmarks()
    center = lm["sternum_center"]
    tube_r = 0.003

    verts = []
    uvs = []
    for i in range(n):
        theta = 2 * np.pi * i / n
        for j in range(8):
            phi = 2 * np.pi * j / 8
            x = center[0] + (radius + tube_r * np.cos(phi)) * np.cos(theta)
            y = center[1] + (radius + tube_r * np.cos(phi)) * np.sin(theta)
            z = center[2] + tube_r * np.sin(phi)
            verts.append([x, y, z])
            uvs.append([i / n, j / 8])

    verts = np.array(verts)
    uvs = np.array(uvs)
    faces = []
    for i in range(n):
        i_next = (i + 1) % n
        for j in range(8):
            j_next = (j + 1) % 8
            v0 = i * 8 + j
            v1 = i * 8 + j_next
            v2 = i_next * 8 + j
            v3 = i_next * 8 + j_next
            faces.append([v0, v2, v1])
            faces.append([v1, v2, v3])

    return GarmentPatch(
        name="connector_ring",
        vertices=verts,
        faces=np.array(faces, dtype=np.int32),
        uvs=uvs,
    )


def cross_connector() -> GarmentPatch:
    """X-shaped cross straps at center."""
    lm = get_landmarks()
    center = lm["sternum_center"]
    offset = 0.04

    p1 = center + np.array([-offset, offset, 0])
    p2 = center + np.array([offset, -offset, 0])
    p3 = center + np.array([-offset, -offset, 0])
    p4 = center + np.array([offset, offset, 0])

    strip1 = _make_strip("connector_cross_a", p1, p2, 0.006, 8, 3)
    strip2 = _make_strip("connector_cross_b", p3, p4, 0.006, 8, 3)

    # Merge
    verts = np.vstack([strip1.vertices, strip2.vertices])
    faces = np.vstack([strip1.faces, strip2.faces + len(strip1.vertices)])
    uvs = np.vstack([strip1.uvs, strip2.uvs])
    return GarmentPatch(name="connector_cross", vertices=verts, faces=faces, uvs=uvs)


def no_connector() -> GarmentPatch | None:
    """No connector — cups are independent (held by straps only)."""
    return None


CONNECTOR_STYLES = {
    "string": string_connector,
    "band": band_connector,
    "ring": ring_connector,
    "cross": cross_connector,
    "none": no_connector,
}
