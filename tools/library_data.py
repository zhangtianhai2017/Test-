"""
Hand-authored component library — ~80 entries across 7 kinds.

Companion to tools/library.py (the schema). Every dict here is a
{id: LibraryEntry} catalog. Combined into LIBRARY at the bottom for
single-import convenience.

Authoring conventions:
- Each entry is a real-world component (real fabric SKU, real industry
  hardware size, real swimwear cut). Citations follow earlier docs
  (Cloth Habit, Yarnspirations, Brother USA, Janome, Marvelous Designer
  Manual, Spandex By Yard).
- local_params_schema declares the entry's internal latent space — only
  variations that keep the entry "still itself" (size grading, color,
  small dimensional tweaks). Cross-component morphing is NOT in this
  space; it's a discrete library_id swap.
- compatible_with is best-effort: empty tuple = pairs with anything;
  non-empty = explicitly required partner ids.
- anatomy_hints supply default Attachment.anatomy_anchor names so the
  Outfit -> Garment cascade can wire up a default deployment without
  per-archetype guessing.
"""
from __future__ import annotations

from library import LibraryEntry


# ---------------------------------------------------------------------------
# CUP_PIECES — 15 entries (5 geometry × 3 size class)
# ---------------------------------------------------------------------------

# Geometry kind notes:
#   triangle           — string-bikini classic, soft fabric, no foam
#   brazilian          — like triangle but smaller, cheekier coverage
#   balconette         — wide horizontal cut, lifts and frames, soft
#   bandeau_unified    — single horizontal strip across both breasts
#   molded_foam        — structured foam dome for shape independent of breast
#   softcup_squareneck — low square front, soft unstructured cup

CUP_PIECES: dict[str, LibraryEntry] = {}

for size_class, scale in (("S", 0.85), ("M", 1.00), ("L", 1.18)):
    CUP_PIECES[f"CUP_TRIANGLE_{size_class}"] = LibraryEntry(
        id=f"CUP_TRIANGLE_{size_class}", kind="cup_piece",
        name=f"Triangle string cup {size_class}",
        tags=("triangle", "brazilian", "soft", "string"),
        compatible_with=(),  # works with any halter or shoulder strap
        anatomy_hints=("front_chest",),
        geometry_kind="triangle", base_polygon_recipe="cup_triangle",
        cup_size_class=size_class,
        local_params_schema={
            "half_u":      (0.10 * scale, 0.20 * scale, 0.16 * scale),
            "half_v":      (0.05 * scale, 0.10 * scale, 0.07 * scale),
            "inner_u":     (0.05, 0.16, 0.12),
            "apex_lift":   (0.0, 0.30, 0.15),
            "underband_dip": (0.0, 0.10, 0.05),
        },
        notes="Brazilian halter classic; soft, no foam.",
    )
    CUP_PIECES[f"CUP_BRAZILIAN_{size_class}"] = LibraryEntry(
        id=f"CUP_BRAZILIAN_{size_class}", kind="cup_piece",
        name=f"Brazilian small triangle {size_class}",
        tags=("brazilian", "triangle", "soft", "small"),
        anatomy_hints=("front_chest",),
        geometry_kind="triangle", base_polygon_recipe="cup_triangle",
        cup_size_class=size_class,
        local_params_schema={
            "half_u":      (0.08 * scale, 0.16 * scale, 0.12 * scale),
            "half_v":      (0.04 * scale, 0.08 * scale, 0.06 * scale),
            "inner_u":     (0.06, 0.12, 0.10),
            "apex_lift":   (0.10, 0.30, 0.20),
            "underband_dip": (0.0, 0.08, 0.04),
        },
        notes="Tighter cheeky Brazilian cut.",
    )
    CUP_PIECES[f"CUP_BALCONETTE_{size_class}"] = LibraryEntry(
        id=f"CUP_BALCONETTE_{size_class}", kind="cup_piece",
        name=f"Balconette wide cup {size_class}",
        tags=("balconette", "wide", "lifted"),
        anatomy_hints=("front_chest",),
        geometry_kind="balconette", base_polygon_recipe="cup_balconette",
        cup_size_class=size_class,
        local_params_schema={
            "half_u":      (0.16 * scale, 0.24 * scale, 0.20 * scale),
            "half_v":      (0.06 * scale, 0.10 * scale, 0.08 * scale),
            "inner_u":     (0.04, 0.10, 0.07),
            "apex_lift":   (-0.05, 0.10, 0.0),
            "underband_dip": (-0.05, 0.05, 0.0),
        },
        notes="Wide horizontal cut for lift and framing.",
    )
    CUP_PIECES[f"CUP_BANDEAU_{size_class}"] = LibraryEntry(
        id=f"CUP_BANDEAU_{size_class}", kind="cup_piece",
        name=f"Bandeau unified {size_class}",
        tags=("bandeau", "unified", "strapless"),
        anatomy_hints=("front_chest", "back_chest"),
        geometry_kind="bandeau_unified", base_polygon_recipe="cup_bandeau",
        cup_size_class=size_class,
        local_params_schema={
            "half_u":      (0.20 * scale, 0.26 * scale, 0.22 * scale),
            "half_v":      (0.08 * scale, 0.12 * scale, 0.10 * scale),
            "inner_u":     (0.0, 0.04, 0.0),
            "apex_lift":   (-0.10, 0.05, -0.05),
            "underband_dip": (-0.10, 0.05, -0.05),
        },
        notes="Single horizontal strip; strapless support relies on band.",
    )
    CUP_PIECES[f"CUP_FOAM_MOLDED_{size_class}"] = LibraryEntry(
        id=f"CUP_FOAM_MOLDED_{size_class}", kind="cup_piece",
        name=f"Molded foam cup {size_class}",
        tags=("molded_foam", "structured", "balconette"),
        compatible_with=("F_FOAM_CUP_3MM",),  # requires foam fabric
        anatomy_hints=("front_chest",),
        geometry_kind="molded_foam", base_polygon_recipe="cup_balconette",
        cup_size_class=size_class, foam_thickness_mm=3.0,
        local_params_schema={
            "half_u":      (0.16 * scale, 0.22 * scale, 0.18 * scale),
            "half_v":      (0.08 * scale, 0.12 * scale, 0.10 * scale),
            "inner_u":     (0.04, 0.10, 0.07),
            "apex_lift":   (0.0, 0.08, 0.04),
            "underband_dip": (0.0, 0.05, 0.02),
            "dome_depth_cm": (1.0, 2.0, 1.5),  # foam dome depth
        },
        notes="3mm EVA foam dome that bridges over breast topology.",
    )

# 15 cups total across 5 geometries × 3 size classes

# ---------------------------------------------------------------------------
# Extra cups under geometry_kind="softcup_squareneck" — high-coverage but
# soft (no foam dome) so they qualify as full-coverage for the modesty
# filter without collapsing the look to molded_foam.  Tagged 'softcup'
# + 'balconette' so they match the bralette / one_piece / bandeau slots
# at strict>=0.66.
# ---------------------------------------------------------------------------

_SOFTCUP_STYLES = {
    "HIGH_NECK": {
        "name_suffix": "high-neck",
        "tags": ("softcup", "balconette", "high_neckline", "structured"),
        "apex_lift": (-0.15, -0.05, -0.10),    # flat top, no V
        "half_v":    (0.090, 0.130, 0.110),    # tall cup -> reaches collarbone
        "half_u":    (0.170, 0.230, 0.200),
        "inner_u":   (0.040, 0.090, 0.065),
        "underband_dip": (0.000, 0.060, 0.020),
        "notes": "Square / high neckline soft cup, reaches collarbone.",
    },
    "ASYM_NECK": {
        "name_suffix": "asymmetric-neck",
        "tags": ("softcup", "balconette", "asymmetric"),
        "apex_lift": (0.20, 0.45, 0.30),       # one shoulder pulls higher
        "half_v":    (0.080, 0.115, 0.095),
        "half_u":    (0.180, 0.240, 0.210),
        "inner_u":   (0.020, 0.070, 0.045),
        "underband_dip": (0.000, 0.040, 0.015),
        "notes": "One-shoulder asymmetric neckline soft cup.",
    },
    "COWL": {
        "name_suffix": "cowl",
        "tags": ("softcup", "balconette", "draped"),
        "apex_lift": (0.05, 0.20, 0.10),       # gentle scoop
        "half_v":    (0.075, 0.110, 0.090),
        "half_u":    (0.190, 0.245, 0.215),
        "inner_u":   (0.010, 0.050, 0.030),    # cups close together (cowl join)
        "underband_dip": (-0.060, 0.020, -0.020),
        "notes": "Draped cowl front, cups join low between with a scoop.",
    },
    "DEEP_V": {
        "name_suffix": "deep-V",
        "tags": ("softcup", "balconette", "deep_v"),
        "apex_lift": (0.40, 0.60, 0.50),       # strong V down between cups
        "half_v":    (0.085, 0.125, 0.105),
        "half_u":    (0.165, 0.225, 0.190),
        "inner_u":   (0.060, 0.140, 0.100),
        "underband_dip": (0.000, 0.050, 0.020),
        "notes": "Plunging V neckline, structured soft cup.",
    },
}

for _size_class, _scale in _SIZE_SCALES.items() if False else (("S", 0.85), ("M", 1.0), ("L", 1.18)):
    for _style_key, _style in _SOFTCUP_STYLES.items():
        _id = f"CUP_SOFTCUP_{_style_key}_{_size_class}"
        CUP_PIECES[_id] = LibraryEntry(
            id=_id, kind="cup_piece",
            name=f"Soft cup {_style['name_suffix']} {_size_class}",
            tags=_style["tags"],
            anatomy_hints=("front_chest",),
            geometry_kind="softcup_squareneck",
            base_polygon_recipe="cup_softcup",
            cup_size_class=_size_class,
            local_params_schema={
                "half_u":      tuple(round(v * _scale, 4) for v in _style["half_u"]),
                "half_v":      tuple(round(v * _scale, 4) for v in _style["half_v"]),
                "inner_u":     _style["inner_u"],
                "apex_lift":   _style["apex_lift"],
                "underband_dip": _style["underband_dip"],
            },
            notes=_style["notes"],
        )

# 12 new softcup_squareneck cups (4 styles x 3 sizes) -> 27 cups total.

# ---------------------------------------------------------------------------
# CUP_PIECES — Phase 1a expansion: 8 new families × 3 sizes = 24 new cups
# (27 -> 51). Each family reuses an existing polygon recipe but with
# distinctive parameter signature so the rendered shape is visibly
# different. References:
#   halter        — high-set V cup, strap goes up to neck (Frederick's,
#                   Tropic of C, ZAFUL halter bikini line)
#   plunge        — extreme deep V between cups (Wolford plunge, Marlies
#                   Dekkers plunge balcony)
#   push_up       — small lifted cup with positive apex_lift (Triangl
#                   pushup, Calzedonia super-push)
#   demi          — flat top above breast peak, half-cup (lingerie demi)
#   bandeau_twist — center-twist bandeau (Hunza G, Vix twist bandeau)
#   micro_triangle — minimal triangle, half_v ≈ 0.04 (Frankies Bikinis micro)
#   sliver        — thin horizontal sliver, ultra-narrow bandeau
#                   (Reina Olga sliver, body-chain bra)
#   body_chain_cup — micro coverage + heavy hardware (chain-bra style,
#                   Givenchy body chain, Honey Birdette body jewelry)
# ---------------------------------------------------------------------------

_NEW_CUP_STYLES = {
    "HALTER": {
        "name_suffix": "halter-neck",
        "tags": ("halter", "triangle", "high_neckline", "string"),
        "recipe": "cup_triangle",
        "geometry_kind": "halter_triangle",
        "params": {
            "half_u":      (0.10, 0.18, 0.14),
            "half_v":      (0.08, 0.14, 0.11),       # taller cup
            "inner_u":     (0.08, 0.16, 0.12),
            "apex_lift":   (0.30, 0.55, 0.42),       # strong upward V
            "underband_dip": (0.0, 0.08, 0.04),
        },
        "notes": "Halter-neck triangle: cup top pulled up toward neck strap.",
    },
    "PLUNGE": {
        "name_suffix": "plunge-deep-V",
        "tags": ("plunge", "deep_v", "triangle", "bold"),
        "recipe": "cup_triangle",
        "geometry_kind": "plunge",
        "params": {
            "half_u":      (0.12, 0.22, 0.17),
            "half_v":      (0.08, 0.13, 0.10),
            "inner_u":     (0.12, 0.22, 0.17),       # wide gap between cups
            "apex_lift":   (0.45, 0.70, 0.58),       # extreme V plunge
            "underband_dip": (0.0, 0.10, 0.05),
        },
        "notes": "Plunge: deep V between cups, low inner edge.",
    },
    "PUSH_UP": {
        "name_suffix": "push-up",
        "tags": ("push_up", "balconette", "structured", "lift"),
        "recipe": "cup_balconette",
        "geometry_kind": "push_up",
        "params": {
            "half_u":      (0.13, 0.19, 0.16),       # narrower than balconette
            "half_v":      (0.07, 0.11, 0.09),
            "inner_u":     (0.05, 0.10, 0.08),
            "apex_lift":   (0.05, 0.18, 0.12),       # slight lift at top
            "underband_dip": (-0.08, 0.0, -0.04),    # snug under-band
        },
        "notes": "Push-up: small balcony cup, gentle lift, snug underband.",
    },
    "DEMI": {
        "name_suffix": "demi-half-cup",
        "tags": ("demi", "balconette", "half_cup", "horizontal"),
        "recipe": "cup_balconette",
        "geometry_kind": "demi",
        "params": {
            "half_u":      (0.16, 0.22, 0.19),
            "half_v":      (0.04, 0.07, 0.05),       # very low — half-cup
            "inner_u":     (0.06, 0.12, 0.09),
            "apex_lift":   (-0.10, 0.0, -0.05),      # flat-ish top
            "underband_dip": (0.0, 0.05, 0.02),
        },
        "notes": "Demi: half cup with flat horizontal top edge above peak.",
    },
    "BANDEAU_TWIST": {
        "name_suffix": "bandeau-twist",
        "tags": ("bandeau", "twist", "center_detail", "strapless"),
        "recipe": "cup_bandeau",
        "geometry_kind": "bandeau_twist",
        "params": {
            "half_u":      (0.22, 0.28, 0.25),
            "half_v":      (0.09, 0.13, 0.11),       # slightly taller bandeau
            "inner_u":     (0.02, 0.06, 0.04),       # small center gap for twist
            "apex_lift":   (-0.05, 0.10, 0.02),
            "underband_dip": (-0.05, 0.05, 0.0),
        },
        "notes": "Bandeau with knotted/twisted center; small center gap.",
    },
    "MICRO_TRIANGLE": {
        "name_suffix": "micro-triangle",
        "tags": ("micro", "triangle", "minimal", "string", "bold"),
        "recipe": "cup_triangle",
        "geometry_kind": "micro_triangle",
        "params": {
            "half_u":      (0.06, 0.11, 0.08),       # very small
            "half_v":      (0.03, 0.06, 0.045),
            "inner_u":     (0.04, 0.10, 0.07),
            "apex_lift":   (0.15, 0.35, 0.25),
            "underband_dip": (0.0, 0.05, 0.02),
        },
        "notes": "Micro triangle: minimal coverage (~5cm peak-to-peak).",
    },
    "SLIVER": {
        "name_suffix": "sliver-band",
        "tags": ("sliver", "bandeau", "ultra_thin", "horizontal", "bold"),
        "recipe": "cup_bandeau",
        "geometry_kind": "sliver",
        "params": {
            "half_u":      (0.18, 0.26, 0.22),
            "half_v":      (0.02, 0.04, 0.03),       # ultra-thin band
            "inner_u":     (0.0, 0.02, 0.01),
            "apex_lift":   (-0.02, 0.02, 0.0),
            "underband_dip": (-0.02, 0.02, 0.0),
        },
        "notes": "Sliver: ultra-thin horizontal band across breasts.",
    },
    "BODY_CHAIN_CUP": {
        "name_suffix": "body-chain-cup",
        "tags": ("body_chain", "triangle", "micro", "hardware", "minimal"),
        "recipe": "cup_triangle",
        "geometry_kind": "body_chain_cup",
        "params": {
            "half_u":      (0.05, 0.09, 0.07),       # tiny cup
            "half_v":      (0.025, 0.05, 0.035),
            "inner_u":     (0.06, 0.14, 0.10),
            "apex_lift":   (0.10, 0.30, 0.20),
            "underband_dip": (0.0, 0.04, 0.02),
        },
        "notes": "Body chain micro-cup: minimal fabric, designed to pair "
                 "with chain/jewelry hardware accessories.",
    },
}

# Instantiate each style × 3 size classes. Schema 'params' values are
# multiplied by size scale for `half_u` and `half_v` (size-affecting
# dims); others (inner_u, apex_lift, underband_dip) are size-independent.
_SIZE_SCALE_MAP = (("S", 0.85), ("M", 1.00), ("L", 1.18))
for _size_class, _scale in _SIZE_SCALE_MAP:
    for _style_key, _style in _NEW_CUP_STYLES.items():
        _id = f"CUP_{_style_key}_{_size_class}"
        _params = {}
        for _pname, _vals in _style["params"].items():
            if _pname in ("half_u", "half_v"):
                _params[_pname] = tuple(round(v * _scale, 4) for v in _vals)
            else:
                _params[_pname] = tuple(round(v, 4) for v in _vals)
        CUP_PIECES[_id] = LibraryEntry(
            id=_id, kind="cup_piece",
            name=f"Cup {_style['name_suffix']} {_size_class}",
            tags=_style["tags"],
            anatomy_hints=("front_chest",),
            geometry_kind=_style["geometry_kind"],
            base_polygon_recipe=_style["recipe"],
            cup_size_class=_size_class,
            local_params_schema=_params,
            notes=_style["notes"],
        )

# 27 + 24 new = 51 cup pieces total.

# ---------------------------------------------------------------------------
# BOTTOM_PIECES — 10 entries (5 geometry × 2 size class)
# ---------------------------------------------------------------------------

# Geometry notes:
#   thong         — minimal back, single string
#   brazilian     — cheeky, partial back coverage
#   cheeky        — moderate, exposes some glute
#   brief         — full bottom coverage classic
#   high_waisted  — rises above natural waist

BOTTOM_PIECES: dict[str, LibraryEntry] = {}
# front_half_u / back_half_u define the polygon's azimuthal half-extent
# in cylindrical body UV space (u ∈ [-1, 1], 0 = front center, ±1 = back).
# At hip Y, the body's surface widens — to actually cover visible hip
# triangles, briefs/highwaist need front_half_u ≈ 0.40-0.55 (i.e. polygon
# wraps from front-center around to the side seam). Anything below ≈ 0.30
# leaves the polygon over thin air at the front and renders nothing.
for cov_class, scale in (("S", 0.85), ("M", 1.00)):
    BOTTOM_PIECES[f"BOT_THONG_{cov_class}"] = LibraryEntry(
        id=f"BOT_THONG_{cov_class}", kind="bottom_piece",
        name=f"Thong bottom {cov_class}",
        tags=("thong", "minimal"),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="thong", base_polygon_recipe="bottom_thong",
        coverage_class="minimal",
        # 2026-05-24: front_top_v raised from (0.20, 0.32, 0.25) to
        # (0.28, 0.38, 0.33). Combined with CROTCH_V=0.16, this gives
        # polygon ~18cm of valid height (was ~9cm and rendering empty
        # after polish_shell). Thong identity preserved via narrow
        # front_half_u — height ~ brief, width still narrow.
        local_params_schema={
            "front_top_v":   (0.28, 0.38, 0.33),
            "front_half_u":  (0.22 * scale, 0.32 * scale, 0.27 * scale),
            "front_leg_curve": (0.50, 0.80, 0.65),
            "back_top_v":    (0.28, 0.36, 0.32),
            "back_half_u":   (0.06, 0.14, 0.09),
        },
    )
    BOTTOM_PIECES[f"BOT_BRAZILIAN_{cov_class}"] = LibraryEntry(
        id=f"BOT_BRAZILIAN_{cov_class}", kind="bottom_piece",
        name=f"Brazilian cheeky {cov_class}",
        tags=("brazilian", "cheeky", "tie-side"),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="brazilian", base_polygon_recipe="bottom_thong",
        coverage_class="minimal",
        # 2026-05-24: front_top_v raised — same reason as thong.
        local_params_schema={
            "front_top_v":   (0.30, 0.40, 0.34),
            "front_half_u":  (0.28 * scale, 0.36 * scale, 0.32 * scale),
            "front_leg_curve": (0.55, 0.80, 0.70),
            "back_top_v":    (0.28, 0.36, 0.32),
            "back_half_u":   (0.10, 0.18, 0.14),
        },
    )
    BOTTOM_PIECES[f"BOT_CHEEKY_{cov_class}"] = LibraryEntry(
        id=f"BOT_CHEEKY_{cov_class}", kind="bottom_piece",
        name=f"Cheeky bottom {cov_class}",
        tags=("cheeky",),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="cheeky", base_polygon_recipe="bottom_brief",
        coverage_class="medium",
        local_params_schema={
            "front_top_v":   (0.24, 0.34, 0.28),
            "front_half_u":  (0.34 * scale, 0.42 * scale, 0.38 * scale),
            "front_leg_curve": (0.50, 0.75, 0.60),
            "back_top_v":    (0.24, 0.32, 0.28),
            "back_half_u":   (0.18, 0.26, 0.22),
        },
    )
    BOTTOM_PIECES[f"BOT_BRIEF_{cov_class}"] = LibraryEntry(
        id=f"BOT_BRIEF_{cov_class}", kind="bottom_piece",
        name=f"Classic brief {cov_class}",
        tags=("brief", "full_coverage"),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="brief", base_polygon_recipe="bottom_brief",
        coverage_class="full",
        local_params_schema={
            "front_top_v":   (0.30, 0.40, 0.34),
            "front_half_u":  (0.42 * scale, 0.52 * scale, 0.46 * scale),
            "front_leg_curve": (0.30, 0.55, 0.45),
            "back_top_v":    (0.30, 0.38, 0.34),
            "back_half_u":   (0.30, 0.42, 0.36),
        },
    )
    BOTTOM_PIECES[f"BOT_HIGHWAIST_{cov_class}"] = LibraryEntry(
        id=f"BOT_HIGHWAIST_{cov_class}", kind="bottom_piece",
        name=f"High-waisted {cov_class}",
        tags=("high_waisted", "retro", "full_coverage"),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="high_waisted", base_polygon_recipe="bottom_brief",
        coverage_class="full",
        local_params_schema={
            "front_top_v":   (0.40, 0.55, 0.48),
            "front_half_u":  (0.46 * scale, 0.58 * scale, 0.50 * scale),
            "front_leg_curve": (0.30, 0.50, 0.40),
            "back_top_v":    (0.40, 0.55, 0.48),
            "back_half_u":   (0.34 * scale, 0.46 * scale, 0.40 * scale),
        },
    )


# ---------------------------------------------------------------------------
# BOTTOM_PIECES — Phase 1c expansion: 14 new families × 3 sizes = 42
# new pieces (10 -> 52). Reuses bottom_thong / bottom_brief recipes
# with new param signatures. Each style is anchored in a real fashion
# category.
# References:
#   hipster        — mid-rise wide brief (Tommy Hilfiger hipster)
#   boy_short      — boyleg trunk, longer leg-line (Speedo BoyLeg)
#   tanga          — between thong and brazilian (Vix tanga)
#   v_front        — sharp V notch in front waistband (Triangl V-front)
#   high_leg       — standard coverage, very high leg cut (Calzedonia)
#   strappy_side   — multiple thin side straps (Frankies, House of CB)
#   asymm_bot      — asymmetric front-band notch
#   ruched         — gathered-fabric look at center back (Hunza G)
#   tie_side       — bow-tied side detail (Bali, ZAFUL tie)
#   double_band    — two parallel side bands (Adore Me cage style)
#   --- minimal / extreme tier ---
#   g_string       — ultra-thin strings, near-nude (Honey Birdette)
#   micro_bot      — between thong and g-string
#   sling_front    — V-cut down from cup to crotch (sling bikini, monokini)
#   side_string_only — string side only, fabric near-absent
# ---------------------------------------------------------------------------

_NEW_BOTTOM_STYLES = {
    "HIPSTER": {
        "name_suffix": "hipster",
        "tags": ("hipster", "medium_coverage", "mid_rise"),
        "recipe": "bottom_brief",
        "geometry_kind": "hipster",
        "coverage_class": "medium",
        "params": {
            "front_top_v":   (0.28, 0.36, 0.32),
            "front_half_u":  (0.40, 0.50, 0.45),
            "front_leg_curve": (0.20, 0.45, 0.32),
            "back_top_v":    (0.28, 0.36, 0.32),
            "back_half_u":   (0.30, 0.42, 0.36),
        },
    },
    "BOY_SHORT": {
        "name_suffix": "boy-short",
        "tags": ("boy_short", "trunk", "full_coverage", "sport"),
        "recipe": "bottom_brief",
        "geometry_kind": "boy_short",
        "coverage_class": "full",
        "params": {
            "front_top_v":   (0.34, 0.42, 0.38),
            "front_half_u":  (0.48, 0.58, 0.52),
            "front_leg_curve": (0.10, 0.30, 0.20),     # flat low-leg
            "back_top_v":    (0.34, 0.42, 0.38),
            "back_half_u":   (0.42, 0.55, 0.48),
        },
    },
    "TANGA": {
        "name_suffix": "tanga",
        "tags": ("tanga", "cheeky", "minimal"),
        "recipe": "bottom_thong",
        "geometry_kind": "tanga",
        "coverage_class": "minimal",
        "params": {
            "front_top_v":   (0.30, 0.38, 0.34),
            "front_half_u":  (0.26, 0.34, 0.30),
            "front_leg_curve": (0.55, 0.78, 0.66),
            "back_top_v":    (0.28, 0.34, 0.31),
            "back_half_u":   (0.12, 0.20, 0.16),
        },
    },
    "V_FRONT": {
        "name_suffix": "V-front-notch",
        "tags": ("v_front", "notched_waistband", "bold"),
        "recipe": "bottom_brief",
        "geometry_kind": "v_front",
        "coverage_class": "medium",
        "params": {
            "front_top_v":   (0.32, 0.42, 0.37),
            "front_half_u":  (0.42, 0.52, 0.46),
            "front_leg_curve": (0.65, 0.90, 0.78),    # high leg curve for V
            "back_top_v":    (0.30, 0.38, 0.34),
            "back_half_u":   (0.30, 0.42, 0.36),
        },
    },
    "HIGH_LEG": {
        "name_suffix": "high-leg",
        "tags": ("high_leg", "leg_lengthening", "bold"),
        "recipe": "bottom_brief",
        "geometry_kind": "high_leg",
        "coverage_class": "medium",
        "params": {
            "front_top_v":   (0.35, 0.45, 0.40),
            "front_half_u":  (0.38, 0.48, 0.42),
            "front_leg_curve": (0.75, 0.95, 0.85),    # extreme high cut
            "back_top_v":    (0.32, 0.40, 0.36),
            "back_half_u":   (0.28, 0.38, 0.33),
        },
    },
    "STRAPPY_SIDE": {
        "name_suffix": "strappy-side",
        "tags": ("strappy_side", "cage", "asymmetric_detail"),
        "recipe": "bottom_brief",
        "geometry_kind": "strappy_side",
        "coverage_class": "medium",
        "params": {
            "front_top_v":   (0.30, 0.40, 0.35),
            "front_half_u":  (0.36, 0.46, 0.41),
            "front_leg_curve": (0.50, 0.70, 0.60),
            "back_top_v":    (0.30, 0.38, 0.34),
            "back_half_u":   (0.26, 0.36, 0.31),
        },
    },
    "ASYMM_BOT": {
        "name_suffix": "asymmetric",
        "tags": ("asymmetric", "modern", "one_side_high"),
        "recipe": "bottom_brief",
        "geometry_kind": "asymm_bot",
        "coverage_class": "medium",
        "params": {
            "front_top_v":   (0.33, 0.43, 0.38),
            "front_half_u":  (0.38, 0.48, 0.43),
            "front_leg_curve": (0.45, 0.75, 0.60),
            "back_top_v":    (0.30, 0.38, 0.34),
            "back_half_u":   (0.28, 0.38, 0.33),
        },
    },
    "RUCHED": {
        "name_suffix": "ruched",
        "tags": ("ruched", "gathered", "texture"),
        "recipe": "bottom_brief",
        "geometry_kind": "ruched",
        "coverage_class": "medium",
        "params": {
            "front_top_v":   (0.28, 0.38, 0.33),
            "front_half_u":  (0.36, 0.46, 0.41),
            "front_leg_curve": (0.45, 0.70, 0.55),
            "back_top_v":    (0.28, 0.36, 0.32),
            "back_half_u":   (0.24, 0.36, 0.30),
        },
    },
    "TIE_SIDE": {
        "name_suffix": "tie-side",
        "tags": ("tie_side", "bow", "adjustable"),
        "recipe": "bottom_thong",
        "geometry_kind": "tie_side",
        "coverage_class": "medium",
        "params": {
            "front_top_v":   (0.30, 0.40, 0.35),
            "front_half_u":  (0.32, 0.42, 0.37),
            "front_leg_curve": (0.55, 0.78, 0.66),
            "back_top_v":    (0.28, 0.36, 0.32),
            "back_half_u":   (0.14, 0.22, 0.18),
        },
    },
    "DOUBLE_BAND": {
        "name_suffix": "double-band",
        "tags": ("double_band", "cage", "structural"),
        "recipe": "bottom_brief",
        "geometry_kind": "double_band",
        "coverage_class": "medium",
        "params": {
            "front_top_v":   (0.32, 0.42, 0.37),
            "front_half_u":  (0.36, 0.46, 0.41),
            "front_leg_curve": (0.40, 0.65, 0.52),
            "back_top_v":    (0.30, 0.38, 0.34),
            "back_half_u":   (0.26, 0.36, 0.31),
        },
    },
    "G_STRING": {
        "name_suffix": "g-string",
        "tags": ("g_string", "minimal", "string", "ultra_minimal"),
        "recipe": "bottom_thong",
        "geometry_kind": "g_string",
        "coverage_class": "minimal",
        # NOTE: front_half_u bumped up to 0.21-0.28 (was 0.15-0.22) so the
        # polygon is wide enough for the body mesh to catch >0 triangles.
        # Truly micro coverage isn't renderable at this body mesh density.
        "params": {
            "front_top_v":   (0.32, 0.40, 0.36),
            "front_half_u":  (0.21, 0.28, 0.24),
            "front_leg_curve": (0.65, 0.90, 0.80),
            "back_top_v":    (0.30, 0.36, 0.33),
            "back_half_u":   (0.06, 0.12, 0.08),
        },
    },
    "MICRO_BOT": {
        "name_suffix": "micro-bottom",
        "tags": ("micro", "minimal", "string", "bold"),
        "recipe": "bottom_thong",
        "geometry_kind": "micro_bot",
        "coverage_class": "minimal",
        "params": {
            "front_top_v":   (0.32, 0.38, 0.35),
            "front_half_u":  (0.23, 0.30, 0.26),
            "front_leg_curve": (0.60, 0.85, 0.74),
            "back_top_v":    (0.30, 0.36, 0.33),
            "back_half_u":   (0.08, 0.14, 0.10),
        },
    },
    "SLING_FRONT": {
        "name_suffix": "sling-front",
        "tags": ("sling", "monokini_inspired", "V_cut", "extreme"),
        "recipe": "bottom_thong",
        "geometry_kind": "sling_front",
        "coverage_class": "minimal",
        "params": {
            "front_top_v":   (0.36, 0.46, 0.41),     # extends up toward chest
            "front_half_u":  (0.16, 0.24, 0.20),     # narrow V
            "front_leg_curve": (0.70, 0.92, 0.83),
            "back_top_v":    (0.28, 0.34, 0.31),
            "back_half_u":   (0.05, 0.10, 0.07),
        },
    },
    "SIDE_STRING_ONLY": {
        "name_suffix": "side-string-only",
        "tags": ("side_string", "minimal", "string_dominant", "extreme"),
        "recipe": "bottom_thong",
        "geometry_kind": "side_string_only",
        "coverage_class": "minimal",
        "params": {
            "front_top_v":   (0.32, 0.38, 0.35),
            "front_half_u":  (0.22, 0.28, 0.25),
            "front_leg_curve": (0.75, 0.95, 0.85),
            "back_top_v":    (0.30, 0.34, 0.32),
            "back_half_u":   (0.05, 0.10, 0.07),
        },
    },
}

# Instantiate each style × S/M/L sizes. half_u dims scale; v dims fixed
# (already anatomically positioned).
for _size_class, _scale in (("S", 0.85), ("M", 1.00), ("L", 1.18)):
    for _style_key, _style in _NEW_BOTTOM_STYLES.items():
        _id = f"BOT_{_style_key}_{_size_class}"
        _params = {}
        for _pname, _vals in _style["params"].items():
            if "half_u" in _pname:
                _params[_pname] = tuple(round(v * _scale, 4) for v in _vals)
            else:
                _params[_pname] = tuple(round(v, 4) for v in _vals)
        BOTTOM_PIECES[_id] = LibraryEntry(
            id=_id, kind="bottom_piece",
            name=f"{_style['name_suffix'].capitalize()} bottom {_size_class}",
            tags=_style["tags"],
            anatomy_hints=("front_pelvis", "back_pelvis"),
            geometry_kind=_style["geometry_kind"],
            base_polygon_recipe=_style["recipe"],
            coverage_class=_style["coverage_class"],
            local_params_schema=_params,
        )

# 14 new styles × 3 sizes = 42 new bottoms; 10 + 42 = 52 total.

# ---------------------------------------------------------------------------
# STRAP_PIECES — 12 entries
# ---------------------------------------------------------------------------

STRAP_PIECES: dict[str, LibraryEntry] = {
    # Halter cords — string going around behind the neck
    "STR_HALTER_3MM": LibraryEntry(
        id="STR_HALTER_3MM", kind="strap_piece",
        name="Halter cord 3 mm round polyester",
        tags=("halter", "cord", "thin"),
        anatomy_hints=("neck_base_back",),
        width_cm=0.3, length_cm=0.0, elastic=False,
        local_params_schema={"length_cm": (40.0, 70.0, 55.0)},
    ),
    "STR_HALTER_5MM": LibraryEntry(
        id="STR_HALTER_5MM", kind="strap_piece",
        name="Halter cord 5 mm round polyester",
        tags=("halter", "cord"),
        anatomy_hints=("neck_base_back",),
        width_cm=0.5, length_cm=0.0, elastic=False,
        local_params_schema={"length_cm": (40.0, 70.0, 55.0)},
    ),
    # Shoulder straps
    "STR_SHOULDER_WOVEN_10MM": LibraryEntry(
        id="STR_SHOULDER_WOVEN_10MM", kind="strap_piece",
        name="Shoulder strap woven 10 mm",
        tags=("shoulder", "woven", "thin"),
        anatomy_hints=("front_clavicle_R", "back_scapula_R"),
        width_cm=1.0, length_cm=0.0, elastic=True,
        local_params_schema={"length_cm": (24.0, 36.0, 30.0)},
    ),
    "STR_SHOULDER_WOVEN_15MM": LibraryEntry(
        id="STR_SHOULDER_WOVEN_15MM", kind="strap_piece",
        name="Shoulder strap woven 15 mm",
        tags=("shoulder", "woven"),
        anatomy_hints=("front_clavicle_R", "back_scapula_R"),
        width_cm=1.5, length_cm=0.0, elastic=True,
        local_params_schema={"length_cm": (24.0, 36.0, 30.0)},
    ),
    "STR_SHOULDER_PADDED_20MM": LibraryEntry(
        id="STR_SHOULDER_PADDED_20MM", kind="strap_piece",
        name="Shoulder strap padded 20 mm",
        tags=("shoulder", "padded", "wide"),
        anatomy_hints=("front_clavicle_R", "back_scapula_R"),
        width_cm=2.0, length_cm=0.0, elastic=True,
        local_params_schema={"length_cm": (24.0, 38.0, 32.0)},
    ),
    # Side ties
    "STR_TIE_CORD_3MM": LibraryEntry(
        id="STR_TIE_CORD_3MM", kind="strap_piece",
        name="Side tie cord 3 mm",
        tags=("tie", "side_tie", "cord", "thin", "hip_side"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=0.3,
        local_params_schema={"length_cm": (15.0, 30.0, 22.0)},
    ),
    "STR_TIE_CORD_5MM": LibraryEntry(
        id="STR_TIE_CORD_5MM", kind="strap_piece",
        name="Side tie cord 5 mm",
        tags=("tie", "side_tie", "cord", "hip_side"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=0.5,
        local_params_schema={"length_cm": (15.0, 30.0, 22.0)},
    ),
    "STR_TIE_RIBBON_15MM": LibraryEntry(
        id="STR_TIE_RIBBON_15MM", kind="strap_piece",
        name="Side tie ribbon 15 mm",
        tags=("tie", "side_tie", "ribbon", "wide", "hip_side"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=1.5,
        local_params_schema={"length_cm": (20.0, 35.0, 28.0)},
    ),
    # Hip-side connectors (no visible knot/dangle — they hold the
    # bottom panels together through tension, not a tied bow).
    "STR_HIP_ELASTIC_8MM": LibraryEntry(
        id="STR_HIP_ELASTIC_8MM", kind="strap_piece",
        name="Hip-side elastic 8 mm",
        tags=("hip_side", "elastic", "thin"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=0.8, elastic=True,
        local_params_schema={"length_cm": (8.0, 14.0, 11.0)},
    ),
    "STR_HIP_ELASTIC_15MM": LibraryEntry(
        id="STR_HIP_ELASTIC_15MM", kind="strap_piece",
        name="Hip-side elastic 15 mm",
        tags=("hip_side", "elastic"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=1.5, elastic=True,
        local_params_schema={"length_cm": (8.0, 14.0, 11.0)},
    ),
    "STR_HIP_BAND_SPORT_25MM": LibraryEntry(
        id="STR_HIP_BAND_SPORT_25MM", kind="strap_piece",
        name="Hip-side sport band 25 mm",
        tags=("hip_side", "elastic", "wide", "sport"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=2.5, elastic=True,
        local_params_schema={"length_cm": (8.0, 14.0, 11.0)},
    ),
    # FOE elastic — fold-over edge finish, also used as underbust band
    "STR_FOE_10MM": LibraryEntry(
        id="STR_FOE_10MM", kind="strap_piece",
        name="3/8\" fold-over elastic 10 mm",
        tags=("FOE", "underbust", "elastic", "edge"),
        anatomy_hints=("sternum",),
        width_cm=1.0, elastic=True,
    ),
    "STR_FOE_15MM": LibraryEntry(
        id="STR_FOE_15MM", kind="strap_piece",
        name="5/8\" fold-over elastic 15 mm",
        tags=("FOE", "underbust", "elastic", "edge"),
        anatomy_hints=("sternum",),
        width_cm=1.5, elastic=True,
    ),
    "STR_FOE_25MM": LibraryEntry(
        id="STR_FOE_25MM", kind="strap_piece",
        name="1\" fold-over elastic 25 mm",
        tags=("FOE", "underbust", "elastic", "edge", "wide"),
        anatomy_hints=("sternum",),
        width_cm=2.5, elastic=True,
    ),
    # Back band (bandeau-style continuous fabric)
    "STR_BACKBAND_RIBBED": LibraryEntry(
        id="STR_BACKBAND_RIBBED", kind="strap_piece",
        name="Back band ribbed wide",
        tags=("back_band", "wide", "structured"),
        anatomy_hints=("back_scapula_R", "back_scapula_L"),
        width_cm=4.0,
        local_params_schema={"height_cm": (3.5, 6.0, 4.5)},
    ),
    "STR_BACKBAND_PLAIN": LibraryEntry(
        id="STR_BACKBAND_PLAIN", kind="strap_piece",
        name="Back band plain",
        tags=("back_band",),
        anatomy_hints=("back_scapula_R", "back_scapula_L"),
        width_cm=3.0,
        local_params_schema={"height_cm": (2.5, 5.0, 3.5)},
    ),
}


# ---------------------------------------------------------------------------
# HARDWARE — 10 entries (rings + sliders + buckles)
# ---------------------------------------------------------------------------

# Hardware anchors: rings/sliders sit where strap-piece meets cup edge
# (front_clavicle), closures sit at the back-band/center-back. Without
# anatomy_hints deploy_to_body would drop these connectors entirely.
HARDWARE: dict[str, LibraryEntry] = {
    "HW_OR_8MM_GOLD": LibraryEntry(
        id="HW_OR_8MM_GOLD", kind="hardware",
        name="O-ring 8 mm gold",
        tags=("o_ring", "small", "gold"),
        anatomy_hints=("front_clavicle_R", "front_clavicle_L"),
        diameter_cm=0.8, metal_finish="gold",
    ),
    "HW_OR_12MM_GOLD": LibraryEntry(
        id="HW_OR_12MM_GOLD", kind="hardware",
        name="O-ring 12 mm gold",
        tags=("o_ring", "gold"),
        anatomy_hints=("front_clavicle_R", "front_clavicle_L"),
        diameter_cm=1.2, metal_finish="gold",
    ),
    "HW_OR_18MM_SILVER": LibraryEntry(
        id="HW_OR_18MM_SILVER", kind="hardware",
        name="O-ring 18 mm silver",
        tags=("o_ring", "large", "silver"),
        anatomy_hints=("front_clavicle_R", "front_clavicle_L"),
        diameter_cm=1.8, metal_finish="silver",
    ),
    "HW_OR_12MM_ROSEGOLD": LibraryEntry(
        id="HW_OR_12MM_ROSEGOLD", kind="hardware",
        name="O-ring 12 mm rose gold",
        tags=("o_ring", "rose_gold"),
        anatomy_hints=("front_clavicle_R", "front_clavicle_L"),
        diameter_cm=1.2, metal_finish="rose_gold",
    ),
    "HW_DR_15MM_SILVER": LibraryEntry(
        id="HW_DR_15MM_SILVER", kind="hardware",
        name="D-ring 15 mm silver",
        tags=("d_ring", "silver"),
        anatomy_hints=("front_clavicle_R", "front_clavicle_L"),
        diameter_cm=1.5, metal_finish="silver",
    ),
    "HW_SLIDER_10MM_NICKEL": LibraryEntry(
        id="HW_SLIDER_10MM_NICKEL", kind="hardware",
        name="Strap slider 10 mm nickel",
        tags=("slider",),
        anatomy_hints=("front_clavicle_R", "front_clavicle_L"),
        width_cm=1.0, metal_finish="silver",
    ),
    "HW_SLIDER_15MM_NICKEL": LibraryEntry(
        id="HW_SLIDER_15MM_NICKEL", kind="hardware",
        name="Strap slider 15 mm nickel",
        tags=("slider",),
        anatomy_hints=("front_clavicle_R", "front_clavicle_L"),
        width_cm=1.5, metal_finish="silver",
    ),
    "HW_SLIDER_20MM_GOLD": LibraryEntry(
        id="HW_SLIDER_20MM_GOLD", kind="hardware",
        name="Strap slider 20 mm gold",
        tags=("slider", "gold"),
        anatomy_hints=("front_clavicle_R", "front_clavicle_L"),
        width_cm=2.0, metal_finish="gold",
    ),
    "HW_BUCKLE_15MM_GOLD": LibraryEntry(
        id="HW_BUCKLE_15MM_GOLD", kind="hardware",
        name="Side buckle 15 mm gold",
        tags=("buckle", "gold"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=1.5, metal_finish="gold",
    ),
    "HW_HOOKEYE_BLACK": LibraryEntry(
        id="HW_HOOKEYE_BLACK", kind="hardware",
        name="Hook & eye pair black",
        tags=("hook_eye", "closure"),
        anatomy_hints=("neck_base_back",),
        width_cm=0.8, metal_finish="none",
    ),
}


# ---------------------------------------------------------------------------
# ACCESSORIES — 10 entries
# ---------------------------------------------------------------------------

ACCESSORIES: dict[str, LibraryEntry] = {
    "ACC_BOW_CHIFFON_30MM": LibraryEntry(
        id="ACC_BOW_CHIFFON_30MM", kind="accessory",
        name="Chiffon bow 30 mm",
        tags=("bow", "chiffon"),
        anatomy_hints=("sternum",),
        local_params_schema={"size_cm": (2.0, 5.0, 3.0)},
    ),
    "ACC_BOW_SATIN_40MM": LibraryEntry(
        id="ACC_BOW_SATIN_40MM", kind="accessory",
        name="Satin bow 40 mm",
        tags=("bow", "satin"),
        anatomy_hints=("sternum",),
        local_params_schema={"size_cm": (3.0, 6.0, 4.0)},
    ),
    "ACC_SHELL_TROCHUS_25MM": LibraryEntry(
        id="ACC_SHELL_TROCHUS_25MM", kind="accessory",
        name="Trochus shell charm 25 mm",
        tags=("shell_charm", "shell", "boho", "natural"),
        anatomy_hints=("sternum",),
        local_params_schema={"size_cm": (1.5, 3.0, 2.5)},
    ),
    "ACC_SHELL_COWRIE_20MM": LibraryEntry(
        id="ACC_SHELL_COWRIE_20MM", kind="accessory",
        name="Cowrie shell 20 mm",
        tags=("shell_charm", "shell", "boho"),
        anatomy_hints=("sternum",),
        local_params_schema={"size_cm": (1.2, 2.5, 2.0)},
    ),
    "ACC_PENDANT_DROP_15MM_GOLD": LibraryEntry(
        id="ACC_PENDANT_DROP_15MM_GOLD", kind="accessory",
        name="Drop pendant 15 mm gold",
        tags=("pendant", "drop", "gold"),
        anatomy_hints=("sternum",),
        metal_finish="gold",
        local_params_schema={"size_cm": (1.0, 2.5, 1.5)},
    ),
    "ACC_FRINGE_BEADED_80MM": LibraryEntry(
        id="ACC_FRINGE_BEADED_80MM", kind="accessory",
        name="Beaded fringe 80 mm",
        tags=("fringe", "beaded", "boho"),
        anatomy_hints=("hip_R", "hip_L"),
        local_params_schema={"length_cm": (5.0, 12.0, 8.0)},
    ),
    "ACC_FRINGE_RAW_60MM": LibraryEntry(
        id="ACC_FRINGE_RAW_60MM", kind="accessory",
        name="Raw fabric fringe 60 mm",
        tags=("fringe", "raw"),
        anatomy_hints=("hip_R", "hip_L"),
        local_params_schema={"length_cm": (4.0, 10.0, 6.0)},
    ),
    "ACC_BEADS_SMALL_4MM": LibraryEntry(
        id="ACC_BEADS_SMALL_4MM", kind="accessory",
        name="Small round beads 4 mm",
        tags=("beads",),
        anatomy_hints=("neck_base_front",),
        local_params_schema={"count": (8, 30, 12)},
    ),
    "ACC_BEADS_OVAL_8MM": LibraryEntry(
        id="ACC_BEADS_OVAL_8MM", kind="accessory",
        name="Oval ceramic beads 8 mm",
        tags=("beads", "ceramic"),
        anatomy_hints=("neck_base_front",),
        local_params_schema={"count": (5, 15, 8)},
    ),
    "ACC_TASSEL_SILK_50MM": LibraryEntry(
        id="ACC_TASSEL_SILK_50MM", kind="accessory",
        name="Silk tassel 50 mm",
        tags=("tassel", "silk"),
        anatomy_hints=("hip_R", "hip_L", "sternum"),
        local_params_schema={"length_cm": (3.0, 8.0, 5.0)},
    ),
}


# ---------------------------------------------------------------------------
# FABRICS — 12 entries (carried over from catalogs.py + cleanup)
# ---------------------------------------------------------------------------

FABRICS: dict[str, LibraryEntry] = {
    "F_ECONYL_PLAIN_LIGHT": LibraryEntry(
        id="F_ECONYL_PLAIN_LIGHT", kind="fabric",
        name="Econyl 4-way light", tags=("plain", "swim", "eco"),
        weave="plain", composition="78% recycled nylon / 22% spandex",
        weight_gsm=190, stretch_warp_pct=180, stretch_weft_pct=160,
        opacity=0.92, sheen=0.35, fabric_source="econyl",
    ),
    "F_ECONYL_PLAIN_HEAVY": LibraryEntry(
        id="F_ECONYL_PLAIN_HEAVY", kind="fabric",
        name="Econyl 4-way heavy", tags=("plain", "swim", "eco", "heavy"),
        weave="plain", composition="80% recycled nylon / 20% spandex",
        weight_gsm=230, stretch_warp_pct=140, stretch_weft_pct=120,
        opacity=1.0, sheen=0.45, fabric_source="econyl",
    ),
    "F_QNOVA_RIBBED": LibraryEntry(
        id="F_QNOVA_RIBBED", kind="fabric",
        name="Q-NOVA ribbed", tags=("ribbed", "swim", "eco"),
        weave="ribbed", composition="80% Q-NOVA nylon / 20% spandex",
        weight_gsm=210, stretch_warp_pct=150, stretch_weft_pct=130,
        opacity=1.0, sheen=0.40, fabric_source="qnova",
    ),
    "F_VIRGIN_VELVET": LibraryEntry(
        id="F_VIRGIN_VELVET", kind="fabric",
        name="Velvet swim", tags=("velvet", "luxe", "shiny"),
        weave="velvet", composition="82% nylon / 18% spandex",
        weight_gsm=240, stretch_warp_pct=130, stretch_weft_pct=130,
        opacity=1.0, sheen=0.65, fabric_source="virgin",
    ),
    "F_HUNZA_CRINKLE": LibraryEntry(
        id="F_HUNZA_CRINKLE", kind="fabric",
        name="Crinkle (Hunza-G style)", tags=("crinkle", "textured"),
        weave="crinkle", composition="78% nylon / 22% spandex",
        weight_gsm=205, stretch_warp_pct=170, stretch_weft_pct=150,
        opacity=0.95, sheen=0.30, fabric_source="virgin",
    ),
    "F_MISSONI_SHINY_KNIT": LibraryEntry(
        id="F_MISSONI_SHINY_KNIT", kind="fabric",
        name="Shiny knit", tags=("shiny_knit", "luxe", "metallic"),
        weave="shiny_knit", composition="80% nylon / 20% spandex",
        weight_gsm=200, stretch_warp_pct=160, stretch_weft_pct=140,
        opacity=1.0, sheen=0.85, metallic=0.15, fabric_source="virgin",
    ),
    "F_MESH_OUTER": LibraryEntry(
        id="F_MESH_OUTER", kind="fabric",
        name="Mesh outer layer", tags=("mesh", "sheer"),
        weave="mesh", composition="85% nylon / 15% spandex",
        weight_gsm=120, stretch_warp_pct=200, stretch_weft_pct=200,
        opacity=0.40, sheen=0.20, fabric_source="virgin",
    ),
    "F_POWERMESH_LINING": LibraryEntry(
        id="F_POWERMESH_LINING", kind="fabric",
        name="Powermesh lining", tags=("powermesh", "lining", "smoothing"),
        weave="mesh", composition="75% nylon / 25% spandex",
        weight_gsm=150, stretch_warp_pct=200, stretch_weft_pct=180,
        opacity=0.55, sheen=0.10, fabric_source="virgin",
    ),
    "F_FOAM_CUP_3MM": LibraryEntry(
        id="F_FOAM_CUP_3MM", kind="fabric",
        name="Molded EVA foam cup 3 mm", tags=("foam", "padding", "structured"),
        weave="foam", composition="EVA foam laminated tricot",
        weight_gsm=380, stretch_warp_pct=20, stretch_weft_pct=20,
        opacity=1.0, sheen=0.10, fabric_source="virgin",
    ),
    "F_CROCHET_COTTON": LibraryEntry(
        id="F_CROCHET_COTTON", kind="fabric",
        name="Crochet cotton", tags=("crochet", "cotton", "boho"),
        weave="crochet", composition="100% organic cotton",
        weight_gsm=170, stretch_warp_pct=30, stretch_weft_pct=30,
        opacity=0.65, sheen=0.05, fabric_source="cotton_blend",
        biodegradable=True,
    ),
    "F_BIOPOLYMER_PLAIN": LibraryEntry(
        id="F_BIOPOLYMER_PLAIN", kind="fabric",
        name="Bio-polyamide plain", tags=("plain", "bio", "eco"),
        weave="plain", composition="82% bio-polyamide / 18% spandex",
        weight_gsm=195, stretch_warp_pct=170, stretch_weft_pct=150,
        opacity=0.95, sheen=0.30, fabric_source="biopolymer",
        biodegradable=True,
    ),
    "F_AMNI_SOUL_RIBBED": LibraryEntry(
        id="F_AMNI_SOUL_RIBBED", kind="fabric",
        name="Amni Soul Eco ribbed", tags=("ribbed", "bio", "eco"),
        weave="ribbed", composition="80% Amni Soul Eco / 20% spandex",
        weight_gsm=215, stretch_warp_pct=140, stretch_weft_pct=120,
        opacity=1.0, sheen=0.30, fabric_source="amni_soul",
        biodegradable=True,
    ),

    # ---------------- Textured / sand-handle ----------------
    "F_SEERSUCKER_STRIPE": LibraryEntry(
        id="F_SEERSUCKER_STRIPE", kind="fabric",
        name="Seersucker stripe", tags=("seersucker", "textured", "sandy"),
        weave="seersucker", composition="65% recycled poly / 30% nylon / 5% spandex",
        weight_gsm=200, stretch_warp_pct=80, stretch_weft_pct=90,
        opacity=1.0, sheen=0.25, fabric_source="virgin",
    ),
    "F_SLUB_LINEN_BLEND": LibraryEntry(
        id="F_SLUB_LINEN_BLEND", kind="fabric",
        name="Slub linen blend", tags=("slub", "textured", "matte"),
        weave="slub", composition="55% linen / 35% nylon / 10% spandex",
        weight_gsm=185, stretch_warp_pct=70, stretch_weft_pct=80,
        opacity=1.0, sheen=0.15, fabric_source="cotton_blend",
        biodegradable=True,
    ),
    "F_TERRY_KNIT": LibraryEntry(
        id="F_TERRY_KNIT", kind="fabric",
        name="Terry loop knit", tags=("terry", "textured", "cover_up", "matte"),
        weave="terry", composition="75% cotton / 22% nylon / 3% spandex",
        weight_gsm=250, stretch_warp_pct=110, stretch_weft_pct=100,
        opacity=1.0, sheen=0.20, fabric_source="cotton_blend",
        biodegradable=True,
    ),
    "F_WAFFLE_HONEYCOMB": LibraryEntry(
        id="F_WAFFLE_HONEYCOMB", kind="fabric",
        name="Waffle honeycomb knit", tags=("waffle", "textured"),
        weave="terry", composition="80% nylon / 20% spandex",
        weight_gsm=220, stretch_warp_pct=140, stretch_weft_pct=130,
        opacity=1.0, sheen=0.25, fabric_source="virgin",
    ),

    # ---------------- Open / cutout / lace ----------------
    "F_LACE_FLORAL": LibraryEntry(
        id="F_LACE_FLORAL", kind="fabric",
        name="Floral lace overlay", tags=("lace", "open", "sheer", "luxe"),
        weave="lace", composition="90% nylon / 10% spandex",
        weight_gsm=110, stretch_warp_pct=160, stretch_weft_pct=140,
        opacity=0.45, sheen=0.20, fabric_source="virgin",
    ),
    "F_BRODERIE_ANGLAISE": LibraryEntry(
        id="F_BRODERIE_ANGLAISE", kind="fabric",
        name="Broderie anglaise eyelet", tags=("eyelet", "open", "cutout"),
        weave="lace", composition="100% cotton",
        weight_gsm=130, stretch_warp_pct=10, stretch_weft_pct=15,
        opacity=0.70, sheen=0.10, fabric_source="cotton_blend",
        biodegradable=True,
    ),
    "F_MACRAME_COTTON": LibraryEntry(
        id="F_MACRAME_COTTON", kind="fabric",
        name="Macrame knot cotton", tags=("macrame", "boho", "open", "structured"),
        weave="crochet", composition="100% cotton",
        weight_gsm=190, stretch_warp_pct=20, stretch_weft_pct=20,
        opacity=0.60, sheen=0.05, fabric_source="cotton_blend",
        biodegradable=True,
    ),
    "F_CUTOUT_JERSEY": LibraryEntry(
        id="F_CUTOUT_JERSEY", kind="fabric",
        name="Laser-cut jersey", tags=("cutout", "open", "modern"),
        weave="lace", composition="80% nylon / 20% spandex",
        weight_gsm=160, stretch_warp_pct=170, stretch_weft_pct=150,
        opacity=0.65, sheen=0.30, fabric_source="virgin",
    ),

    # ---------------- Mesh varieties ----------------
    "F_TULLE_NET": LibraryEntry(
        id="F_TULLE_NET", kind="fabric",
        name="Soft tulle net", tags=("tulle", "mesh", "sheer", "soft"),
        weave="mesh", composition="100% nylon",
        weight_gsm=80, stretch_warp_pct=80, stretch_weft_pct=70,
        opacity=0.30, sheen=0.15, fabric_source="virgin",
    ),
    "F_FISHNET_OPEN": LibraryEntry(
        id="F_FISHNET_OPEN", kind="fabric",
        name="Wide-open fishnet", tags=("fishnet", "open", "sheer"),
        weave="fishnet", composition="80% nylon / 20% spandex",
        weight_gsm=100, stretch_warp_pct=180, stretch_weft_pct=180,
        opacity=0.20, sheen=0.25, fabric_source="virgin",
    ),

    # ---------------- Sport / tech ----------------
    "F_NEOPRENE_1MM": LibraryEntry(
        id="F_NEOPRENE_1MM", kind="fabric",
        name="Neoprene 1 mm laminate", tags=("neoprene", "sport", "structured", "matte"),
        weave="neoprene", composition="neoprene core / nylon face",
        weight_gsm=320, stretch_warp_pct=60, stretch_weft_pct=60,
        opacity=1.0, sheen=0.10, fabric_source="virgin",
    ),
    "F_NEOPRENE_2MM": LibraryEntry(
        id="F_NEOPRENE_2MM", kind="fabric",
        name="Neoprene 2 mm laminate", tags=("neoprene", "sport", "heavy", "matte"),
        weave="neoprene", composition="neoprene core / double nylon face",
        weight_gsm=460, stretch_warp_pct=40, stretch_weft_pct=40,
        opacity=1.0, sheen=0.10, fabric_source="virgin",
    ),
    "F_COMPRESSION_SPORT": LibraryEntry(
        id="F_COMPRESSION_SPORT", kind="fabric",
        name="High-compression sport jersey", tags=("compression", "sport"),
        weave="ribbed", composition="70% nylon / 30% spandex",
        weight_gsm=260, stretch_warp_pct=110, stretch_weft_pct=110,
        opacity=1.0, sheen=0.40, fabric_source="virgin",
    ),

    # ---------------- Luxe ----------------
    "F_SEQUIN_DENSE": LibraryEntry(
        id="F_SEQUIN_DENSE", kind="fabric",
        name="Dense sequin tile", tags=("sequined", "luxe", "metallic", "shiny"),
        weave="sequined", composition="polyester sequins on nylon mesh base",
        weight_gsm=280, stretch_warp_pct=80, stretch_weft_pct=70,
        opacity=1.0, sheen=0.90, metallic=0.55, fabric_source="virgin",
    ),
    "F_FOIL_COATED_GOLD": LibraryEntry(
        id="F_FOIL_COATED_GOLD", kind="fabric",
        name="Gold-foil coated swim", tags=("foil", "luxe", "metallic", "shiny"),
        weave="plain", composition="nylon-spandex with metallic foil coat",
        weight_gsm=210, stretch_warp_pct=150, stretch_weft_pct=130,
        opacity=1.0, sheen=0.95, metallic=0.75, fabric_source="virgin",
    ),
    "F_JACQUARD_FLORAL": LibraryEntry(
        id="F_JACQUARD_FLORAL", kind="fabric",
        name="Floral jacquard knit", tags=("jacquard", "luxe", "textured"),
        weave="jacquard", composition="78% nylon / 22% spandex",
        weight_gsm=235, stretch_warp_pct=120, stretch_weft_pct=110,
        opacity=1.0, sheen=0.45, fabric_source="virgin",
    ),

    # ---------------- Eco / bio additions ----------------
    "F_HEMP_BLEND": LibraryEntry(
        id="F_HEMP_BLEND", kind="fabric",
        name="Hemp-nylon blend", tags=("plain", "eco", "matte"),
        weave="plain", composition="55% hemp / 35% recycled nylon / 10% spandex",
        weight_gsm=215, stretch_warp_pct=120, stretch_weft_pct=110,
        opacity=1.0, sheen=0.20, fabric_source="cotton_blend",
        biodegradable=True,
    ),
    "F_ALGAE_BLEND": LibraryEntry(
        id="F_ALGAE_BLEND", kind="fabric",
        name="Algae-based bio knit", tags=("plain", "bio", "eco"),
        weave="plain", composition="65% algae yarn / 25% nylon / 10% spandex",
        weight_gsm=195, stretch_warp_pct=150, stretch_weft_pct=140,
        opacity=0.97, sheen=0.30, fabric_source="biopolymer",
        biodegradable=True,
    ),
    "F_MUSHROOM_LEATHER": LibraryEntry(
        id="F_MUSHROOM_LEATHER", kind="fabric",
        name="Mycelium leather panel", tags=("vegan_leather", "bio", "structured", "matte"),
        weave="foam", composition="mycelium-based mat with cotton backing",
        weight_gsm=340, stretch_warp_pct=15, stretch_weft_pct=15,
        opacity=1.0, sheen=0.20, fabric_source="biopolymer",
        biodegradable=True,
    ),
}


# ---------------------------------------------------------------------------
# BODY_JEWELRY — 10 entries (NEW v2 — independent body-worn accessories)
# ---------------------------------------------------------------------------

BODY_JEWELRY: dict[str, LibraryEntry] = {
    "BJ_BRACELET_CHAIN_GOLD": LibraryEntry(
        id="BJ_BRACELET_CHAIN_GOLD", kind="body_jewelry",
        name="Wrist chain bracelet gold",
        tags=("bracelet", "chain", "gold"),
        anatomy_hints=("wrist_R",), jewelry_form="bracelet_chain",
        metal_finish="gold",
        local_params_schema={"diameter_cm": (5.5, 7.5, 6.5)},
    ),
    "BJ_BRACELET_BEADED": LibraryEntry(
        id="BJ_BRACELET_BEADED", kind="body_jewelry",
        name="Beaded wrist bracelet",
        tags=("bracelet", "beaded", "boho"),
        anatomy_hints=("wrist_R",), jewelry_form="bracelet_beaded",
        local_params_schema={"diameter_cm": (5.5, 7.5, 6.5)},
    ),
    "BJ_NECKLACE_CHOKER_GOLD": LibraryEntry(
        id="BJ_NECKLACE_CHOKER_GOLD", kind="body_jewelry",
        name="Gold choker necklace",
        tags=("necklace", "choker", "gold"),
        anatomy_hints=("neck_front",), jewelry_form="necklace_choker",
        metal_finish="gold",
        local_params_schema={"width_cm": (0.3, 1.5, 0.6)},
    ),
    "BJ_NECKLACE_PENDANT_SHELL": LibraryEntry(
        id="BJ_NECKLACE_PENDANT_SHELL", kind="body_jewelry",
        name="Shell pendant necklace",
        tags=("necklace", "pendant", "shell", "boho"),
        anatomy_hints=("neck_front",), jewelry_form="necklace_pendant",
        local_params_schema={"chain_length_cm": (40.0, 55.0, 45.0)},
    ),
    "BJ_EARRING_DROP_GOLD": LibraryEntry(
        id="BJ_EARRING_DROP_GOLD", kind="body_jewelry",
        name="Gold drop earring",
        tags=("earring", "drop", "gold"),
        anatomy_hints=("earlobe_R", "earlobe_L"), jewelry_form="earring_drop",
        metal_finish="gold",
        local_params_schema={"length_cm": (1.5, 4.0, 2.5)},
    ),
    "BJ_EARRING_STUD_PEARL": LibraryEntry(
        id="BJ_EARRING_STUD_PEARL", kind="body_jewelry",
        name="Pearl stud earring",
        tags=("earring", "stud", "pearl"),
        anatomy_hints=("earlobe_R", "earlobe_L"), jewelry_form="earring_stud",
        metal_finish="pearl",
        local_params_schema={"size_cm": (0.4, 1.0, 0.6)},
    ),
    "BJ_BODY_CHAIN_WAIST": LibraryEntry(
        id="BJ_BODY_CHAIN_WAIST", kind="body_jewelry",
        name="Body chain waist gold",
        tags=("body_chain", "waist", "gold"),
        anatomy_hints=("belly_button",), jewelry_form="body_chain_waist",
        metal_finish="gold",
        local_params_schema={"length_cm": (60.0, 90.0, 75.0)},
    ),
    "BJ_BODY_CHAIN_BELLY": LibraryEntry(
        id="BJ_BODY_CHAIN_BELLY", kind="body_jewelry",
        name="Belly chain layered",
        tags=("body_chain", "belly", "layered"),
        anatomy_hints=("belly_button",), jewelry_form="body_chain_belly",
        metal_finish="silver",
        local_params_schema={"length_cm": (55.0, 85.0, 68.0)},
    ),
    "BJ_ANKLET_CHAIN": LibraryEntry(
        id="BJ_ANKLET_CHAIN", kind="body_jewelry",
        name="Anklet chain silver",
        tags=("anklet", "chain", "silver"),
        anatomy_hints=("ankle_R",), jewelry_form="anklet_chain",
        metal_finish="silver",
        local_params_schema={"diameter_cm": (7.0, 10.0, 8.5)},
    ),
    "BJ_ANKLET_CHARM_BEACH": LibraryEntry(
        id="BJ_ANKLET_CHARM_BEACH", kind="body_jewelry",
        name="Beach charm anklet",
        tags=("anklet", "charm", "beach", "boho"),
        anatomy_hints=("ankle_R",), jewelry_form="anklet_charm",
        local_params_schema={"diameter_cm": (7.0, 10.0, 8.5)},
    ),
}


# ---------------------------------------------------------------------------
# SEAM_TYPES — 6 entries
# ---------------------------------------------------------------------------

SEAM_TYPES: dict[str, LibraryEntry] = {
    "S_OVERLOCK_4THREAD": LibraryEntry(
        id="S_OVERLOCK_4THREAD", kind="seam_type",
        name="4-thread overlock", tags=("structural", "overlock"),
        machine="overlock", threads=4, spi=12, structural=True,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle"),
    ),
    "S_COVERSTITCH_3NEEDLE": LibraryEntry(
        id="S_COVERSTITCH_3NEEDLE", kind="seam_type",
        name="3-needle coverstitch", tags=("decorative", "coverstitch"),
        machine="coverstitch", threads=5, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle"),
    ),
    "S_FOE_BIND_25MM": LibraryEntry(
        id="S_FOE_BIND_25MM", kind="seam_type",
        name="1\" FOE binding seam", tags=("FOE", "edge", "wide"),
        machine="coverstitch", threads=3, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit", "velvet"),
    ),
    "S_FOE_BIND_15MM": LibraryEntry(
        id="S_FOE_BIND_15MM", kind="seam_type",
        name="5/8\" FOE binding seam", tags=("FOE", "edge"),
        machine="coverstitch", threads=3, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle"),
    ),
    "S_BARTACK": LibraryEntry(
        id="S_BARTACK", kind="seam_type",
        name="Bartack reinforcement", tags=("bartack", "reinforce"),
        machine="bartack", threads=2, spi=20, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle", "crochet"),
    ),
    "S_FLATLOCK": LibraryEntry(
        id="S_FLATLOCK", kind="seam_type",
        name="Flatlock decorative seam", tags=("decorative", "flatlock"),
        machine="overlock", threads=4, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "shiny_knit"),
    ),
}


# ---------------------------------------------------------------------------
# Combined library — merge all kind dicts into one id-keyed lookup
# ---------------------------------------------------------------------------

LIBRARY: dict[str, LibraryEntry] = {}
for d in (CUP_PIECES, BOTTOM_PIECES, STRAP_PIECES, HARDWARE,
            ACCESSORIES, FABRICS, BODY_JEWELRY, SEAM_TYPES):
    LIBRARY.update(d)


# ---------------------------------------------------------------------------
# Derive edge_finish_policy per fabric from its weave family.
# Kept here (vs hand-set on every entry) so a new fabric automatically
# inherits the right policy as long as its weave is one of the known
# families. Override on the entry if a specific fabric is special.
# ---------------------------------------------------------------------------

_RAW_OK_WEAVES      = {"neoprene", "foam"}
_SELVEDGE_WEAVES    = {"crochet", "lace", "fishnet", "mesh"}

for _fid, _e in FABRICS.items():
    if _e.edge_finish_policy != "must_bind":
        continue   # respect any hand-set override
    if _e.weave in _RAW_OK_WEAVES:
        object.__setattr__(_e, "edge_finish_policy", "raw_ok")
    elif _e.weave in _SELVEDGE_WEAVES:
        object.__setattr__(_e, "edge_finish_policy", "selvedge_only")


# ---------------------------------------------------------------------------
# Plug the historical "center_v = 0.74" template leak.
#
# `outfit.outfit_to_genome` does `cup_p.get("center_v", 0.74)`.  No
# cup entry's local_params_schema declared `center_v`, so 100% of
# generated cups inherited the fallback 0.74 -- which happens to be
# swimsuit_2's cup vertical centre.  Result: every one of 240 batch
# variants had cups at the SAME vertical position.
#
# Fix by giving every cup an explicit center_v range tied to its
# geometry kind, so each variant samples its own centre.
# ---------------------------------------------------------------------------

def _center_v_range_for(entry: LibraryEntry) -> tuple[float, float, float]:
    """(lo, hi, default) for cup_piece center_v based on geometry kind."""
    g = entry.geometry_kind
    if g == "molded_foam":
        return (0.69, 0.79, 0.74)
    if g == "softcup_squareneck":
        return (0.66, 0.82, 0.74)
    if g == "bandeau_unified":
        return (0.70, 0.78, 0.74)
    if g in ("triangle", "brazilian"):
        return (0.70, 0.83, 0.76)
    if g == "balconette":
        return (0.68, 0.78, 0.73)
    return (0.68, 0.80, 0.74)

for _cup in CUP_PIECES.values():
    if "center_v" not in _cup.local_params_schema:
        _new_schema = dict(_cup.local_params_schema)
        _new_schema["center_v"] = _center_v_range_for(_cup)
        _cup.local_params_schema = _new_schema


def entries_by_kind(kind: str) -> list[LibraryEntry]:
    return [e for e in LIBRARY.values() if e.kind == kind]


def entries_matching_slot(slot) -> list[LibraryEntry]:
    """Return all library entries that satisfy a SlotSpec."""
    return [e for e in LIBRARY.values() if slot.matches(e)]


# Sanity: every SlotSpec.allowed_tags has at least 2 matching entries
def _sanity_slot_coverage():
    from library import ARCHETYPE_SLOTS
    issues = []
    for arch, slots in ARCHETYPE_SLOTS.items():
        for s in slots:
            matches = entries_matching_slot(s)
            if s.required and len(matches) < 1:
                issues.append(f"  {arch}.{s.name}: 0 matches "
                              f"(required, kind={s.kind} tags={s.allowed_tags})")
            elif len(matches) < 2:
                issues.append(f"  {arch}.{s.name}: {len(matches)} matches "
                              f"(below diversity floor of 2)")
    return issues


if __name__ == "__main__":
    print(f"library size: {len(LIBRARY)} entries")
    by_kind = {}
    for e in LIBRARY.values():
        by_kind.setdefault(e.kind, []).append(e.id)
    for k in sorted(by_kind):
        print(f"  {k:14s} {len(by_kind[k]):3d}")
    issues = _sanity_slot_coverage()
    if issues:
        print(f"\n{len(issues)} slot coverage issue(s):")
        for i in issues:
            print(i)
    else:
        print("\nall slots have >=2 matching entries")
