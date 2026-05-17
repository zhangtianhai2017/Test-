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


REGIONS = ("torso", "arm_l", "arm_r", "leg_l", "leg_r", "head_neck")
FORBIDDEN_REGIONS = ("arm_l", "arm_r", "leg_l", "leg_r", "head_neck")


def classify_vertices(body_verts: np.ndarray,
                       landmarks: AnatomyLandmarks,
                       arm_x_slack_cm: float = 1.0,
                       leg_y_slack_cm: float = 1.5,
                       ) -> np.ndarray:
    """Return an array of length len(body_verts) with one region string
    per vertex.

    `arm_x_slack_cm` controls how far past the torso's axilla-radius a
    vertex must be in |x| to count as arm material.  Default 1.0 cm
    keeps the deltoid cap as torso (so shoulder straps stay valid) but
    catches the inner-upper-arm surface that bridges to wide cup polys.

    `leg_y_slack_cm` lifts the leg cutoff above y_pelvis a touch so the
    inner-thigh surface that sits just above the crotch (and bridges
    to wide bottom polys) is also tagged as leg.
    """
    V = np.asarray(body_verts, dtype=np.float32)
    x = V[:, 0]
    y = V[:, 1]

    arm_x_thresh = landmarks.axilla_radius_xz + arm_x_slack_cm
    leg_y_thresh = landmarks.y_pelvis + leg_y_slack_cm

    region = np.full(len(V), "torso", dtype=object)

    is_head_neck = y > landmarks.y_acromion
    region[is_head_neck] = "head_neck"

    is_leg = y < leg_y_thresh
    region[is_leg & (x > 0)] = "leg_r"
    region[is_leg & (x <= 0)] = "leg_l"

    # Arms: any vertex that sits past the torso-x-extent AND is not
    # already classified as leg/head.  We use `axilla_radius_xz`, which
    # is the body's actual x-half-width at the axilla level -- so any
    # vertex past that *plus a small slack* is on the arm side of the
    # armpit gap, regardless of its y.
    is_arm = (np.abs(x) > arm_x_thresh) & ~is_head_neck & ~is_leg
    region[is_arm & (x > 0)] = "arm_r"
    region[is_arm & (x <= 0)] = "arm_l"

    return region


def classify_triangles_strict(vertex_regions: np.ndarray,
                               triangle_indices: np.ndarray
                               ) -> np.ndarray:
    """Boolean array of len(triangles).  True iff ALL three vertices
    of the triangle are in `torso` (so the triangle is safe to include
    in a fabric shell)."""
    tri_regions = vertex_regions[triangle_indices]   # (n_tri, 3)
    return (tri_regions == "torso").all(axis=1)


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
