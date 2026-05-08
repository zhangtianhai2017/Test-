"""
Anatomy landmark detector — derives anatomical Y levels and lateral
extents from a body mesh, so downstream garment code can route around
real human anatomy (acromion, axilla, clavicle, neck base) instead of
working from pure cylindrical UV.

Why this exists
---------------
Without anatomy: cylindrical_uvs maps v=1 to y_neck (a constant 0.939
of body height). Any vertex with y > y_neck has v clipped to 1.0, so
head triangles end up inside polygons that reach v=1 — they get pulled
into the fabric shell as visible "fabric on the ears". Same problem on
the lateral side: the radius filter doesn't know where the axilla is,
so the upper torso shell extends laterally onto the deltoid / upper arm.

What we detect
--------------
Sampling cross-sections at fine Y resolution and tracking lateral
extent gives a clean signal for each landmark:

  y_pelvis     — bottom of torso fabric region
  y_waist      — narrowest non-bust point in the lower torso
  y_axilla     — Y where lateral extent jumps (arms detach from torso)
  y_chest      — between axilla and acromion, nominal bust line
  y_acromion   — Y of shoulder peak (max torso lateral extent above
                 axilla, before neck narrowing)
  y_neck_base  — Y where torso narrows to neck thickness
  y_head_top   — top of mesh

  axilla_radius_xz  — torso_extent at y_axilla (use as max radius for
                       fabric shell triangles between y_axilla and
                       y_acromion to keep arms out)

Public API
----------
    landmarks = detect(body_mesh) -> AnatomyLandmarks
    landmarks.y_acromion          # float, world Y in cm
    landmarks.cylindrical_v(y)    # the v that should be used for this
                                  # Y instead of cylindrical_uvs's
                                  # naive linear remap
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import open3d as o3d


@dataclass
class AnatomyLandmarks:
    y_pelvis: float
    y_waist: float
    y_axilla: float
    y_chest: float
    y_acromion: float
    y_neck_base: float
    y_head_top: float
    axilla_radius_xz: float
    deltoid_radius_xz: float
    waist_radius_xz: float

    def is_above_garment(self, y: float, slack: float = 1.0) -> bool:
        """True if this Y is above the highest point a swimwear garment
        should reach (= acromion / shoulder peak). Used to exclude head
        and neck verts from polygon containment."""
        return y > self.y_acromion + slack

    def torso_max_radius(self, y: float) -> float:
        """Anatomically-aware torso radius cap at this Y. Below the
        axilla we can use a generous radius (waist hangs at ~17 cm).
        Between axilla and acromion the cap must be deltoid-tight or
        the shell extends onto the upper arm."""
        if y < self.y_axilla:
            return max(self.waist_radius_xz, self.axilla_radius_xz) + 0.5
        if y < self.y_acromion:
            return self.deltoid_radius_xz + 0.4
        return self.deltoid_radius_xz


def _torso_extent_at(y: float, V: np.ndarray, half: float = 1.0,
                      r_filter: float = 20.0) -> tuple[float, float, int]:
    """Return (torso_max_x, full_max_x, n) at a Y slab."""
    near = V[(V[:, 1] > y - half) & (V[:, 1] < y + half)]
    if len(near) == 0:
        return 0.0, 0.0, 0
    full_w = float(np.max(np.abs(near[:, 0])))
    r = np.sqrt(near[:, 0] ** 2 + near[:, 2] ** 2)
    inside = near[r < r_filter]
    if len(inside) == 0:
        return 0.0, full_w, 0
    return float(np.max(np.abs(inside[:, 0]))), full_w, len(inside)


def detect(body_mesh: o3d.geometry.TriangleMesh,
            n_samples: int = 80) -> AnatomyLandmarks:
    """Walk Y from low to high and read the cross-section signals."""
    V = np.asarray(body_mesh.vertices)
    y = V[:, 1]
    y_lo, y_hi = float(np.percentile(y, 2)), float(np.percentile(y, 98))
    H = y_hi - y_lo
    ys = np.linspace(y_lo + 0.4 * H, y_lo + 1.0 * H, n_samples)
    torso_w = np.zeros(n_samples)
    full_w = np.zeros(n_samples)
    for i, yi in enumerate(ys):
        torso_w[i], full_w[i], _ = _torso_extent_at(float(yi), V)

    # Arms-attached signal: where full_w jumps but torso_w stays similar.
    # Compute a simple "arm gap" = full_w - torso_w, and find the Y where
    # this jumps from ~0 (arms not in slab) to large (arms in slab).
    arm_gap = full_w - torso_w
    # First Y above the waist where arm_gap > 5 cm = axilla bottom edge
    waist_idx = int(np.argmax(torso_w[: n_samples // 2]))
    y_waist = float(ys[waist_idx])
    waist_radius = float(torso_w[waist_idx])

    # axilla = first y above waist where arm_gap > 5
    axilla_idx = waist_idx
    for i in range(waist_idx + 1, n_samples):
        if arm_gap[i] > 5.0:
            axilla_idx = i
            break
    y_axilla = float(ys[axilla_idx])
    axilla_radius = float(torso_w[axilla_idx])

    # acromion = local maximum of torso_w ABOVE the axilla (where the
    # deltoid bulge re-creates a wide torso slice). Search from
    # axilla_idx up; find Y where torso_w peaks again.
    above = np.arange(axilla_idx + 2, n_samples)
    if len(above) == 0:
        y_acromion = ys[-1]
        deltoid_radius = waist_radius
    else:
        # Find local max of torso_w in upper half.
        peak_local = above[int(np.argmax(torso_w[above]))]
        y_acromion = float(ys[peak_local])
        deltoid_radius = float(torso_w[peak_local])

    # chest is between axilla and acromion at 60% of the way up.
    y_chest = 0.4 * y_axilla + 0.6 * y_acromion

    # neck_base = first Y above acromion where torso_w drops below 60%
    # of acromion's torso_w (transition into neck).
    neck_thresh = 0.55 * deltoid_radius
    neck_idx = -1
    for i in range(int(np.where(np.isclose(ys, y_acromion))[0][0]) + 1, n_samples):
        if torso_w[i] < neck_thresh:
            neck_idx = i
            break
    y_neck_base = float(ys[neck_idx]) if neck_idx > 0 else y_acromion + 6.0
    y_head_top = y_hi

    # y_pelvis — actual hip ridge, derived from body topology rather
    # than a hardcoded fraction. We sweep a wider Y range than the
    # ys we sampled above (which started at y_lo + 0.4*H — too high
    # for some standing-pose meshes whose pelvis sits at ~50%) and
    # find the first prominent local max of torso width going up from
    # the bottom. That's where the legs converge into the hip.
    pelvis_ys = np.linspace(y_lo + 0.05 * H, y_lo + 0.65 * H, 40)
    pelvis_w = np.zeros(len(pelvis_ys))
    for i, yi in enumerate(pelvis_ys):
        pw, _, _ = _torso_extent_at(float(yi), V, half=2.0, r_filter=22.0)
        pelvis_w[i] = pw
    # Smooth and find first prominent peak above the leg width
    leg_baseline = float(np.median(pelvis_w[: len(pelvis_w) // 4]))
    pelvis_idx = -1
    for i in range(2, len(pelvis_ys) - 1):
        if (pelvis_w[i] > leg_baseline + 1.0
                and pelvis_w[i] >= pelvis_w[i - 1]
                and pelvis_w[i] >= pelvis_w[i + 1]):
            pelvis_idx = i
            break
    if pelvis_idx > 0:
        y_pelvis = float(pelvis_ys[pelvis_idx])
    else:
        # Fallback to the old hardcoded fraction.
        y_pelvis = y_lo + 0.30 * H

    return AnatomyLandmarks(
        y_pelvis=y_pelvis,
        y_waist=y_waist,
        y_axilla=y_axilla,
        y_chest=y_chest,
        y_acromion=y_acromion,
        y_neck_base=y_neck_base,
        y_head_top=y_head_top,
        axilla_radius_xz=axilla_radius,
        deltoid_radius_xz=deltoid_radius,
        waist_radius_xz=waist_radius,
    )


def front_clavicle_point(body_mesh: o3d.geometry.TriangleMesh,
                          landmarks: AnatomyLandmarks,
                          side: str = "R",
                          ) -> np.ndarray:
    """Locate the front-of-shoulder anchor (clavicle / pectoral edge):
    the body surface point at acromion Y, on the front (z>0), with
    large lateral extent on the chosen side. side='R' returns +X, 'L' returns -X."""
    V = np.asarray(body_mesh.vertices)
    y = V[:, 1]
    sign = +1 if side == "R" else -1
    # Slab around acromion height, lateral edge on the chosen side,
    # require z > 0 (genuine front).
    mask = ((y > landmarks.y_acromion - 3.0) & (y < landmarks.y_acromion + 2.0)
            & (np.sign(V[:, 0]) == sign) & (V[:, 2] > 0.0))
    cands = V[mask]
    if len(cands) == 0:
        return np.array([sign * landmarks.deltoid_radius_xz,
                          landmarks.y_acromion, 5.0], dtype=np.float64)
    # Rank by lateral extent first, but only among the front-half verts.
    # We want the point that's both lateral AND forward — clavicle ridge.
    score = sign * cands[:, 0] + 0.6 * cands[:, 2]
    return cands[int(np.argmax(score))].astype(np.float64)


def back_scapula_point(body_mesh: o3d.geometry.TriangleMesh,
                        landmarks: AnatomyLandmarks,
                        side: str = "R",
                        ) -> np.ndarray:
    """Locate the back-of-shoulder anchor (scapula edge): mirror of the
    clavicle anchor on the back side (z<0)."""
    V = np.asarray(body_mesh.vertices)
    y = V[:, 1]
    sign = +1 if side == "R" else -1
    mask = ((y > landmarks.y_acromion - 5.0) & (y < landmarks.y_acromion + 1.0)
            & (np.sign(V[:, 0]) == sign) & (V[:, 2] < 0.0))
    cands = V[mask]
    if len(cands) == 0:
        return np.array([sign * landmarks.deltoid_radius_xz,
                          landmarks.y_acromion - 2.0, -5.0], dtype=np.float64)
    score = sign * cands[:, 0] - 0.6 * cands[:, 2]
    return cands[int(np.argmax(score))].astype(np.float64)


# ---------------------------------------------------------------------------
# Extended body-jewelry anchors (v2)
#
# These resolve named anchors used by body_jewelry / accessory library
# entries: wrist / forearm / bicep (arm chain), earlobe (earrings),
# ankle (anklet), belly_button (body chain), neck_front (necklace).
# ---------------------------------------------------------------------------

def _arm_anchor(body_mesh: o3d.geometry.TriangleMesh,
                landmarks: AnatomyLandmarks,
                side: str, fraction_from_shoulder: float
                ) -> np.ndarray:
    """Pick a vertex on the laterally-extended arm at a given fraction
    along the shoulder→hand line. fraction=0 ≈ deltoid (acromion lateral),
    fraction=1 ≈ hand tip. Wrist ≈ 0.85, forearm-mid ≈ 0.65, bicep ≈ 0.30."""
    V = np.asarray(body_mesh.vertices)
    y = V[:, 1]
    sign = +1 if side == "R" else -1
    # Hand tip = vertex with most extreme |x| anywhere
    abs_x = np.abs(V[:, 0])
    hand_idx = int(np.argmax(abs_x))
    hand_x = V[hand_idx, 0]
    hand_y = V[hand_idx, 1]
    # Shoulder lateral (deltoid) = at acromion height
    shoulder_x = sign * landmarks.deltoid_radius_xz
    shoulder_y = landmarks.y_acromion
    target_x = shoulder_x + fraction_from_shoulder * (sign * abs(hand_x) - shoulder_x)
    target_y = shoulder_y + fraction_from_shoulder * (hand_y - shoulder_y)
    # Pick the body vertex closest to (target_x, target_y) on the right side
    candidates_idx = np.where((np.sign(V[:, 0]) == sign)
                                & (np.abs(V[:, 0]) > 8))[0]
    if len(candidates_idx) == 0:
        return np.array([target_x, target_y, 0.0], dtype=np.float64)
    cand = V[candidates_idx]
    d2 = (cand[:, 0] - target_x) ** 2 + (cand[:, 1] - target_y) ** 2
    return cand[int(np.argmin(d2))].astype(np.float64)


def wrist_point(body_mesh, landmarks, side: str = "R") -> np.ndarray:
    return _arm_anchor(body_mesh, landmarks, side, fraction_from_shoulder=0.85)


def forearm_point(body_mesh, landmarks, side: str = "R") -> np.ndarray:
    return _arm_anchor(body_mesh, landmarks, side, fraction_from_shoulder=0.65)


def bicep_point(body_mesh, landmarks, side: str = "R") -> np.ndarray:
    return _arm_anchor(body_mesh, landmarks, side, fraction_from_shoulder=0.30)


def earlobe_point(body_mesh: o3d.geometry.TriangleMesh,
                   landmarks: AnatomyLandmarks,
                   side: str = "R") -> np.ndarray:
    """Lateral edge of head at ~70% of head height."""
    V = np.asarray(body_mesh.vertices)
    sign = +1 if side == "R" else -1
    # Head Y window: from neck_base + 4 cm to head_top - 5 cm
    y_lo = landmarks.y_neck_base + 4.0
    y_hi = landmarks.y_head_top - 5.0
    mask = ((V[:, 1] > y_lo) & (V[:, 1] < y_hi) & (np.sign(V[:, 0]) == sign))
    cands = V[mask]
    if len(cands) == 0:
        return np.array([sign * 8.5, (y_lo + y_hi) * 0.5, 0.0], dtype=np.float64)
    # Most lateral on the chosen side
    return cands[int(np.argmax(sign * cands[:, 0]))].astype(np.float64)


def ankle_point(body_mesh: o3d.geometry.TriangleMesh,
                 landmarks: AnatomyLandmarks,
                 side: str = "R") -> np.ndarray:
    """Ankle ≈ a few cm above the foot (near body Y minimum)."""
    V = np.asarray(body_mesh.vertices)
    y = V[:, 1]
    y_lo = float(np.percentile(y, 1))
    sign = +1 if side == "R" else -1
    mask = ((y > y_lo + 2.0) & (y < y_lo + 12.0) & (np.sign(V[:, 0]) == sign))
    cands = V[mask]
    if len(cands) == 0:
        return np.array([sign * 13.0, y_lo + 7.0, 0.0], dtype=np.float64)
    # Pick vert closest to centroid of the chosen-side leg slab
    cx = float(np.mean(cands[:, 0]))
    d2 = (cands[:, 0] - cx) ** 2
    return cands[int(np.argmin(d2))].astype(np.float64)


def belly_button_point(body_mesh: o3d.geometry.TriangleMesh,
                         landmarks: AnatomyLandmarks) -> np.ndarray:
    """Belly button: front center between pelvis and axilla."""
    V = np.asarray(body_mesh.vertices)
    y_target = (landmarks.y_pelvis + landmarks.y_axilla) * 0.5
    mask = ((V[:, 1] > y_target - 1.5) & (V[:, 1] < y_target + 1.5)
            & (np.abs(V[:, 0]) < 3.0) & (V[:, 2] > 0.0))
    cands = V[mask]
    if len(cands) == 0:
        return np.array([0.0, y_target, 7.0], dtype=np.float64)
    # Most-forward (max z) closest to center
    score = cands[:, 2] - np.abs(cands[:, 0]) * 0.5
    return cands[int(np.argmax(score))].astype(np.float64)


def neck_front_point(body_mesh: o3d.geometry.TriangleMesh,
                       landmarks: AnatomyLandmarks) -> np.ndarray:
    """Front of neck — between collar bones, just below jaw."""
    V = np.asarray(body_mesh.vertices)
    y_target = landmarks.y_neck_base + 2.0
    mask = ((V[:, 1] > y_target - 1.5) & (V[:, 1] < y_target + 1.5)
            & (np.abs(V[:, 0]) < 4.0) & (V[:, 2] > 0.0))
    cands = V[mask]
    if len(cands) == 0:
        return np.array([0.0, y_target, 4.0], dtype=np.float64)
    score = cands[:, 2] - np.abs(cands[:, 0]) * 0.5
    return cands[int(np.argmax(score))].astype(np.float64)


# ---------------------------------------------------------------------------
# Named body regions — the second leg of the cascaded latent stack
# (Genome → Garment → BodyDeployment → mesh). A BodyRegion classifies
# any 3D point on the body into a coarse anatomical zone, which is the
# vocabulary BodyMapping uses for `covers_regions` and `must_clear`.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BodyRegion:
    """A coarse anatomical zone in body coordinates.

    side="any" means the region wraps the full circumference;
    "front" restricts to z>0; "back" restricts to z<0; "side" is the
    lateral strips u in (-0.6, -0.4) and (0.4, 0.6).
    """
    name: str
    y_min: float
    y_max: float
    side: str = "any"           # "any" / "front" / "back" / "side"
    notes: str = ""

    def contains(self, x: float, y: float, z: float) -> bool:
        if not (self.y_min <= y <= self.y_max):
            return False
        if self.side == "front" and z < 0:
            return False
        if self.side == "back" and z > 0:
            return False
        if self.side == "side":
            # u = atan2(x, z) / pi; |u| in [0.4, 0.6]
            if abs(x) < 1e-3 and abs(z) < 1e-3:
                return False
            theta = np.arctan2(x, z)
            u = theta / np.pi
            if not (0.4 <= abs(u) <= 0.6):
                return False
        return True


def body_regions(L: AnatomyLandmarks) -> dict[str, BodyRegion]:
    """Build the v1 set of named regions a swimwear PatternPiece can
    declare it covers / must clear. Y bounds derive from the
    AnatomyLandmarks already detected on the body."""
    epsilon = 0.5
    return {
        # Forbidden zones for swimwear pieces
        "legs":      BodyRegion("legs",
                                  y_min=-1e6, y_max=L.y_pelvis - epsilon),
        "head":      BodyRegion("head",
                                  y_min=L.y_neck_base + epsilon, y_max=1e6),
        "neck":      BodyRegion("neck",
                                  y_min=L.y_acromion + epsilon,
                                  y_max=L.y_neck_base + epsilon),

        # Torso zones — the legitimate coverage targets
        "chest":     BodyRegion("chest",
                                  y_min=L.y_axilla, y_max=L.y_acromion + epsilon),
        "front_chest": BodyRegion("front_chest",
                                  y_min=L.y_axilla, y_max=L.y_acromion + epsilon,
                                  side="front"),
        "back_chest": BodyRegion("back_chest",
                                  y_min=L.y_axilla, y_max=L.y_acromion + epsilon,
                                  side="back"),
        "pelvis":    BodyRegion("pelvis",
                                  y_min=L.y_pelvis - epsilon, y_max=L.y_axilla),
        "front_pelvis": BodyRegion("front_pelvis",
                                  y_min=L.y_pelvis - epsilon, y_max=L.y_axilla,
                                  side="front"),
        "back_pelvis": BodyRegion("back_pelvis",
                                  y_min=L.y_pelvis - epsilon, y_max=L.y_axilla,
                                  side="back"),
        "side_torso": BodyRegion("side_torso",
                                  y_min=L.y_pelvis - epsilon,
                                  y_max=L.y_acromion + epsilon, side="side"),
    }


def classify_point(x: float, y: float, z: float,
                   regions: dict[str, BodyRegion],
                   max_torso_radius: float | None = None) -> str:
    """Return the FIRST region (in dict order) that contains (x,y,z),
    or "arms" if the XZ radius exceeds max_torso_radius (lateral
    extreme = arm), or "outside" otherwise.

    Order matters because of overlap (e.g., a point can be both
    front_chest and chest). We resolve in dict order, so put more
    specific regions first.
    """
    if max_torso_radius is not None:
        r_xz = (x * x + z * z) ** 0.5
        if r_xz > max_torso_radius:
            return "arms"
    for name, r in regions.items():
        if r.contains(x, y, z):
            return name
    return "outside"
