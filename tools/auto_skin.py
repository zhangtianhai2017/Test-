"""Proximity-based skin weight transfer.

Given an outfit mesh (just vertices) and a body mesh that already has
skin weights, propagate those weights to the outfit by finding each
outfit vertex's k-nearest body vertices and distance-weighting their
joint influences.

This is the "auto-skin" pipeline used to make a v2 bikini deform with
its host MetaHuman skeleton without a manual rig pass. Quality is
acceptable for full-body fabric overlays where the underlying body
already drives most of the deformation; sharp anatomical regions (bust
under-curve, inner thigh) may show soft seams. For a milestone-1
validation that's fine; production rigging would use heat-map skinning
or hand-painted weights.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def transfer_weights(outfit_verts: np.ndarray,
                     body_verts: np.ndarray,
                     body_joints: np.ndarray,
                     body_weights: np.ndarray,
                     k: int = 4,
                     max_influences: int = 4,
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Transfer per-vertex skin weights from body to outfit.

    Parameters
    ----------
    outfit_verts : (N, 3) float
    body_verts   : (M, 3) float
    body_joints  : (M, K_body) int   — joint indices per body vertex
    body_weights : (M, K_body) float — corresponding weights, summing to 1
    k            : neighbours per outfit vertex (default 4)
    max_influences : per-output-vertex influence cap (glTF cap is 4)

    Returns
    -------
    out_joints  : (N, max_influences) uint16
    out_weights : (N, max_influences) float32, rows sum to 1
    """
    if outfit_verts.shape[1] != 3 or body_verts.shape[1] != 3:
        raise ValueError("verts must be (·, 3)")
    if body_joints.shape != body_weights.shape:
        raise ValueError("body_joints and body_weights must have same shape")

    tree = cKDTree(body_verts)
    dists, idx = tree.query(outfit_verts, k=k)        # (N, k)
    if k == 1:
        dists = dists[:, None]; idx = idx[:, None]

    # inverse-distance with eps to avoid div by zero
    inv = 1.0 / np.maximum(dists, 1e-6)
    inv /= inv.sum(axis=1, keepdims=True)             # (N, k)

    # accumulate per-joint weights into a sparse dict per vertex
    n = outfit_verts.shape[0]
    accum: list[dict[int, float]] = [dict() for _ in range(n)]
    for ki in range(k):
        nbr_joint  = body_joints[idx[:, ki]]    # (N, K_body)
        nbr_weight = body_weights[idx[:, ki]]   # (N, K_body)
        scale      = inv[:, ki][:, None]        # (N, 1)
        contrib    = nbr_weight * scale         # (N, K_body)
        for vi in range(n):
            for jb in range(nbr_joint.shape[1]):
                w = contrib[vi, jb]
                if w <= 1e-6:
                    continue
                jt = int(nbr_joint[vi, jb])
                accum[vi][jt] = accum[vi].get(jt, 0.0) + float(w)

    out_joints  = np.zeros((n, max_influences), dtype=np.uint16)
    out_weights = np.zeros((n, max_influences), dtype=np.float32)

    for vi in range(n):
        if not accum[vi]:
            # unreachable in practice; pad with root-bone identity
            out_joints[vi, 0] = 0
            out_weights[vi, 0] = 1.0
            continue
        items = sorted(accum[vi].items(), key=lambda x: -x[1])[:max_influences]
        s = sum(w for _, w in items)
        for slot, (jt, w) in enumerate(items):
            out_joints[vi, slot]  = jt
            out_weights[vi, slot] = w / s if s > 0 else 0.0

    return out_joints, out_weights


def _self_test():
    rng = np.random.default_rng(0)
    body = rng.standard_normal((100, 3))
    bj   = np.zeros((100, 4), dtype=int);  bj[:, 0] = np.arange(100) % 5
    bw   = np.zeros((100, 4));             bw[:, 0] = 1.0
    outfit = body + 0.01 * rng.standard_normal(body.shape)
    j, w = transfer_weights(outfit, body, bj, bw)
    assert j.shape == (100, 4) and w.shape == (100, 4)
    assert np.allclose(w.sum(axis=1), 1.0, atol=1e-5)
    print("auto_skin self-test ok")


if __name__ == "__main__":
    _self_test()
