"""Cloth simulation using Position-Based Dynamics (PBD).

Key physics:
- NO anchor points — garment stays on purely through collision + friction + tension
- Body collision uses a pre-computed continuous surface model (no gaps)
- Elastic tension via shortened rest lengths (fabric presses against body)
- Coulomb friction model prevents sliding along body surface
"""

import taichi as ti
import numpy as np
from ..config import PHYSICS


def _build_body_surface_lut(n_y=128, n_theta=128):
    """Pre-compute body surface radius lookup table.

    Uses the BodySurface ellipsoidal model from loop_generator to get
    a continuous, gap-free body surface representation.

    Returns: (lut, y_min, y_max) where lut is (n_y, n_theta) float32 array
    """
    from ..garment.loop_generator import BodySurface
    body = BodySurface()

    # Y range covering the garment region
    y_min = 0.75
    y_max = 1.50

    lut = np.zeros((n_y, n_theta), dtype=np.float32)
    y_values = np.linspace(y_min, y_max, n_y)
    theta_values = np.linspace(0, 2 * np.pi, n_theta, endpoint=False)

    for iy, y in enumerate(y_values):
        for it, theta in enumerate(theta_values):
            lut[iy, it] = body.get_surface_radius(y, theta)

    return lut, y_min, y_max


@ti.data_oriented
class ClothSimulator:
    """Cloth simulator with mesh-based collision — no anchor points needed."""

    def __init__(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        anchor_ids: list[int] = None,
        anchor_positions: list[np.ndarray] = None,
        collision_primitives: list[dict] = None,
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

        # --- Build body surface LUT for gap-free collision ---
        self.lut_ny = 128
        self.lut_ntheta = 128
        lut, self.y_min, self.y_max = _build_body_surface_lut(
            self.lut_ny, self.lut_ntheta
        )
        self.body_lut = ti.field(dtype=ti.f32, shape=(self.lut_ny, self.lut_ntheta))
        self.body_lut.from_numpy(lut)

        # --- Taichi fields ---
        self.pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)
        self.old_pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)
        self.initial_pos = ti.Vector.field(3, dtype=ti.f32, shape=self.n_verts)

        self.edge_indices = ti.Vector.field(2, dtype=ti.i32, shape=max(self.n_edges, 1))
        self.edge_rest_len = ti.field(dtype=ti.f32, shape=max(self.n_edges, 1))
        self.inv_mass = ti.field(dtype=ti.f32, shape=self.n_verts)

        # --- Initialize ---
        pos_np = vertices.astype(np.float32)
        self.pos.from_numpy(pos_np)
        self.old_pos.from_numpy(pos_np)
        self.initial_pos.from_numpy(pos_np)

        # Edges — rest lengths scaled by 0.88 for strong elastic tension
        # The garment wants to be 12% shorter than its initial span,
        # creating strong inward pressure that keeps it pressed against body
        elastic_scale = 0.88
        if self.n_edges > 0:
            edge_np = np.array(all_edges, dtype=np.int32)
            self.edge_indices.from_numpy(edge_np)
            rest_lens = np.array([
                np.linalg.norm(pos_np[a] - pos_np[b]) * elastic_scale
                for a, b in all_edges
            ], dtype=np.float32)
            self.edge_rest_len.from_numpy(rest_lens)

        # All vertices have equal mass (no anchors)
        inv_mass = np.ones(self.n_verts, dtype=np.float32) / self.mass
        self.inv_mass.from_numpy(inv_mass)

        # Keep legacy anchor fields for API compatibility but don't use them
        self.n_anchors = 0
        self.is_anchored = ti.field(dtype=ti.i32, shape=self.n_verts)
        self.is_anchored.from_numpy(np.zeros(self.n_verts, dtype=np.int32))

    @ti.kernel
    def _predict_positions(self, dt: ti.f32, damping: ti.f32, gravity: ti.f32):
        """Verlet integration: apply gravity and velocity damping."""
        for i in range(self.n_verts):
            vel = (self.pos[i] - self.old_pos[i]) * damping
            self.old_pos[i] = self.pos[i]
            self.pos[i] = self.pos[i] + vel + ti.Vector([0.0, gravity * dt * dt, 0.0])

    @ti.kernel
    def _solve_distance_constraints(self, compliance: ti.f32):
        """PBD distance constraint solver."""
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

            error = dist - rest
            correction = error * diff / (dist * w_sum)
            stiffness_factor = 1.0 / (1.0 + compliance)

            self.pos[a] += correction * w_a * stiffness_factor
            self.pos[b] -= correction * w_b * stiffness_factor

    @ti.kernel
    def _collide_body_surface(self, friction: ti.f32, margin: ti.f32,
                               y_min: ti.f32, y_max: ti.f32,
                               lut_ny: ti.i32, lut_ntheta: ti.i32):
        """Collision with continuous body surface using LUT.

        For each vertex:
        1. Convert position to cylindrical coords (y, theta)
        2. Look up body surface radius from pre-computed table
        3. If vertex is inside body + margin, push outward
        4. Apply Coulomb friction to tangential velocity
        """
        for i in range(self.n_verts):
            px = self.pos[i][0]
            py = self.pos[i][1]
            pz = self.pos[i][2]

            # Skip vertices outside the torso Y range
            if py < y_min - 0.05 or py > y_max + 0.05:
                continue

            # Cylindrical coords from body center axis (0, y, 0)
            # theta: 0=+Z(front), pi/2=-X(left), pi=-Z(back)
            theta = ti.atan2(-px, pz)  # atan2(-x, z) to match convention
            if theta < 0:
                theta += 2.0 * 3.14159265358979

            radial_dist = ti.sqrt(px * px + pz * pz)

            # Clamp Y for LUT lookup
            y_clamped = ti.max(y_min, ti.min(y_max, py))

            # Bilinear interpolation in LUT
            y_frac = (y_clamped - y_min) / (y_max - y_min) * (lut_ny - 1)
            t_frac = theta / (2.0 * 3.14159265358979) * lut_ntheta

            iy0 = ti.cast(ti.floor(y_frac), ti.i32)
            it0 = ti.cast(ti.floor(t_frac), ti.i32)
            iy1 = ti.min(iy0 + 1, lut_ny - 1)
            it1 = (it0 + 1) % lut_ntheta
            iy0 = ti.max(0, ti.min(iy0, lut_ny - 1))
            it0 = it0 % lut_ntheta

            fy = y_frac - ti.floor(y_frac)
            ft = t_frac - ti.floor(t_frac)

            # Bilinear interpolation
            r00 = self.body_lut[iy0, it0]
            r01 = self.body_lut[iy0, it1]
            r10 = self.body_lut[iy1, it0]
            r11 = self.body_lut[iy1, it1]

            body_radius = (r00 * (1 - fy) * (1 - ft) +
                           r01 * (1 - fy) * ft +
                           r10 * fy * (1 - ft) +
                           r11 * fy * ft)

            min_radius = body_radius + margin

            # Friction band: apply friction when within 3x margin of body
            friction_band = margin * 3.0
            max_radius = body_radius + friction_band

            if radial_dist > 1e-6 and radial_dist < max_radius:
                # --- Collision: push out if penetrating ---
                if radial_dist < min_radius:
                    scale = min_radius / radial_dist
                    px = px * scale
                    pz = pz * scale
                    radial_dist = min_radius
                    self.pos[i] = ti.Vector([px, py, pz])

                # --- Surface friction (applies in entire friction band) ---
                # Strength: 100% at surface, fading to 0% at edge of band
                dist_from_surface = radial_dist - min_radius
                band_width = max_radius - min_radius
                proximity = 1.0 - dist_from_surface / band_width  # 1=touching, 0=far
                proximity = ti.max(0.0, proximity)

                vel = self.pos[i] - self.old_pos[i]

                # Normal direction (radial outward)
                normal = ti.Vector([px, 0.0, pz])
                n_len = normal.norm()
                if n_len > 1e-7:
                    normal = normal / n_len

                # Decompose velocity
                vel_n = vel.dot(normal) * normal
                vel_t = vel - vel_n
                vel_t_mag = vel_t.norm()

                # Friction damps tangential velocity proportional to proximity
                if vel_t_mag > 1e-7:
                    # retain=0 at surface (fully stuck), retain=1 at band edge (free)
                    retain = ti.max(0.0, 1.0 - friction * proximity)
                    vel_t = vel_t * retain

                self.old_pos[i] = self.pos[i] - vel_t

    @ti.kernel
    def _attract_to_body(self, strength: ti.f32, margin: ti.f32,
                          y_min: ti.f32, y_max: ti.f32,
                          lut_ny: ti.i32, lut_ntheta: ti.i32):
        """Pull vertices toward body surface — models elastic inward pressure.

        Vertices far from the body get pulled back. This prevents loops
        from drifting away. Combined with collision (prevents going inside),
        creates a stable equilibrium at body_surface + margin.
        """
        for i in range(self.n_verts):
            px = self.pos[i][0]
            py = self.pos[i][1]
            pz = self.pos[i][2]

            if py < y_min - 0.05 or py > y_max + 0.05:
                continue

            theta = ti.atan2(-px, pz)
            if theta < 0:
                theta += 2.0 * 3.14159265358979

            radial_dist = ti.sqrt(px * px + pz * pz)
            if radial_dist < 1e-6:
                continue

            y_clamped = ti.max(y_min, ti.min(y_max, py))
            y_frac = (y_clamped - y_min) / (y_max - y_min) * (lut_ny - 1)
            t_frac = theta / (2.0 * 3.14159265358979) * lut_ntheta

            iy0 = ti.cast(ti.floor(y_frac), ti.i32)
            it0 = ti.cast(ti.floor(t_frac), ti.i32)
            iy1 = ti.min(iy0 + 1, lut_ny - 1)
            it1 = (it0 + 1) % lut_ntheta
            iy0 = ti.max(0, ti.min(iy0, lut_ny - 1))
            it0 = it0 % lut_ntheta

            fy = y_frac - ti.floor(y_frac)
            ft = t_frac - ti.floor(t_frac)

            body_radius = (self.body_lut[iy0, it0] * (1 - fy) * (1 - ft) +
                           self.body_lut[iy0, it1] * (1 - fy) * ft +
                           self.body_lut[iy1, it0] * fy * (1 - ft) +
                           self.body_lut[iy1, it1] * fy * ft)

            target_r = body_radius + margin
            gap = radial_dist - target_r

            # Only attract if vertex is ABOVE the surface (gap > 0)
            # Attraction grows linearly with distance
            if gap > 0.001:  # more than 1mm away
                # Pull toward target radius
                pull = gap * strength
                new_r = radial_dist - pull
                if new_r < target_r:
                    new_r = target_r
                scale = new_r / radial_dist
                self.pos[i][0] = px * scale
                self.pos[i][2] = pz * scale

    def simulate(self) -> np.ndarray:
        """Run the full PBD simulation and return final vertex positions.

        No anchors, no attraction — pure physics:
        - Gravity pulls down
        - Distance constraints (with elastic tension) resist stretching
        - Body collision prevents penetration
        - Surface friction resists sliding
        """
        for step in range(self.num_steps):
            self._predict_positions(self.dt, self.damping, self.gravity)

            for _ in range(self.num_constraint_iters):
                self._solve_distance_constraints(self.stretch_compliance)
                self._collide_body_surface(
                    self.friction, self.collision_margin,
                    self.y_min, self.y_max,
                    self.lut_ny, self.lut_ntheta,
                )

        return self.pos.to_numpy()

    def get_max_displacement(self) -> float:
        """Compute maximum vertex displacement from initial position."""
        final = self.pos.to_numpy()
        initial = self.initial_pos.to_numpy()
        displacements = np.linalg.norm(final - initial, axis=1)
        valid = np.isfinite(displacements)
        if valid.any():
            return float(np.max(displacements[valid]))
        return 0.0
