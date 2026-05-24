"""Per-template placement recipes for body-jewelry hardware
(bow / fringe / beads / shell).

Phase 2 #5, 2026-05-25. Mirrors Phase 2 #2 O-ring per-anchor rewrite.

Background. The original `_build_bow_mesh` / `_build_fringe_meshes` /
`_build_beads_meshes` / `_build_shell_mesh` in render3d_uv.py each
chose ONE hardcoded position formula:

    bow    → 1 bow at (u=0, v=top_center_v)             # always center-front
    beads  → 6 strands along bust ring, mirrored        # always around bust
    shell  → 1 charm at (u=0, v=top_center_v - 2.5)     # always under sternum
    fringe → 9 strips at u ∈ [-0.30, +0.30] along front # always front leg-opening

So every design that switched on `has_bow` got the same single bow in
the same spot. That's the same "永久同质性" the user keeps flagging:
the NN can vote yes/no on bow, but never on a bow's *placement*.

This module gives each hardware kind a set of named placement recipes
that return a list of `(name, u, v, scale_mult)` anchors. A library
entry picks one via the `*_placement` field on LibraryEntry. The build
functions in render3d_uv.py instantiate one mesh per anchor.

If a placement is "" or unknown, the build function falls back to the
legacy single-anchor behavior — old library entries keep working
without changes.

Convention:
  u ∈ [-1, 1]  (0 = front center, ±1 = back seam)
  v ∈ [0, 1]   (0 = crotch, 1 = neck base)
  scale_mult   multiplies the base size of the piece (0.6 = smaller bow)
"""
from __future__ import annotations
from typing import Callable


# ---------------------------------------------------------------------------
# Bow placements
# ---------------------------------------------------------------------------

def _bow_single_center(g):
    return [("bow_C", 0.0, getattr(g, "top_center_v", 0.74), 1.0)]


def _bow_hip_pair(g):
    # Bows on either hip — common on tie-side bikinis.
    return [
        ("bow_LH", -0.45, 0.48, 0.7),
        ("bow_RH", +0.45, 0.48, 0.7),
    ]


def _bow_back_neck(g):
    # Single bow at back-of-neck (halter knot decorative bow).
    # u=1 is back seam; v=0.94 is just below neck base.
    return [("bow_BN", 1.0, 0.94, 0.9)]


def _bow_three(g):
    # Front center + two smaller hip bows.
    v_top = getattr(g, "top_center_v", 0.74)
    return [
        ("bow_C",  0.0,  v_top, 0.8),
        ("bow_LH", -0.40, 0.48, 0.55),
        ("bow_RH", +0.40, 0.48, 0.55),
    ]


def _bow_butt_pair(g):
    # Back-side decorative bows (above each butt cheek).
    # u≈±0.7 reaches the back-flank curve.
    return [
        ("bow_LB", -0.70, 0.38, 0.65),
        ("bow_RB", +0.70, 0.38, 0.65),
    ]


def _bow_collar_pair(g):
    # Pair flanking the sternum on the upper chest — bralette dress
    # style. Inside the inner cup edge.
    v_top = getattr(g, "top_center_v", 0.74)
    return [
        ("bow_LC", -0.08, v_top + 0.04, 0.55),
        ("bow_RC", +0.08, v_top + 0.04, 0.55),
    ]


BOW_PLACEMENTS: dict[str, Callable] = {
    "single_center": _bow_single_center,
    "hip_pair":      _bow_hip_pair,
    "back_neck":     _bow_back_neck,
    "three":         _bow_three,
    "butt_pair":     _bow_butt_pair,
    "collar_pair":   _bow_collar_pair,
}


# ---------------------------------------------------------------------------
# Beads placements
#
# Beads are tiny spheres along a curve. A placement returns the (u, v)
# control points — the build function strings beads between them at
# fixed pitch.
# ---------------------------------------------------------------------------

def _beads_bust_ring(g):
    # The legacy behavior — beads along the bust ring from cup edge to
    # back seam, mirrored.
    v = getattr(g, "top_center_v", 0.74)
    inner = getattr(g, "top_inner_u", 0.15)
    half = getattr(g, "top_half_u", 0.18)
    cup_outer = inner + 2 * half
    # Anchor pts: 6 points outward to back seam on each side.
    pts = []
    for i, u in enumerate([cup_outer + 0.02, 0.40, 0.60, 0.80, 0.92, 1.0]):
        pts.append((f"bead_R{i}", float(u), v, 1.0))
        pts.append((f"bead_L{i}", float(-u), v, 1.0))
    return pts


def _beads_drape_y(g):
    # Vertical drape from sternum down to waist, single center column.
    v_top = getattr(g, "top_center_v", 0.74)
    pts = []
    for i, v in enumerate([v_top - 0.04, v_top - 0.12, v_top - 0.20,
                            v_top - 0.28, v_top - 0.36]):
        pts.append((f"bead_DR{i}", 0.0, float(v), 1.0))
    return pts


def _beads_halter_loop(g):
    # Beaded halter strap — from one cup top, around the back of the
    # neck, to the other cup top.
    v_top = getattr(g, "top_center_v", 0.74)
    v_neck = 0.95
    pts = [
        ("bead_NL3", -0.18, v_top + 0.02, 1.0),
        ("bead_NL2", -0.20, v_top + 0.10, 1.0),
        ("bead_NL1", -0.20, v_neck - 0.04, 1.0),
        ("bead_NC",   1.00, v_neck,       1.0),  # back of neck
        ("bead_NR1", +0.20, v_neck - 0.04, 1.0),
        ("bead_NR2", +0.20, v_top + 0.10, 1.0),
        ("bead_NR3", +0.18, v_top + 0.02, 1.0),
    ]
    return pts


def _beads_side_swag(g):
    # Two side swags hanging from waist — connect waist to upper hip
    # on each side.
    pts = []
    for i, v in enumerate([0.55, 0.50, 0.46, 0.42]):
        pts.append((f"bead_SLR{i}", -0.50 - i * 0.04, float(v), 1.0))
        pts.append((f"bead_SRR{i}", +0.50 + i * 0.04, float(v), 1.0))
    return pts


BEADS_PLACEMENTS: dict[str, Callable] = {
    "bust_ring":   _beads_bust_ring,
    "drape_y":     _beads_drape_y,
    "halter_loop": _beads_halter_loop,
    "side_swag":   _beads_side_swag,
}


# ---------------------------------------------------------------------------
# Shell (or any single decorative charm) placements
# ---------------------------------------------------------------------------

def _shell_single_charm(g):
    # Legacy: one shell hanging below the sternum bridge.
    v_top = getattr(g, "top_center_v", 0.74)
    return [("shell_C", 0.0, v_top - 0.05, 1.0)]


def _shell_collar_row(g):
    # A small row of three shells across the upper chest, suggesting
    # a beach-themed collar charm.
    v_top = getattr(g, "top_center_v", 0.74)
    return [
        ("shell_L", -0.12, v_top + 0.02, 0.6),
        ("shell_C",  0.0,  v_top + 0.03, 0.7),
        ("shell_R", +0.12, v_top + 0.02, 0.6),
    ]


def _shell_navel(g):
    # One shell sitting at the navel — common on belly chains.
    return [("shell_navel", 0.0, 0.50, 0.8)]


def _shell_hip_pair(g):
    # Twin shells at outer hip — boho swim style.
    return [
        ("shell_LH", -0.55, 0.45, 0.7),
        ("shell_RH", +0.55, 0.45, 0.7),
    ]


SHELL_PLACEMENTS: dict[str, Callable] = {
    "single_charm": _shell_single_charm,
    "collar_row":   _shell_collar_row,
    "navel":        _shell_navel,
    "hip_pair":     _shell_hip_pair,
}


# ---------------------------------------------------------------------------
# Fringe placements
#
# A placement returns (band_u_start, band_u_end, band_v, n_strands,
# length_scale) tuples — one per fringe band. The build function reads
# this and creates n_strands tubes hanging from the band line.
# ---------------------------------------------------------------------------

def _fringe_front_hem(g):
    # Legacy: front leg-opening, 9 strands across u=[-0.30, +0.30].
    return [(-0.30, +0.30, "leg_hem_front", 9, 1.0)]


def _fringe_full_ring(g):
    # All the way around the hip — 24 strands in 3 spans (front + L + R).
    return [
        (-0.30, +0.30, "leg_hem_front", 9, 1.0),
        (-0.95, -0.32, "leg_hem_left",  9, 1.0),
        (+0.32, +0.95, "leg_hem_right", 9, 1.0),
    ]


def _fringe_long_drape(g):
    # Long flowing strands at front only, fewer but each longer.
    return [(-0.40, +0.40, "long_drape", 7, 2.0)]


def _fringe_side_only(g):
    # Fringe only on one side — asymmetric design.
    return [(+0.20, +0.50, "side_R", 5, 1.4)]


def _fringe_upper_band(g):
    # Fringe hanging from underbust band — flapper style.
    v_top = getattr(g, "top_center_v", 0.74)
    return [(-0.30, +0.30, "underbust", 9, 0.7),
            (0.0, 0.0, "_anchor_v", 1, v_top - 0.05)]  # marker: place at this v


FRINGE_PLACEMENTS: dict[str, Callable] = {
    "front_hem":   _fringe_front_hem,
    "full_ring":   _fringe_full_ring,
    "long_drape":  _fringe_long_drape,
    "side_only":   _fringe_side_only,
    "upper_band":  _fringe_upper_band,
}


# ---------------------------------------------------------------------------
# Resolve API — used by render3d_uv.py
# ---------------------------------------------------------------------------

def resolve_bow(placement_key: str, g) -> list:
    """Return list of (name, u, v, scale_mult) for bow placement, or [] if
    placement_key is unknown / empty — caller falls back to legacy."""
    fn = BOW_PLACEMENTS.get(placement_key)
    return fn(g) if fn else []


def resolve_beads(placement_key: str, g) -> list:
    fn = BEADS_PLACEMENTS.get(placement_key)
    return fn(g) if fn else []


def resolve_shell(placement_key: str, g) -> list:
    fn = SHELL_PLACEMENTS.get(placement_key)
    return fn(g) if fn else []


def resolve_fringe(placement_key: str, g) -> list:
    fn = FRINGE_PLACEMENTS.get(placement_key)
    return fn(g) if fn else []


# Used by smoke-test + library count checks.
def all_placements() -> dict[str, list[str]]:
    return {
        "bow":    sorted(BOW_PLACEMENTS),
        "beads":  sorted(BEADS_PLACEMENTS),
        "shell":  sorted(SHELL_PLACEMENTS),
        "fringe": sorted(FRINGE_PLACEMENTS),
    }


if __name__ == "__main__":
    # Sanity: every placement function returns non-empty list given a
    # bare object that exposes the few attributes they read.
    class _G:
        top_center_v = 0.74
        top_inner_u = 0.15
        top_half_u = 0.18

    g = _G()
    for kind, fn_map in [
        ("bow", BOW_PLACEMENTS), ("beads", BEADS_PLACEMENTS),
        ("shell", SHELL_PLACEMENTS), ("fringe", FRINGE_PLACEMENTS),
    ]:
        print(f"=== {kind} ===")
        for name, fn in fn_map.items():
            out = fn(g)
            assert len(out) >= 1, f"{kind}.{name} empty"
            print(f"  {name:15s}: {len(out)} pts")
    print("OK")
