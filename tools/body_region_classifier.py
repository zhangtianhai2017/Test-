"""Standalone body-region classifier — tags every body vertex with an
anatomical region (`torso`, `arm_l`, `arm_r`, `leg_l`, `leg_r`,
`head_neck`).  Independent of the v2 garment cascade so it can run
unconditionally inside `build_fabric_shell`, eliminating the class of
bug where fabric appears in the armpit gap or between the inner thighs
just because the cascade-built deployment was None.

Geometry assumptions (T-pose MetaHuman / NPC body):
  - Arms extend out along ±X from the shoulder; an arm vertex's |x|
    sits beyond the torso's x-extent at the same height.
  - Legs sit below the pelvis ridge; vertices with y < y_pelvis are
    leg material regardless of |x|.
  - Head / neck sits above the acromion line.
  - Everything else is torso (includes the deltoid cap so straps can
    wrap the shoulder).

Classification is at the VERTEX level.  A triangle is "torso-safe"
iff all three of its vertices classify as `torso` -- this is strict,
which is the right side of the trade-off (no fabric anywhere near an
arm or leg).
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from anatomy import AnatomyLandmarks, detect


REGIONS = ("torso", "pelvis", "arm_l", "arm_r", "leg_l", "leg_r", "head_neck")
FORBIDDEN_REGIONS = ("arm_l", "arm_r", "leg_l", "leg_r", "head_neck")
# Regions that count as "fabric-safe" for the strict triangle filter.
# Both torso (chest/abdomen) and pelvis (hip ridge down to crotch) are
# legitimate places for a swimsuit panel to sit on.
SAFE_REGIONS = ("torso", "pelvis")


def classify_vertices(body_verts: np.ndarray,
                       landmarks: AnatomyLandmarks,
                       arm_x_slack_cm: float = 1.0,
                       leg_y_slack_cm: float = 1.5,
                       pelvis_drop_cm: float = 8.0,
                       ) -> np.ndarray:
    """Return an array of length len(body_verts) with one region string
    per vertex.

    `arm_x_slack_cm` controls how far past the torso's axilla-radius a
    vertex must be in |x| to count as arm material.  Default 1.0 cm
    keeps the deltoid cap as torso (so shoulder straps stay valid) but
    catches the inner-upper-arm surface that bridges to wide cup polys.

    `leg_y_slack_cm` lifts the upper bound of the pelvis region above
    y_pelvis a touch (so abdomen vertices very close to the hip ridge
    still get tagged torso, not pelvis).

    `pelvis_drop_cm` extends the pelvis region downward from y_pelvis
    by this many centimeters. Anatomically the iliac crest (y_pelvis)
    sits ~8 cm above the perineum on a standing pose, so 8 cm captures
    the bikini-bottom / one-piece-crotch fabric-bearing zone. Below
    y_pelvis - pelvis_drop is the upper thigh = leg.

    Region layout from top to bottom:
      head_neck:   y > y_acromion
      torso:       y_pelvis+slack < y < y_acromion (and inside arm_x)
      pelvis:      y_pelvis-pelvis_drop < y < y_pelvis+slack
                   (the fabric-safe hip-to-crotch zone; introduced
                    2026-05-23 to fix the long-deferred
                    "bottom mesh not rendered despite valid slot" bug.
                    Without this, bottom polys mapped to y ~63-90 cm
                    fell entirely below the old leg cutoff (y_pelvis+1.5)
                    and got zero geometry through classify_triangles_strict.)
      leg_l/r:     y < y_pelvis - pelvis_drop_cm
      arm_l/r:     |x| > axilla_radius + slack, not in head/leg/pelvis
    """
    V = np.asarray(body_verts, dtype=np.float32)
    x = V[:, 0]
    y = V[:, 1]

    arm_x_thresh = landmarks.axilla_radius_xz + arm_x_slack_cm
    pelvis_top  = landmarks.y_pelvis + leg_y_slack_cm
    pelvis_bot  = landmarks.y_pelvis - pelvis_drop_cm

    region = np.full(len(V), "torso", dtype=object)

    is_head_neck = y > landmarks.y_acromion
    region[is_head_neck] = "head_neck"

    is_leg = y < pelvis_bot
    region[is_leg & (x > 0)] = "leg_r"
    region[is_leg & (x <= 0)] = "leg_l"

    # Pelvis: strictly between leg and torso. Same x-bounds as torso
    # (no arm reclassification here — arms don't extend down here on
    # a T-pose).
    is_pelvis = (~is_head_neck) & (~is_leg) & (y < pelvis_top)
    region[is_pelvis] = "pelvis"

    # Arms: any vertex that sits past the torso-x-extent AND is not
    # already classified as leg/head/pelvis.  We use `axilla_radius_xz`,
    # which is the body's actual x-half-width at the axilla level -- so
    # any vertex past that *plus a small slack* is on the arm side of
    # the armpit gap, regardless of its y.
    is_arm = ((np.abs(x) > arm_x_thresh) & ~is_head_neck
               & ~is_leg & ~is_pelvis)
    region[is_arm & (x > 0)] = "arm_r"
    region[is_arm & (x <= 0)] = "arm_l"

    return region


def classify_triangles_strict(vertex_regions: np.ndarray,
                               triangle_indices: np.ndarray
                               ) -> np.ndarray:
    """Boolean array of len(triangles).  True iff ALL three vertices
    of the triangle are in a fabric-SAFE region (torso OR pelvis).
    Other regions (legs, arms, head/neck) are forbidden.

    Until 2026-05-23 this required strict torso. That gated out the
    entire pelvis zone, so bottom panels couldn't render despite
    valid polygon UVs."""
    tri_regions = vertex_regions[triangle_indices]   # (n_tri, 3)
    is_safe = np.isin(tri_regions, SAFE_REGIONS)
    return is_safe.all(axis=1)


def classify_triangles_majority(vertex_regions: np.ndarray,
                                  triangle_indices: np.ndarray
                                  ) -> np.ndarray:
    """Looser version: triangle is safe if MAJORITY of its vertices
    are torso (handy if the strict mode eats too many boundary
    triangles).  Currently unused; kept for tuning."""
    tri_regions = vertex_regions[triangle_indices]
    torso_count = (tri_regions == "torso").sum(axis=1)
    return torso_count >= 2


# ---------------------------------------------------------------------------
# Sanity / debug
# ---------------------------------------------------------------------------

def region_summary(vertex_regions: np.ndarray) -> dict:
    from collections import Counter
    counts = Counter(vertex_regions.tolist())
    return dict(counts)


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
    from render3d_uv import load_body_mesh
    body = load_body_mesh()
    L = detect(body)
    V = np.asarray(body.vertices)
    T = np.asarray(body.triangles)
    regions = classify_vertices(V, L)
    print("vertex region distribution:", region_summary(regions))
    print(f"triangles safe (all-torso): "
          f"{int(classify_triangles_strict(regions, T).sum())}/{len(T)}")
    print(f"triangles safe (majority torso): "
          f"{int(classify_triangles_majority(regions, T).sum())}/{len(T)}")
