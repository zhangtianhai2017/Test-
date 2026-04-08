"""Coverage verification: ensure garment covers required body zones.

Uses proximity-based checking: for each coverage point, finds the nearest
garment vertex and checks if it's within a threshold distance.
More robust than ray casting for thin cloth meshes.
"""

import numpy as np
from scipy.spatial import cKDTree
from ..body.landmarks import get_coverage_points


def check_coverage(
    vertices: np.ndarray,
    faces: np.ndarray,
    body_vertices: np.ndarray | None = None,
    max_distance: float = 0.06,  # 6cm — max distance to count as "covered"
) -> dict[str, bool]:
    """Check if the garment mesh covers all required zones.

    For each coverage zone point, finds the nearest garment vertex.
    If within max_distance, the zone is considered covered.

    Args:
        vertices: garment vertex positions (N, 3)
        faces: garment face indices (M, 3)
        max_distance: maximum distance to count as covered

    Returns:
        dict mapping zone name -> is_covered
    """
    if len(vertices) == 0:
        return {name: False for name in get_coverage_points()}

    # Build KD-tree of garment vertices for fast nearest-neighbor lookup
    tree = cKDTree(vertices)
    coverage_points = get_coverage_points()

    results = {}
    for zone_name, points in coverage_points.items():
        zone_covered = True
        for point in points:
            dist, idx = tree.query(point)
            if dist > max_distance:
                zone_covered = False
                break
        results[zone_name] = zone_covered

    return results


def coverage_score(results: dict[str, bool]) -> float:
    """Return fraction of zones that are covered (0.0 to 1.0)."""
    if not results:
        return 0.0
    return sum(1 for v in results.values() if v) / len(results)


def all_covered(results: dict[str, bool]) -> bool:
    """Check if all zones are covered."""
    return all(results.values())
