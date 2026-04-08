"""GarmentAssembly: combines multiple GarmentPatches into a full bikini."""

import numpy as np
from dataclasses import dataclass, field
from .patch import GarmentPatch


@dataclass
class AttachmentConstraint:
    """Defines a connection between garment and body or between patches."""
    patch_name: str
    vertex_ids: list[int]
    target_positions: list[np.ndarray]  # body surface points
    stiffness: float = 1.0  # 0=loose, 1=rigid


@dataclass
class GarmentAssembly:
    """Complete bikini garment = collection of patches + constraints."""
    patches: list[GarmentPatch] = field(default_factory=list)
    constraints: list[AttachmentConstraint] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # design description, style tags

    def add_patch(self, patch: GarmentPatch):
        self.patches.append(patch)

    def add_constraint(self, constraint: AttachmentConstraint):
        self.constraints.append(constraint)

    def get_patch(self, name: str) -> GarmentPatch | None:
        for p in self.patches:
            if p.name == name:
                return p
        return None

    def total_vertices(self) -> int:
        return sum(p.vertex_count() for p in self.patches)

    def total_faces(self) -> int:
        return sum(p.face_count() for p in self.patches)

    def merge_to_single_mesh(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Merge all patches into one mesh. Returns (vertices, faces, uvs)."""
        if not self.patches:
            return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32), np.zeros((0, 2))

        all_verts = []
        all_faces = []
        all_uvs = []
        offset = 0

        for patch in self.patches:
            all_verts.append(patch.vertices)
            all_faces.append(patch.faces + offset)
            all_uvs.append(patch.uvs)
            offset += patch.vertex_count()

        return (
            np.vstack(all_verts),
            np.vstack(all_faces),
            np.vstack(all_uvs),
        )

    def get_all_anchors(self) -> tuple[list[int], list[np.ndarray]]:
        """Collect all anchor vertex IDs and body positions across patches.

        Returns global vertex indices (offset by patch position in assembly).
        """
        anchor_ids = []
        anchor_positions = []
        offset = 0

        for patch in self.patches:
            for local_id, body_pos in zip(
                patch.anchor_vertex_ids, patch.anchor_body_positions
            ):
                anchor_ids.append(local_id + offset)
                anchor_positions.append(body_pos)
            offset += patch.vertex_count()

        return anchor_ids, anchor_positions
