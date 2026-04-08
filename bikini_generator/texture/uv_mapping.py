"""UV mapping utilities for texture application."""

import numpy as np


def normalize_uvs(uvs: np.ndarray) -> np.ndarray:
    """Normalize UV coordinates to [0, 1] range."""
    if len(uvs) == 0:
        return uvs
    uv_min = uvs.min(axis=0)
    uv_max = uvs.max(axis=0)
    uv_range = uv_max - uv_min
    uv_range[uv_range == 0] = 1.0
    return (uvs - uv_min) / uv_range


def pack_uv_islands(
    patches_uvs: list[np.ndarray],
    padding: float = 0.02,
) -> list[np.ndarray]:
    """Pack multiple UV islands into a single [0,1] UV space.

    Simple row-based packing. Each patch gets a rectangular region.
    """
    n = len(patches_uvs)
    if n == 0:
        return []

    # Compute a grid layout
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))

    cell_w = (1.0 - padding * (cols + 1)) / cols
    cell_h = (1.0 - padding * (rows + 1)) / rows

    result = []
    for idx, uvs in enumerate(patches_uvs):
        row = idx // cols
        col = idx % cols

        # Normalize this patch's UVs to [0,1]
        norm_uv = normalize_uvs(uvs.copy())

        # Scale and offset into the grid cell
        offset_x = padding + col * (cell_w + padding)
        offset_y = padding + row * (cell_h + padding)

        packed = norm_uv * np.array([cell_w, cell_h]) + np.array([offset_x, offset_y])
        result.append(packed)

    return result
