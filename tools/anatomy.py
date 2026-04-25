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

    y_pelvis = y_lo + 0.30 * H  # crotch level for these meshes

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
