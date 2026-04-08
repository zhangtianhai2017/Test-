"""Decorative elements: chains, rings, charms, bows, tassels, cutouts."""

import numpy as np
from .patch import GarmentPatch


def chain_dangle(
    attach_point: np.ndarray,
    length: float = 0.05,
    n_links: int = 8,
    link_radius: float = 0.003,
) -> GarmentPatch:
    """A dangling chain from an attachment point."""
    verts = []
    uvs = []
    n_around = 6

    for i in range(n_links):
        center_y = attach_point[1] - (i / n_links) * length
        # Alternate link orientation
        for j in range(n_around):
            angle = 2 * np.pi * j / n_around
            if i % 2 == 0:
                x = attach_point[0] + link_radius * np.cos(angle)
                z = attach_point[2] + link_radius * np.sin(angle)
            else:
                x = attach_point[0] + link_radius * np.sin(angle)
                z = attach_point[2] + link_radius * np.cos(angle)
            verts.append([x, center_y, z])
            uvs.append([i / n_links, j / n_around])

    verts = np.array(verts)
    uvs = np.array(uvs)

    faces = []
    for i in range(n_links - 1):
        for j in range(n_around):
            j_next = (j + 1) % n_around
            v0 = i * n_around + j
            v1 = i * n_around + j_next
            v2 = (i + 1) * n_around + j
            v3 = (i + 1) * n_around + j_next
            faces.append([v0, v2, v1])
            faces.append([v1, v2, v3])

    patch = GarmentPatch(
        name="deco_chain",
        vertices=verts,
        faces=np.array(faces, dtype=np.int32),
        uvs=uvs,
        material_name="metal",
    )
    patch.anchor_vertex_ids = list(range(n_around))
    patch.anchor_body_positions = [attach_point] * n_around
    return patch


def bow(
    center: np.ndarray,
    size: float = 0.02,
    n: int = 12,
) -> GarmentPatch:
    """A decorative bow shape."""
    verts = []
    uvs = []

    # Two loops (butterfly shape)
    for loop in range(2):
        sign = 1 if loop == 0 else -1
        for i in range(n):
            t = i / (n - 1)
            angle = t * np.pi
            x = center[0] + sign * size * np.sin(angle) * 0.7
            y = center[1] + size * np.cos(angle) * 0.3
            z = center[2] + 0.005
            verts.append([x, y, z])
            uvs.append([loop * 0.5 + t * 0.5, 0.5])

    # Knot center
    for j in range(4):
        angle = j / 4 * 2 * np.pi
        verts.append([
            center[0] + 0.003 * np.cos(angle),
            center[1] + 0.003 * np.sin(angle),
            center[2] + 0.006,
        ])
        uvs.append([0.5, 0.5])

    verts = np.array(verts)
    uvs = np.array(uvs)

    # Simple fan triangulation
    faces = []
    knot_start = 2 * n
    for loop in range(2):
        base = loop * n
        for i in range(n - 1):
            faces.append([base + i, base + i + 1, knot_start])
    for i in range(3):
        faces.append([knot_start + i, knot_start + i + 1, knot_start])

    patch = GarmentPatch(
        name="deco_bow",
        vertices=verts,
        faces=np.array(faces, dtype=np.int32),
        uvs=uvs,
        material_name="fabric",
    )
    return patch


def tassel(
    attach_point: np.ndarray,
    length: float = 0.04,
    n_strands: int = 8,
    strand_width: float = 0.002,
) -> GarmentPatch:
    """Decorative tassel hanging from a point."""
    verts = []
    uvs = []
    faces = []

    for s in range(n_strands):
        angle = 2 * np.pi * s / n_strands
        spread = 0.008
        tip_x = attach_point[0] + spread * np.cos(angle)
        tip_z = attach_point[2] + spread * np.sin(angle)

        base_idx = len(verts)
        # Two vertices per strand (top and bottom)
        verts.append([attach_point[0], attach_point[1], attach_point[2]])
        verts.append([tip_x, attach_point[1] - length, tip_z])
        # Side vertices for width
        verts.append([attach_point[0] + strand_width, attach_point[1], attach_point[2]])
        verts.append([tip_x + strand_width, attach_point[1] - length, tip_z])

        uvs.extend([[s / n_strands, 1], [s / n_strands, 0],
                     [(s + 0.5) / n_strands, 1], [(s + 0.5) / n_strands, 0]])

        faces.append([base_idx, base_idx + 1, base_idx + 2])
        faces.append([base_idx + 2, base_idx + 1, base_idx + 3])

    patch = GarmentPatch(
        name="deco_tassel",
        vertices=np.array(verts),
        faces=np.array(faces, dtype=np.int32),
        uvs=np.array(uvs),
        material_name="fabric",
    )
    patch.anchor_vertex_ids = [i * 4 for i in range(n_strands)]
    patch.anchor_body_positions = [attach_point] * n_strands
    return patch


def metal_ring(
    center: np.ndarray,
    radius: float = 0.012,
    tube_radius: float = 0.002,
    n_ring: int = 16,
    n_tube: int = 6,
) -> GarmentPatch:
    """Decorative metal ring/O-ring."""
    verts = []
    uvs = []
    for i in range(n_ring):
        theta = 2 * np.pi * i / n_ring
        for j in range(n_tube):
            phi = 2 * np.pi * j / n_tube
            x = center[0] + (radius + tube_radius * np.cos(phi)) * np.cos(theta)
            y = center[1] + (radius + tube_radius * np.cos(phi)) * np.sin(theta)
            z = center[2] + tube_radius * np.sin(phi)
            verts.append([x, y, z])
            uvs.append([i / n_ring, j / n_tube])

    verts = np.array(verts)
    uvs = np.array(uvs)
    faces = []
    for i in range(n_ring):
        i_next = (i + 1) % n_ring
        for j in range(n_tube):
            j_next = (j + 1) % n_tube
            v0 = i * n_tube + j
            v1 = i * n_tube + j_next
            v2 = i_next * n_tube + j
            v3 = i_next * n_tube + j_next
            faces.append([v0, v2, v1])
            faces.append([v1, v2, v3])

    return GarmentPatch(
        name="deco_ring",
        vertices=verts,
        faces=np.array(faces, dtype=np.int32),
        uvs=uvs,
        material_name="metal",
    )


DECORATION_TYPES = {
    "chain": chain_dangle,
    "bow": bow,
    "tassel": tassel,
    "ring": metal_ring,
}
