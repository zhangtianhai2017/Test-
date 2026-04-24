"""
UV-unwrap bikini GA verifier.

Represents the torso as a flat UV rectangle (like a world-map projection):
    u in [-1, 1]   angular position:  -1 = back seam, 0 = front center, +1 = back seam (wraps)
    v in [ 0, 1]   vertical:          0 = groin, 1 = neck

A bikini is a set of 2D polygons in this plane. The GA operates directly
on the polygon-control-point parameters, so shapes like triangle / bandeau /
halter / bralette emerge from a single continuous space instead of being
discrete archetypes.

Run: `python3 tools/verify_ga_uv.py`.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, asdict

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
from matplotlib.colors import hsv_to_rgb

SEED = 42
N_OFFSPRING = 8
BLX_ALPHA = 0.3
MUT_SIGMA = 0.08
MUT_PROB_CAT = 0.08
OUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Body landmarks in UV space (fixed, used for rendering guides)
LANDMARKS_V = {
    "neck":      0.96,
    "bust":      0.78,
    "underbust": 0.70,
    "waist":     0.48,
    "hip":       0.22,
    "crotch":    0.06,
}
PATTERNS = [
    "solid", "stripe", "polka", "checker",
    # Batch 1 additions — more print varieties.
    "gingham", "chevron", "floral", "tropical", "leopard",
    "tie_dye", "ombre", "herringbone",
]

# Batch 1 discrete enumerations
FABRIC_WEAVES = [
    "plain",        # default flat weave
    "mesh",         # open grid, see-through
    "crochet",      # handmade texture, chunky
    "ribbed",       # strong vertical ribs
    "velvet",       # pile surface, matte
    "crinkle",      # Hunza G signature — high-freq crinkle
    "shiny_knit",   # Missoni-ish shiny knit
]

# 2025 hardware / trim palette
HARDWARE_METALS = ["none", "gold", "silver", "rose_gold", "pearl", "chrome"]

# Style archetypes (Batch 2 §4). Each one pulls several Genome fields
# toward a designer / regional signature. See _STYLE_TARGETS below.
STYLE_ARCHETYPES = [
    "free",                  # no bias
    "brazilian",             # low rise, tiny sides, cheeky, vivid
    "italian_luxe",          # big prints, heavy metal, baroque
    "japanese_minimal",      # clean lines, muted, tiny hardware
    "korean_feminine",       # pastel, bows, ribbons
    "scandi_minimal",        # black/white, matte, no print
    "spanish_mediterranean", # crochet, earth tones, ruffles
    "american_sporty",       # rash-guard inspired, bold blocks
    "boho_cultgaia",         # crochet + shells + fringe
    "retro_missoni",         # chevron / zigzag, striped
    "hunzag_crinkle",        # Hunza G — crinkle fabric
    "avantgarde_cutout",     # editorial, high contrast, cutouts
    "sporty_chromat",        # strap-heavy, athletic
    "eres_architect",        # molded cups, no hardware
]

PALETTE_PRESETS = [
    "free",                 # unconstrained — GA can pick any hue/sat/light
    "future_dusk",          # WGSN 2025 color of the year — dark blue-purple
    "transcendent_pink",    # WGSN 2025 — near-neutral pale pink
    "aquatic_awe",          # WGSN 2025 — deep ocean teal
    "ethereal_highlight",   # WGSN 2025 — moonlit warm white
    "galactic_cobalt",      # WGSN 2025 — saturated deep blue
    "sunset_peach",         # common 2025 summer accent
]
FABRIC_SOURCES = [
    "econyl",               # regenerated nylon from ocean / fishing net waste
    "biopolymer",           # bio-based polyamide (>=80% renewable: sugarcane, etc)
    "qnova",                # Fulgar Q-NOVA, recycled pre-consumer nylon
    "amni_soul",            # biodegradable polyamide (~5 yr in landfill)
    "virgin",               # conventional virgin nylon/elastane — the baseline
    "cotton_blend",         # organic cotton + spandex (bio-based, less stretch)
]

# Continuous Genome fields. Kept flat so GA operators are uniform.
CONT_FIELDS = [
    # TOP
    "top_center_v",        # vertical position of cup centroid (bust area ~0.75)
    "top_half_v",          # vertical half-size of each cup
    "top_half_u",          # horizontal half-size of each cup (in u units)
    "top_inner_u",         # inner edge distance from u=0 (0 -> bandeau, big -> split V)
    "top_apex_lift",       # concave top edge: +ve = V at center (triangle), -ve = bandeau flat
    "top_underband_dip",   # concave bottom edge: +ve pushes bottom inward under bust
    "top_back_coverage",   # 0 = back strap only, 1 = full back panel
    "top_neck_strap",      # 0 = none, 1 = prominent halter across the back of the neck
    "top_shoulder_strap",  # 0 = none, 1 = prominent shoulder straps (triangle-style)
    # BOTTOM
    "bot_front_top_v",     # waistline height at front
    "bot_front_half_u",    # half-width of front panel around u=0
    "bot_front_leg_curve", # concavity of front leg opening
    "bot_back_top_v",      # waistline height at back
    "bot_back_half_u",     # half-width of back panel around u=±1 (small -> thong)
    "bot_tie_dangle",      # 0 = no knot tails, 1 = long dangling strings past the hip
    # COLOR (Batch 1 expanded)
    "hue",                 # primary HSL hue
    "saturation",          # primary HSL saturation
    "lightness",           # primary HSL lightness (was fixed 0.90, now a gene)
    "secondary_hue",       # secondary color (used by gingham / chevron / ombre / tie-dye)
    "secondary_saturation",
    "secondary_lightness",
    "pattern_scale",       # size multiplier for pattern motifs (0 small -> 1 huge)
    "pattern_angle",       # 0..1 mapped to 0..180 deg rotation
    "trim_color_mode",     # 0 = binding matches body, 1 = strong contrast (dark/white)
    # FABRIC (Batch 1 new)
    "fabric_sheen",        # 0 matte -> 1 satin/wet-look. Drives material roughness.
    "fabric_metallic",     # 0 non-metal -> 1 lurex / metallic foil shine.
    "fabric_opacity",      # 0.5 sheer -> 1.0 fully opaque. Drives material alpha.
    "fabric_weight",       # 0 light/drapey -> 1 heavy/structured. Tweaks wrinkles.
    # SUSTAINABILITY (Batch 1 new)
    "biodegradable",       # continuous in [0,1] but thresholded to 0/1 by constraints
    "single_material",     # ditto — recyclability by design
    # HARDWARE / TRIM (Batch 2 new)
    "has_oring",           # 0/1 threshold: metal rings at strap junctions
    "oring_size",          # 0..1 -> diameter 0.8..2.6 cm
    "has_bow",             # 0/1: decorative bow at front center gore
    "bow_size",            # 0..1 -> bow wingspan 1..5 cm
    "has_fringe",          # 0/1: fringes hanging from bottom-panel leg cut
    "fringe_length",       # 0..1 -> 1..10 cm
    "has_beads",           # 0/1: small beads along the top-band edge
    "has_shell",           # 0/1: shell-like charm hanging at front center
]


@dataclass
class Genome:
    # shape
    pattern: str
    top_center_v: float
    top_half_v: float
    top_half_u: float
    top_inner_u: float
    top_apex_lift: float
    top_underband_dip: float
    top_back_coverage: float
    top_neck_strap: float
    top_shoulder_strap: float
    bot_front_top_v: float
    bot_front_half_u: float
    bot_front_leg_curve: float
    bot_back_top_v: float
    bot_back_half_u: float
    bot_tie_dangle: float
    # color (Batch 1 expanded)
    hue: float
    saturation: float
    lightness: float
    secondary_hue: float
    secondary_saturation: float
    secondary_lightness: float
    pattern_scale: float
    pattern_angle: float
    trim_color_mode: float
    # fabric (Batch 1 new)
    fabric_sheen: float
    fabric_metallic: float
    fabric_opacity: float
    fabric_weight: float
    fabric_weave: str
    # palette + sustainability (Batch 1 new)
    palette_preset: str
    fabric_source: str
    biodegradable: float
    single_material: float
    # hardware (Batch 2 new)
    has_oring: float
    oring_size: float
    has_bow: float
    bow_size: float
    has_fringe: float
    fringe_length: float
    has_beads: float
    has_shell: float
    # style (Batch 2 new)
    style_archetype: str
    hardware_metal: str

    def as_dict(self) -> dict:
        return asdict(self)

    def clipped(self) -> "Genome":
        d = self.as_dict()
        for k in CONT_FIELDS:
            if k in ("hue", "secondary_hue", "pattern_angle"):
                d[k] = d[k] % 1.0
            else:
                d[k] = float(np.clip(d[k], 0.0, 1.0))
        return Genome(**d)

# Privacy seeds: minimum-coverage rectangles in UV space. Every Genome's
# polygons must CONTAIN these — `_enforce_constraints` clamps the Genome
# parameters so the trapezoidal cups and front panel grow to at least
# this size. They are not overlays painted on top; they're a lower bound
# baked into the parameter ranges, so the bikini smoothly grows from them.
#
# Coordinate notes for the bundled UE NPC body: the cylindrical UV map
# in render3d_uv.py places the breast peak at Genome v~=0.74 and the
# crotch line at v~=0.18 (not 0.06 — that's the Genome's LANDMARKS_V
# convention, which sits below the body's crotch on this mesh). Seeds
# are therefore placed in the Genome v range that actually overlaps the
# anatomy, not where LANDMARKS_V would put them.
#   (u_lo, u_hi, v_lo, v_hi)
PRIVACY_SEEDS = {
    "right_nipple": (0.10, 0.22, 0.70, 0.80),
    "left_nipple":  (-0.22, -0.10, 0.70, 0.80),
    "pelvic_front": (-0.08, 0.08, 0.30, 0.42),
}

# --------------------------------------------------------------------------
# GA operators — same flavour as the front-view version but much simpler
# because every geometric field is now just a scalar.
# --------------------------------------------------------------------------

def _blx(a: float, b: float, rng: random.Random) -> float:
    lo, hi = (a, b) if a <= b else (b, a)
    d = hi - lo
    return rng.uniform(lo - BLX_ALPHA * d, hi + BLX_ALPHA * d)


def _blx_circular(a: float, b: float, rng: random.Random) -> float:
    diff = (b - a) % 1.0
    b_adj = b - 1.0 if diff > 0.5 else b
    return _blx(a, b_adj, rng) % 1.0


_CIRCULAR_CONT = {"hue", "secondary_hue", "pattern_angle"}
_DISCRETE_ENUMS = {
    "pattern": PATTERNS,
    "fabric_weave": FABRIC_WEAVES,
    "palette_preset": PALETTE_PRESETS,
    "fabric_source": FABRIC_SOURCES,
    "style_archetype": STYLE_ARCHETYPES,
    "hardware_metal": HARDWARE_METALS,
}


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    d = {}
    # Discrete fields: single-point inheritance from one of the parents.
    for k in _DISCRETE_ENUMS:
        d[k] = rng.choice([getattr(a, k), getattr(b, k)])
    # Continuous fields: BLX-alpha (circular-aware for angle/hue fields).
    for k in CONT_FIELDS:
        va, vb = getattr(a, k), getattr(b, k)
        d[k] = _blx_circular(va, vb, rng) if k in _CIRCULAR_CONT else _blx(va, vb, rng)
    return Genome(**d).clipped()


def mutate(g: Genome, rng: random.Random) -> Genome:
    d = g.as_dict()
    # Discrete resample with per-field probability
    for k, enum in _DISCRETE_ENUMS.items():
        if rng.random() < MUT_PROB_CAT:
            d[k] = rng.choice(enum)
    # Continuous gaussian perturbation
    for k in CONT_FIELDS:
        noise = rng.gauss(0, MUT_SIGMA)
        if k in _CIRCULAR_CONT:
            d[k] = (d[k] + noise) % 1.0
        else:
            d[k] = d[k] + noise
    return _enforce_constraints(Genome(**d).clipped())


def _enforce_constraints(g: Genome) -> Genome:
    """Hard rules: keep polygons non-degenerate AND guarantee they contain
    the PRIVACY_SEEDS. Each clamp below is derived analytically from the
    polygon shape — never paints over the result, just constrains parameters
    so the trapezoidal cups / front panel grow at least to the seed extent.

    Ordering matters: archetype + palette biases are applied FIRST (they're
    soft attractors), then the privacy / topology clamps have the last word
    so they can't be overridden by an aggressive archetype.
    """
    d = g.as_dict()

    # --- Batch 1 + 2: threshold booleans (do up-front so downstream
    # archetype targets for these fields snap cleanly)
    for k in ("biodegradable", "single_material",
              "has_oring", "has_bow", "has_fringe",
              "has_beads", "has_shell"):
        d[k] = 1.0 if d[k] >= 0.5 else 0.0

    # --- Style archetype soft-anchors many fields (Batch 2) -------------
    arch = d.get("style_archetype", "free")
    arch_targets = _STYLE_TARGETS.get(arch)
    if arch_targets is not None:
        blend = 0.55
        for k, tv in arch_targets.items():
            if k in _DISCRETE_ENUMS:
                if rng_coin(k, d, blend):
                    d[k] = tv
            elif k in CONT_FIELDS:
                if k in _CIRCULAR_CONT:
                    cur = d[k]
                    diff = (tv - cur) % 1.0
                    if diff > 0.5:
                        diff -= 1.0
                    d[k] = (cur + blend * diff) % 1.0
                else:
                    d[k] = (1 - blend) * d[k] + blend * tv

    # --- WGSN palette preset soft-anchors hue/saturation/lightness ------
    preset = d.get("palette_preset", "free")
    targets = _PALETTE_TARGETS.get(preset)
    if targets is not None:
        blend = 0.6
        th, ts, tl = targets
        cur_h = d["hue"]
        diff = (th - cur_h) % 1.0
        if diff > 0.5:
            diff -= 1.0
        d["hue"] = (cur_h + blend * diff) % 1.0
        d["saturation"] = float(np.clip(
            (1 - blend) * d["saturation"] + blend * ts, 0.0, 1.0))
        d["lightness"] = float(np.clip(
            (1 - blend) * d["lightness"] + blend * tl, 0.0, 1.0))

    # --- Re-threshold booleans after archetype blend (some archetypes
    # set e.g. has_oring=1.0, some set 0.0; blend can leave mid-values)
    for k in ("biodegradable", "single_material",
              "has_oring", "has_bow", "has_fringe",
              "has_beads", "has_shell"):
        d[k] = 1.0 if d[k] >= 0.5 else 0.0

    # ====================================================================
    # Privacy-seed containment (final authority — can override archetype)
    # ====================================================================

    # --- privacy seeds for the cup (right nipple drives both due to symmetry)
    s_u_lo, s_u_hi, s_v_lo, s_v_hi = PRIVACY_SEEDS["right_nipple"]

    # cup must straddle the seed vertically: cv+hv >= s_v_hi, cv-hv <= s_v_lo
    # so cv ∈ [s_v_hi - hv_min, s_v_lo + hv_min] and hv >= max(s_v_hi-cv, cv-s_v_lo)
    # we anchor cv into a band centered on the seed midline first, then enlarge hv.
    seed_mid_v = (s_v_lo + s_v_hi) / 2
    seed_half_v = (s_v_hi - s_v_lo) / 2
    d["top_center_v"] = float(np.clip(d["top_center_v"],
                                       seed_mid_v - 0.04,
                                       seed_mid_v + 0.04))
    needed_hv = max(seed_half_v + 0.01,
                    abs(d["top_center_v"] - s_v_hi),
                    abs(d["top_center_v"] - s_v_lo))
    d["top_half_v"] = max(d["top_half_v"], needed_hv)

    # cup must cover the seed in u: inner edge <= s_u_lo, outer edge >= s_u_hi
    d["top_inner_u"] = min(d["top_inner_u"], s_u_lo - 0.005)
    d["top_inner_u"] = max(d["top_inner_u"], 0.0)
    needed_hu = max(0.05, (s_u_hi - d["top_inner_u"] + 0.01) / 2.0)
    d["top_half_u"] = max(d["top_half_u"], needed_hu)

    # apex_lift drops the inner-top edge by apex*0.6 — cap so it stays
    # above the seed top: cv + hv - apex*0.6 >= s_v_hi
    apex_max = (d["top_center_v"] + d["top_half_v"] - s_v_hi) / 0.6
    d["top_apex_lift"] = min(d["top_apex_lift"], max(0.0, apex_max))

    # underband_dip raises the inner-bottom edge by dip*0.3 — cap so it stays
    # below the seed bottom: cv - hv + dip*0.3 <= s_v_lo
    dip_max = (s_v_lo - d["top_center_v"] + d["top_half_v"]) / 0.3
    d["top_underband_dip"] = min(d["top_underband_dip"], max(0.0, dip_max))

    # --- privacy seed for the front panel (pelvic_front)
    p_u_lo, p_u_hi, p_v_lo, p_v_hi = PRIVACY_SEEDS["pelvic_front"]
    # panel top must be at or above the seed top
    d["bot_front_top_v"] = max(d["bot_front_top_v"], p_v_hi + 0.04)
    # at the polygon's narrowest point (midline) width = hu*(1 - leg/2);
    # require this to cover the seed half-width comfortably
    needed_front_hu = max((p_u_hi + 0.01) / max(1e-3, 1 - 0.5 * d["bot_front_leg_curve"]),
                          p_u_hi + 0.01)
    d["bot_front_half_u"] = max(d["bot_front_half_u"], needed_front_hu)
    # if leg curve is too aggressive given hu, reduce it
    max_leg = 2 * (1 - (p_u_hi + 0.01) / d["bot_front_half_u"])
    d["bot_front_leg_curve"] = min(d["bot_front_leg_curve"], max(0.0, max_leg))

    # --- minimum back coverage so back panels never collapse to nothing
    d["bot_back_half_u"] = max(d["bot_back_half_u"], 0.04)

    # --- TOPOLOGY: a bikini that stays on the body needs closed loops.
    # The top needs at least one band connecting the front cups to the back
    # (otherwise the cups dangle forward and fall). The bottom needs the
    # front and back panels to close into a single waist loop via the side
    # ties — that only works if front and back waist-lines are close enough
    # in v that the side tie can span them.
    d["top_back_coverage"] = max(d["top_back_coverage"], 0.05)
    # clamp front/back waist-v difference so the side tie can bridge them
    MAX_WAIST_DIFF = 0.10
    diff = d["bot_front_top_v"] - d["bot_back_top_v"]
    if diff > MAX_WAIST_DIFF:
        d["bot_back_top_v"] = d["bot_front_top_v"] - MAX_WAIST_DIFF
    elif diff < -MAX_WAIST_DIFF:
        d["bot_front_top_v"] = d["bot_back_top_v"] - MAX_WAIST_DIFF

    # --- non-degeneracy guards (kept from before)
    d["top_half_v"] = max(d["top_half_v"], 0.05)
    d["top_half_u"] = max(d["top_half_u"], 0.05)
    d["bot_front_half_u"] = max(d["bot_front_half_u"], 0.05)

    # front panel top must sit below the cup bottom
    cup_bottom_v = d["top_center_v"] - d["top_half_v"]
    if d["bot_front_top_v"] > cup_bottom_v - 0.02:
        d["bot_front_top_v"] = max(p_v_hi + 0.04, cup_bottom_v - 0.05)

    # --- Batch 1: fabric_weight affects drape ---------------------------
    # heavier fabric -> less stretch -> panels stay more structured.
    # (No-op here; used downstream in render_mesh for wrinkle amplitude.)

    return Genome(**d)


# Deterministic coin based on a hashed field key + current value so the
# style-archetype discrete snaps are reproducible per-Genome without
# needing an RNG argument. Returns True with probability `p`.
def rng_coin(key: str, d: dict, p: float) -> bool:
    val = d.get(key, "")
    h = hash(f"{key}:{val}") & 0xffff
    return (h / 0xffff) < p


# Style archetype targets — each value is a (field -> target) dict. The
# constraint blender pulls the Genome 55% toward these values, so the
# archetype acts as an "attractor" without hard-overriding the GA. Only
# the most distinctive fields for each style are listed; everything else
# floats freely.
_STYLE_TARGETS: dict[str, dict] = {
    "brazilian": {            # low-rise, tiny sides, cheeky, vivid
        "bot_front_top_v": 0.25, "bot_back_half_u": 0.08,
        "bot_front_half_u": 0.16, "bot_front_leg_curve": 0.75,
        "saturation": 0.85, "lightness": 0.55,
        "top_back_coverage": 0.10, "fabric_sheen": 0.55,
    },
    "italian_luxe": {         # big prints + heavy metal
        "pattern": "floral", "pattern_scale": 0.75,
        "has_oring": 1.0, "oring_size": 0.75, "hardware_metal": "gold",
        "fabric_metallic": 0.25, "saturation": 0.78,
    },
    "japanese_minimal": {     # clean lines, muted, tiny hardware
        "pattern": "solid", "saturation": 0.25, "lightness": 0.70,
        "fabric_sheen": 0.35, "has_oring": 0.0, "has_bow": 0.0,
        "top_back_coverage": 0.30, "bot_front_leg_curve": 0.30,
    },
    "korean_feminine": {      # pastel + bows
        "pattern": "polka", "has_bow": 1.0, "bow_size": 0.55,
        "saturation": 0.35, "lightness": 0.82,
        "palette_preset": "transcendent_pink",
    },
    "scandi_minimal": {       # black-or-white matte
        "pattern": "solid", "saturation": 0.05, "lightness": 0.25,
        "fabric_sheen": 0.10, "fabric_source": "econyl",
        "has_oring": 0.0, "has_bow": 0.0, "has_fringe": 0.0,
    },
    "spanish_mediterranean": {  # crochet + earth + ruffle
        "fabric_weave": "crochet", "pattern": "solid",
        "hue": 0.08, "saturation": 0.55, "lightness": 0.55,
        "has_fringe": 1.0, "fringe_length": 0.55,
    },
    "american_sporty": {      # bold blocks, rash-guard
        "pattern": "solid", "top_back_coverage": 0.85,
        "top_shoulder_strap": 0.75, "bot_front_top_v": 0.55,
        "fabric_sheen": 0.20,
    },
    "boho_cultgaia": {        # crochet + shell + fringe
        "fabric_weave": "crochet", "has_shell": 1.0,
        "has_fringe": 1.0, "fringe_length": 0.75,
        "hue": 0.09, "saturation": 0.50, "lightness": 0.55,
        "has_beads": 1.0,
    },
    "retro_missoni": {        # chevron / zigzag
        "pattern": "chevron", "pattern_scale": 0.45,
        "fabric_weave": "shiny_knit", "fabric_sheen": 0.55,
    },
    "hunzag_crinkle": {       # Hunza G signature
        "fabric_weave": "crinkle", "fabric_weight": 0.35,
        "pattern": "solid", "saturation": 0.70,
    },
    "avantgarde_cutout": {    # editorial, high contrast
        "trim_color_mode": 0.95, "top_back_coverage": 0.25,
        "top_shoulder_strap": 0.05, "fabric_sheen": 0.85,
    },
    "sporty_chromat": {       # strap-heavy athletic
        "top_shoulder_strap": 0.90, "top_back_coverage": 0.70,
        "top_neck_strap": 0.60, "pattern": "solid",
    },
    "eres_architect": {       # molded cups, no hardware
        "has_oring": 0.0, "has_bow": 0.0, "has_fringe": 0.0,
        "has_beads": 0.0, "has_shell": 0.0,
        "pattern": "solid", "fabric_sheen": 0.35,
        "top_back_coverage": 0.55,
    },
}


# WGSN 2025 palette targets in HSL (each in [0,1]).
_PALETTE_TARGETS = {
    "future_dusk":          (0.69, 0.45, 0.32),  # dark blue-purple
    "transcendent_pink":    (0.97, 0.20, 0.85),  # near-neutral pale pink
    "aquatic_awe":          (0.53, 0.72, 0.42),  # deep ocean teal
    "ethereal_highlight":   (0.15, 0.22, 0.90),  # moonlit warm white
    "galactic_cobalt":      (0.62, 0.92, 0.32),  # saturated deep blue
    "sunset_peach":         (0.05, 0.65, 0.72),  # warm peach
}


# --------------------------------------------------------------------------
# Genome -> polygons in UV space
# --------------------------------------------------------------------------

def _cup_polygon(g: Genome, side: int) -> list[tuple[float, float]]:
    """One cup as a 4-point polygon with a concave top (V) and slight concave bottom.

    side: +1 = right (u > 0), -1 = left (u < 0).
    When top_inner_u is 0 the two cups touch in the middle -> effective bandeau.
    """
    cv = g.top_center_v
    hv = g.top_half_v
    hu = g.top_half_u
    inner_u = g.top_inner_u
    apex = g.top_apex_lift * 0.6
    dip = g.top_underband_dip * 0.3

    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)

    top_v_outer = cv + hv
    top_v_inner = cv + hv - apex        # V apex if apex>0
    bot_v_outer = cv - hv
    bot_v_inner = cv - hv + dip

    # traverse: inner-top -> outer-top -> outer-bottom -> inner-bottom
    return [
        (inner, top_v_inner),
        (outer, top_v_outer),
        (outer, bot_v_outer),
        (inner, bot_v_inner),
        (inner, top_v_inner),
    ]


def _back_top_polygons(g: Genome) -> list[list[tuple[float, float]]]:
    """Optional back band. Two separate strips (one on each seam), not a single
    polygon with a zero-area bridge — that would draw a hairline across."""
    if g.top_back_coverage < 0.05:
        return []
    cv = g.top_center_v
    band_h = 0.04 + 0.30 * g.top_back_coverage
    reach = 0.10 + 0.45 * g.top_back_coverage
    v0 = cv - band_h / 2
    v1 = cv + band_h / 2
    left = [(-1.0, v0), (-1.0 + reach, v0), (-1.0 + reach, v1), (-1.0, v1), (-1.0, v0)]
    right = [(1.0 - reach, v0), (1.0, v0), (1.0, v1), (1.0 - reach, v1), (1.0 - reach, v0)]
    return [left, right]


def _bottom_front_polygon(g: Genome) -> list[tuple[float, float]]:
    """Front panel of the bottom, centered on u=0."""
    top_v = g.bot_front_top_v
    hu = g.bot_front_half_u
    crotch_v = LANDMARKS_V["crotch"]
    leg = g.bot_front_leg_curve * 0.5
    return [
        (-hu, top_v),
        ( hu, top_v),
        ( hu * (1 - 0.5 * leg), (top_v + crotch_v) / 2),
        ( max(0.05, hu * 0.25), crotch_v),
        (-max(0.05, hu * 0.25), crotch_v),
        (-hu * (1 - 0.5 * leg), (top_v + crotch_v) / 2),
        (-hu, top_v),
    ]


def _bottom_back_polygons(g: Genome) -> list[list[tuple[float, float]]]:
    """Back panel as two strips on either side of the seam."""
    top_v = g.bot_back_top_v
    hu = g.bot_back_half_u
    crotch_v = LANDMARKS_V["crotch"]
    left = [
        (-1.0, top_v), (-1.0 + hu, top_v),
        (-1.0 + hu * 0.6, crotch_v), (-1.0, crotch_v), (-1.0, top_v),
    ]
    right = [
        (1.0 - hu, top_v), (1.0, top_v),
        (1.0, crotch_v), (1.0 - hu * 0.6, crotch_v), (1.0 - hu, top_v),
    ]
    return [left, right]


def _side_tie_polygons(g: Genome) -> list[list[tuple[float, float]]]:
    """Side connectors bridging front and back bottom panels at u = ±0.5.

    They must span the vertical range [min(front, back), max(front, back)] +
    a small safety margin so the two panels are actually joined into one
    waist loop (otherwise the bikini bottom is two disconnected flaps and
    can't physically stay on).
    """
    v_lo = min(g.bot_front_top_v, g.bot_back_top_v) - 0.03
    v_hi = max(g.bot_front_top_v, g.bot_back_top_v) + 0.01
    w = 0.06
    return [
        [(-0.5 - w, v_lo), (-0.5 + w, v_lo), (-0.5 + w, v_hi), (-0.5 - w, v_hi), (-0.5 - w, v_lo)],
        [( 0.5 - w, v_lo), ( 0.5 + w, v_lo), ( 0.5 + w, v_hi), ( 0.5 - w, v_hi), ( 0.5 - w, v_lo)],
    ]


def _center_gore_polygon(g: Genome) -> list[tuple[float, float]] | None:
    """Small bridge polygon between the two cups at the sternum. Without
    this a triangle-style top with top_inner_u > 0 leaves a visible gap
    between the cups that no real bikini has — real tops have either a
    center panel (gore), a ring, or a knot there.
    """
    if g.top_inner_u < 0.01:
        return None  # bandeau — cups already touch
    cv = g.top_center_v
    hv = g.top_half_v
    dip = g.top_underband_dip * 0.3
    apex = g.top_apex_lift * 0.6
    # gore is a rectangle mirroring the cups' inner edges: spans u=+/-inner_u
    # and vertically from the cup's inner-bottom up to the cup's inner-top
    u_w = g.top_inner_u
    v_bot = cv - hv + dip
    v_top = cv + hv - apex
    # pull the top of the gore down a bit so it reads as a narrow bridge,
    # not as a solid center panel spanning the full cup height
    v_top = max(v_bot + 0.02, v_top - 0.6 * (v_top - v_bot))
    return [
        (-u_w, v_bot), (u_w, v_bot), (u_w, v_top), (-u_w, v_top), (-u_w, v_bot),
    ]


def genome_polygons(g: Genome) -> list[list[tuple[float, float]]]:
    polys: list[list[tuple[float, float]]] = []
    polys.append(_cup_polygon(g,  1))
    polys.append(_cup_polygon(g, -1))
    gore = _center_gore_polygon(g)
    if gore is not None:
        polys.append(gore)
    polys.extend(_back_top_polygons(g))
    polys.append(_bottom_front_polygon(g))
    polys.extend(_bottom_back_polygons(g))
    polys.extend(_side_tie_polygons(g))
    return polys


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _color(g: Genome) -> tuple[float, float, float]:
    """Primary fabric color as an RGB tuple in [0,1]."""
    import colorsys
    l = 0.25 + 0.55 * g.lightness
    s = 0.25 + 0.65 * g.saturation
    return colorsys.hls_to_rgb(g.hue, l, s)


def _secondary_color(g: Genome) -> tuple[float, float, float]:
    """Secondary fabric color (for patterns needing two colors)."""
    import colorsys
    l = 0.20 + 0.60 * g.secondary_lightness
    s = 0.10 + 0.80 * g.secondary_saturation
    return colorsys.hls_to_rgb(g.secondary_hue, l, s)


def _trim_color(g: Genome) -> tuple[float, float, float]:
    """Binding color: from 'same as body darker' (trim_color_mode=0) to
    'strong contrast' (trim_color_mode=1), i.e., near black or near white
    depending on primary lightness."""
    import colorsys
    r, gg, b = _color(g)
    t = g.trim_color_mode
    if t < 0.5:
        k = 0.6 - 0.3 * (t / 0.5)  # 0.6..0.3, darker matching trim
        return (r * k, gg * k, b * k)
    else:
        # contrasting: pick near-white if primary is dark, near-black otherwise
        primary_l = (r + gg + b) / 3
        target = 0.05 if primary_l > 0.5 else 0.95
        mix = (t - 0.5) / 0.5
        return (r * (1 - mix) + target * mix,
                gg * (1 - mix) + target * mix,
                b * (1 - mix) + target * mix)


def _draw_uv_canvas(ax):
    """Paint skin tone + body landmark guide lines on a UV rectangle."""
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect("auto")
    # skin background
    ax.add_patch(Rectangle((-1, 0), 2, 1, facecolor="#f3d9c0", edgecolor="#9c7a5c",
                           linewidth=1.0, zorder=1))
    # horizontal landmark lines
    for name, v in LANDMARKS_V.items():
        ax.axhline(v, color="#b38c6e", linewidth=0.5, linestyle=":", zorder=1.5, alpha=0.7)
        ax.text(-1.04, v, name, fontsize=6, color="#8a6a50", va="center", ha="right")
    # vertical landmarks: back seam (u=±1), sides (u=±0.5), front center (u=0)
    for u, name in [(-1.0, "back"), (-0.5, "side"), (0.0, "front"), (0.5, "side"), (1.0, "back")]:
        ax.axvline(u, color="#b38c6e", linewidth=0.5, linestyle=":", zorder=1.5, alpha=0.6)
        ax.text(u, 1.04, name, fontsize=6, color="#8a6a50", ha="center")
    # privacy seeds: dashed outlines that all genome polygons must enclose
    for name, (u0, u1, v0, v1) in PRIVACY_SEEDS.items():
        ax.add_patch(Rectangle((u0, v0), u1 - u0, v1 - v0,
                               fill=False, edgecolor="#c0392b", linewidth=0.7,
                               linestyle="--", zorder=2.0))
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("left", "right", "top", "bottom"):
        ax.spines[side].set_visible(False)


def _fill_polygon(ax, verts, color, pattern, zorder=3):
    if len(verts) < 3:
        return
    patch = Polygon(verts, closed=True, facecolor=color, edgecolor="#222",
                    linewidth=0.6, zorder=zorder)
    ax.add_patch(patch)
    if pattern == "solid":
        return
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    overlay = (1.0, 1.0, 1.0, 0.55)
    if pattern == "stripe":
        n = 7
        for i in range(n):
            y = y0 + (i + 0.5) * (y1 - y0) / n
            h = (y1 - y0) / (n * 2.4)
            r = Rectangle((x0, y - h / 2), x1 - x0, h, facecolor=overlay,
                          edgecolor=None, zorder=zorder + 0.1)
            r.set_clip_path(patch)
            ax.add_patch(r)
    elif pattern == "polka":
        rng = np.random.default_rng(0)
        for _ in range(20):
            cx = rng.uniform(x0, x1)
            cy = rng.uniform(y0, y1)
            dot = plt.Circle((cx, cy), 0.012, facecolor=overlay, zorder=zorder + 0.1)
            dot.set_clip_path(patch)
            ax.add_patch(dot)
    elif pattern == "checker":
        n = 8
        dx = (x1 - x0) / n
        dy = (y1 - y0) / n
        for i in range(n):
            for j in range(n):
                if (i + j) % 2 == 0:
                    r = Rectangle((x0 + i * dx, y0 + j * dy), dx, dy,
                                  facecolor=overlay, edgecolor=None, zorder=zorder + 0.1)
                    r.set_clip_path(patch)
                    ax.add_patch(r)
    else:
        # Batch 1 new patterns (gingham/chevron/floral/tropical/leopard/
        # tie_dye/ombre/herringbone): the 2D verifier shows just a subtle
        # crosshatch so the patch is distinguishable from solid. The full
        # pattern art is rendered in the 3D texture path.
        n = 10
        for i in range(n):
            y = y0 + (i + 0.5) * (y1 - y0) / n
            h = (y1 - y0) / (n * 3)
            r = Rectangle((x0, y - h / 2), x1 - x0, h,
                          facecolor=(1, 1, 1, 0.30),
                          edgecolor=None, zorder=zorder + 0.1)
            r.set_clip_path(patch)
            ax.add_patch(r)


def render_one(ax, g: Genome, title: str):
    _draw_uv_canvas(ax)
    color = _color(g)
    for poly in genome_polygons(g):
        _fill_polygon(ax, poly, color, g.pattern, zorder=3)
    ax.set_title(title, fontsize=9)


# --------------------------------------------------------------------------
# Parents + pipeline
# --------------------------------------------------------------------------

def make_parents() -> tuple[Genome, Genome]:
    # Parent A: triangle top + thong + shoulder straps + long hip dangles,
    # matte rayon-ish virgin fabric, solid scarlet with sunset_peach palette.
    a = Genome(
        pattern="solid",
        top_center_v=0.76, top_half_v=0.09, top_half_u=0.18,
        top_inner_u=0.12, top_apex_lift=0.10, top_underband_dip=0.08,
        top_back_coverage=0.12,
        top_neck_strap=0.0, top_shoulder_strap=0.85,
        bot_front_top_v=0.22, bot_front_half_u=0.25, bot_front_leg_curve=0.60,
        bot_back_top_v=0.20, bot_back_half_u=0.12,
        bot_tie_dangle=0.75,
        hue=0.97, saturation=0.75, lightness=0.55,
        secondary_hue=0.12, secondary_saturation=0.5, secondary_lightness=0.85,
        pattern_scale=0.5, pattern_angle=0.0, trim_color_mode=0.2,
        fabric_sheen=0.25, fabric_metallic=0.0,
        fabric_opacity=1.0, fabric_weight=0.45,
        fabric_weave="plain",
        palette_preset="sunset_peach",
        fabric_source="econyl",
        biodegradable=0.0, single_material=1.0,
        has_oring=1.0, oring_size=0.6,
        has_bow=0.0, bow_size=0.3,
        has_fringe=1.0, fringe_length=0.45,
        has_beads=0.0, has_shell=0.0,
        style_archetype="brazilian",
        hardware_metal="gold",
    )
    # Parent B: halter bandeau + high-waist + no dangles + classic blue
    # stripe, satin-y recycled nylon, "aquatic awe" WGSN palette.
    b = Genome(
        pattern="stripe",
        top_center_v=0.74, top_half_v=0.08, top_half_u=0.45,
        top_inner_u=0.0,  top_apex_lift=-0.03, top_underband_dip=0.02,
        top_back_coverage=0.55,
        top_neck_strap=0.80, top_shoulder_strap=0.0,
        bot_front_top_v=0.42, bot_front_half_u=0.55, bot_front_leg_curve=0.20,
        bot_back_top_v=0.42, bot_back_half_u=0.55,
        bot_tie_dangle=0.05,
        hue=0.57, saturation=0.85, lightness=0.50,
        secondary_hue=0.15, secondary_saturation=0.05, secondary_lightness=0.95,
        pattern_scale=0.4, pattern_angle=0.0, trim_color_mode=0.8,
        fabric_sheen=0.7, fabric_metallic=0.05,
        fabric_opacity=1.0, fabric_weight=0.55,
        fabric_weave="plain",
        palette_preset="aquatic_awe",
        fabric_source="qnova",
        biodegradable=1.0, single_material=1.0,
        has_oring=0.0, oring_size=0.4,
        has_bow=1.0, bow_size=0.55,
        has_fringe=0.0, fringe_length=0.2,
        has_beads=1.0, has_shell=0.0,
        style_archetype="retro_missoni",
        hardware_metal="pearl",
    )
    return _enforce_constraints(a.clipped()), _enforce_constraints(b.clipped())


def run_ga(a: Genome, b: Genome, n: int, rng: random.Random) -> list[Genome]:
    return [mutate(crossover(a, b, rng), rng) for _ in range(n)]


def save_figure(parents, offspring, out_path: str):
    n = len(offspring)
    cols = 5
    rows = (2 + n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.8, rows * 2.2), facecolor="white")
    axes = np.array(axes).reshape(-1)
    render_one(axes[0], parents[0], "Parent A")
    render_one(axes[1], parents[1], "Parent B")
    for i, child in enumerate(offspring):
        render_one(axes[2 + i], child, f"Child {i + 1}")
    for j in range(2 + n, len(axes)):
        axes[j].axis("off")
    fig.suptitle("Bikini GA on UV-unwrapped torso (u: back-front-back, v: hip-neck)",
                 fontsize=11, y=0.995)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def dump_genomes(parents, offspring, out_path):
    payload = {
        "seed": SEED,
        "representation": "uv_unwrap",
        "u_range": [-1.0, 1.0],
        "v_range": [0.0, 1.0],
        "landmarks_v": LANDMARKS_V,
        "blx_alpha": BLX_ALPHA,
        "mut_sigma": MUT_SIGMA,
        "mut_prob_cat": MUT_PROB_CAT,
        "parent_a": parents[0].as_dict(),
        "parent_b": parents[1].as_dict(),
        "offspring": [g.as_dict() for g in offspring],
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = random.Random(SEED)
    parents = make_parents()
    offspring = run_ga(parents[0], parents[1], N_OFFSPRING, rng)
    png = os.path.join(OUT_DIR, "ga_verification_uv.png")
    js  = os.path.join(OUT_DIR, "ga_verification_uv.json")
    save_figure(parents, offspring, png)
    dump_genomes(parents, offspring, js)
    print(f"wrote {png}")
    print(f"wrote {js}")


if __name__ == "__main__":
    main()
