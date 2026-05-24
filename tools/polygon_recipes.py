"""
Polygon recipes — geometry generators for cup / bottom / strap / gore
PatternPieces, refactored from `tools/verify_ga_uv.py`'s private
`_cup_polygon` / `_bottom_*` family.

In the v2 architecture each LibraryEntry of geometry kind references
ONE recipe by name (`base_polygon_recipe`). The recipe takes a
**local_params dict** (NOT a full Genome) where keys / ranges come
from the entry's `local_params_schema`. This gives clean separation:

  - LibraryEntry declares which recipe + which params it uses
  - Recipe is pure geometry, no Genome coupling, no archetype branching
  - Outfit's slot_assignment carries the concrete local_params values

The recipes return polygons in the same body-cylinder UV space
([-1, 1] × [0, 1]) the rest of the pipeline already consumes, so
`build_fabric_shell` etc. work unchanged.

Keys in local_params per recipe (with sensible defaults if missing):

  cup_triangle / cup_balconette / cup_bandeau:
    half_u, half_v, inner_u, apex_lift, underband_dip, center_v

  bottom_thong / bottom_brief:
    front_top_v, front_half_u, front_leg_curve, back_top_v, back_half_u

  side_tie:
    front_top_v, back_top_v, half_u_at (where on body, default 0.5)

  center_gore:
    inner_u, half_v, center_v, apex_lift, underband_dip

  back_top_band:
    center_v, height, reach
"""
from __future__ import annotations

from typing import Callable

# v=0 in genome UV maps via cylindrical_uvs(body) to body y ≈ 56.6 cm
# (= y_min + 0.337*body_height for the current NPC). That's mid-thigh,
# NOT the actual perineum. Actual perineum sits around body y ≈ 78-80
# (≈ y_pelvis - 8 cm), which corresponds to v ≈ 0.20-0.22.
#
# 2026-05-24: CROTCH_V raised 0.06 → 0.22 so polygon bottom edges align
# with the actual crotch. The old 0.06 value caused thong/brazilian
# polygons to sit mostly in the upper-thigh body region (which the
# body_region_classifier rejects as "leg"), producing empty meshes
# silently.
#
# Side effect: brief/highwaist polygons get slightly smaller (their
# v range starts at 0.22 instead of 0.06) but stay anatomically
# correct — the original 0.06 bottom was meaningless fabric on the leg.
CROTCH_V = 0.16     # body crotch in genome UV (lowest v any bottom polygon should reach)


# ---------------------------------------------------------------------------
# Internal helper: param fetch with defaults
# ---------------------------------------------------------------------------

def _p(params: dict, name: str, default: float) -> float:
    return float(params.get(name, default))


# ---------------------------------------------------------------------------
# Cup recipes
# ---------------------------------------------------------------------------

def cup_triangle(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Triangle / Brazilian / string cup. Concave V at top, gentle bottom."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.07)
    hu = _p(params, "half_u", 0.16)
    inner_u = _p(params, "inner_u", 0.10)
    apex = _p(params, "apex_lift", 0.15) * 0.6
    dip = _p(params, "underband_dip", 0.05) * 0.3

    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    top_v_outer = cv + hv
    top_v_inner = cv + hv - apex
    bot_v_outer = cv - hv
    bot_v_inner = cv - hv + dip
    return [
        (inner, top_v_inner),
        (outer, top_v_outer),
        (outer, bot_v_outer),
        (inner, bot_v_inner),
        (inner, top_v_inner),
    ]


def cup_balconette(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Balconette: wide horizontal cut, flatter top edge, slight underband
    curve. Same 5-point closed polygon, different curvature defaults."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.08)
    hu = _p(params, "half_u", 0.20)
    inner_u = _p(params, "inner_u", 0.07)
    # balconette: top edge nearly horizontal (low apex_lift), gentle dip
    apex = _p(params, "apex_lift", 0.0) * 0.4
    dip = _p(params, "underband_dip", 0.0) * 0.5
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    top_v_outer = cv + hv
    top_v_inner = cv + hv - apex
    bot_v_outer = cv - hv
    bot_v_inner = cv - hv + dip
    return [
        (inner, top_v_inner),
        (outer, top_v_outer),
        (outer, bot_v_outer),
        (inner, bot_v_inner),
        (inner, top_v_inner),
    ]


def cup_bandeau(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Bandeau: each half is a wide rectangle; the two halves touch (or
    nearly touch) at center so they read as one continuous strip."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.10)
    hu = _p(params, "half_u", 0.22)
    inner_u = _p(params, "inner_u", 0.0)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    top_v = cv + hv
    bot_v = cv - hv
    return [
        (inner, top_v), (outer, top_v),
        (outer, bot_v), (inner, bot_v),
        (inner, top_v),
    ]


def cup_sweetheart(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Sweetheart: heart-shaped neckline. Top edge has a CENTER dip
    (where the two breasts meet) and rises toward the outer side, giving
    the classic heart/V-with-curves shape.

    9-point polygon traces the heart curve: rises from inner-bottom up
    over a peak at ~30% of the cup width, dips down again at center for
    the heart V, mirrors on outer half (per side, the recipe returns one
    side; mirroring is handled by the caller).
    """
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.08)
    hu = _p(params, "half_u", 0.20)
    inner_u = _p(params, "inner_u", 0.08)
    apex_drop = _p(params, "apex_lift", 0.20) * 0.45
    dip = _p(params, "underband_dip", 0.0) * 0.3

    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    mid_u = (inner + outer) / 2
    top_v_outer = cv + hv
    top_v_peak  = cv + hv + apex_drop * 0.5   # peak slightly above outer
    top_v_inner = cv + hv - apex_drop * 1.2   # V dip at center for heart
    bot_v_outer = cv - hv
    bot_v_inner = cv - hv + dip
    return [
        (inner,  top_v_inner),
        (mid_u * 0.5 + inner * 0.5, top_v_peak),     # upward sweep
        (mid_u, top_v_outer + apex_drop * 0.2),       # heart bump
        (mid_u * 0.5 + outer * 0.5, top_v_peak),      # second bump
        (outer,  top_v_outer),
        (outer,  bot_v_outer),
        (mid_u,  (bot_v_outer + bot_v_inner) / 2),    # smooth underband
        (inner,  bot_v_inner),
        (inner,  top_v_inner),
    ]


def cup_wrap(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Wrap / surplice: asymmetric drape where one cup extends inward
    past midline, simulating one piece wrapping over the other.

    Side=1 (right) extends inward; side=-1 (left) is the back panel
    (smaller). Asymmetry creates the visual cross-front drape.
    """
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.10)
    hu = _p(params, "half_u", 0.22)
    inner_u = _p(params, "inner_u", 0.05)
    asym = _p(params, "asym_amount", 0.15)

    if side > 0:
        # Right cup: extends inward past midline by asym (wraps over)
        inner = -asym * 0.5    # crosses midline
        outer = inner_u + 2 * hu
        top_v = cv + hv
        bot_v = cv - hv
        # Diagonal top edge — pulls down toward the wrap point
        top_v_inner = cv + hv - asym * 0.2
        return [
            (inner, top_v_inner),
            (outer, top_v),
            (outer, bot_v),
            (inner, bot_v + asym * 0.1),
            (inner, top_v_inner),
        ]
    else:
        # Left cup: smaller, tucks behind
        inner = -inner_u
        outer = -(inner_u + 2 * hu * 0.8)   # narrower
        top_v = cv + hv * 0.85               # lower top
        bot_v = cv - hv
        return [
            (inner, top_v),
            (outer, top_v),
            (outer, bot_v),
            (inner, bot_v),
            (inner, top_v),
        ]


def cup_corset_bands(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Corset-band cup: stacked horizontal bands giving a corset/lingerie
    look. Approximated as a single polygon spanning full cup height,
    with the band detail provided by pattern overlay (the renderer
    paints horizontal stripes in 'stripe' pattern over this shape).

    Geometrically same as bandeau but TALLER. Distinct from cup_bandeau
    via wider hv default and slight outer chamfer.
    """
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.13)     # taller than bandeau
    hu = _p(params, "half_u", 0.21)
    inner_u = _p(params, "inner_u", 0.03)
    chamfer = _p(params, "apex_lift", 0.10) * 0.15

    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    top_v = cv + hv
    bot_v = cv - hv
    # Chamfered outer corners — slight cut at top-outer and bottom-outer
    return [
        (inner, top_v),
        (outer * 0.92, top_v),
        (outer, top_v - chamfer),
        (outer, bot_v + chamfer),
        (outer * 0.92, bot_v),
        (inner, bot_v),
        (inner, top_v),
    ]


# ---------------------------------------------------------------------------
# Bottom recipes
# ---------------------------------------------------------------------------

def bottom_thong(params: dict) -> list[tuple[float, float]]:
    """Front panel of a thong/brazilian/cheeky bottom (used for the FRONT
    panel — back is built separately via back_bottom_strips)."""
    top_v = _p(params, "front_top_v", 0.25)
    hu = _p(params, "front_half_u", 0.18)
    leg = _p(params, "front_leg_curve", 0.65) * 0.5
    cv = CROTCH_V
    return [
        (-hu, top_v),
        ( hu, top_v),
        ( hu * (1 - 0.5 * leg), (top_v + cv) / 2),
        ( max(0.05, hu * 0.25), cv),
        (-max(0.05, hu * 0.25), cv),
        (-hu * (1 - 0.5 * leg), (top_v + cv) / 2),
        (-hu, top_v),
    ]


def bottom_brief(params: dict) -> list[tuple[float, float]]:
    """Front panel of brief / cheeky / high_waisted bottom — wider hu and
    a flatter leg curve than thong."""
    top_v = _p(params, "front_top_v", 0.34)
    hu = _p(params, "front_half_u", 0.22)
    leg = _p(params, "front_leg_curve", 0.45) * 0.5
    cv = CROTCH_V
    return [
        (-hu, top_v),
        ( hu, top_v),
        ( hu * (1 - 0.4 * leg), (top_v + cv) / 2),
        ( max(0.10, hu * 0.45), cv),
        (-max(0.10, hu * 0.45), cv),
        (-hu * (1 - 0.4 * leg), (top_v + cv) / 2),
        (-hu, top_v),
    ]


def back_bottom_strips(params: dict) -> list[list[tuple[float, float]]]:
    """Two back-panel strips (one per back seam at u = ±1)."""
    top_v = _p(params, "back_top_v", 0.25)
    hu = _p(params, "back_half_u", 0.10)
    cv = CROTCH_V
    left = [
        (-1.0, top_v), (-1.0 + hu, top_v),
        (-1.0 + hu * 0.6, cv), (-1.0, cv), (-1.0, top_v),
    ]
    right = [
        (1.0 - hu, top_v), (1.0, top_v),
        (1.0, cv), (1.0 - hu * 0.6, cv), (1.0 - hu, top_v),
    ]
    return [left, right]


# ---------------------------------------------------------------------------
# Side tie + back top band + center gore recipes
# ---------------------------------------------------------------------------

def side_tie(params: dict) -> list[list[tuple[float, float]]]:
    """Side connector strips bridging front and back bottom waistlines
    at u = ±half_u_at (default ±0.5)."""
    fv = _p(params, "front_top_v", 0.25)
    bv = _p(params, "back_top_v", 0.25)
    u0 = _p(params, "half_u_at", 0.5)
    w = _p(params, "width", 0.06)
    v_lo = min(fv, bv) - 0.03
    v_hi = max(fv, bv) + 0.01
    return [
        [(-u0 - w, v_lo), (-u0 + w, v_lo),
          (-u0 + w, v_hi), (-u0 - w, v_hi), (-u0 - w, v_lo)],
        [( u0 - w, v_lo), ( u0 + w, v_lo),
          ( u0 + w, v_hi), ( u0 - w, v_hi), ( u0 - w, v_lo)],
    ]


def back_top_band(params: dict) -> list[list[tuple[float, float]]]:
    """Two back-panel strips at chest level (one per side seam) for
    archetypes with a continuous back band (bandeau / bralette /
    one-piece). For triangle/string halter the back panel is replaced
    by a tie cord and these strips should not be emitted."""
    cv = _p(params, "center_v", 0.74)
    coverage = _p(params, "coverage", 0.55)
    if coverage < 0.05:
        return []
    band_h = 0.04 + 0.30 * coverage
    reach = 0.10 + 0.45 * coverage
    v0 = cv - band_h / 2
    v1 = cv + band_h / 2
    left = [(-1.0, v0), (-1.0 + reach, v0),
             (-1.0 + reach, v1), (-1.0, v1), (-1.0, v0)]
    right = [(1.0 - reach, v0), (1.0, v0),
              (1.0, v1), (1.0 - reach, v1), (1.0 - reach, v0)]
    return [left, right]


def center_gore(params: dict) -> list[tuple[float, float]] | None:
    """Bridge polygon between the two cups at the sternum (only emitted
    if cups don't touch — i.e. inner_u > 0)."""
    inner_u = _p(params, "inner_u", 0.10)
    if inner_u < 0.01:
        return None
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.07)
    dip = _p(params, "underband_dip", 0.05) * 0.3
    apex = _p(params, "apex_lift", 0.15) * 0.6
    v_bot = cv - hv + dip
    v_top = cv + hv - apex
    v_top = max(v_bot + 0.02, v_top - 0.6 * (v_top - v_bot))
    return [
        (-inner_u, v_bot), (inner_u, v_bot),
        (inner_u, v_top), (-inner_u, v_top), (-inner_u, v_bot),
    ]


# ---------------------------------------------------------------------------
# Recipe registry — looked up by LibraryEntry.base_polygon_recipe
# ---------------------------------------------------------------------------

RECIPES: dict[str, Callable] = {
    "cup_triangle":     cup_triangle,
    "cup_balconette":   cup_balconette,
    "cup_bandeau":      cup_bandeau,
    "cup_sweetheart":   cup_sweetheart,
    "cup_wrap":         cup_wrap,
    "cup_corset_bands": cup_corset_bands,
    "bottom_thong":     bottom_thong,
    "bottom_brief":     bottom_brief,
    "back_bottom_strips": back_bottom_strips,
    "side_tie":         side_tie,
    "back_top_band":    back_top_band,
    "center_gore":      center_gore,
}


def get_recipe(name: str) -> Callable:
    if name not in RECIPES:
        raise KeyError(f"unknown polygon recipe '{name}'. "
                        f"Known: {sorted(RECIPES.keys())}")
    return RECIPES[name]


def call_recipe(name: str, params: dict, **kwargs):
    """Convenience wrapper: get_recipe(name)(params, **kwargs)."""
    return get_recipe(name)(params, **kwargs)


# ---------------------------------------------------------------------------
# Quick smoke
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("registered recipes:", sorted(RECIPES.keys()))
    # Sanity: every recipe runs with empty params (defaults kick in)
    p = cup_triangle({}, side=1)
    print(f"cup_triangle default: {len(p)} pts, span "
          f"u=[{min(x for x,_ in p):.2f}, {max(x for x,_ in p):.2f}]")
    p = bottom_thong({})
    print(f"bottom_thong default: {len(p)} pts, span "
          f"v=[{min(y for _,y in p):.2f}, {max(y for _,y in p):.2f}]")
    bt = back_top_band({"coverage": 0.7})
    print(f"back_top_band(coverage=0.7): {len(bt)} strips")
