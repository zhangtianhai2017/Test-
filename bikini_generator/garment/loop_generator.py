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
            radius_y=0.06,
            radius_xz=0.08,
            min_strip_width=0.10,
        ),
        CoverageZone(
            name="right_breast",
            center=lm["right_breast_apex"],
            radius_y=0.06,
            radius_xz=0.08,
            min_strip_width=0.10,
        ),
        CoverageZone(
            name="crotch",
            center=lm["crotch_center"] + np.array([0, 0.04, 0]),
            radius_y=0.08,
            radius_xz=0.07,
            min_strip_width=0.09,
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
    garment_offset: float = 0.008,
) -> np.ndarray:
    """Sample a loop curve into 3D points projected onto the body surface.

    The curve wraps around the body in cylindrical coordinates.
    At each angle θ, the height Y is modulated by Fourier harmonics.
    The radius follows the body surface contour.

    Returns: (n_samples, 3) array of 3D points forming a closed loop.
    """
    theta = np.linspace(0, 2 * np.pi, n_samples, endpoint=False)
    points = np.zeros((n_samples, 3))

    for i, t in enumerate(theta):
        # Compute Y from Fourier series (smooth periodic height variation)
        y = curve.y_center
        for amp, freq, phase in curve.harmonics_y:
            y += amp * np.sin(freq * t + phase)

        # Clamp Y to valid body range
        y = np.clip(y, 0.75, 1.55)

        # Compute radius offset from Fourier series
        r_offset = 0.0
        for amp, freq, phase in curve.harmonics_r:
            r_offset += amp * np.sin(freq * t + phase)

        # Get body surface radius at this (y, theta) and add offset
        body_r = body.get_surface_radius(y, t)
        r = body_r + garment_offset + r_offset

        # Convert cylindrical to Cartesian
        center = body.get_center_at_height(y)
        x = center[0] + (-np.sin(t)) * r
        z = center[2] + np.cos(t) * r

        # Clamp X to torso width (no arm penetration)
        max_x = body.get_max_torso_x(y)
        if abs(x) > max_x:
            x = np.sign(x) * max_x

        points[i] = np.array([x, y, z])

    # Smooth the loop to remove any jitter from clamping
    # Circular Gaussian smoothing
    kernel_size = max(3, n_samples // 30)
    if kernel_size % 2 == 0:
        kernel_size += 1
    half_k = kernel_size // 2
    smoothed = np.zeros_like(points)
    for i in range(n_samples):
        weights = np.zeros(kernel_size)
        for j in range(kernel_size):
            offset = j - half_k
            weights[j] = np.exp(-0.5 * (offset / (half_k / 2)) ** 2)
        weights /= weights.sum()
        for j in range(kernel_size):
            idx = (i + j - half_k) % n_samples
            smoothed[i] += points[idx] * weights[j]

    # Project each point onto body surface for tight fit
    for i in range(n_samples):
        smoothed[i] = body.project_point_to_surface(smoothed[i], garment_offset)

    return smoothed


# ── Coverage detection and width modulation ─────────────────────────

def compute_strip_widths(
    loop_points: np.ndarray,
    coverage_zones: list[CoverageZone],
    base_width: float = 0.012,
    max_width: float = 0.08,
) -> np.ndarray:
    """Compute width at each point of the loop based on coverage zone proximity.

    Returns: (n_points,) array of widths.
    """
    n = len(loop_points)
    widths = np.full(n, base_width)

    for zone in coverage_zones:
        for i, pt in enumerate(loop_points):
            # Distance from zone center (ellipsoidal)
            dy = (pt[1] - zone.center[1]) / zone.radius_y
            dxz = np.sqrt(
                (pt[0] - zone.center[0])**2 + (pt[2] - zone.center[2])**2
            ) / zone.radius_xz
            dist = np.sqrt(dy**2 + dxz**2)

            if dist < 1.5:
                # Smooth falloff: full width at center, tapering to base
                blend = max(0, 1.0 - dist / 1.5)
                blend = blend ** 0.5  # square root for smoother transition
                zone_width = base_width + (zone.min_strip_width - base_width) * blend
                widths[i] = max(widths[i], zone_width)

    # Smooth the widths to avoid abrupt changes
    kernel_size = max(3, n // 20)
    if kernel_size % 2 == 0:
        kernel_size += 1
    # Circular smoothing
    padded = np.concatenate([widths[-kernel_size:], widths, widths[:kernel_size]])
    kernel = np.ones(kernel_size) / kernel_size
    smoothed = np.convolve(padded, kernel, mode='same')
    widths = smoothed[kernel_size:kernel_size + n]

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
    garment_offset: float = 0.008,
) -> GarmentPatch:
    """Generate a closed strip mesh from loop points and varying widths.

    The strip follows the loop curve, with width varying based on
    coverage zone proximity. Both edges are projected onto the body surface.

    Args:
        loop_points: (N, 3) closed loop centerline
        widths: (N,) width at each point
        body: body surface for projection
        n_width: number of vertices across the strip width
        garment_offset: distance above body surface

    Returns:
        GarmentPatch with closed topology
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
            # Fallback: use up direction
            side = np.cross(tangent, np.array([0, 1, 0]))
            side_norm = np.linalg.norm(side)
        if side_norm > 1e-6:
            side = side / side_norm

        # Generate width vertices
        for j in range(n_width):
            t = (j / (n_width - 1)) - 0.5  # -0.5 to 0.5
            offset_pt = pt + side * t * w

            # Project onto body surface to follow contours
            projected = body.project_point_to_surface(offset_pt, garment_offset)

            # Blend between projected and offset (more projection at edges)
            blend = abs(t) * 0.6  # edges follow body more
            final_pt = offset_pt * (1 - blend) + projected * blend

            verts.append(final_pt)
            uvs.append([i / n_length, j / (n_width - 1)])

    verts = np.array(verts, dtype=np.float64)
    uvs = np.array(uvs, dtype=np.float64)

    # Generate faces — closed loop (last row connects to first row)
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

    patch = GarmentPatch(
        name="loop_strip",
        vertices=verts,
        faces=faces,
        uvs=uvs,
    )
    patch.compute_normals()
    return patch


# ── Main loop bikini generator ──────────────────────────────────────

@dataclass
class LoopBikiniConfig:
    """Configuration for loop-based bikini generation."""
    n_loops: int = 8               # total number of loops
    base_width: float = 0.015      # strap width (meters)
    garment_offset: float = 0.005  # distance above body
    n_samples: int = 128           # points per loop curve
    n_width: int = 6               # vertices across strip
    n_harmonics: int = 3           # Fourier harmonics (1-3)
    max_amp_y: float = 0.08        # max height variation
    max_amp_r: float = 0.015       # max radius variation


def generate_loop_bikini(
    seed: int | None = None,
    config: LoopBikiniConfig | None = None,
) -> list[GarmentPatch]:
    """Generate a bikini using the loop-based algorithm.

    Algorithm:
    1. Generate mandatory loops that cover breast and crotch zones
    2. Generate additional decorative/structural loops
    3. Project all loops onto body surface
    4. Widen strips at coverage zones
    5. Return list of GarmentPatch meshes

    The breast loop is a gentle horizontal ring at bust height.
    The crotch loop uses -cos(2θ) to dip at front AND back (crotch)
    while staying high at the sides (hips).

    Args:
        seed: random seed for reproducibility
        config: generation parameters

    Returns:
        List of GarmentPatch (one per loop strip)
    """
    rng = np.random.default_rng(seed)
    cfg = config or LoopBikiniConfig()
    body = BodySurface()
    zones = _get_coverage_zones()
    lm = get_landmarks()

    patches = []

    def make_patch(loop, name):
        pts = sample_loop_curve(loop, body, cfg.n_samples, cfg.garment_offset)
        widths = compute_strip_widths(pts, zones, cfg.base_width)
        patch = generate_strip_mesh(pts, widths, body, cfg.n_width, cfg.garment_offset)
        patch.name = name
        return patch

    # ── Phase 1: Mandatory breast loop ──────────────────────────

    breast_y = (lm["left_breast_apex"][1] + lm["right_breast_apex"][1]) / 2
    breast_loop = LoopCurve(
        y_center=breast_y,
        harmonics_y=[
            # Gentle undulation, stay near breast height
            (rng.uniform(0.005, 0.02), 1, rng.uniform(0, 2 * np.pi)),
            (rng.uniform(0.003, 0.01), 2, rng.uniform(0, 2 * np.pi)),
        ],
        harmonics_r=[
            (rng.uniform(0.002, 0.008), 2, rng.uniform(0, 2 * np.pi)),
        ],
    )
    patches.append(make_patch(breast_loop, "loop_breast"))

    # ── Phase 2: Mandatory crotch loop ──────────────────────────
    # Key: use -cos(2θ) so it dips at front (θ=0) and back (θ=π),
    # stays high at sides (θ=π/2, 3π/2) = hip height
    #
    # Y_side (hip) ≈ 0.97,  Y_dip (crotch) ≈ 0.82
    # Y_mid = 0.895,  amplitude = 0.075
    # -cos(2θ) = sin(2θ + π/2) → use freq=2, phase=-π/2

    hip_y = (lm["hip_left"][1] + lm["hip_right"][1]) / 2  # ~0.975
    crotch_y = lm["crotch_center"][1]  # ~0.781
    y_mid = (hip_y + crotch_y) / 2 + 0.02  # slightly higher
    dip_amp = (hip_y - crotch_y) / 2 - 0.01  # how deep it dips

    crotch_loop = LoopCurve(
        y_center=y_mid,
        harmonics_y=[
            # Primary: -cos(2θ) → dip at front and back
            (dip_amp, 2, -np.pi / 2 + rng.uniform(-0.15, 0.15)),
            # Small k=1 for asymmetry (front vs back can differ slightly)
            (rng.uniform(0.005, 0.02), 1, rng.uniform(0, 2 * np.pi)),
        ],
        harmonics_r=[
            (rng.uniform(0.003, 0.008), 2, rng.uniform(0, 2 * np.pi)),
        ],
    )
    patches.append(make_patch(crotch_loop, "loop_crotch"))

    # ── Phase 3: Additional structural/decorative loops ─────────

    n_extra = max(0, cfg.n_loops - 2)
    # Constrain extras to torso range (not below hip, not above shoulder)
    y_low = lm["hip_front"][1]
    y_high = lm["left_shoulder"][1] - 0.03

    for i in range(n_extra):
        y_center = rng.uniform(y_low, y_high)
        loop = generate_loop_curve(
            y_center=y_center,
            n_harmonics=min(cfg.n_harmonics, 2),  # keep it smooth
            max_amp_y=min(cfg.max_amp_y, 0.05),    # less wild
            max_amp_r=cfg.max_amp_r,
            rng=rng,
        )
        patches.append(make_patch(loop, f"loop_extra_{i}"))

    return patches
