"""GarmentPatch: fundamental mesh primitive for garment pieces.

Each patch is a triangulated surface generated from a parametric function
f(u, v) -> (x, y, z), carrying vertices, faces, UVs, and anchor info.
"""

import numpy as np
from dataclasses import dataclass, field


@dataclass
class GarmentPatch:
    """A single piece of garment geometry."""
    name: str
    vertices: np.ndarray          # (N, 3) float64
    faces: np.ndarray             # (M, 3) int32 — triangle indices
    uvs: np.ndarray               # (N, 2) float64 — per-vertex UV
    normals: np.ndarray | None = None  # (N, 3) computed lazily
    anchor_vertex_ids: list[int] = field(default_factory=list)
    anchor_body_positions: list[np.ndarray] = field(default_factory=list)
    material_name: str = "default"

    def compute_normals(self) -> np.ndarray:
        """Compute per-vertex normals via face-area weighting."""
        normals = np.zeros_like(self.vertices)
        v0 = self.vertices[self.faces[:, 0]]
        v1 = self.vertices[self.faces[:, 1]]
        v2 = self.vertices[self.faces[:, 2]]
        face_normals = np.cross(v1 - v0, v2 - v0)
        for i in range(3):
            np.add.at(normals, self.faces[:, i], face_normals)
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.normals = normals / norms
        return self.normals

    def vertex_count(self) -> int:
        return len(self.vertices)

    def face_count(self) -> int:
        return len(self.faces)

    @staticmethod
    def from_parametric(
        name: str,
        func,
        u_range: tuple[float, float] = (0, 1),
        v_range: tuple[float, float] = (0, 1),
        nu: int = 20,
        nv: int = 20,
    ) -> "GarmentPatch":
        """Create a patch from a parametric surface function.

        Args:
            func: callable(u, v) -> np.ndarray of shape (3,)
            u_range, v_range: parameter bounds
            nu, nv: subdivision count
        """
        us = np.linspace(u_range[0], u_range[1], nu)
        vs = np.linspace(v_range[0], v_range[1], nv)

        vertices = []
        uvs = []
        for i, u in enumerate(us):
            for j, v in enumerate(vs):
                vertices.append(func(u, v))
                uvs.append([i / (nu - 1), j / (nv - 1)])

        vertices = np.array(vertices, dtype=np.float64)
        uvs = np.array(uvs, dtype=np.float64)

        faces = []
        for i in range(nu - 1):
            for j in range(nv - 1):
                idx = i * nv + j
                faces.append([idx, idx + nv, idx + 1])
                faces.append([idx + 1, idx + nv, idx + nv + 1])

        faces = np.array(faces, dtype=np.int32)
        patch = GarmentPatch(name=name, vertices=vertices, faces=faces, uvs=uvs)
        patch.compute_normals()
        return patch

    def translate(self, offset: np.ndarray) -> "GarmentPatch":
        """Return a translated copy."""
        return GarmentPatch(
            name=self.name,
            vertices=self.vertices + offset,
            faces=self.faces.copy(),
            uvs=self.uvs.copy(),
            normals=self.normals.copy() if self.normals is not None else None,
            anchor_vertex_ids=self.anchor_vertex_ids.copy(),
            anchor_body_positions=[p.copy() for p in self.anchor_body_positions],
            material_name=self.material_name,
        )

    def transform(self, matrix: np.ndarray) -> "GarmentPatch":
        """Apply a 4x4 transform matrix. Returns new patch."""
        rot = matrix[:3, :3]
        trans = matrix[:3, 3]
        new_verts = (self.vertices @ rot.T) + trans
        new_normals = None
        if self.normals is not None:
            new_normals = self.normals @ rot.T
            norms = np.linalg.norm(new_normals, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            new_normals = new_normals / norms
        return GarmentPatch(
            name=self.name,
            vertices=new_verts,
            faces=self.faces.copy(),
            uvs=self.uvs.copy(),
            normals=new_normals,
            anchor_vertex_ids=self.anchor_vertex_ids.copy(),
            anchor_body_positions=[p.copy() for p in self.anchor_body_positions],
            material_name=self.material_name,
        )

    def get_edge_vertices(self, edge: str = "top") -> np.ndarray:
        """Get vertex indices along a mesh edge.

        For a grid mesh with nu x nv verts:
        - 'top': first row (u=0)
        - 'bottom': last row (u=max)
        - 'left': first column (v=0)
        - 'right': last column (v=max)
        """
        n = self.vertex_count()
        # Estimate grid dims from vertex count and face pattern
        nv = 1
        if len(self.faces) > 0:
            # For a nu x nv grid, row stride = nv
            # Find nv from face connectivity
            first_face = self.faces[0]
            nv = first_face[1] - first_face[0]  # stride between rows
            if nv <= 0:
                nv = int(np.sqrt(n))
        nu = n // nv if nv > 0 else n

        if edge == "top":
            return np.arange(nv)
        elif edge == "bottom":
            return np.arange((nu - 1) * nv, nu * nv)
        elif edge == "left":
            return np.arange(0, n, nv)
        elif edge == "right":
            return np.arange(nv - 1, n, nv)
        return np.array([], dtype=np.int32)
