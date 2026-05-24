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
    "none",                  # 0 — no cutout (default)
    "side_left_circle",      # 1 — circular hole on left side of bottom panel
    "side_right_circle",     # 2 — circular hole on right side
    "under_bust_band",       # 3 — thin horizontal slice removed under cup
    "navel_circle",          # 4 — small circle around navel
    "navel_diamond",         # 5 — diamond shape around navel
    "collar_v",              # 6 — V-cut from neckline down between cups
    "collar_keyhole",        # 7 — keyhole (small circle) at sternum
    "collar_o",              # 8 — round opening at upper chest center
    "back_panel_remove",     # 9 — large rectangular cutout at upper back
    "asym_panel_left",       # 10 — asymmetric chunk removed from left torso
    "asym_panel_right",      # 11 — asymmetric chunk removed from right torso
    "waist_diagonal",        # 12 — diagonal slice through waist
    "hip_window",            # 13 — small rectangular window at hip
    "mid_torso_window",      # 14 — horizontal window mid-torso (between bust and waist)
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

    # Side cutouts — apply only when there's a side panel (one-piece or wide
    # brief). For triangle/string archetypes the bottom is too narrow for
    # side cutouts to land on fabric, so they no-op naturally (the cutout
    # polygon is just outside the fabric polygon).
    if mode == "side_left_circle":
        return [_circle(-0.30, 0.42, 0.05, 0.06)]
    if mode == "side_right_circle":
        return [_circle(+0.30, 0.42, 0.05, 0.06)]

    # Under-bust thin slice (horizontal cut below cup line, between cups
    # and abdomen). v=0.55-0.60 is the under-bust band; cut a thin strip.
    if mode == "under_bust_band":
        return [_rect(-0.30, +0.30, 0.55, 0.59)]

    # Navel cutouts at v~0.48 (between hip and bust = navel level)
    if mode == "navel_circle":
        return [_circle(0.0, 0.48, 0.05, 0.06)]
    if mode == "navel_diamond":
        return [_diamond(0.0, 0.48, 0.07, 0.09)]

    # Collar / neckline cutouts at top of cup, v=0.78-0.86
    if mode == "collar_v":
        # V-cut from cup center going up
        return [[
            (-0.04, 0.74), (+0.04, 0.74),
            (+0.10, 0.86), (-0.10, 0.86),
            (-0.04, 0.74),
        ]]
    if mode == "collar_keyhole":
        return [_circle(0.0, 0.80, 0.04, 0.05)]
    if mode == "collar_o":
        return [_circle(0.0, 0.78, 0.07, 0.07)]

    # Back panel removal — large rectangle at the back seam region.
    # u ≈ ±1 is the back seam. Cut a band there at chest height.
    if mode == "back_panel_remove":
        return [
            _rect(-1.00, -0.80, 0.60, 0.85),
            _rect(+0.80, +1.00, 0.60, 0.85),
        ]

    # Asymmetric panel cutouts — diagonal-feel chunk on one side of mid-torso
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

    # Waist diagonal: cuts a diagonal slice through the waist (only
    # affects one-piece / wide brief style fabric there)
    if mode == "waist_diagonal":
        return [[
            (-0.35, 0.48), (-0.10, 0.55),
            (+0.35, 0.52), (+0.10, 0.45),
            (-0.35, 0.48),
        ]]

    # Hip window: small rect at the hip-side area (works on briefs)
    if mode == "hip_window":
        return [
            _rect(-0.45, -0.30, 0.42, 0.52),
            _rect(+0.30, +0.45, 0.42, 0.52),
        ]

    # Mid-torso horizontal window (for one-pieces)
    if mode == "mid_torso_window":
        return [_rect(-0.25, +0.25, 0.55, 0.65)]

    # Unknown mode -> no-op (defensive)
    return []


def _smoke_test():
    """Sanity: each mode produces parseable polygons (or empty list for none)."""
    for mode in CUTOUT_MODES:
        polys = cutout_polygons(mode)
        if mode == "none":
            assert polys == [], f"{mode} should be empty, got {polys}"
        else:
            assert len(polys) >= 1, f"{mode} produced no polygons"
            for p in polys:
                assert len(p) >= 4, f"{mode} polygon too short"
                assert p[0] == p[-1], f"{mode} polygon not closed"
        n_pts = sum(len(p) for p in polys)
        print(f"  {mode:25s}: {len(polys)} poly(s), {n_pts} pts total")


if __name__ == "__main__":
    print(f"CUTOUT_MODES: {len(CUTOUT_MODES)}")
    _smoke_test()
    print("OK")
