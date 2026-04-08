"""Coverage verification: ensure garment covers required body zones.

Uses ray casting from coverage points outward to check if garment mesh
intercepts the ray.
"""

import numpy as np
import trimesh
from ..body.landmarks import get_coverage_points


def check_coverage(
    vertices: np.ndarray,
    faces: np.ndarray,
    body_vertices: np.ndarray | None = None,
) -> dict[str, bool]:
    """Check if the garment mesh covers all required zones.

    For each coverage zone, casts rays outward from the body surface
    and checks if they hit garment geometry.

    Returns:
        dict mapping zone name -> is_covered
    """
    # Build trimesh from garment
    garment_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    coverage_points = get_coverage_points()

    results = {}
    for zone_name, points in coverage_points.items():
        zone_covered = True
        for point in points:
            # Cast rays in multiple directions outward
            directions = _get_ray_directions(zone_name)
            hit_any = False
            for direction in directions:
                origin = point - direction * 0.001  # slightly inside body
                locations, index_ray, index_tri = garment_mesh.ray.intersects_location(
                    ray_origins=np.array([origin]),
                    ray_directions=np.array([direction]),
                )
                if len(locations) > 0:
                    # Check distance — garment should be close to body
                    dists = np.linalg.norm(locations - point, axis=1)
                    if np.min(dists) < 0.1:  # within 10cm
                        hit_any = True
                        break

            if not hit_any:
                zone_covered = False
                break

        results[zone_name] = zone_covered

    return results


def _get_ray_directions(zone_name: str) -> list[np.ndarray]:
    """Get outward ray directions for a coverage zone."""
    if "breast" in zone_name:
        # Rays pointing forward and slightly outward
        return [
            np.array([0, 0, 1]),    # forward
            np.array([0, 0.2, 1]), # slightly up-forward
            np.array([0, -0.2, 1]),  # slightly down-forward
        ]
    elif "crotch_front" in zone_name:
        return [
            np.array([0, 0, 1]),     # forward
            np.array([0, -0.3, 1]),  # down-forward
        ]
    elif "crotch_back" in zone_name:
        return [
            np.array([0, 0, -1]),    # backward
            np.array([0, -0.3, -1]), # down-backward
        ]
    else:
        # General: radial outward
        return [
            np.array([0, 0, 1]),
            np.array([0, 0, -1]),
            np.array([1, 0, 0]),
            np.array([-1, 0, 0]),
        ]


def coverage_score(results: dict[str, bool]) -> float:
    """Return fraction of zones that are covered (0.0 to 1.0)."""
    if not results:
        return 0.0
    return sum(1 for v in results.values() if v) / len(results)


def all_covered(results: dict[str, bool]) -> bool:
    """Check if all zones are covered."""
    return all(results.values())
