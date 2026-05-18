"""Symbolic fitness — score an outfit config WITHOUT rendering.

All scores are PyTorch tensors in [0, 1] so autograd flows back to
the generator NN.  No image involved, no slow geometry, no Open3D.
This is "Stage 1" of the two-stage fitness in
docs/design/2026-05-17_option_D_architecture.md: the cheap symbolic
pass that filters / shapes generator output before the expensive
vision-judge pass.

Score functions operate on the generator's RAW outputs (torch
tensors), not on the post-pipeline Genome.  This preserves the
gradient path from loss back to generator parameters.

Inputs (generator output dict):
    {
        "hue":            tensor (batch,) in [0,1]
        "saturation":     tensor (batch,) in [0,1]
        "lightness":      tensor (batch,) in [0,1]
        "secondary_hue":  tensor (batch,) in [0,1]
        "top_half_u":     tensor (batch,) in [0.05, 0.30]
        "top_half_v":     tensor (batch,) in [0.04, 0.16]
        "top_inner_u":    tensor (batch,) in [-0.05, 0.28]
        "top_apex_lift":  tensor (batch,) in [-0.20, 0.55]
        "bot_front_half_u":  tensor (batch,) in [0.10, 0.60]
        "bot_front_top_v":   tensor (batch,) in [0.20, 0.65]
        "asym_amount":    tensor (batch,) in [0, 1]
        "cup_logits":     tensor (batch, N_cup_entries)  # softmax later
        "fabric_logits":  tensor (batch, N_fabric_entries)
        "pattern_logits": tensor (batch, N_patterns)
        "archetype_logits": tensor (batch, 4)
    }

Outputs:
    dict with each score axis + "total" (weighted sum, in [0,1])
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import Tensor


# ---------------------------------------------------------------------------
# Color harmony
# ---------------------------------------------------------------------------

def color_saturation_balance(saturation: Tensor) -> Tensor:
    """Reward picks that aren't stuck at the vivid extremes.  Mid-vivid
    (0.3-0.85) gets full score.  Pure white (sat=0) or hyper-saturated
    (sat=1) get penalised since both feel cheap.

    Bell curve centred at 0.55 with std 0.30."""
    mu, sigma = 0.55, 0.30
    return torch.exp(-0.5 * ((saturation - mu) / sigma) ** 2)


def color_lightness_balance(lightness: Tensor) -> Tensor:
    """Same idea for L.  Avoid black-hole (L<0.15) or blown-out
    (L>0.90).  Mid-ish preferred but with broader spread than sat."""
    mu, sigma = 0.55, 0.32
    return torch.exp(-0.5 * ((lightness - mu) / sigma) ** 2)


def color_pair_contrast(hue: Tensor, secondary_hue: Tensor) -> Tensor:
    """Reward complementary / analogous / triadic relationships
    between primary and secondary hue.  Score peaks at 0°
    (analogous), 120°/240° (triadic) and 180° (complementary).
    Penalise muddled mid-angles."""
    # Angular distance in unit circle: hue \in [0,1] -> radians
    diff = torch.remainder(secondary_hue - hue, 1.0)
    angle = diff * 2 * math.pi
    # Sweet spots: 0, 2π/3, π, 4π/3 -> equivalent to spikes at
    # diff in {0, 1/3, 1/2, 2/3}.  Use sum of three gaussians.
    score = torch.zeros_like(diff)
    for target in (0.0, 1.0 / 3, 0.5, 2.0 / 3):
        d = torch.remainder(diff - target + 0.5, 1.0) - 0.5
        score = score + torch.exp(-0.5 * (d / 0.08) ** 2)
    return torch.clamp(score / 1.0, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Geometric proportions
# ---------------------------------------------------------------------------

PHI = 1.618033988749895
THIRDS = 1.5


def cup_aspect_ratio(half_u: Tensor, half_v: Tensor) -> Tensor:
    """Reward cup hu/hv ratios near golden (1.618) or thirds (1.5).
    Penalise extreme aspect ratios (too thin/tall or too wide/flat)."""
    ratio = half_u / torch.clamp(half_v, min=1e-3)
    # Gaussian peaks at PHI and THIRDS, broad penalty outside [1.0, 3.0]
    s_phi = torch.exp(-0.5 * ((ratio - PHI) / 0.35) ** 2)
    s_thirds = torch.exp(-0.5 * ((ratio - THIRDS) / 0.35) ** 2)
    s_far = torch.exp(-0.5 * ((ratio - 2.0) / 1.5) ** 2)  # mild fallback
    return torch.clamp(torch.maximum(torch.maximum(s_phi, s_thirds), s_far),
                        0.0, 1.0)


def cup_size_proportion(half_u: Tensor, half_v: Tensor) -> Tensor:
    """Penalise cups that are too small (no coverage) or absurdly
    large (extends past torso width).  Sweet spot:
    half_u in [0.12, 0.25], half_v in [0.05, 0.12]."""
    u_score = _bell(half_u, mu=0.18, sigma=0.07)
    v_score = _bell(half_v, mu=0.085, sigma=0.04)
    return (u_score * v_score) ** 0.5  # geometric mean


def bottom_proportion(half_u: Tensor, top_v: Tensor) -> Tensor:
    """Bottom front panel.  Half_u 0.30-0.50 is wearable cheeky/brief,
    top_v 0.28-0.45 gives a normal waistline."""
    u_score = _bell(half_u, mu=0.40, sigma=0.13)
    v_score = _bell(top_v, mu=0.36, sigma=0.10)
    return (u_score * v_score) ** 0.5


def apex_within_design_range(apex_lift: Tensor) -> Tensor:
    """Apex_lift can be negative (bandeau curve down) or positive (V).
    Allow the full schema range -0.20..0.55 but discourage exact 0
    (which reads as boring) and over-extreme deep V > 0.50."""
    # Two acceptable design zones: -0.15..-0.05 (subtle scoop) and
    # 0.15..0.45 (clear V).  Penalise the dead middle.
    s_scoop = torch.exp(-0.5 * ((apex_lift + 0.10) / 0.10) ** 2)
    s_v     = torch.exp(-0.5 * ((apex_lift - 0.30) / 0.20) ** 2)
    return torch.clamp(torch.maximum(s_scoop, s_v), 0.0, 1.0)


# ---------------------------------------------------------------------------
# Symmetry binary
# ---------------------------------------------------------------------------

def symmetry_binary(asym_amount: Tensor) -> Tensor:
    """Reward perfect mirror (asym_amount near 0) OR dramatic
    asymmetry (asym_amount >= 0.5).  Penalise the limp middle
    (small accidental skew, reads as construction error)."""
    s_mirror = torch.exp(-0.5 * (asym_amount / 0.05) ** 2)
    s_dramatic = torch.sigmoid((asym_amount - 0.5) * 20.0)
    return torch.clamp(torch.maximum(s_mirror, s_dramatic), 0.0, 1.0)


# ---------------------------------------------------------------------------
# Privacy coverage (a soft version of the hard PRIVACY_SEEDS constraint)
# ---------------------------------------------------------------------------

PRIVACY_SEEDS = {
    # (u_lo, u_hi, v_lo, v_hi)
    "right_nipple":  (0.10, 0.22, 0.70, 0.80),
    "left_nipple":   (-0.22, -0.10, 0.70, 0.80),
    "pelvic_front":  (-0.08, 0.08, 0.30, 0.42),
}


def cup_covers_seed(half_u: Tensor, half_v: Tensor, inner_u: Tensor,
                     center_v: Tensor) -> Tensor:
    """Soft 'does the cup cover the nipple seed' check.  Compares
    cup polygon's u/v extent against right_nipple seed via signed
    distance + sigmoid."""
    seed_u_lo, seed_u_hi, seed_v_lo, seed_v_hi = PRIVACY_SEEDS["right_nipple"]
    cup_u_lo = inner_u
    cup_u_hi = inner_u + 2 * half_u
    cup_v_lo = center_v - half_v
    cup_v_hi = center_v + half_v
    # Margin: how much the cup overshoots the seed on each side.
    # Positive margin = good cover; negative = uncovered.
    margin_u_lo = cup_u_lo - seed_u_lo   # want this <= 0
    margin_u_hi = cup_u_hi - seed_u_hi   # want this >= 0
    margin_v_lo = cup_v_lo - seed_v_lo   # want this <= 0
    margin_v_hi = cup_v_hi - seed_v_hi   # want this >= 0
    # Use sigmoid to softly convert "good coverage" booleans into score
    SHARPNESS = 50.0
    s_u_lo = torch.sigmoid(-margin_u_lo * SHARPNESS)
    s_u_hi = torch.sigmoid( margin_u_hi * SHARPNESS)
    s_v_lo = torch.sigmoid(-margin_v_lo * SHARPNESS)
    s_v_hi = torch.sigmoid( margin_v_hi * SHARPNESS)
    return (s_u_lo * s_u_hi * s_v_lo * s_v_hi)


def bottom_covers_pelvic_seed(half_u: Tensor, top_v: Tensor) -> Tensor:
    """Soft pelvic-front coverage check.  Bottom front panel must
    contain the pelvic_front seed rectangle.

    Bottom always reaches down past v=0.10 (legs), well below the
    seed's v_lo=0.30, so only the u extent and top edge need a soft
    check."""
    seed_u_lo, seed_u_hi, _seed_v_lo, seed_v_hi = PRIVACY_SEEDS["pelvic_front"]
    bot_u_lo = -half_u   # symmetric around u=0
    bot_u_hi =  half_u
    bot_v_hi = top_v
    SHARPNESS = 50.0
    s_u_lo = torch.sigmoid((seed_u_lo - bot_u_lo) * SHARPNESS)
    s_u_hi = torch.sigmoid((bot_u_hi - seed_u_hi) * SHARPNESS)
    s_v_hi = torch.sigmoid((bot_v_hi - seed_v_hi) * SHARPNESS)
    return (s_u_lo * s_u_hi * s_v_hi)


# ---------------------------------------------------------------------------
# Slot compatibility (using soft softmax distributions)
# ---------------------------------------------------------------------------

def slot_pair_compat(slot_logits_a: Tensor, slot_logits_b: Tensor,
                     compat_matrix: Tensor) -> Tensor:
    """Score that two slot choices respect known compatibility.

    slot_logits_a: (batch, N_a) — unnormalised logits for slot A
    slot_logits_b: (batch, N_b)
    compat_matrix: (N_a, N_b) — 1.0 where compatible, ~0.3 where neutral,
                                  0.0 where incompatible (eg foam_cup
                                  fabric paired with non-foam_molded
                                  cup)
    Returns: (batch,) score in [0,1]
    """
    p_a = torch.softmax(slot_logits_a, dim=-1)      # (B, N_a)
    p_b = torch.softmax(slot_logits_b, dim=-1)      # (B, N_b)
    # Expected compatibility = sum_{i,j} p_a[i] * p_b[j] * C[i,j]
    score = torch.einsum("bi,bj,ij->b", p_a, p_b, compat_matrix)
    return torch.clamp(score, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bell(x: Tensor, mu: float, sigma: float) -> Tensor:
    return torch.exp(-0.5 * ((x - mu) / sigma) ** 2)


# ---------------------------------------------------------------------------
# Combined fitness
# ---------------------------------------------------------------------------

@dataclass
class FitnessWeights:
    color_balance:        float = 1.0
    color_pair:           float = 0.7
    cup_aspect:           float = 0.8
    cup_size:             float = 1.0
    bottom_proportion:    float = 1.0
    apex:                 float = 0.5
    symmetry:             float = 0.6
    cup_covers_seed:      float = 1.5    # privacy weighted high
    bottom_covers_seed:   float = 1.5
    slot_compat:          float = 0.8


def total_fitness(g: dict, weights: FitnessWeights | None = None,
                   compat_matrices: dict | None = None) -> dict:
    """Compute every score axis + weighted total.

    g: dict of torch tensors (one batch dim).  Required keys:
       hue, saturation, lightness, secondary_hue,
       top_half_u, top_half_v, top_inner_u, top_apex_lift, top_center_v,
       bot_front_half_u, bot_front_top_v,
       asym_amount.
    weights: optional FitnessWeights override.
    compat_matrices: optional {"cup_fabric": tensor, ...} for slot
                     compat scoring.  If None, slot_compat skipped.

    Returns: dict including a scalar "total" averaged across the batch.
    """
    if weights is None:
        weights = FitnessWeights()

    scores: dict[str, Tensor] = {}

    scores["color_sat_balance"] = color_saturation_balance(g["saturation"])
    scores["color_light_balance"] = color_lightness_balance(g["lightness"])
    if "secondary_hue" in g:
        scores["color_pair"] = color_pair_contrast(g["hue"], g["secondary_hue"])

    scores["cup_aspect"] = cup_aspect_ratio(g["top_half_u"], g["top_half_v"])
    scores["cup_size"]   = cup_size_proportion(g["top_half_u"], g["top_half_v"])
    scores["bottom_proportion"] = bottom_proportion(g["bot_front_half_u"],
                                                       g["bot_front_top_v"])
    scores["apex"]       = apex_within_design_range(g["top_apex_lift"])
    scores["symmetry"]   = symmetry_binary(g["asym_amount"])

    if "top_center_v" in g and "top_inner_u" in g:
        scores["cup_covers_seed"] = cup_covers_seed(
            g["top_half_u"], g["top_half_v"],
            g["top_inner_u"], g["top_center_v"])
    scores["bottom_covers_seed"] = bottom_covers_pelvic_seed(
        g["bot_front_half_u"], g["bot_front_top_v"])

    if compat_matrices is not None:
        if "cup_fabric" in compat_matrices and \
                "cup_logits" in g and "fabric_logits" in g:
            scores["slot_compat_cup_fabric"] = slot_pair_compat(
                g["cup_logits"], g["fabric_logits"],
                compat_matrices["cup_fabric"])

    # Weighted total
    total = torch.zeros_like(next(iter(scores.values())))
    total_w = 0.0
    weight_map = {
        "color_sat_balance":   weights.color_balance,
        "color_light_balance": weights.color_balance,
        "color_pair":          weights.color_pair,
        "cup_aspect":          weights.cup_aspect,
        "cup_size":            weights.cup_size,
        "bottom_proportion":   weights.bottom_proportion,
        "apex":                weights.apex,
        "symmetry":            weights.symmetry,
        "cup_covers_seed":     weights.cup_covers_seed,
        "bottom_covers_seed":  weights.bottom_covers_seed,
        "slot_compat_cup_fabric": weights.slot_compat,
    }
    for k, s in scores.items():
        w = weight_map.get(k, 0.0)
        total = total + w * s
        total_w += w
    if total_w > 0:
        total = total / total_w

    scores["total"] = total
    return scores


# ---------------------------------------------------------------------------
# Sanity / smoke
# ---------------------------------------------------------------------------

def _smoke_test() -> None:
    """Quick verification that everything runs + autograd flows."""
    torch.manual_seed(0)
    B = 8

    # All inputs must be LEAF tensors with requires_grad=True so .grad
    # populates after backward.  Build via raw assignment, not via
    # arithmetic-on-a-leaf (which produces a non-leaf result).
    def leaf(t):
        return t.detach().clone().requires_grad_(True)

    g = {
        "hue":              leaf(torch.rand(B)),
        "saturation":       leaf(torch.rand(B) * 0.6 + 0.2),
        "lightness":        leaf(torch.rand(B) * 0.6 + 0.2),
        "secondary_hue":    leaf(torch.rand(B)),
        "top_center_v":     leaf(torch.rand(B) * 0.10 + 0.70),
        "top_half_u":       leaf(torch.rand(B) * 0.15 + 0.10),
        "top_half_v":       leaf(torch.rand(B) * 0.08 + 0.05),
        "top_inner_u":      leaf(torch.rand(B) * 0.20 - 0.05),
        "top_apex_lift":    leaf(torch.rand(B) * 0.6 - 0.1),
        "bot_front_half_u": leaf(torch.rand(B) * 0.40 + 0.20),
        "bot_front_top_v":  leaf(torch.rand(B) * 0.30 + 0.25),
        "asym_amount":      leaf(torch.rand(B)),
    }
    out = total_fitness(g)
    print(f"score axes: {sorted(out.keys())}")
    print(f"total fitness per sample: {out['total'].detach().numpy()}")
    print(f"mean fitness: {out['total'].mean().item():.3f}")

    # Verify autograd: differentiate total wrt all generator outputs
    loss = -out["total"].mean()
    loss.backward()
    print(f"\ngradients populated:")
    for k, v in g.items():
        if v.grad is not None:
            print(f"  {k:20s} grad norm={v.grad.norm().item():.4f}")
        else:
            print(f"  {k:20s} grad is None (NOT differentiable!)")


if __name__ == "__main__":
    _smoke_test()
