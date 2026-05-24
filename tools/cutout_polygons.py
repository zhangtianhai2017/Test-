"""Cutout system — subtractive polygon regions removed from the fabric
shell after extraction.

A cutout MODE is a name (e.g. "side_left_circle", "navel_diamond").
`cutout_polygons(mode, archetype)` returns a list of UV-space polygons
(each = list of (u, v) tuples). Any shell triangle whose centroid sits
inside ANY of these polygons is dropped from the mesh, leaving the body
visible through the hole.

UV-space convention (matches polygon_recipes.py + cylindrical_uvs):
  u in [-1, 1]  — 0 = front center, ±1 = back seam
  v in [0, 1]   — 0 = body crotch (via cylindrical_uvs y_min frac),
                  1 = body neck base
  v ~ 0.50      — pelvis ridge / navel level
  v ~ 0.74      — bust peak
  v ~ 0.90      — collarbone

Each polygon is a closed loop (last pt == first). Most are simple
shapes (circle approx, rect, diamond, V) chosen so the cutout reads
recognizably on body. Phase 1f, 2026-05-24.

Added to NN's discrete head via discrete_sizes_from_library() picking
up `len(CUTOUT_MODES)`. ConfigToOutfit reads the pick and writes it to
`outfit.global_design["cutout_mode"]`; iter.capture.render_views looks
it up and asks for the corresponding polygons.
"""
from __future__ import annotations
import math


CUTOUT_MODES: list[str] = [
    # Keep 15 names so existing trained checkpoints (cutout head sized 15)
    # still load. But several of them are now ALIASED TO no-op via the
    # cutout_polygons() returning []. User flagged "circular ring at
    # navel" — root was that 8/15 modes were circles/diamonds at navel
    # or torso center, and NN softmax gave only 7% chance to pick "none".
    # Active (real cutout polys): none, collar_v, back_panel_remove,
    #   asym_panel_left, asym_panel_right, mid_torso_window.
    # Aliased to no-op: side_left_circle, side_right_circle,
    #   under_bust_band, navel_circle, navel_diamond, collar_keyhole,
    #   collar_o, waist_diagonal, hip_window.
    "none",                  # 0 — no cutout (default)
    "side_left_circle",      # 1 — ALIASED no-op
    "side_right_circle",     # 2 — ALIASED no-op
    "under_bust_band",       # 3 — ALIASED no-op
    "navel_circle",          # 4 — ALIASED no-op (user complaint)
    "navel_diamond",         # 5 — ALIASED no-op (user complaint)
    "collar_v",              # 6 — V-cut at neckline (kept)
    "collar_keyhole",        # 7 — ALIASED no-op
    "collar_o",              # 8 — ALIASED no-op
    "back_panel_remove",     # 9 — back cutout (kept)
    "asym_panel_left",       # 10 — asymmetric panel (kept)
    "asym_panel_right",      # 11 — asymmetric panel (kept)
    "waist_diagonal",        # 12 — ALIASED no-op (user complaint)
    "hip_window",            # 13 — ALIASED no-op
    "mid_torso_window",      # 14 — horizontal window (kept)
]


def _circle(cu: float, cv: float, r_u: float, r_v: float | None = None,
            n: int = 18) -> list[tuple[float, float]]:
    """Approximated circle/ellipse polygon centered at (cu, cv).
    `r_u` = horizontal half-axis in u-space, `r_v` = vertical half-axis
    in v-space (defaults to same as r_u, giving a circle in UV space)."""
    if r_v is None:
        r_v = r_u
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        pts.append((cu + r_u * math.cos(a), cv + r_v * math.sin(a)))
    pts.append(pts[0])
    return pts


def _rect(u_lo: float, u_hi: float, v_lo: float, v_hi: float
          ) -> list[tuple[float, float]]:
    """Axis-aligned rectangle polygon."""
    return [
        (u_lo, v_lo), (u_hi, v_lo),
        (u_hi, v_hi), (u_lo, v_hi),
        (u_lo, v_lo),
    ]


def _diamond(cu: float, cv: float, half_u: float, half_v: float
             ) -> list[tuple[float, float]]:
    return [
        (cu, cv - half_v), (cu + half_u, cv),
        (cu, cv + half_v), (cu - half_u, cv),
        (cu, cv - half_v),
    ]


def cutout_polygons(mode: str,
                    archetype: str = "triangle_string_halter"
                    ) -> list[list[tuple[float, float]]]:
    """Return cutout polygons for the given mode + archetype.

    Returns empty list for "none" or unknown modes (defensive).
    Returns one or more polygons that the renderer subtracts from the
    fabric shell.
    """
    if mode == "none" or not mode:
        return []

    # Collar V-cut: vertical V from cup top going up to neckline.
    # Real design feature for bandeau / plunge styles.
    if mode == "collar_v":
        return [[
            (-0.04, 0.74), (+0.04, 0.74),
            (+0.10, 0.86), (-0.10, 0.86),
            (-0.04, 0.74),
        ]]

    # Back panel removal — large rectangle at the back seam region.
    # u≈±1 is back seam. Invisible from front camera.
    if mode == "back_panel_remove":
        return [
            _rect(-1.00, -0.80, 0.60, 0.85),
            _rect(+0.80, +1.00, 0.60, 0.85),
        ]

    # Asymmetric panel cutouts — diagonal chunk on one side of mid-torso
    if mode == "asym_panel_left":
        return [[
            (-0.30, 0.45), (-0.10, 0.50),
            (-0.05, 0.65), (-0.25, 0.62),
            (-0.30, 0.45),
        ]]
    if mode == "asym_panel_right":
        return [[
            (+0.30, 0.45), (+0.10, 0.50),
            (+0.05, 0.65), (+0.25, 0.62),
            (+0.30, 0.45),
        ]]

    # Mid-torso horizontal window (rare modern one-piece design)
    if mode == "mid_torso_window":
        return [_rect(-0.25, +0.25, 0.55, 0.65)]

    # Deep-V under-bust: vertical V from underbust down to abdomen,
    # for plunging designs. Note narrow + tall, not a hole.
    if mode == "deep_v_underbust":
        return [[
            (-0.03, 0.66), (+0.03, 0.66),
            (+0.08, 0.50), (-0.08, 0.50),
            (-0.03, 0.66),
        ]]

    # Unknown mode -> no-op (defensive)
    return []


_ALIASED_NO_OP = {
    "side_left_circle", "side_right_circle", "under_bust_band",
    "navel_circle", "navel_diamond", "collar_keyhole", "collar_o",
    "waist_diagonal", "hip_window",
}


def _smoke_test():
    """Sanity: each mode produces parseable polygons (or empty list for
    none + aliased-no-op modes that intentionally have no implementation)."""
    n_active = 0
    n_aliased = 0
    for mode in CUTOUT_MODES:
        polys = cutout_polygons(mode)
        if mode == "none":
            assert polys == [], f"{mode} should be empty, got {polys}"
        elif mode in _ALIASED_NO_OP:
            assert polys == [], f"{mode} is aliased no-op, expected []"
            n_aliased += 1
        else:
            assert len(polys) >= 1, f"{mode} produced no polygons"
            for p in polys:
                assert len(p) >= 4, f"{mode} polygon too short"
                assert p[0] == p[-1], f"{mode} polygon not closed"
            n_active += 1
        n_pts = sum(len(p) for p in polys)
        tag = " (aliased)" if mode in _ALIASED_NO_OP else ""
        print(f"  {mode:25s}: {len(polys)} poly(s), {n_pts} pts total{tag}")
    print(f"\nactive modes: {n_active}  |  aliased no-op: {n_aliased}  |  none: 1")


if __name__ == "__main__":
    print(f"CUTOUT_MODES: {len(CUTOUT_MODES)}")
    _smoke_test()
    print("OK")
