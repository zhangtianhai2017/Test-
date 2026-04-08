"""Procedural mannequin body mesh generation.

Generates a simplified female body mesh with higher polygon density
around chest, crotch, and buttocks for accurate garment fitting.
"""

import numpy as np
from ..config import BODY, GENERATION


def _ellipsoid_points(
    center: np.ndarray,
    radii: np.ndarray,
    n_lat: int,
    n_lon: int,
    lat_range: tuple[float, float] = (0, np.pi),
    lon_range: tuple[float, float] = (0, 2 * np.pi),
) -> tuple[np.ndarray, np.ndarray]:
    """Generate vertices and faces for an ellipsoid patch."""
    lats = np.linspace(lat_range[0], lat_range[1], n_lat)
    lons = np.linspace(lon_range[0], lon_range[1], n_lon)
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")

    x = center[0] + radii[0] * np.sin(lat_grid) * np.cos(lon_grid)
    y = center[1] + radii[1] * np.cos(lat_grid)
    z = center[2] + radii[2] * np.sin(lat_grid) * np.sin(lon_grid)

    verts = np.stack([x.ravel(), y.ravel(), z.ravel()], axis=-1)

    faces = []
    for i in range(n_lat - 1):
        for j in range(n_lon - 1):
            v0 = i * n_lon + j
            v1 = v0 + 1
            v2 = (i + 1) * n_lon + j
            v3 = v2 + 1
            faces.append([v0, v2, v1])
            faces.append([v1, v2, v3])

    return verts, np.array(faces, dtype=np.int32)


def _sphere_points(
    center: np.ndarray, radius: float, n: int
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a sphere mesh."""
    return _ellipsoid_points(center, np.array([radius, radius, radius]), n, n)


def _merge_meshes(
    meshes: list[tuple[np.ndarray, np.ndarray]]
) -> tuple[np.ndarray, np.ndarray]:
    """Merge multiple (vertices, faces) tuples into one mesh."""
    all_verts = []
    all_faces = []
    offset = 0
    for verts, faces in meshes:
        all_verts.append(verts)
        all_faces.append(faces + offset)
        offset += len(verts)
    return np.vstack(all_verts), np.vstack(all_faces)


def _torso_profile(y: float) -> tuple[float, float]:
    """Return (x_radius, z_radius) of torso cross-section at height y."""
    b = BODY
    # Normalize y to [0,1] range from crotch to shoulder
    t = np.clip((y - b.crotch_height) / (b.shoulder_height - b.crotch_height), 0, 1)

    # Piecewise profile
    hip_t = (b.hip_height - b.crotch_height) / (b.shoulder_height - b.crotch_height)
    waist_t = (b.waist_height - b.crotch_height) / (b.shoulder_height - b.crotch_height)
    bust_t = (b.bust_height - b.crotch_height) / (b.shoulder_height - b.crotch_height)

    # X (side) radius at key heights
    hip_rx = b.hip_circumference / (2 * np.pi) * 1.1
    waist_rx = b.waist_circumference / (2 * np.pi) * 1.05
    bust_rx = b.bust_circumference / (2 * np.pi) * 0.95
    shoulder_rx = b.shoulder_width / 2

    # Z (front-back) radius
    hip_rz = hip_rx * 0.85
    waist_rz = waist_rx * 0.80
    bust_rz = bust_rx * 0.75
    shoulder_rz = shoulder_rx * 0.55

    # Interpolate
    if t < hip_t:
        s = t / hip_t if hip_t > 0 else 0
        # Taper from narrow crotch to hips
        rx = 0.06 + s * (hip_rx - 0.06)
        rz = 0.04 + s * (hip_rz - 0.04)
    elif t < waist_t:
        s = (t - hip_t) / (waist_t - hip_t)
        rx = hip_rx + s * (waist_rx - hip_rx)
        rz = hip_rz + s * (waist_rz - hip_rz)
    elif t < bust_t:
        s = (t - waist_t) / (bust_t - waist_t)
        rx = waist_rx + s * (bust_rx - waist_rx)
        rz = waist_rz + s * (bust_rz - waist_rz)
    else:
        s = (t - bust_t) / (1.0 - bust_t)
        rx = bust_rx + s * (shoulder_rx - bust_rx)
        rz = bust_rz + s * (shoulder_rz - bust_rz)

    return float(rx), float(rz)


def generate_torso_mesh(
    n_rings_low: int | None = None,
    n_rings_high: int | None = None,
    n_lon: int = 48,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate torso mesh with variable ring density.

    Higher density around bust, waist, and hip regions.
    """
    b = BODY
    n_low = n_rings_low or GENERATION.body_mesh_resolution_low
    n_high = n_rings_high or GENERATION.body_mesh_resolution_high

    # Define height segments with adaptive density
    segments = [
        (b.crotch_height, b.hip_height - 0.02, n_high),      # crotch region (high)
        (b.hip_height - 0.02, b.hip_height + 0.04, n_high),   # hip (high)
        (b.hip_height + 0.04, b.waist_height - 0.02, n_low),  # lower torso (low)
        (b.waist_height - 0.02, b.waist_height + 0.02, n_low),  # waist
        (b.waist_height + 0.02, b.bust_height - 0.06, n_low),  # mid torso (low)
        (b.bust_height - 0.06, b.bust_height + 0.06, n_high),  # bust region (high)
        (b.bust_height + 0.06, b.shoulder_height, n_low),      # upper torso (low)
    ]

    all_verts = []
    all_faces = []
    offset = 0

    for y_start, y_end, n_rings in segments:
        heights = np.linspace(y_start, y_end, n_rings)
        ring_verts = []

        for y in heights:
            rx, rz = _torso_profile(y)
            angles = np.linspace(0, 2 * np.pi, n_lon, endpoint=False)
            ring = np.zeros((n_lon, 3))
            ring[:, 0] = rx * np.cos(angles)
            ring[:, 1] = y
            ring[:, 2] = rz * np.sin(angles)
            ring_verts.append(ring)

        verts = np.vstack(ring_verts)
        faces = []
        for i in range(len(heights) - 1):
            for j in range(n_lon):
                j_next = (j + 1) % n_lon
                v0 = i * n_lon + j
                v1 = i * n_lon + j_next
                v2 = (i + 1) * n_lon + j
                v3 = (i + 1) * n_lon + j_next
                faces.append([v0, v2, v1])
                faces.append([v1, v2, v3])

        if faces:
            all_verts.append(verts)
            all_faces.append(np.array(faces, dtype=np.int32) + offset)
            offset += len(verts)

    return np.vstack(all_verts), np.vstack(all_faces)


def generate_breast_mesh(
    side: str = "left",
    n: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a breast hemisphere mesh (high poly)."""
    b = BODY
    n = n or GENERATION.body_mesh_resolution_high
    sign = -1.0 if side == "left" else 1.0
    center = np.array([
        sign * b.breast_spacing / 2,
        b.bust_height,
        0.10,
    ])
    radii = np.array([b.breast_radius, b.breast_radius * 0.9, b.breast_projection + 0.02])
    # Only front hemisphere
    return _ellipsoid_points(
        center, radii, n, n,
        lat_range=(0, np.pi / 2),
        lon_range=(-np.pi * 0.8, np.pi * 0.8),
    )


def generate_buttock_mesh(
    side: str = "left",
    n: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a buttock hemisphere mesh (high poly)."""
    b = BODY
    n = n or GENERATION.body_mesh_resolution_high
    sign = -1.0 if side == "left" else 1.0
    center = np.array([
        sign * 0.08,
        b.hip_height - 0.04,
        -0.10,
    ])
    radii = np.array([0.08, 0.06, 0.05])
    return _ellipsoid_points(
        center, radii, n, n,
        lat_range=(0, np.pi / 2),
        lon_range=(-np.pi * 0.7, np.pi * 0.7),
    )


def generate_full_body() -> tuple[np.ndarray, np.ndarray]:
    """Generate the complete mannequin body mesh.

    Returns (vertices, faces) as numpy arrays.
    Chest, crotch, and buttocks have higher polygon density.
    """
    meshes = [
        generate_torso_mesh(),
        generate_breast_mesh("left"),
        generate_breast_mesh("right"),
        generate_buttock_mesh("left"),
        generate_buttock_mesh("right"),
    ]
    return _merge_meshes(meshes)


def get_body_collision_primitives() -> list[dict]:
    """Return simplified collision shapes for physics simulation.

    Each primitive is a dict with 'type', 'center', and shape-specific params.
    Used by the Taichi cloth sim for collision detection.
    """
    b = BODY
    return [
        # Main torso - approximated as a tapered capsule via stacked spheres
        {
            "type": "ellipsoid",
            "center": [0.0, (b.waist_height + b.bust_height) / 2, 0.0],
            "radii": [0.14, (b.bust_height - b.waist_height) / 2, 0.10],
        },
        # Hip region
        {
            "type": "ellipsoid",
            "center": [0.0, (b.hip_height + b.waist_height) / 2, -0.01],
            "radii": [0.16, (b.waist_height - b.hip_height) / 2, 0.12],
        },
        # Left breast
        {
            "type": "sphere",
            "center": [-b.breast_spacing / 2, b.bust_height, 0.10],
            "radius": b.breast_radius + 0.01,
        },
        # Right breast
        {
            "type": "sphere",
            "center": [b.breast_spacing / 2, b.bust_height, 0.10],
            "radius": b.breast_radius + 0.01,
        },
        # Left buttock
        {
            "type": "sphere",
            "center": [-0.08, b.hip_height - 0.04, -0.10],
            "radius": 0.07,
        },
        # Right buttock
        {
            "type": "sphere",
            "center": [0.08, b.hip_height - 0.04, -0.10],
            "radius": 0.07,
        },
        # Crotch bridge
        {
            "type": "ellipsoid",
            "center": [0.0, b.crotch_height + 0.02, 0.0],
            "radii": [0.06, 0.03, 0.05],
        },
    ]
