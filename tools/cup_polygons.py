"""Per-cup-type polygon recipes — replaces the 6 shared recipes
(cup_triangle, cup_balconette, cup_bandeau, cup_softcup, cup_sweetheart,
cup_wrap, cup_corset_bands) that 60 cup library entries were calling
with merely different params.

Phase 2 #6b rewrite (2026-05-24): same problem as bottoms — different
cup IDs collapsed to same shape family at render time. Each cup TYPE
gets its own polygon function with reference inline.

Each recipe is per-half (returns ONE side; the caller mirrors u for
the other side). Functions take (params, side=1) where side ∈ {+1, -1}.

UV convention (matches polygon_recipes.py):
  u in [-1, 1]   — 0 = front center, ±1 = back seam
  v in [0, 1]    — typical cup v range 0.60-0.90
"""
from __future__ import annotations
from typing import Callable


def _p(params: dict, name: str, default: float) -> float:
    return float(params.get(name, default))


# v-coordinate safety band — keeps polygon vertices inside the
# body_region_classifier's torso/pelvis zone. Above 0.95 the renderer
# rejects triangles as head_neck. Below 0.16 they'd land in legs.
# Phase 2 bug-fix 2026-05-24: clip every cup polygon vertex into
# this range before returning, so per-type recipes can specify
# expressive shapes without anatomy overflow.
V_HI_SAFE = 0.95
V_LO_SAFE = 0.16


def _clip_v(poly):
    """Clip each vertex's v coord to safe anatomy band."""
    return [(u, max(V_LO_SAFE, min(V_HI_SAFE, v))) for u, v in poly]


# ===========================================================================
# CUP POLYGON RECIPES (per TYPE, not shared)
# Each TYPE has its own polygon shape derived from a real-world cup style.
# ===========================================================================

# ---- Triangle family (5 distinct shapes, not all "triangle") ----

def cup_triangle(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Classic triangle: equilateral/isoceles triangle with flat bottom,
    apex pointing toward sternum. Real ref: classic string bikini cup."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.07)
    hu = _p(params, "half_u", 0.16)
    inner_u = _p(params, "inner_u", 0.10)
    apex = _p(params, "apex_lift", 0.15) * 0.6
    dip = _p(params, "underband_dip", 0.05) * 0.3
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv - apex),
        (outer, cv + hv),
        (outer, cv - hv),
        (inner, cv - hv + dip),
        (inner, cv + hv - apex),
    ]


def cup_brazilian_new(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Brazilian cup: SMALLER, more pointed-bottom triangle than classic.
    Apex more pronounced, inner side cuts back inward. Real ref: Vix
    brazilian, Frankies Brazilian."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.06)
    hu = _p(params, "half_u", 0.12)
    inner_u = _p(params, "inner_u", 0.10)
    apex = _p(params, "apex_lift", 0.20) * 0.7
    dip = _p(params, "underband_dip", 0.04) * 0.4
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    mid_v = (cv + hv + cv - hv) / 2
    return [
        (inner, cv + hv - apex),
        (outer, cv + hv * 0.85),         # outer top slightly lower
        (outer, mid_v),                   # mid-outer (point)
        (inner + side * 0.02, cv - hv + dip),  # narrow bottom
        (inner, cv + hv - apex),
    ]


def cup_halter(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Halter cup: triangle with EXTRA strap-up point at top center
    (apex stretches UP toward the neck strap). 6-point polygon."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.10)
    hu = _p(params, "half_u", 0.14)
    inner_u = _p(params, "inner_u", 0.12)
    apex = _p(params, "apex_lift", 0.42)
    dip = _p(params, "underband_dip", 0.04) * 0.3
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    # Extra point at top-inner pulls UP toward neck strap
    return [
        (inner, cv + hv + apex * 0.5),       # peak going UP
        (inner + side * 0.04, cv + hv),       # quick down to cup top
        (outer, cv + hv * 0.85),
        (outer, cv - hv),
        (inner, cv - hv + dip),
        (inner, cv + hv + apex * 0.5),
    ]


def cup_plunge(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Plunge: DEEP V between cups, inner edge curves down sharply.
    Real ref: Wolford plunge, Marlies Dekkers plunge balcony."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.10)
    hu = _p(params, "half_u", 0.17)
    inner_u = _p(params, "inner_u", 0.17)
    apex = _p(params, "apex_lift", 0.58)
    dip = _p(params, "underband_dip", 0.05) * 0.3
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    # Inner edge dips DOWN significantly (the V plunge)
    return [
        (inner, cv - hv * 0.5),               # inner top dips into V
        (inner + side * 0.04, cv + hv - apex * 0.3),
        (outer, cv + hv),
        (outer, cv - hv),
        (inner, cv - hv + dip),
        (inner, cv - hv * 0.5),
    ]


def cup_micro_triangle(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Micro triangle: tiny triangle, ~5cm peak-to-peak. Apex strong,
    base very small. Real ref: Frankies micro triangle."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.045)
    hu = _p(params, "half_u", 0.08)
    inner_u = _p(params, "inner_u", 0.07)
    apex = _p(params, "apex_lift", 0.25)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv - apex),
        (outer, cv + hv * 0.9),
        (outer, cv - hv),
        (inner, cv - hv),
        (inner, cv + hv - apex),
    ]


def cup_body_chain(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Body-chain cup: minimal fabric, mostly a small accent piece
    designed to be visually anchored by chain hardware. Diamond shape
    (4-point) rather than triangle. Real ref: Givenchy body chain bra."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.035)
    hu = _p(params, "half_u", 0.07)
    inner_u = _p(params, "inner_u", 0.10)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    mid_u = (inner + outer) / 2
    # Diamond/rhombus shape (not triangle)
    return [
        (mid_u, cv + hv),
        (outer, cv),
        (mid_u, cv - hv),
        (inner, cv),
        (mid_u, cv + hv),
    ]


# ---- Balconette family (4 distinct shapes) ----

def cup_balconette(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Balconette: WIDE horizontal cut, flatter top edge, gentle
    underband curve. Real ref: Wacoal balconette."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.08)
    hu = _p(params, "half_u", 0.20)
    inner_u = _p(params, "inner_u", 0.07)
    apex = _p(params, "apex_lift", 0.0) * 0.4
    dip = _p(params, "underband_dip", 0.0) * 0.5
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv - apex),
        (outer, cv + hv),
        (outer, cv - hv),
        (inner, cv - hv + dip),
        (inner, cv + hv - apex),
    ]


def cup_foam_molded(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Foam-molded cup: structured dome with ROUNDED outer edges.
    Slightly different polygon outline indicating molding seam.
    Real ref: Triangl foam cup, padded swim bra."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.10)
    hu = _p(params, "half_u", 0.18)
    inner_u = _p(params, "inner_u", 0.07)
    apex = _p(params, "apex_lift", 0.04) * 0.5
    dip = _p(params, "underband_dip", 0.02) * 0.4
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    # 6-point polygon to suggest rounded molded edge
    return [
        (inner, cv + hv - apex),
        (inner + side * 0.06, cv + hv * 1.05),     # rounded outer-top
        (outer, cv + hv * 0.85),
        (outer, cv - hv * 0.85),
        (inner + side * 0.06, cv - hv * 1.05),     # rounded outer-bottom
        (inner, cv - hv + dip),
        (inner, cv + hv - apex),
    ]


def cup_push_up(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Push-up: SMALL balcony cup with positive apex lift creating an
    upward sweep. Inner edge tighter. Real ref: Calzedonia push-up."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.09)
    hu = _p(params, "half_u", 0.16)
    inner_u = _p(params, "inner_u", 0.08)
    apex = _p(params, "apex_lift", 0.12) * 0.5
    dip = _p(params, "underband_dip", -0.04) * 0.5
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv - apex),
        (outer, cv + hv * 1.10),                  # outer pulls UP
        (outer, cv - hv * 0.92),
        (inner, cv - hv + dip),
        (inner, cv + hv - apex),
    ]


def cup_demi(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Demi: HALF cup, top edge is FLAT-CUT horizontal above breast peak.
    Polygon is rectangular with tight inner-edge taper.
    Real ref: demi-bra silhouette."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.05)               # very short cup height
    hu = _p(params, "half_u", 0.19)
    inner_u = _p(params, "inner_u", 0.09)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv),                          # flat top
        (outer, cv + hv),
        (outer, cv - hv),
        (inner, cv - hv * 1.10),
        (inner, cv + hv),
    ]


# ---- Bandeau family (3 distinct shapes) ----

def cup_bandeau(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Bandeau: rectangular strip across both breasts (each half is a
    wide rectangle that meets the other at center). Real ref: Hunza G."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.10)
    hu = _p(params, "half_u", 0.22)
    inner_u = _p(params, "inner_u", 0.0)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv), (outer, cv + hv),
        (outer, cv - hv), (inner, cv - hv),
        (inner, cv + hv),
    ]


def cup_bandeau_twist(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Bandeau with center TWIST/KNOT detail. Polygon has an INWARD
    PINCH at the inner edge representing the gathered fabric where the
    twist sits. Real ref: Vix twist bandeau, Hunza G twist."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.11)
    hu = _p(params, "half_u", 0.25)
    inner_u = _p(params, "inner_u", 0.04)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    # Inner edge has a horizontal V-pinch (twist) at the centerline
    return [
        (inner, cv + hv),
        (outer, cv + hv * 1.05),
        (outer, cv - hv * 1.05),
        (inner, cv - hv),
        (inner + side * 0.06, cv),       # pinch point (twist)
        (inner, cv + hv),
    ]


def cup_sliver(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Sliver: ULTRA THIN horizontal band, barely-there strip. Polygon
    is very flat with small hv. Real ref: Reina Olga sliver, body-chain
    bra."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.03)
    hu = _p(params, "half_u", 0.22)
    inner_u = _p(params, "inner_u", 0.01)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv), (outer, cv + hv),
        (outer, cv - hv), (inner, cv - hv),
        (inner, cv + hv),
    ]


# ---- Softcup family (4 distinct shapes — square / cowl / asym / V) ----

def cup_softcup_high_neck(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Soft cup with HIGH SQUARE neckline reaching toward collarbone.
    Tall rectangular polygon with flat top. Real ref: square-neck swim."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.11)
    hu = _p(params, "half_u", 0.20)
    inner_u = _p(params, "inner_u", 0.065)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv * 1.15),       # extends UP for high neck
        (outer, cv + hv),
        (outer, cv - hv),
        (inner, cv - hv * 0.95),
        (inner, cv + hv * 1.15),
    ]


def cup_softcup_asym(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """One-shoulder asymmetric soft cup. One shoulder strap; the OTHER
    side has no strap. Different polygon for left vs right.
    side=+1 has strap-up; side=-1 is flat."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.095)
    hu = _p(params, "half_u", 0.21)
    inner_u = _p(params, "inner_u", 0.045)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    if side > 0:
        # Right cup: outer side pulls up to shoulder strap
        return [
            (inner, cv + hv),
            (outer, cv + hv * 1.6),     # strap-up at outer
            (outer, cv - hv * 0.9),
            (inner, cv - hv),
            (inner, cv + hv),
        ]
    else:
        # Left cup: flat, no strap
        return [
            (inner, cv + hv * 0.85),
            (outer, cv + hv * 0.9),
            (outer, cv - hv),
            (inner, cv - hv),
            (inner, cv + hv * 0.85),
        ]


def cup_softcup_cowl(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Cowl-drape: cups join LOW at center with a draped scoop.
    Inner edge dips down then rises. 6-point polygon for cowl curve."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.09)
    hu = _p(params, "half_u", 0.215)
    inner_u = _p(params, "inner_u", 0.03)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv - hv * 0.3),           # inner-top dips low (cowl)
        (inner + side * 0.05, cv + hv * 0.7),     # cowl rises out
        (outer, cv + hv),
        (outer, cv - hv),
        (inner, cv - hv * 0.95),
        (inner, cv - hv * 0.3),
    ]


def cup_softcup_deep_v(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Deep-V soft: plunging V between cups, like plunge but soft (no
    structure). Inner edge curves down to a deep dip."""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.105)
    hu = _p(params, "half_u", 0.19)
    inner_u = _p(params, "inner_u", 0.10)
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv - hv * 0.4),            # dips into V
        (inner + side * 0.03, cv + hv * 0.5),
        (outer, cv + hv),
        (outer, cv - hv),
        (inner, cv - hv * 0.95),
        (inner, cv - hv * 0.4),
    ]


# ---- Already-distinct (kept from Phase 1b) ----

def cup_sweetheart(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Sweetheart: heart-shaped neckline. 9-point polygon. (Imported
    from polygon_recipes.py — already distinct.)"""
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
    top_v_peak  = cv + hv + apex_drop * 0.5
    top_v_inner = cv + hv - apex_drop * 1.2
    bot_v_outer = cv - hv
    bot_v_inner = cv - hv + dip
    return [
        (inner,  top_v_inner),
        (mid_u * 0.5 + inner * 0.5, top_v_peak),
        (mid_u, top_v_outer + apex_drop * 0.2),
        (mid_u * 0.5 + outer * 0.5, top_v_peak),
        (outer,  top_v_outer),
        (outer,  bot_v_outer),
        (mid_u,  (bot_v_outer + bot_v_inner) / 2),
        (inner,  bot_v_inner),
        (inner,  top_v_inner),
    ]


def cup_wrap(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Wrap/surplice: asymmetric drape. Right cup extends past midline;
    left tucks behind. (Imported from polygon_recipes.py.)"""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.10)
    hu = _p(params, "half_u", 0.22)
    inner_u = _p(params, "inner_u", 0.05)
    asym = _p(params, "asym_amount", 0.15)
    if side > 0:
        inner = -asym * 0.5
        outer = inner_u + 2 * hu
        return [
            (inner, cv + hv - asym * 0.2),
            (outer, cv + hv),
            (outer, cv - hv),
            (inner, cv - hv + asym * 0.1),
            (inner, cv + hv - asym * 0.2),
        ]
    else:
        inner = -inner_u
        outer = -(inner_u + 2 * hu * 0.8)
        return [
            (inner, cv + hv * 0.85),
            (outer, cv + hv * 0.85),
            (outer, cv - hv),
            (inner, cv - hv),
            (inner, cv + hv * 0.85),
        ]


def cup_corset_bands(params: dict, side: int = 1) -> list[tuple[float, float]]:
    """Corset-band: tall cup with chamfered outer corners.
    (Imported from polygon_recipes.py.)"""
    cv = _p(params, "center_v", 0.74)
    hv = _p(params, "half_v", 0.13)
    hu = _p(params, "half_u", 0.21)
    inner_u = _p(params, "inner_u", 0.03)
    chamfer = _p(params, "apex_lift", 0.10) * 0.15
    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)
    return [
        (inner, cv + hv),
        (outer * 0.92, cv + hv),
        (outer, cv + hv - chamfer),
        (outer, cv - hv + chamfer),
        (outer * 0.92, cv - hv),
        (inner, cv - hv),
        (inner, cv + hv),
    ]


# ===========================================================================
# Recipe registry — keyed on geometry_kind (matches library_data.py)
# ===========================================================================

CUP_RECIPES: dict[str, Callable] = {
    # triangle family
    "cup_triangle":       cup_triangle,
    "cup_brazilian_new":  cup_brazilian_new,
    "cup_halter":         cup_halter,
    "cup_plunge":         cup_plunge,
    "cup_micro_triangle": cup_micro_triangle,
    "cup_body_chain":     cup_body_chain,
    # balconette family
    "cup_balconette":     cup_balconette,
    "cup_foam_molded":    cup_foam_molded,
    "cup_push_up":        cup_push_up,
    "cup_demi":           cup_demi,
    # bandeau family
    "cup_bandeau":        cup_bandeau,
    "cup_bandeau_twist":  cup_bandeau_twist,
    "cup_sliver":         cup_sliver,
    # softcup family
    "cup_softcup_high_neck": cup_softcup_high_neck,
    "cup_softcup_asym":    cup_softcup_asym,
    "cup_softcup_cowl":    cup_softcup_cowl,
    "cup_softcup_deep_v":  cup_softcup_deep_v,
    # already-distinct
    "cup_sweetheart":     cup_sweetheart,
    "cup_wrap":           cup_wrap,
    "cup_corset_bands":   cup_corset_bands,
}


# Maps geometry_kind (set in library_data.py per template) to recipe name
GEOMETRY_TO_CUP_RECIPE = {
    "triangle":            "cup_triangle",
    "brazilian":           "cup_brazilian_new",
    "balconette":          "cup_balconette",
    "bandeau_unified":     "cup_bandeau",
    "molded_foam":         "cup_foam_molded",
    "softcup_squareneck":  "cup_softcup_high_neck",   # fallback for 4 softcup styles
    "halter_triangle":     "cup_halter",
    "plunge":              "cup_plunge",
    "push_up":             "cup_push_up",
    "demi":                "cup_demi",
    "bandeau_twist":       "cup_bandeau_twist",
    "micro_triangle":      "cup_micro_triangle",
    "sliver":              "cup_sliver",
    "body_chain_cup":      "cup_body_chain",
    "sweetheart":          "cup_sweetheart",
    "wrap":                "cup_wrap",
    "corset_bands":        "cup_corset_bands",
}


def resolve_cup_recipe(geometry_kind: str, fallback: str = "") -> Callable:
    """Resolve a cup template's polygon recipe.
    Wraps with:
      1. coverage bump: hu/hv multiplied 1.18 so per-type cups produce
         enough fabric area to pass CV's chest_cov >= 0.34 gate (Phase 2
         #6 had pass rate drop because most recipes used hu/hv midpoints
         calibrated for the old shared cup_triangle, producing
         under-coverage).  Minimal-by-design types (micro, body_chain,
         sliver) keep their character — the bump is multiplicative so
         they stay smallest, just enough larger to register fabric.
      2. v-clip to anatomy-safe band [0.16, 0.95] so expressive recipes
         (halter strap-up, etc.) don't trigger head_neck rejection.
    """
    if geometry_kind in GEOMETRY_TO_CUP_RECIPE:
        fn = CUP_RECIPES[GEOMETRY_TO_CUP_RECIPE[geometry_kind]]
    elif fallback and fallback in CUP_RECIPES:
        fn = CUP_RECIPES[fallback]
    else:
        fn = CUP_RECIPES["cup_triangle"]
    def _wrapped(params, side=1):
        # 2026-05-24 hotfix removed: 1.18x coverage bump compounded
        # with library schema's size scale (L=1.18x) and produced
        # polygons up to u=0.71 — wrapped past body silhouette,
        # creating a visible "ring around abdomen" artifact user flagged.
        # Sizing is already in library schema; recipe should use
        # params as-is.
        return _clip_v(fn(params, side=side))
    _wrapped.__name__ = fn.__name__
    return _wrapped


if __name__ == "__main__":
    print(f"CUP_RECIPES: {len(CUP_RECIPES)} unique per-TYPE polygon functions")
    for name, fn in CUP_RECIPES.items():
        poly = fn({}, side=1)
        u_lo = min(p[0] for p in poly); u_hi = max(p[0] for p in poly)
        v_lo = min(p[1] for p in poly); v_hi = max(p[1] for p in poly)
        print(f"  {name:25s}: {len(poly)} pts, "
              f"u=[{u_lo:+.2f}, {u_hi:+.2f}] v=[{v_lo:.2f}, {v_hi:.2f}]")
    print(f"GEOMETRY_TO_CUP_RECIPE: {len(GEOMETRY_TO_CUP_RECIPE)} mappings")
