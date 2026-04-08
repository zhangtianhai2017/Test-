"""Loop-based bikini generator using Fourier harmonic curves.

Core algorithm:
1. Generate N closed loop curves around the body using low-frequency
   periodic functions (smooth, elegant mathematical curves)
2. Project/shrink-wrap loops onto body surface
3. Where loops cross coverage zones (breasts, crotch), widen into fabric panels
4. Non-coverage regions remain as narrow straps
5. All topology is inherently correct — each loop is one continuous mesh

The curves use Fourier series: Y(θ) = Y₀ + Σ aₖ·sin(kθ + φₖ), k=1..3
This guarantees smooth, closed, beautiful curves.
"""

import numpy as np
from dataclasses import dataclass, field
from .patch import GarmentPatch
from ..body.landmarks import get_landmarks
from ..body.mannequin import generate_full_body
from scipy.spatial import KDTree


# ── Coverage zone definitions (expanded for detection) ──────────────

@dataclass
class CoverageZone:
    """A region on the body that must be covered with fabric."""
    name: str
    center: np.ndarray       # 3D center point
    radius_y: float          # vertical extent
    radius_xz: float         # lateral extent
    min_strip_width: float   # minimum width when a loop crosses this zone


def _get_coverage_zones() -> list[CoverageZone]:
    """Define the mandatory coverage zones on the body."""
    lm = get_landmarks()
    return [
        CoverageZone(
            name="left_breast",
            center=lm["left_breast_apex"],
            radius_y=0.08,
            radius_xz=0.10,
            min_strip_width=0.12,
        ),
        CoverageZone(
            name="right_breast",
            center=lm["right_breast_apex"],
            radius_y=0.08,
            radius_xz=0.10,
            min_strip_width=0.12,
        ),
        CoverageZone(
            name="crotch",
            center=lm["crotch_center"] + np.array([0, 0.06, 0]),
            radius_y=0.14,
            radius_xz=0.10,
            min_strip_width=0.18,  # 18cm wide — covers full pubic triangle
        ),
    ]


# ── Body surface query ──────────────────────────────────────────────

class BodySurface:
    """Queryable body surface using a clean ellipsoidal torso model.

    Instead of raw mesh cross-sections (which include arms), uses
    a smooth multi-ellipsoid model interpolated from anatomical landmarks.
    This guarantees arm-free body contours.
    """

    def __init__(self):
        verts, _ = generate_full_body()
        self.verts = verts
        lm = get_landmarks()

        # Build torso-only KDTree (for surface projection)
        self._build_torso_kdtree(lm)

        # Build ellipsoidal torso profile
        self._build_torso_profile(lm)

    def _build_torso_kdtree(self, lm):
        """Build KDTree from torso-only vertices."""
        shoulder_y = (lm["left_shoulder"][1] + lm["right_shoulder"][1]) / 2

        # Aggressive arm filtering: at each height, only keep vertices
        # within the expected torso X range
        torso_mask = np.ones(len(self.verts), dtype=bool)
        for i, v in enumerate(self.verts):
            max_x = self._torso_x_limit(v[1], lm)
            if abs(v[0]) > max_x:
                torso_mask[i] = False

        self.torso_verts = self.verts[torso_mask]
        self.torso_tree = KDTree(self.torso_verts)

    def _torso_x_limit(self, y: float, lm: dict) -> float:
        """Maximum torso |X| at height y (excludes arms).

        Generous limits to keep all torso/hip vertices,
        but strict enough to exclude arm geometry.
        """
        shoulder_y = (lm["left_shoulder"][1] + lm["right_shoulder"][1]) / 2
        bust_y = lm["left_breast_apex"][1]
        waist_y = lm["waist_front"][1]
        hip_y = lm["hip_front"][1]
        crotch_y = lm["crotch_center"][1]

        if y > shoulder_y:
            return 0.14
        elif y > bust_y:
            t = (y - bust_y) / (shoulder_y - bust_y)
            return 0.16 - t * 0.02
        elif y > waist_y:
            return 0.16
        elif y > hip_y:
            t = (y - hip_y) / (waist_y - hip_y)
            return 0.20 - t * 0.04
        elif y > crotch_y:
            t = (y - crotch_y) / (hip_y - crotch_y)
            return 0.12 + t * 0.08
        else:
            return 0.12

    def _build_torso_profile(self, lm):
        """Build smooth torso cross-section profile from landmarks.

        At each height, the torso is modeled as an ellipse in the XZ plane
        with parameters (center_x, center_z, radius_x, radius_z_front, radius_z_back).
        """
        # Define profile keyframes from landmarks
        self.profile_y = []
        self.profile_rx = []      # X radius (half-width)
        self.profile_rz_f = []    # Z radius front
        self.profile_rz_b = []    # Z radius back
        self.profile_cx = []      # center X
        self.profile_cz = []      # center Z

        # From top to bottom
        keyframes = [
            # (y, rx, rz_front, rz_back)
            # Derived from actual body mesh and collision primitives
            (lm["neck_front"][1],  0.07, 0.06, 0.06),      # neck
            (lm["sternum_top"][1], 0.11, 0.10, 0.10),      # upper chest
            (lm["left_breast_apex"][1], 0.14, 0.13, 0.11), # bust (breasts protrude)
            (lm["left_underbust"][1], 0.14, 0.12, 0.10),   # underbust
            (lm["waist_front"][1], 0.14, 0.10, 0.10),      # waist
            (lm["hip_front"][1],   0.17, 0.10, 0.11),      # upper hip
            ((lm["hip_left"][1]+lm["hip_right"][1])/2, 0.18, 0.11, 0.14), # mid hip
            (lm["hip_back"][1],    0.16, 0.08, 0.14),      # lower hip
            (lm["crotch_front"][1], 0.09, 0.06, 0.11),     # upper crotch
            (lm["crotch_center"][1], 0.05, 0.03, 0.04),    # crotch center
        ]

        for y, rx, rzf, rzb in keyframes:
            self.profile_y.append(y)
            self.profile_rx.append(rx)
            self.profile_rz_f.append(rzf)
            self.profile_rz_b.append(rzb)
            self.profile_cx.append(0.0)
            self.profile_cz.append(0.0)

        self.profile_y = np.array(self.profile_y)
        self.profile_rx = np.array(self.profile_rx)
        self.profile_rz_f = np.array(self.profile_rz_f)
        self.profile_rz_b = np.array(self.profile_rz_b)

    def _interp_profile(self, y: float):
        """Interpolate torso profile at height y."""
        y_clamped = np.clip(y, self.profile_y.min(), self.profile_y.max())
        rx = np.interp(y_clamped, self.profile_y[::-1], self.profile_rx[::-1])
        rzf = np.interp(y_clamped, self.profile_y[::-1], self.profile_rz_f[::-1])
        rzb = np.interp(y_clamped, self.profile_y[::-1], self.profile_rz_b[::-1])
        return rx, rzf, rzb

    def get_center_at_height(self, y: float) -> np.ndarray:
        """Get the body center axis at a given height."""
        return np.array([0.0, y, 0.0])

    def get_surface_radius(self, y: float, theta: float) -> float:
        """Get body surface radius at height y and angle theta.

        Uses smooth ellipsoidal profile (no arm contamination).
        theta: 0=+Z (front), π/2=-X (left), π=-Z (back), 3π/2=+X (right)
        """
        rx, rzf, rzb = self._interp_profile(y)

        # Direction in XZ plane
        dx = -np.sin(theta)  # X component
        dz = np.cos(theta)   # Z component

        # Asymmetric ellipse: front and back have different Z radii
        rz = rzf if dz > 0 else rzb

        # Ellipse radius in direction (dx, dz):
        # r = rx * rz / sqrt((rz*dx)^2 + (rx*dz)^2)
        denom = np.sqrt((rz * dx) ** 2 + (rx * dz) ** 2)
        if denom < 1e-8:
            return rx
        return rx * rz / denom

    def project_point_to_surface(self, point: np.ndarray,
                                  offset: float = 0.008) -> np.ndarray:
        """Project a point onto the torso surface + offset.

        Uses torso-only KDTree for precise surface location,
        with fallback to ellipsoidal model.
        """
        dist, idx = self.torso_tree.query(point)
        surface_pt = self.torso_verts[idx].copy()

        # Outward direction from body center
        center = self.get_center_at_height(surface_pt[1])
        outward = point - center
        outward[1] = 0  # only push radially
        norm = np.linalg.norm(outward)
        if norm < 1e-6:
            outward = np.array([0.0, 0.0, 1.0])
        else:
            outward = outward / norm

        return surface_pt + outward * offset

    def get_max_torso_x(self, y: float) -> float:
        """Get maximum torso |X| at height y."""
        rx, _, _ = self._interp_profile(y)
        return rx

    def is_in_arm_region(self, point: np.ndarray) -> bool:
        """Check if a point is outside the torso envelope."""
        return abs(point[0]) > self.get_max_torso_x(point[1])


# ── Fourier loop curve generator ────────────────────────────────────

@dataclass
class LoopCurve:
    """A closed curve defined by Fourier harmonics in cylindrical coords."""
    y_center: float          # base height
    harmonics_y: list        # [(amplitude, frequency, phase), ...]
    harmonics_r: list        # [(amplitude, frequency, phase), ...] radius offset
    harmonics_w: list = None # [(amplitude, frequency, phase), ...] width modulation
    tilt_x: float = 0.0     # tilt of loop plane in X
    tilt_z: float = 0.0     # tilt of loop plane in Z


def generate_loop_curve(
    y_center: float,
    n_harmonics: int = 3,
    max_amp_y: float = 0.08,
    max_amp_r: float = 0.015,
    rng: np.random.Generator | None = None,
) -> LoopCurve:
    """Generate a random smooth closed curve using low-frequency Fourier series.

    Args:
        y_center: base height of the loop on the body
        n_harmonics: number of harmonics (1-3 for smooth curves)
        max_amp_y: max amplitude for Y (height) variation
        max_amp_r: max amplitude for radius offset
        rng: random generator
    """
    rng = rng or np.random.default_rng()

    harmonics_y = []
    harmonics_r = []

    for k in range(1, n_harmonics + 1):
        # Y harmonics: amplitude decreases with frequency
        amp_y = rng.uniform(0, max_amp_y / k)
        phase_y = rng.uniform(0, 2 * np.pi)
        harmonics_y.append((amp_y, k, phase_y))

        # Radius harmonics: small variation
        amp_r = rng.uniform(0, max_amp_r / k)
        phase_r = rng.uniform(0, 2 * np.pi)
        harmonics_r.append((amp_r, k, phase_r))

    return LoopCurve(
        y_center=y_center,
        harmonics_y=harmonics_y,
        harmonics_r=harmonics_r,
    )


def sample_loop_curve(
    curve: LoopCurve,
    body: BodySurface,
    n_samples: int = 128,
    garment_offset: float = 0.005,
) -> np.ndarray:
    """Sample a loop curve into 3D points on the body surface.

    Uses ONLY the smooth ellipsoidal torso model — no mesh projection
    on the centerline. This guarantees jitter-free, mathematically
    smooth curves.

    Returns: (n_samples, 3) array of 3D points forming a closed loop.
    """
    theta = np.linspace(0, 2 * np.pi, n_samples, endpoint=False)
    points = np.zeros((n_samples, 3))

    for i, t in enumerate(theta):
        # Y from Fourier series
        y = curve.y_center
        for amp, freq, phase in curve.harmonics_y:
            y += amp * np.sin(freq * t + phase)
        y = np.clip(y, 0.75, 1.55)

        # Radius offset from Fourier series
        r_offset = 0.0
        for amp, freq, phase in curve.harmonics_r:
            r_offset += amp * np.sin(freq * t + phase)

        # Smooth ellipsoidal body radius (no mesh = no jitter)
        body_r = body.get_surface_radius(y, t)
        r = body_r + garment_offset + r_offset

        # Cylindrical → Cartesian
        x = (-np.sin(t)) * r
        z = np.cos(t) * r

        points[i] = np.array([x, y, z])

    return points


# ── Coverage detection and width modulation ─────────────────────────

def compute_strip_widths(
    loop_points: np.ndarray,
    coverage_zones: list[CoverageZone],
    base_width: float = 0.015,
    curve: LoopCurve | None = None,
) -> np.ndarray:
    """Compute width at each point using coverage zones + periodic modulation.

    Width varies smoothly along the loop in two ways:
    1. Coverage zones widen the strip where it passes private areas
    2. Fourier width harmonics (from curve.harmonics_w) add periodic
       gradual variation — max 2-3 cycles per revolution

    Returns: (n_points,) array of widths.
    """
    n = len(loop_points)
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)

    # Start with base width
    widths = np.full(n, base_width)

    # 1. Coverage zone widening
    for zone in coverage_zones:
        for i, pt in enumerate(loop_points):
            dy = (pt[1] - zone.center[1]) / zone.radius_y
            dxz = np.sqrt(
                (pt[0] - zone.center[0])**2 + (pt[2] - zone.center[2])**2
            ) / zone.radius_xz
            dist = np.sqrt(dy**2 + dxz**2)

            if dist < 1.5:
                blend = max(0, 1.0 - dist / 1.5)
                blend = blend ** 0.5
                zone_width = base_width + (zone.min_strip_width - base_width) * blend
                widths[i] = max(widths[i], zone_width)

    # 2. Periodic width modulation (Fourier — smooth, 2-3 cycles max)
    if curve is not None and curve.harmonics_w:
        for amp, freq, phase in curve.harmonics_w:
            # Multiplicative: width *= (1 + a*sin(k*θ + φ))
            modulation = amp * np.sin(freq * theta + phase)
            widths *= (1.0 + modulation)

    # Ensure minimum width (max 25cm to allow full breast/crotch coverage)
    widths = np.clip(widths, base_width * 0.5, 0.25)

    return widths


def loop_covers_zone(
    loop_points: np.ndarray,
    zone: CoverageZone,
    threshold: float = 1.2,
) -> bool:
    """Check if a loop passes close enough to a coverage zone to cover it."""
    for pt in loop_points:
        dy = (pt[1] - zone.center[1]) / zone.radius_y
        dxz = np.sqrt(
            (pt[0] - zone.center[0])**2 + (pt[2] - zone.center[2])**2
        ) / zone.radius_xz
        if np.sqrt(dy**2 + dxz**2) < threshold:
            return True
    return False


# ── Strip mesh generation ───────────────────────────────────────────

def generate_strip_mesh(
    loop_points: np.ndarray,
    widths: np.ndarray,
    body: BodySurface,
    n_width: int = 6,
    garment_offset: float = 0.005,
) -> GarmentPatch:
    """Generate a closed strip mesh from loop points and varying widths.

    Anchors are placed where the strip wraps tightly around the body
    (narrow width regions and side-body contact points). This lets
    physics simulation keep the strip on while allowing natural drape.
    """
    n_length = len(loop_points)
    verts = []
    uvs = []

    for i in range(n_length):
        pt = loop_points[i]
        w = widths[i]

        # Compute tangent (circular — wraps around)
        i_next = (i + 1) % n_length
        i_prev = (i - 1) % n_length
        tangent = loop_points[i_next] - loop_points[i_prev]
        tangent = tangent / (np.linalg.norm(tangent) + 1e-8)

        # Compute outward normal from body center
        center = body.get_center_at_height(pt[1])
        outward = pt - center
        outward[1] = 0
        norm = np.linalg.norm(outward)
        if norm < 1e-6:
            outward = np.array([0.0, 0.0, 1.0])
        else:
            outward = outward / norm

        # Side direction: perpendicular to tangent and outward
        side = np.cross(tangent, outward)
        side_norm = np.linalg.norm(side)
        if side_norm < 1e-6:
            side = np.cross(tangent, np.array([0, 1, 0]))
            side_norm = np.linalg.norm(side)
        if side_norm > 1e-6:
            side = side / side_norm

        # Generate width vertices
        for j in range(n_width):
            t = (j / (n_width - 1)) - 0.5
            final_pt = pt + side * t * w
            verts.append(final_pt)
            uvs.append([i / n_length, j / (n_width - 1)])

    verts = np.array(verts, dtype=np.float64)
    uvs = np.array(uvs, dtype=np.float64)

    # Generate faces — closed loop
    faces = []
    for i in range(n_length):
        i_next = (i + 1) % n_length
        for j in range(n_width - 1):
            v0 = i * n_width + j
            v1 = v0 + 1
            v2 = i_next * n_width + j
            v3 = v2 + 1
            faces.append([v0, v2, v1])
            faces.append([v1, v2, v3])

    faces = np.array(faces, dtype=np.int32)

    # No anchor points — physics uses body surface collision + friction
    anchor_ids = []
    anchor_positions = []

    patch = GarmentPatch(
        name="loop_strip",
        vertices=verts,
        faces=faces,
        uvs=uvs,
        anchor_vertex_ids=anchor_ids,
        anchor_body_positions=anchor_positions,
    )
    patch.compute_normals()
    return patch


# ── Main loop bikini generator ──────────────────────────────────────

@dataclass
class LoopBikiniConfig:
    """Configuration for loop-based bikini generation."""
    n_loops: int = 6               # total loops (2 mandatory + extras)
    base_width: float = 0.015      # strap width (meters)
    garment_offset: float = 0.004  # matches collision_margin — starts at collision surface
    n_samples: int = 128           # points per loop curve
    n_width: int = 10              # vertices across strip (enough for coverage panels)


def _generate_base_coverage(body: BodySurface, garment_offset: float = 0.005) -> list[GarmentPatch]:
    """Generate minimal coverage patches for the three privacy zones.

    These are small fabric pieces that GUARANTEE coverage regardless
    of how the decorative loops are placed. They sit directly on the
    body surface as the bottom layer.
    """
    lm = get_landmarks()
    patches = []

    # ── Breast patches (one per side) ───────────────────────────
    for side in ["left", "right"]:
        x_sign = -1.0 if side == "left" else 1.0
        apex = lm[f"{side}_breast_apex"]
        outer = lm[f"{side}_breast_outer"]
        inner = lm[f"{side}_breast_inner"]
        underbust = lm[f"{side}_underbust"]

        cx = apex[0]
        cy = (apex[1] + underbust[1]) / 2
        rx = abs(outer[0] - inner[0]) / 2 + 0.015
        ry = abs(apex[1] - underbust[1]) / 2 + 0.01
        cz_base = (inner[2] + outer[2]) / 2
        rz = apex[2] - cz_base + 0.005

        nu, nv = 16, 16

        def make_breast_func(cx, cy, cz_base, rx, ry, rz, x_sign):
            def func(u, v):
                theta = u * np.pi * 0.65
                phi = (v - 0.5) * np.pi * 0.8
                x = cx + rx * np.sin(theta) * np.sin(phi) * x_sign
                y = cy + ry * np.cos(theta)
                z = cz_base + rz * np.sin(theta) * np.cos(phi) + garment_offset
                return np.array([x, y, z])
            return func

        patch = GarmentPatch.from_parametric(
            f"base_cup_{side}",
            make_breast_func(cx, cy, cz_base, rx, ry, rz, x_sign),
            (0.05, 0.95), (0.05, 0.95), nu, nv,
        )
        if side == "left":
            patch.faces = patch.faces[:, [0, 2, 1]]
            patch.compute_normals()

        # No anchor points — relies on body collision + friction
        patch.anchor_vertex_ids = []
        patch.anchor_body_positions = []
        patches.append(patch)

    # ── Bottom panel: front V-shape + crotch strip + back panel ──
    # Front panel: wide at top (hip level), narrows to crotch
    # Back panel: from crotch up to buttocks
    hip_front = lm["hip_front"]
    pubic = lm["pubic_top"]
    crotch_c = lm["crotch_center"]
    crotch_b = lm["crotch_back"]
    buttock_l = lm["left_buttock_apex"]
    buttock_r = lm["right_buttock_apex"]

    nu, nv = 20, 12

    # Front panel top (wide): Y≈0.96, Z≈0.08 (body surface front)
    front_top_y = hip_front[1] - 0.03   # ~0.966
    front_top_z = hip_front[2]           # ~0.086
    front_half_w = 0.06                  # half-width at top (~12cm total)

    # Crotch narrowest point
    crotch_half_w = 0.025                # half-width at crotch (~5cm)

    # Back panel top: Y≈0.92, Z≈-0.13
    back_top_y = (buttock_l[1] + buttock_r[1]) / 2  # ~0.927
    back_top_z = (buttock_l[2] + buttock_r[2]) / 2   # ~-0.14
    back_half_w = 0.055                  # half-width at back top

    def bottom_func(u, v):
        # u: 0=front top → 0.4=crotch center → 1.0=back top
        # v: 0=left edge → 1=right edge

        if u < 0.4:
            # Front panel: hip → crotch
            t = u / 0.4
            y = front_top_y * (1 - t) + crotch_c[1] * t
            z = front_top_z * (1 - t) + crotch_c[2] * t
            half_w = front_half_w * (1 - t) + crotch_half_w * t
        elif u < 0.6:
            # Crotch bridge: narrow strip between legs
            t = (u - 0.4) / 0.2
            y = crotch_c[1]
            z = crotch_c[2] * (1 - t) + crotch_b[2] * 0.3 * t
            half_w = crotch_half_w
        else:
            # Back panel: crotch → buttocks
            t = (u - 0.6) / 0.4
            y = crotch_c[1] * (1 - t) + back_top_y * t
            z_start = crotch_c[2] + (crotch_b[2] - crotch_c[2]) * 0.3
            z = z_start * (1 - t) + back_top_z * t
            half_w = crotch_half_w * (1 - t) + back_half_w * t

        x = (v - 0.5) * 2 * half_w
        return np.array([x, y, z + garment_offset * np.sign(z + 0.01)])

    patch = GarmentPatch.from_parametric(
        "base_bottom", bottom_func,
        (0.0, 1.0), (0.0, 1.0), nu, nv,
    )
    # No anchor points — relies on body collision + friction
    patch.anchor_vertex_ids = []
    patch.anchor_body_positions = []
    patches.append(patch)

    return patches


def generate_loop_bikini(
    seed: int | None = None,
    config: LoopBikiniConfig | None = None,
) -> list[GarmentPatch]:
    """Generate a bikini using the loop-based algorithm.

    Structure:
    - Base layer: 3 small coverage patches (2 breast cups + 1 crotch)
      guaranteeing the three privacy zones are always covered
    - Loop layer: N closed Fourier-harmonic loops with periodic width
      modulation — these create the strappy design aesthetic

    Curves are purely mathematical (ellipsoidal model, no mesh projection)
    ensuring perfectly smooth, jitter-free lines.

    Width varies along each loop using Fourier harmonics (max 2-3 cycles
    per revolution) for beautiful periodic gradients.
    """
    rng = np.random.default_rng(seed)
    cfg = config or LoopBikiniConfig()
    body = BodySurface()
    zones = _get_coverage_zones()
    lm = get_landmarks()

    patches = []

    # No independent base patches — coverage comes from loops
    # widening at privacy zones (breast/crotch). Every piece of
    # fabric is part of a structurally supported loop.

    # ── Helper: make a loop patch with width harmonics ──────────
    def make_patch(loop, name):
        pts = sample_loop_curve(loop, body, cfg.n_samples, cfg.garment_offset)
        widths = compute_strip_widths(pts, zones, cfg.base_width, curve=loop)
        patch = generate_strip_mesh(pts, widths, body, cfg.n_width, cfg.garment_offset)
        patch.name = name
        return patch

    def rand_width_harmonics():
        """Random periodic width modulation: 1-2 harmonics, freq 1-3."""
        h = []
        n = rng.integers(1, 3)  # 1 or 2 harmonics
        for _ in range(n):
            amp = rng.uniform(0.15, 0.5)   # ±15-50% width variation
            freq = rng.integers(1, 4)       # 1, 2, or 3 cycles per revolution
            phase = rng.uniform(0, 2 * np.pi)
            h.append((amp, int(freq), phase))
        return h

    # ── Breast loop ─────────────────────────────────────────────
    breast_y = (lm["left_breast_apex"][1] + lm["right_breast_apex"][1]) / 2
    breast_loop = LoopCurve(
        y_center=breast_y,
        harmonics_y=[
            (rng.uniform(0.005, 0.015), 1, rng.uniform(0, 2 * np.pi)),
            (rng.uniform(0.002, 0.008), 2, rng.uniform(0, 2 * np.pi)),
        ],
        harmonics_r=[],  # no radial offset — stay on body surface
        harmonics_w=rand_width_harmonics(),
    )
    patches.append(make_patch(breast_loop, "loop_breast"))

    # ── Crotch loop (dips at front and back) ────────────────────
    hip_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2
    crotch_y = lm["crotch_center"][1]
    y_mid = (hip_y + crotch_y) / 2 + 0.02
    # Dip must reach crotch_center Y — full depth for coverage
    dip_amp = y_mid - crotch_y

    crotch_loop = LoopCurve(
        y_center=y_mid,
        harmonics_y=[
            (dip_amp, 2, -np.pi / 2 + rng.uniform(-0.05, 0.05)),
            (rng.uniform(0.003, 0.010), 1, rng.uniform(0, 2 * np.pi)),
        ],
        harmonics_r=[],  # no radial offset — stay on body surface
        harmonics_w=rand_width_harmonics(),
    )
    patches.append(make_patch(crotch_loop, "loop_crotch"))

    # ── Extra decorative loops ──────────────────────────────────
    n_extra = max(0, cfg.n_loops - 2)
    y_low = lm["hip_front"][1]
    y_high = lm["left_shoulder"][1] - 0.03

    for i in range(n_extra):
        y_center = rng.uniform(y_low, y_high)
        loop = LoopCurve(
            y_center=y_center,
            harmonics_y=[
                (rng.uniform(0.005, 0.03), 1, rng.uniform(0, 2 * np.pi)),
                (rng.uniform(0.003, 0.015), 2, rng.uniform(0, 2 * np.pi)),
            ],
            harmonics_r=[],  # no radial offset — stay on body surface
            harmonics_w=rand_width_harmonics(),
        )
        patches.append(make_patch(loop, f"loop_extra_{i}"))

    # ── Project ALL vertices onto body surface ───────────────────
    # Ensures every garment vertex starts touching the body.
    _project_all_to_body(patches, body, cfg.garment_offset)

    return patches


def _project_all_to_body(patches: list, body: 'BodySurface', offset: float):
    """Project every garment vertex onto the body surface + offset.

    For each vertex, compute its cylindrical coords (y, theta),
    look up the body radius, and place it at body_radius + offset.
    This guarantees the garment starts flush against the body.
    """
    for patch in patches:
        for i in range(len(patch.vertices)):
            v = patch.vertices[i]
            y = v[1]

            # Skip vertices outside torso range
            if y < 0.75 or y > 1.50:
                continue

            # Cylindrical coords
            x, z = v[0], v[2]
            theta = np.arctan2(-x, z)
            if theta < 0:
                theta += 2 * np.pi

            radial_dist = np.sqrt(x**2 + z**2)
            if radial_dist < 1e-6:
                continue

            body_r = body.get_surface_radius(y, theta)
            target_r = body_r + offset

            # Scale to target radius
            scale = target_r / radial_dist
            patch.vertices[i][0] = x * scale
            patch.vertices[i][2] = z * scale

        patch.compute_normals()
