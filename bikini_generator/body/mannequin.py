"""Body mesh loading and collision primitive extraction.

Loads the real ZBrush body mesh from assets/base_body.obj,
converts from cm to meters, and provides collision primitives
for the cloth physics simulation.
"""

import os
import numpy as np
from ..config import BODY


def _find_mesh_path() -> str:
    """Resolve the body mesh path relative to the project root."""
    # Try relative to this file first, then CWD
    this_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(this_dir))
    candidates = [
        os.path.join(project_root, BODY.mesh_path),
        BODY.mesh_path,
        os.path.join(os.getcwd(), BODY.mesh_path),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"Body mesh not found. Searched: {candidates}. "
        f"Please place the OBJ file at {BODY.mesh_path}"
    )


def load_body_mesh() -> tuple[np.ndarray, np.ndarray]:
    """Load the real body mesh from OBJ file.

    Returns (vertices, faces) in meters.
    Vertices are scaled from the original ZBrush cm coordinates.
    """
    path = _find_mesh_path()
    vertices = []
    faces = []

    with open(path) as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == 'v' and len(parts) >= 4:
                vertices.append([
                    float(parts[1]),
                    float(parts[2]),
                    float(parts[3]),
                ])
            elif parts[0] == 'f':
                face = []
                for p in parts[1:]:
                    idx = int(p.split('/')[0]) - 1  # OBJ is 1-indexed
                    face.append(idx)
                # Triangulate if quad
                if len(face) == 3:
                    faces.append(face)
                elif len(face) == 4:
                    faces.append([face[0], face[1], face[2]])
                    faces.append([face[0], face[2], face[3]])

    vertices = np.array(vertices, dtype=np.float64) * BODY.mesh_scale
    faces = np.array(faces, dtype=np.int32)
    return vertices, faces


# Cache for loaded mesh
_cached_mesh: tuple[np.ndarray, np.ndarray] | None = None


def generate_full_body() -> tuple[np.ndarray, np.ndarray]:
    """Return the full body mesh (vertices, faces).

    Uses cached version after first load.
    """
    global _cached_mesh
    if _cached_mesh is None:
        _cached_mesh = load_body_mesh()
    return _cached_mesh


def get_body_collision_primitives() -> list[dict]:
    """Return simplified collision shapes for physics simulation.

    Derived from the real mesh dimensions. Each primitive is a dict
    with 'type', 'center', and shape-specific params.
    """
    return [
        # Upper torso (ribcage to shoulders)
        {
            "type": "ellipsoid",
            "center": [0.0, 1.34, -0.005],
            "radii": [0.14, 0.08, 0.10],
        },
        # Lower torso (waist to bust)
        {
            "type": "ellipsoid",
            "center": [0.0, 1.16, 0.0],
            "radii": [0.13, 0.08, 0.09],
        },
        # Waist region
        {
            "type": "ellipsoid",
            "center": [0.0, 1.03, 0.0],
            "radii": [0.13, 0.04, 0.09],
        },
        # Hip region
        {
            "type": "ellipsoid",
            "center": [0.0, 0.97, 0.02],
            "radii": [0.16, 0.05, 0.10],
        },
        # Left breast
        {
            "type": "sphere",
            "center": [-0.073, 1.298, 0.105],
            "radius": 0.050,
        },
        # Right breast
        {
            "type": "sphere",
            "center": [0.072, 1.297, 0.105],
            "radius": 0.050,
        },
        # Left buttock
        {
            "type": "sphere",
            "center": [-0.062, 0.926, -0.130],
            "radius": 0.065,
        },
        # Right buttock
        {
            "type": "sphere",
            "center": [0.061, 0.929, -0.130],
            "radius": 0.065,
        },
        # Crotch bridge
        {
            "type": "ellipsoid",
            "center": [0.0, 0.81, -0.01],
            "radii": [0.06, 0.04, 0.06],
        },
    ]
