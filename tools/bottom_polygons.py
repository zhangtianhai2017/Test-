"""Per-bottom-type FRONT polygon recipes — replaces the 2 shared
recipes (bottom_thong / bottom_brief) that 52 bottom library entries
were calling with merely different param values.

Phase 2 #6a rewrite (2026-05-24): user observed that despite 52
bottoms in library, the rendered designs still felt "uniform/same
kind" — root cause being all bottoms shared one of 2 hexagonal-with-
chamfer polygon shapes. Different ID, same underlying silhouette.

This module gives each of 19 bottom TYPES its own polygon function,
each anchored to a real-world fashion silhouette (brand reference
inline). Different TYPES produce genuinely different geometries (not
just different params on the same shape).

Within a TYPE, size variants (S/M/L) still reuse the function with
a `scale` multiplier on width params — this matches how real garment
patterns are graded.

UV convention (matches polygon_recipes.py + cylindrical_uvs):
  u in [-1, 1]   — 0 = front center
  v in [0, 1]    — 0 ≈ body crotch (CROTCH_V=0.16 baseline)

Each recipe returns ONE polygon (list of (u, v) closed loop) for the
front panel. Back panel is per-template via back_polygons.py.
"""
from __future__ import annotations
from typing import Callable

CROTCH_V = 0.16


def _p(params: dict, name: str, default: float) -> float:
    return float(params.get(name, default))


# v-coordinate safety band for bottom polygons. Below 0.16 lands in
# legs (rejected by body_region_classifier). Above 0.55 lands in
# upper torso (above natural waist), only highwaist legitimately
# reaches there.
V_HI_SAFE = 0.55
V_LO_SAFE = 0.16


def _clip_v(poly, v_lo=V_LO_SAFE, v_hi=V_HI_SAFE):
    """Clip each vertex's v coord to safe anatomy band."""
    return [(u, max(v_lo, min(v_hi, v))) for u, v in poly]


# ===========================================================================
# 19 BOTTOM FRONT POLYGON RECIPES
# Each TYPE produces a visually distinct silhouette.
# ===========================================================================

def bot_thong(params: dict) -> list[tuple[float, float]]:
    """Classic thong front: narrow top, deep V-shape coming to point at
    crotch. Real ref: Hunza G thong, La Perla string thong.
    """
    top_v = _p(params, "front_top_v", 0.33)
    hu    = _p(params, "front_half_u", 0.18)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.45, (top_v + CROTCH_V) * 0.5),     # gentle taper
        (0.03, CROTCH_V + 0.02),                    # point near crotch
        (-0.03, CROTCH_V + 0.02),
        (-hu * 0.45, (top_v + CROTCH_V) * 0.5),
        (-hu, top_v),
    ]


def bot_brazilian(params: dict) -> list[tuple[float, float]]:
    """Brazilian: small triangular front, pointed crotch, narrower than
    cheeky but wider than thong. Real ref: Vix brazilian, Maaji.
    """
    top_v = _p(params, "front_top_v", 0.34)
    hu    = _p(params, "front_half_u", 0.22)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.65, (top_v + CROTCH_V) * 0.55),
        (hu * 0.30, CROTCH_V + 0.04),
        (-hu * 0.30, CROTCH_V + 0.04),
        (-hu * 0.65, (top_v + CROTCH_V) * 0.55),
        (-hu, top_v),
    ]


def bot_cheeky(params: dict) -> list[tuple[float, float]]:
    """Cheeky: rounded front panel with HIGH leg cut (concave curve
    arcing inward at sides). Different from brief in the leg-curve
    shape — cheeky's leg cuts at a steeper angle. Real ref: VS cheeky.
    """
    top_v = _p(params, "front_top_v", 0.31)
    hu    = _p(params, "front_half_u", 0.32)
    mid_v = (top_v + CROTCH_V) * 0.58
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.80, mid_v + 0.04),                  # high-cut indentation
        (hu * 0.42, CROTCH_V + 0.07),
        (-hu * 0.42, CROTCH_V + 0.07),
        (-hu * 0.80, mid_v + 0.04),
        (-hu, top_v),
    ]


def bot_brief(params: dict) -> list[tuple[float, float]]:
    """Classic full-coverage brief: wide trapezoid, modest leg curve,
    rounded bottom. Real ref: classic Speedo brief, Calvin Klein brief.
    """
    top_v = _p(params, "front_top_v", 0.36)
    hu    = _p(params, "front_half_u", 0.42)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.90, (top_v + CROTCH_V) * 0.5),
        (hu * 0.65, CROTCH_V + 0.10),
        (0.0, CROTCH_V + 0.06),
        (-hu * 0.65, CROTCH_V + 0.10),
        (-hu * 0.90, (top_v + CROTCH_V) * 0.5),
        (-hu, top_v),
    ]


def bot_highwaist(params: dict) -> list[tuple[float, float]]:
    """High-waist: TALL rectangular front rising above natural waist.
    The top edge sits ~4-5 cm above pelvis. Real ref: retro 50s
    high-waist, Calzedonia retro, Marina West high.
    """
    top_v = _p(params, "front_top_v", 0.50)
    hu    = _p(params, "front_half_u", 0.46)
    return [
        (-hu, top_v), (hu, top_v),
        (hu, (top_v + CROTCH_V) * 0.62),
        (hu * 0.72, CROTCH_V + 0.10),
        (0.0, CROTCH_V + 0.04),
        (-hu * 0.72, CROTCH_V + 0.10),
        (-hu, (top_v + CROTCH_V) * 0.62),
        (-hu, top_v),
    ]


def bot_hipster(params: dict) -> list[tuple[float, float]]:
    """Hipster: mid-rise, wide flat-ish trapezoid sitting on hipbones.
    Lower top edge than brief, more horizontal leg openings.
    Real ref: Tommy Hilfiger hipster, Tezenis hipster.
    """
    top_v = _p(params, "front_top_v", 0.32)
    hu    = _p(params, "front_half_u", 0.40)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.92, (top_v + CROTCH_V) * 0.45),
        (hu * 0.50, CROTCH_V + 0.08),
        (-hu * 0.50, CROTCH_V + 0.08),
        (-hu * 0.92, (top_v + CROTCH_V) * 0.45),
        (-hu, top_v),
    ]


def bot_boy_short(params: dict) -> list[tuple[float, float]]:
    """Boy-short / boyleg trunk: extended LOW leg cut, almost rectangular,
    extends below the standard leg-opening line. Real ref: Speedo Boyleg.
    """
    top_v = _p(params, "front_top_v", 0.38)
    hu    = _p(params, "front_half_u", 0.50)
    bot_extend_v = CROTCH_V + 0.02       # very low bottom edge
    return [
        (-hu, top_v), (hu, top_v),
        (hu, bot_extend_v + 0.05),         # nearly straight side
        (hu * 0.95, bot_extend_v),
        (-hu * 0.95, bot_extend_v),
        (-hu, bot_extend_v + 0.05),
        (-hu, top_v),
    ]


def bot_tanga(params: dict) -> list[tuple[float, float]]:
    """Tanga: between thong and brazilian. Slightly wider, less pointed
    at crotch. Real ref: tanga lingerie, Andres Sarda tanga.
    """
    top_v = _p(params, "front_top_v", 0.34)
    hu    = _p(params, "front_half_u", 0.28)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.55, (top_v + CROTCH_V) * 0.55),
        (hu * 0.20, CROTCH_V + 0.03),
        (-hu * 0.20, CROTCH_V + 0.03),
        (-hu * 0.55, (top_v + CROTCH_V) * 0.55),
        (-hu, top_v),
    ]


def bot_v_front(params: dict) -> list[tuple[float, float]]:
    """V-front: distinctive V-shaped NOTCH in the top waistband (not the
    leg). Real ref: Triangl V-front, Frankies Tropic V.
    """
    top_v = _p(params, "front_top_v", 0.37)
    hu    = _p(params, "front_half_u", 0.40)
    notch_v = top_v - 0.07     # V-notch dips down
    return [
        (-hu, top_v),
        (-hu * 0.40, top_v),
        (0.0, notch_v),                # V-notch dip
        (hu * 0.40, top_v),
        (hu, top_v),
        (hu * 0.85, (top_v + CROTCH_V) * 0.5),
        (hu * 0.45, CROTCH_V + 0.06),
        (-hu * 0.45, CROTCH_V + 0.06),
        (-hu * 0.85, (top_v + CROTCH_V) * 0.5),
        (-hu, top_v),
    ]


def bot_high_leg(params: dict) -> list[tuple[float, float]]:
    """High-leg: leg opening cuts UP very high (almost to hip bone).
    Standard waist height but VERY high leg cut. Real ref: 80s Baywatch.
    """
    top_v = _p(params, "front_top_v", 0.40)
    hu    = _p(params, "front_half_u", 0.40)
    # leg curve cuts way up, polygon side comes inward sharply
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.55, top_v - 0.04),       # cuts inward sharply
        (hu * 0.25, top_v - 0.16),       # high leg curve
        (hu * 0.18, CROTCH_V + 0.04),
        (-hu * 0.18, CROTCH_V + 0.04),
        (-hu * 0.25, top_v - 0.16),
        (-hu * 0.55, top_v - 0.04),
        (-hu, top_v),
    ]


def bot_strappy_side(params: dict) -> list[tuple[float, float]]:
    """Strappy side: front panel has SCALLOPED side edges where multiple
    side straps attach. Real ref: House of CB strappy, Frankies Lola.
    """
    top_v = _p(params, "front_top_v", 0.35)
    hu    = _p(params, "front_half_u", 0.38)
    mid_v = (top_v + CROTCH_V) * 0.6
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.82, top_v - 0.04),
        (hu * 0.65, mid_v + 0.06),       # scallop dip
        (hu * 0.78, mid_v - 0.02),       # scallop bump
        (hu * 0.55, CROTCH_V + 0.07),
        (-hu * 0.55, CROTCH_V + 0.07),
        (-hu * 0.78, mid_v - 0.02),
        (-hu * 0.65, mid_v + 0.06),
        (-hu * 0.82, top_v - 0.04),
        (-hu, top_v),
    ]


def bot_asym(params: dict) -> list[tuple[float, float]]:
    """Asymmetric: one side noticeably higher / different from the other.
    Real ref: Norma Kamali asym swim, Maaji asym bottom.
    """
    top_v = _p(params, "front_top_v", 0.38)
    hu    = _p(params, "front_half_u", 0.40)
    asym = 0.10              # right side higher than left by this much
    return [
        (-hu, top_v), (hu, top_v + asym),     # right top higher
        (hu * 0.92, top_v * 0.55 + CROTCH_V * 0.45),
        (hu * 0.55, CROTCH_V + 0.10),
        (-hu * 0.40, CROTCH_V + 0.05),       # asymmetric crotch attachment
        (-hu * 0.85, (top_v + CROTCH_V) * 0.45),
        (-hu, top_v),
    ]


def bot_ruched(params: dict) -> list[tuple[float, float]]:
    """Ruched: gathered/scrunched front panel. Polygon is slightly
    different shape with a center-pinched look (narrow vertical strip
    in middle representing the ruching seam). Real ref: Hunza G ruched.
    """
    top_v = _p(params, "front_top_v", 0.33)
    hu    = _p(params, "front_half_u", 0.40)
    return [
        (-hu, top_v),
        (-hu * 0.20, top_v - 0.02),   # slight indent at center top
        (0.0, top_v - 0.03),          # ruching pull at center
        (hu * 0.20, top_v - 0.02),
        (hu, top_v),
        (hu * 0.88, (top_v + CROTCH_V) * 0.45),
        (hu * 0.45, CROTCH_V + 0.07),
        (0.0, CROTCH_V + 0.02),       # center ruching seam at bottom
        (-hu * 0.45, CROTCH_V + 0.07),
        (-hu * 0.88, (top_v + CROTCH_V) * 0.45),
        (-hu, top_v),
    ]


def bot_tie_side(params: dict) -> list[tuple[float, float]]:
    """Tie-side: similar to brazilian but with VERY high side cuts where
    the bow ties go. Real ref: classic tie-side bikini, Eres tie-side.
    """
    top_v = _p(params, "front_top_v", 0.35)
    hu    = _p(params, "front_half_u", 0.36)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.50, (top_v + CROTCH_V) * 0.58),  # cuts inward strongly
        (hu * 0.18, CROTCH_V + 0.03),
        (-hu * 0.18, CROTCH_V + 0.03),
        (-hu * 0.50, (top_v + CROTCH_V) * 0.58),
        (-hu, top_v),
    ]


def bot_double_band(params: dict) -> list[tuple[float, float]]:
    """Double-band: front panel with VISIBLE seam line splitting it into
    upper band + lower body. Approximated as a polygon with a horizontal
    pinch at mid-height. Real ref: Adore Me double band cage.
    """
    top_v = _p(params, "front_top_v", 0.37)
    hu    = _p(params, "front_half_u", 0.41)
    mid_v = (top_v + CROTCH_V) * 0.55
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.95, mid_v + 0.03),       # pinch at mid
        (hu * 0.92, mid_v - 0.03),       # ...continues
        (hu * 0.60, CROTCH_V + 0.07),
        (-hu * 0.60, CROTCH_V + 0.07),
        (-hu * 0.92, mid_v - 0.03),
        (-hu * 0.95, mid_v + 0.03),
        (-hu, top_v),
    ]


def bot_g_string(params: dict) -> list[tuple[float, float]]:
    """G-string: TINY V-shape, almost just a string outline.
    Real ref: Honey Birdette g-string, La Perla micro g.
    """
    top_v = _p(params, "front_top_v", 0.36)
    hu    = _p(params, "front_half_u", 0.24)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.25, (top_v + CROTCH_V) * 0.55),
        (0.02, CROTCH_V + 0.04),
        (-0.02, CROTCH_V + 0.04),
        (-hu * 0.25, (top_v + CROTCH_V) * 0.55),
        (-hu, top_v),
    ]


def bot_micro(params: dict) -> list[tuple[float, float]]:
    """Micro: between thong and g-string. Slightly more coverage than
    g-string but still extreme minimal. Real ref: Frankies micro.
    """
    top_v = _p(params, "front_top_v", 0.35)
    hu    = _p(params, "front_half_u", 0.26)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.40, (top_v + CROTCH_V) * 0.55),
        (0.04, CROTCH_V + 0.03),
        (-0.04, CROTCH_V + 0.03),
        (-hu * 0.40, (top_v + CROTCH_V) * 0.55),
        (-hu, top_v),
    ]


def bot_sling(params: dict) -> list[tuple[float, float]]:
    """Sling / monokini-inspired: V-cut that comes up between the legs
    and extends UP through the abdomen toward the cups. Polygon is a
    narrow tall triangle. Real ref: sling bikini.
    """
    top_v = _p(params, "front_top_v", 0.41)
    hu    = _p(params, "front_half_u", 0.20)
    return [
        (-hu, top_v), (hu, top_v),
        (hu * 0.35, (top_v + CROTCH_V) * 0.5),
        (hu * 0.10, CROTCH_V + 0.03),
        (-hu * 0.10, CROTCH_V + 0.03),
        (-hu * 0.35, (top_v + CROTCH_V) * 0.5),
        (-hu, top_v),
    ]


def bot_side_string(params: dict) -> list[tuple[float, float]]:
    """Side-string-only: NARROW vertical strip in front, fabric only at
    crotch level with strings up to waistband at edges. Polygon is
    extremely narrow at top, slightly wider at crotch.
    Real ref: extreme micro thong with side strings.
    """
    top_v = _p(params, "front_top_v", 0.35)
    hu    = _p(params, "front_half_u", 0.25)
    return [
        # very narrow top (strings on sides only)
        (-hu * 0.15, top_v), (hu * 0.15, top_v),
        # widens slightly toward crotch
        (hu * 0.45, (top_v + CROTCH_V) * 0.55),
        (hu * 0.20, CROTCH_V + 0.04),
        (-hu * 0.20, CROTCH_V + 0.04),
        (-hu * 0.45, (top_v + CROTCH_V) * 0.55),
        (-hu * 0.15, top_v),
    ]


# ===========================================================================
# Recipe registry
# ===========================================================================

BOTTOM_RECIPES: dict[str, Callable] = {
    "bot_thong":         bot_thong,
    "bot_brazilian":     bot_brazilian,
    "bot_cheeky":        bot_cheeky,
    "bot_brief":         bot_brief,
    "bot_highwaist":     bot_highwaist,
    "bot_hipster":       bot_hipster,
    "bot_boy_short":     bot_boy_short,
    "bot_tanga":         bot_tanga,
    "bot_v_front":       bot_v_front,
    "bot_high_leg":      bot_high_leg,
    "bot_strappy_side":  bot_strappy_side,
    "bot_asym":          bot_asym,
    "bot_ruched":        bot_ruched,
    "bot_tie_side":      bot_tie_side,
    "bot_double_band":   bot_double_band,
    "bot_g_string":      bot_g_string,
    "bot_micro":         bot_micro,
    "bot_sling":         bot_sling,
    "bot_side_string":   bot_side_string,
}


# Maps the geometry_kind set in library_data.py to the per-type recipe
GEOMETRY_TO_BOT_RECIPE = {
    "thong":            "bot_thong",
    "brazilian":        "bot_brazilian",
    "cheeky":           "bot_cheeky",
    "brief":            "bot_brief",
    "high_waisted":     "bot_highwaist",
    "highwaist":        "bot_highwaist",
    "hipster":          "bot_hipster",
    "boy_short":        "bot_boy_short",
    "tanga":            "bot_tanga",
    "v_front":          "bot_v_front",
    "high_leg":         "bot_high_leg",
    "strappy_side":     "bot_strappy_side",
    "asymm_bot":        "bot_asym",
    "ruched":           "bot_ruched",
    "tie_side":         "bot_tie_side",
    "double_band":      "bot_double_band",
    "g_string":         "bot_g_string",
    "micro_bot":        "bot_micro",
    "sling_front":      "bot_sling",
    "side_string_only": "bot_side_string",
}


def resolve_bot_recipe(geometry_kind: str) -> Callable:
    """Resolve a bottom template's front-polygon recipe by geometry_kind.
    Returns a wrapped function that clips polygon v coords to anatomy-
    safe range. highwaist uses a wider v range (allowed up to 0.55).
    Falls back to bot_brief for unknown kinds.
    """
    name = GEOMETRY_TO_BOT_RECIPE.get(geometry_kind, "bot_brief")
    fn = BOTTOM_RECIPES[name]
    # highwaist legitimately extends higher; allow up to 0.60
    v_hi = 0.60 if "highwaist" in name else V_HI_SAFE
    def _wrapped(params):
        return _clip_v(fn(params), v_hi=v_hi)
    _wrapped.__name__ = fn.__name__
    return _wrapped


if __name__ == "__main__":
    print(f"BOTTOM_RECIPES: {len(BOTTOM_RECIPES)} unique front-polygon types")
    for name, fn in BOTTOM_RECIPES.items():
        poly = fn({})
        u_lo = min(p[0] for p in poly); u_hi = max(p[0] for p in poly)
        v_lo = min(p[1] for p in poly); v_hi = max(p[1] for p in poly)
        print(f"  {name:20s}: {len(poly)} pts, "
              f"u=[{u_lo:+.2f}, {u_hi:+.2f}] v=[{v_lo:.2f}, {v_hi:.2f}]")
    print(f"GEOMETRY_TO_BOT_RECIPE: {len(GEOMETRY_TO_BOT_RECIPE)} mappings")
