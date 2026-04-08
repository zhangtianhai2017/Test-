"""GPU-accelerated cloth simulation using Taichi.

Implements a mass-spring system with:
- Stretch, shear, and bend springs
- Body collision with friction
- Anchor constraints (pinned vertices)
- Elastic tension modeling
- Verlet integration on GPU
"""

import taichi as ti
import numpy as np
from ..config import PHYSICS


@ti.data_oriented
class ClothSimulator:
    """GPU cloth simulator using Taichi mass-spring model."""

    def __init__(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        anchor_ids: list[int],
        anchor_positions: list[np.ndarray],
        collision_primitives: list[dict],
        config: object | None = None,
    ):
        cfg = config or PHYSICS
        self.dt = cfg.dt
        self.num_steps = cfg.num_steps
        self.gravity = cfg.gravity
        self.damping = cfg.damping
        self.friction = cfg.friction_coefficient
        self.collision_margin = cfg.collision_margin
        self.stretch_k = cfg.stretch_stiffness
        self.shear_k = cfg.shear_stiffness
        self.bend_k = cfg.bend_stiffness
        self.mass = cfg.cloth_mass_per_vertex

        self.n_verts = len(vertices)
        self.n_faces = len(faces)

        # Build spring connectivity from mesh edges
        edges = set()
        face_adj = {}  # edge -> list of opposite vertex for bend springs

        for f in faces:
            for i in range(3):
                a, b = int(f[i]), int(f[(i + 1) % 3])
                c = int(f[(i + 2) % 3])  # opposite vertex
                edge = (min(a, b), max(a, b))
                edges.add(edge)
                if edge not in face_adj:
                    face_adj[edge] = []
                face_adj[edge].append(c)

        # Stretch springs = mesh edges
        stretch_springs = list(edges)

        # Shear springs = face diagonals (connecting non-adjacent vertices)
        shear_springs = []
        for f in faces:
            for i in range(3):
                a, b = int(f[i]), int(f[(i + 2) % 3])
                edge = (min(a, b), max(a, b))
                if edge not in edges:
                    shear_springs.append(edge)
                    edges.add(edge)

        # Bend springs = connect opposite vertices of adjacent faces
        bend_springs = []
        for edge_key, opposites in face_adj.items():
            if len(opposites) == 2:
                a, b = opposites
                bend_edge = (min(a, b), max(a, b))
                if bend_edge not in edges:
                    bend_springs.append(bend_edge)
                    edges.add(bend_edge)

        all_springs = stretch_springs + shear_springs + bend_springs
        n_stretch = len(stretch_springs)
        n_shear = len(shear_springs)
        self.n_springs = len(all_springs)

        # --- Taichi fields ---
        self.pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)
        self.old_pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)
        self.vel = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)
        self.force = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)
        self.initial_pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)

        # Springs: [idx_a, idx_b]
        self.spring_indices = ti.Vector.field(2, dtype=ti.i32, shape=self.n_springs)
        self.spring_rest_len = ti.field(dtype=ti.f32, shape=self.n_springs)
        self.spring_stiffness = ti.field(dtype=ti.f32, shape=self.n_springs)

        # Anchors
        self.n_anchors = len(anchor_ids)
        self.anchor_ids_field = ti.field(dtype=ti.i32, shape=max(self.n_anchors, 1))
        self.anchor_targets = ti.Vector.field(3, dtype=ti.f32, shape=max(self.n_anchors, 1))
        self.is_anchored = ti.field(dtype=ti.i32, shape=self.n_verts)

        # Collision primitives
        # Support spheres and ellipsoids
        max_prims = max(len(collision_primitives), 1)
        self.n_colliders = len(collision_primitives)
        self.collider_type = ti.field(dtype=ti.i32, shape=max_prims)  # 0=sphere, 1=ellipsoid
        self.collider_center = ti.Vector.field(3, dtype=ti.f32, shape=max_prims)
        self.collider_radii = ti.Vector.field(3, dtype=ti.f32, shape=max_prims)

        # --- Initialize ---
        pos_np = vertices.astype(np.float32)
        self.pos.from_numpy(pos_np)
        self.old_pos.from_numpy(pos_np)
        self.initial_pos.from_numpy(pos_np)
        self.vel.from_numpy(np.zeros_like(pos_np))

        # Springs
        spring_np = np.array(all_springs, dtype=np.int32)
        self.spring_indices.from_numpy(spring_np)

        # Compute rest lengths and assign stiffness
        rest_lens = np.zeros(self.n_springs, dtype=np.float32)
        stiffness = np.zeros(self.n_springs, dtype=np.float32)
        for i, (a, b) in enumerate(all_springs):
            rest_lens[i] = np.linalg.norm(pos_np[a] - pos_np[b])
            if i < n_stretch:
                stiffness[i] = self.stretch_k
            elif i < n_stretch + n_shear:
                stiffness[i] = self.shear_k
            else:
                stiffness[i] = self.bend_k
        self.spring_rest_len.from_numpy(rest_lens)
        self.spring_stiffness.from_numpy(stiffness)

        # Anchors
        anchored = np.zeros(self.n_verts, dtype=np.int32)
        if self.n_anchors > 0:
            anchor_ids_np = np.array(anchor_ids, dtype=np.int32)
            anchor_targets_np = np.array([p.astype(np.float32) for p in anchor_positions])
            self.anchor_ids_field.from_numpy(anchor_ids_np)
            self.anchor_targets.from_numpy(anchor_targets_np)
            for aid in anchor_ids:
                if 0 <= aid < self.n_verts:
                    anchored[aid] = 1
        self.is_anchored.from_numpy(anchored)

        # Collision primitives
        for i, prim in enumerate(collision_primitives):
            center = np.array(prim["center"], dtype=np.float32)
            if prim["type"] == "sphere":
                r = prim["radius"]
                self.collider_type[i] = 0
                self.collider_center[i] = ti.Vector(center.tolist())
                self.collider_radii[i] = ti.Vector([r, r, r])
            elif prim["type"] == "ellipsoid":
                radii = np.array(prim["radii"], dtype=np.float32)
                self.collider_type[i] = 1
                self.collider_center[i] = ti.Vector(center.tolist())
                self.collider_radii[i] = ti.Vector(radii.tolist())

    @ti.kernel
    def _apply_forces(self):
        """Apply gravity and spring forces."""
        # Reset forces
        for i in range(self.n_verts):
            self.force[i] = ti.Vector([0.0, self.gravity * self.mass, 0.0])

        # Spring forces
        for s in range(self.n_springs):
            a = self.spring_indices[s][0]
            b = self.spring_indices[s][1]
            diff = self.pos[b] - self.pos[a]
            dist = diff.norm()
            if dist > 1e-7:
                rest = self.spring_rest_len[s]
                k = self.spring_stiffness[s]
                # Hooke's law with direction
                f = k * (dist - rest) * diff / dist
                self.force[a] += f
                self.force[b] -= f

    @ti.kernel
    def _integrate(self, dt: ti.f32, damping: ti.f32):
        """Verlet integration step."""
        for i in range(self.n_verts):
            if self.is_anchored[i] == 0:
                # Verlet integration
                new_pos = (
                    self.pos[i]
                    + (self.pos[i] - self.old_pos[i]) * damping
                    + self.force[i] / self.mass * dt * dt
                )
                self.old_pos[i] = self.pos[i]
                self.pos[i] = new_pos

    @ti.kernel
    def _apply_anchors(self):
        """Pin anchored vertices to their target positions."""
        for i in range(self.n_anchors):
            aid = self.anchor_ids_field[i]
            if aid >= 0 and aid < self.n_verts:
                self.pos[aid] = self.anchor_targets[i]
                self.old_pos[aid] = self.anchor_targets[i]

    @ti.kernel
    def _collide_body(self, friction: ti.f32, margin: ti.f32):
        """Handle collision with body primitives including friction."""
        for i in range(self.n_verts):
            if self.is_anchored[i] == 1:
                continue

            for c in range(self.n_colliders):
                center = self.collider_center[c]
                radii = self.collider_radii[c]

                # Transform to ellipsoid-local space
                local = self.pos[i] - center
                # Normalized distance (in ellipsoid space)
                nx = local[0] / radii[0]
                ny = local[1] / radii[1]
                nz = local[2] / radii[2]
                dist_sq = nx * nx + ny * ny + nz * nz

                if dist_sq < (1.0 + margin) * (1.0 + margin):
                    # Inside or too close to body surface
                    dist = ti.sqrt(dist_sq)
                    if dist < 1e-7:
                        dist = 1e-7

                    # Normal direction in world space
                    normal = ti.Vector([
                        nx / radii[0],
                        ny / radii[1],
                        nz / radii[2],
                    ])
                    normal = normal / normal.norm()

                    # Push out to surface + margin
                    penetration = (1.0 + margin) - dist
                    correction = normal * penetration * ti.sqrt(
                        radii[0] * radii[0] * normal[0] * normal[0]
                        + radii[1] * radii[1] * normal[1] * normal[1]
                        + radii[2] * radii[2] * normal[2] * normal[2]
                    )
                    self.pos[i] += correction

                    # Friction: reduce tangential velocity
                    vel = self.pos[i] - self.old_pos[i]
                    vel_n = vel.dot(normal) * normal
                    vel_t = vel - vel_n

                    # Coulomb friction model
                    vel_t_mag = vel_t.norm()
                    if vel_t_mag > 1e-7:
                        friction_force = friction * ti.abs(vel_n.norm())
                        if friction_force > vel_t_mag:
                            friction_force = vel_t_mag
                        vel_t = vel_t * (1.0 - friction_force / vel_t_mag)

                    # Update: only keep tangential component (bounce = 0)
                    self.old_pos[i] = self.pos[i] - vel_t

    def simulate(self) -> np.ndarray:
        """Run the full simulation and return final vertex positions."""
        for step in range(self.num_steps):
            self._apply_forces()
            self._integrate(self.dt, self.damping)
            self._apply_anchors()
            self._collide_body(self.friction, self.collision_margin)

        return self.pos.to_numpy()

    def get_max_displacement(self) -> float:
        """Compute maximum vertex displacement from initial position."""
        final = self.pos.to_numpy()
        initial = self.initial_pos.to_numpy()
        displacements = np.linalg.norm(final - initial, axis=1)

        # Ignore anchored vertices
        anchored = self.is_anchored.to_numpy()
        displacements[anchored == 1] = 0

        return float(np.max(displacements)) if len(displacements) > 0 else 0.0
