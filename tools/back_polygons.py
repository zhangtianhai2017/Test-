"""Per-bottom-template back polygon recipes — replaces the single
shared `back_bottom_strips` in polygon_recipes.py.

Phase 2 rewrite (2026-05-24): the old shared back-strip produced
identical "two-thin-side-panels at u=±[0.88, 1.00]" geometry for every
bottom in the library, which on render appeared as recurring side
"wings" at the abdomen — the visible-from-front portion of the back-
panel wrap. User flagged it as the source of permanent visual
sameness across all designs.

Each function here produces the back-panel polygon(s) for ONE bottom
geometry style. They're anchored to real-world bikini-bottom back
construction, not a single shared chamfer formula.

UV convention (matches polygon_recipes.py + cylindrical_uvs):
  u in [-1, 1]   — 0 = front center, ±1 = back seam.
                   u in [0.5, 1.0] wraps body's right-back.
  v in [0, 1]    — 0 = body crotch, 1 = neck base.
                   CROTCH_V = 0.16 is the polygon-lower-edge baseline.

Each recipe returns: list of polygons (each polygon = list of
(u, v) closed loop). Returning [] = no back panel (e.g., pure thong
front-only).

Real-world references inline per-function (brand catalogs + Helen
Joseph-Armstrong patternmaking).
"""
from __future__ import annotations
from typing import Callable

CROTCH_V = 0.16     # matches polygon_recipes.CROTCH_V


def _p(params: dict, name: str, default: float) -> float:
    return float(params.get(name, default))


# ===========================================================================
# Reference: real swimsuit back-panel construction
#
# Coverage type     Back-panel shape                Coverage (cm² approx)
# ----------------- ------------------------------- ----------------------
# G-string          1 single vertical string strip   ~5  (string only)
# Thong             narrow Y or V back               ~15-25
# Brazilian         small cheeky triangle            ~80-120 (½ glute)
# Tanga             slightly wider than brazilian    ~150
# Cheeky            mid coverage diamond/trapezoid   ~200-250
# Hipster           wide-back full coverage          ~400-500
# Brief             full back panel                  ~500-700
# High-waist        rises above natural waist        ~700-900
# Boy-short         extends down lower leg           ~800-1000
# Sling (monokini)  thin strap up between glutes     ~5-10
# Side-string-only  same as g-string back            ~5
# ===========================================================================

def back_g_string(params: dict) -> list:
    """G-string: single vertical thin string from crotch to waistband at
    back center. ~5 cm² of visible 'fabric' (technically a string)."""
    top_v = _p(params, "back_top_v", 0.32)
    w     = _p(params, "back_half_u", 0.04)   # very narrow
    return [[
        (-w, CROTCH_V), (w, CROTCH_V),
        (w, top_v),     (-w, top_v),
        (-w, CROTCH_V),
    ]]


def back_thong(params: dict) -> list:
    """Thong: narrow Y at back, wide at waist, narrows to a point at
    the crotch. Single panel, no wrap to side."""
    top_v = _p(params, "back_top_v", 0.32)
    hu    = _p(params, "back_half_u", 0.10)
    return [[
        (-hu, top_v), (hu, top_v),
        (0.03, CROTCH_V + 0.04), (-0.03, CROTCH_V + 0.04),
        (-hu, top_v),
    ]]


def back_brazilian(params: dict) -> list:
    """Brazilian: cheeky low coverage. Inverted-triangle / heart shape
    sitting low on glutes. Real ref: Frankies Bikinis brazilian back."""
    top_v = _p(params, "back_top_v", 0.32)
    hu    = _p(params, "back_half_u", 0.18)
    mid_v = (top_v + CROTCH_V) / 2
    return [[
        (-hu, top_v), (hu, top_v),
        (hu * 0.55, mid_v),
        (0.06, CROTCH_V + 0.02), (-0.06, CROTCH_V + 0.02),
        (-hu * 0.55, mid_v),
        (-hu, top_v),
    ]]


def back_tanga(params: dict) -> list:
    """Tanga: between brazilian and cheeky. Slightly fuller V at sides."""
    top_v = _p(params, "back_top_v", 0.32)
    hu    = _p(params, "back_half_u", 0.22)
    mid_v = (top_v + CROTCH_V) / 2
    return [[
        (-hu, top_v), (hu, top_v),
        (hu * 0.7, mid_v),
        (0.08, CROTCH_V + 0.02), (-0.08, CROTCH_V + 0.02),
        (-hu * 0.7, mid_v),
        (-hu, top_v),
    ]]


def back_cheeky(params: dict) -> list:
    """Cheeky: rounded trapezoid with curved leg openings, covers
    upper-mid glute. Real ref: Vix cheeky back."""
    top_v = _p(params, "back_top_v", 0.32)
    hu    = _p(params, "back_half_u", 0.26)
    return [[
        (-hu, top_v), (hu, top_v),
        (hu * 0.75, top_v - (top_v - CROTCH_V) * 0.4),
        (hu * 0.5, CROTCH_V + 0.04),
        (-hu * 0.5, CROTCH_V + 0.04),
        (-hu * 0.75, top_v - (top_v - CROTCH_V) * 0.4),
        (-hu, top_v),
    ]]


def back_hipster(params: dict) -> list:
    """Hipster: wide flat-ish back with mid-rise top edge."""
    top_v = _p(params, "back_top_v", 0.34)
    hu    = _p(params, "back_half_u", 0.34)
    return [[
        (-hu, top_v), (hu, top_v),
        (hu * 0.9, CROTCH_V + 0.06),
        (-hu * 0.9, CROTCH_V + 0.06),
        (-hu, top_v),
    ]]


def back_brief(params: dict) -> list:
    """Brief: full back coverage, classic 5-point trapezoid with
    moderate leg curve."""
    top_v = _p(params, "back_top_v", 0.36)
    hu    = _p(params, "back_half_u", 0.40)
    return [[
        (-hu, top_v), (hu, top_v),
        (hu * 0.85, CROTCH_V + 0.06),
        (-hu * 0.85, CROTCH_V + 0.06),
        (-hu, top_v),
    ]]


def back_highwaist(params: dict) -> list:
    """High-waist: full coverage rising above natural waist. Tall
    rectangle with slight leg cut."""
    top_v = _p(params, "back_top_v", 0.50)
    hu    = _p(params, "back_half_u", 0.42)
    return [[
        (-hu, top_v), (hu, top_v),
        (hu * 0.88, CROTCH_V + 0.10),
        (-hu * 0.88, CROTCH_V + 0.10),
        (-hu, top_v),
    ]]


def back_boy_short(params: dict) -> list:
    """Boy-short: full back + extends LOWER on glute (trunk style).
    Real ref: Speedo Boyleg back panel."""
    top_v = _p(params, "back_top_v", 0.38)
    hu    = _p(params, "back_half_u", 0.46)
    # boyshort back extends almost to CROTCH_V with minimal leg curve
    return [[
        (-hu, top_v), (hu, top_v),
        (hu * 0.95, CROTCH_V + 0.02),
        (-hu * 0.95, CROTCH_V + 0.02),
        (-hu, top_v),
    ]]


def back_sling(params: dict) -> list:
    """Sling (monokini-inspired): thin strap up between glutes, no
    coverage on either side. Single narrow vertical strip."""
    top_v = _p(params, "back_top_v", 0.40)
    w     = _p(params, "back_half_u", 0.06)
    return [[
        (-w, CROTCH_V + 0.02), (w, CROTCH_V + 0.02),
        (w * 1.5, top_v), (-w * 1.5, top_v),
        (-w, CROTCH_V + 0.02),
    ]]


def back_none(params: dict) -> list:
    """No back panel at all — for designs where back coverage is
    delegated to body chains or hardware, not fabric."""
    return []


# ===========================================================================
# Recipe registry — looked up by LibraryEntry.back_polygon_recipe.
# Each bottom geometry_kind maps to one of these.
# ===========================================================================

BACK_RECIPES: dict[str, Callable] = {
    "back_g_string":   back_g_string,
    "back_thong":      back_thong,
    "back_brazilian":  back_brazilian,
    "back_tanga":      back_tanga,
    "back_cheeky":     back_cheeky,
    "back_hipster":    back_hipster,
    "back_brief":      back_brief,
    "back_highwaist":  back_highwaist,
    "back_boy_short":  back_boy_short,
    "back_sling":      back_sling,
    "back_none":       back_none,
}


# Default mapping geometry_kind -> back recipe (used when a template
# doesn't explicitly set back_polygon_recipe). Keeps migration light:
# any existing template inherits a sensible default but can override.
GEOMETRY_TO_BACK_RECIPE = {
    "thong":           "back_thong",
    "g_string":        "back_g_string",
    "brazilian":       "back_brazilian",
    "tanga":           "back_tanga",
    "cheeky":          "back_cheeky",
    "hipster":         "back_hipster",
    "brief":           "back_brief",
    "high_waisted":    "back_highwaist",
    "highwaist":       "back_highwaist",
    "boy_short":       "back_boy_short",
    "v_front":         "back_brief",
    "high_leg":        "back_brief",
    "strappy_side":    "back_cheeky",
    "asymm_bot":       "back_cheeky",
    "ruched":          "back_cheeky",
    "tie_side":        "back_brazilian",
    "double_band":     "back_brief",
    "micro_bot":       "back_thong",
    "sling_front":     "back_sling",
    "side_string_only": "back_g_string",
}


def get_back_recipe(name: str) -> Callable:
    if name in BACK_RECIPES:
        return BACK_RECIPES[name]
    raise KeyError(f"unknown back recipe '{name}'. Known: "
                    f"{sorted(BACK_RECIPES.keys())}")


def resolve_back_for(geometry_kind: str, explicit: str = "") -> Callable:
    """Resolve a template's back recipe: explicit override > geometry
    default > legacy strip fallback. Returns a callable."""
    if explicit:
        return get_back_recipe(explicit)
    if geometry_kind in GEOMETRY_TO_BACK_RECIPE:
        return get_back_recipe(GEOMETRY_TO_BACK_RECIPE[geometry_kind])
    # Legacy fallback for unknown geometry: use cheeky as safe default
    return get_back_recipe("back_cheeky")


if __name__ == "__main__":
    print(f"BACK_RECIPES: {len(BACK_RECIPES)}")
    for name, fn in BACK_RECIPES.items():
        polys = fn({})
        n_pts = sum(len(p) for p in polys) if polys else 0
        print(f"  {name:18s}: {len(polys)} poly(s), {n_pts} pts total")
    print(f"GEOMETRY_TO_BACK_RECIPE: {len(GEOMETRY_TO_BACK_RECIPE)} mappings")
