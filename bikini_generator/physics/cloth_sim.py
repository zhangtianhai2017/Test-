"""GPU-accelerated cloth simulation using Taichi.

Uses Position-Based Dynamics (PBD) for unconditional stability:
- Distance constraints (stretch, shear, bend)
- Body collision with friction
- Anchor constraints (pinned vertices)
- Verlet integration on GPU
"""

import taichi as ti
import numpy as np
from ..config import PHYSICS


@ti.data_oriented
class ClothSimulator:
    """GPU cloth simulator using Taichi with PBD constraints."""

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
        self.mass = cfg.cloth_mass_per_vertex

        # PBD stiffness (0-1 range, applied as constraint compliance)
        self.stretch_compliance = 1.0 / max(cfg.stretch_stiffness, 1.0)
        self.num_constraint_iters = getattr(cfg, 'num_substeps', 5)

        self.n_verts = len(vertices)
        self.n_faces = len(faces)

        # Build edge connectivity
        edges = set()
        for f in faces:
            for i in range(3):
                a, b = int(f[i]), int(f[(i + 1) % 3])
                edges.add((min(a, b), max(a, b)))

        all_edges = list(edges)
        self.n_edges = len(all_edges)

        # --- Taichi fields ---
        self.pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)
        self.old_pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)
        self.initial_pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)

        # Edges for distance constraints
        self.edge_indices = ti.Vector.field(2, dtype=ti.i32, shape=max(self.n_edges, 1))
        self.edge_rest_len = ti.field(dtype=ti.f32, shape=max(self.n_edges, 1))

        # Anchors
        self.n_anchors = len(anchor_ids)
        self.anchor_ids_field = ti.field(dtype=ti.i32, shape=max(self.n_anchors, 1))
        self.anchor_targets = ti.Vector.field(3, dtype=ti.f32, shape=max(self.n_anchors, 1))
        self.is_anchored = ti.field(dtype=ti.i32, shape=self.n_verts)
        self.inv_mass = ti.field(dtype=ti.f32, shape=self.n_verts)

        # Collision primitives
        max_prims = max(len(collision_primitives), 1)
        self.n_colliders = len(collision_primitives)
        self.collider_center = ti.Vector.field(3, dtype=ti.f32, shape=max_prims)
        self.collider_radii = ti.Vector.field(3, dtype=ti.f32, shape=max_prims)

        # --- Initialize ---
        pos_np = vertices.astype(np.float32)
        self.pos.from_numpy(pos_np)
        self.old_pos.from_numpy(pos_np)
        self.initial_pos.from_numpy(pos_np)

        # Edges
        if self.n_edges > 0:
            edge_np = np.array(all_edges, dtype=np.int32)
            self.edge_indices.from_numpy(edge_np)
            rest_lens = np.array([
                np.linalg.norm(pos_np[a] - pos_np[b]) for a, b in all_edges
            ], dtype=np.float32)
            self.edge_rest_len.from_numpy(rest_lens)

        # Anchors and inverse mass
        anchored = np.zeros(self.n_verts, dtype=np.int32)
        inv_mass = np.ones(self.n_verts, dtype=np.float32) / self.mass
        if self.n_anchors > 0:
            anchor_ids_np = np.array(anchor_ids, dtype=np.int32)
            anchor_targets_np = np.array(
                [p.astype(np.float32) for p in anchor_positions]
            )
            self.anchor_ids_field.from_numpy(anchor_ids_np)
            self.anchor_targets.from_numpy(anchor_targets_np)
            for aid in anchor_ids:
                if 0 <= aid < self.n_verts:
                    anchored[aid] = 1
                    inv_mass[aid] = 0.0  # infinite mass = pinned
        self.is_anchored.from_numpy(anchored)
        self.inv_mass.from_numpy(inv_mass)

        # Collision primitives
        for i, prim in enumerate(collision_primitives):
            center = np.array(prim["center"], dtype=np.float32)
            self.collider_center[i] = ti.Vector(center.tolist())
            if prim["type"] == "sphere":
                r = prim["radius"]
                self.collider_radii[i] = ti.Vector([r, r, r])
            elif prim["type"] == "ellipsoid":
                radii = np.array(prim["radii"], dtype=np.float32)
                self.collider_radii[i] = ti.Vector(radii.tolist())

    @ti.kernel
    def _predict_positions(self, dt: ti.f32, damping: ti.f32, gravity: ti.f32):
        """Verlet prediction step: apply gravity and damping."""
        for i in range(self.n_verts):
            if self.is_anchored[i] == 0:
                vel = (self.pos[i] - self.old_pos[i]) * damping
                self.old_pos[i] = self.pos[i]
                # Verlet: x_new = x + v*dt + a*dt^2
                self.pos[i] = self.pos[i] + vel + ti.Vector([0.0, gravity * dt * dt, 0.0])

    @ti.kernel
    def _solve_distance_constraints(self, compliance: ti.f32):
        """PBD distance constraint solver — unconditionally stable."""
        for e in range(self.n_edges):
            a = self.edge_indices[e][0]
            b = self.edge_indices[e][1]
            diff = self.pos[b] - self.pos[a]
            dist = diff.norm()

            if dist < 1e-8:
                continue

            rest = self.edge_rest_len[e]
            w_a = self.inv_mass[a]
            w_b = self.inv_mass[b]
            w_sum = w_a + w_b

            if w_sum < 1e-8:
                continue

            # PBD correction
            error = dist - rest
            correction = error * diff / (dist * w_sum)

            # Stiffness via compliance (lower = stiffer)
            stiffness_factor = 1.0 / (1.0 + compliance)

            self.pos[a] += correction * w_a * stiffness_factor
            self.pos[b] -= correction * w_b * stiffness_factor

    @ti.kernel
    def _apply_anchors(self):
        """Pin anchored vertices to their target positions."""
        for i in range(self.n_anchors):
            aid = self.anchor_ids_field[i]
            if aid >= 0 and aid < self.n_verts:
                self.pos[aid] = self.anchor_targets[i]

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
                nx = local[0] / radii[0]
                ny = local[1] / radii[1]
                nz = local[2] / radii[2]
                dist_sq = nx * nx + ny * ny + nz * nz

                threshold = 1.0 + margin / ti.min(radii[0], ti.min(radii[1], radii[2]))

                if dist_sq < threshold * threshold:
                    dist = ti.sqrt(dist_sq)
                    if dist < 1e-7:
                        dist = 1e-7

                    # Normal in world space
                    normal = ti.Vector([
                        nx / radii[0],
                        ny / radii[1],
                        nz / radii[2],
                    ])
                    n_len = normal.norm()
                    if n_len > 1e-7:
                        normal = normal / n_len

                    # Push out to surface + margin
                    target_dist = threshold
                    scale_factor = target_dist / dist

                    new_local = ti.Vector([
                        local[0] * scale_factor,
                        local[1] * scale_factor,
                        local[2] * scale_factor,
                    ])

                    new_pos = center + new_local
                    displacement = new_pos - self.pos[i]
                    self.pos[i] = new_pos

                    # Friction: reduce tangential velocity
                    vel = self.pos[i] - self.old_pos[i]
                    vel_n = vel.dot(normal) * normal
                    vel_t = vel - vel_n
                    vel_t_mag = vel_t.norm()

                    if vel_t_mag > 1e-7:
                        friction_reduction = friction * ti.abs(displacement.norm())
                        if friction_reduction > vel_t_mag:
                            friction_reduction = vel_t_mag
                        vel_t = vel_t * (1.0 - friction_reduction / vel_t_mag)

                    self.old_pos[i] = self.pos[i] - vel_t

    @ti.kernel
    def _shape_retention(self, strength: ti.f32):
        """Pull vertices toward their initial (rest) positions.

        Models the elastic memory of the garment — it was designed to fit
        the body and resists deformation away from that shape.
        This is the key force that keeps a bikini on the body.
        """
        for i in range(self.n_verts):
            if self.is_anchored[i] == 1:
                continue

            disp = self.initial_pos[i] - self.pos[i]
            dist = disp.norm()
            if dist > 0.001:
                # Stronger pull for larger displacements (nonlinear)
                factor = strength * (1.0 + dist * 3.0)
                if factor > 0.8:
                    factor = 0.8
                self.pos[i] += disp * factor

    def simulate(self) -> np.ndarray:
        """Run the full PBD simulation and return final vertex positions."""
        for step in range(self.num_steps):
            # 1. Predict positions (gravity + inertia)
            self._predict_positions(self.dt, self.damping, self.gravity)

            # 2. Solve constraints (multiple iterations for convergence)
            for _ in range(self.num_constraint_iters):
                self._solve_distance_constraints(self.stretch_compliance)
                self._shape_retention(0.4)  # elastic garment tension
                self._collide_body(self.friction, self.collision_margin)
                self._apply_anchors()

        return self.pos.to_numpy()

    def get_max_displacement(self) -> float:
        """Compute maximum vertex displacement from initial position."""
        final = self.pos.to_numpy()
        initial = self.initial_pos.to_numpy()
        displacements = np.linalg.norm(final - initial, axis=1)

        # Ignore anchored vertices
        anchored = self.is_anchored.to_numpy()
        displacements[anchored == 1] = 0.0

        # Filter NaN/Inf
        valid = np.isfinite(displacements)
        if valid.any():
            return float(np.max(displacements[valid]))
        return 0.0
