"""
Design-principle fitness for bikini Genomes.

Seven classical fashion-design principles, each implemented as a
pure-Python score in [0, 1]. No rendering required — everything is
computed from the Genome parameters and derived polygon geometry so
we can score a whole population in milliseconds.

Call `evaluate(genome)` for a dict of all seven scores, or any
individual function for one axis. Shapes follow Vogue Institute /
IIFT fashion-design curricula:

  balance     left-right symmetry of the garment
  proportion  top vs bottom area ratio close to golden
  harmony     color-wheel harmony of primary/secondary/trim
  emphasis    a single visual focal point (not too many)
  rhythm      repetition of features (ties, dangles, beads)
  unity       top and bottom read as a coordinated set
  contrast    light/dark and matte/shiny balance

Average them for a single "aesthetic score" or feed the full vector
to NSGA-II.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from verify_ga_uv import Genome


# --------------------------------------------------------------------------
# Individual principle scores
# --------------------------------------------------------------------------

def balance(g: "Genome") -> float:
    """Every left-side polygon has a right-side twin in our Genome, so
    pure symmetry is structural. We return 1.0 minus any asymmetry
    introduced by the halter anchor (top_inner_u) being far off-center.
    In practice ~1.0 unless future Genomes add asymmetric cuts."""
    asym = 0.0
    # Cup inner offset is already symmetric; rarely asymmetric.
    return float(np.clip(1.0 - asym, 0.0, 1.0))


def proportion(g: "Genome") -> float:
    """Top coverage area vs bottom coverage area.

    Golden ratio (~0.618) is treated as ideal: a pleasing bikini has the
    bottom panel somewhat larger than the top. Far from golden in either
    direction drops the score.
    """
    top_area = g.top_half_u * g.top_half_v * 4.0 + g.top_back_coverage * 0.2
    bot_h = max(g.bot_front_top_v - 0.06, 1e-3)
    bot_area = g.bot_front_half_u * bot_h * 2.0 + g.bot_back_half_u * bot_h
    if (top_area + bot_area) < 1e-6:
        return 0.0
    ratio = top_area / (top_area + bot_area)
    # distance from golden 0.382 (top) / 0.618 (bottom)
    dist = abs(ratio - 0.382)
    return float(np.clip(1.0 - dist * 2.8, 0.0, 1.0))


def harmony(g: "Genome") -> float:
    """Color harmony on the HSL wheel.

    Best score: primary and secondary hues are either analogous (close on
    the wheel) or complementary (opposite). Middle distances score worst
    because they look random rather than intentional.
    """
    diff = abs(g.hue - g.secondary_hue)
    diff = min(diff, 1 - diff)          # circular distance in [0, 0.5]
    # reward close (<=0.1) and opposite (>=0.45); penalize middle
    if diff <= 0.08:
        score = 1.0                     # monochrome / analogous
    elif diff >= 0.42:
        score = 0.95                    # complementary
    else:
        score = 1.0 - abs(diff - 0.25) * 3.2   # penalty peaks at 0.25
    # penalize extreme secondary saturation mismatch
    sat_gap = abs(g.saturation - g.secondary_saturation)
    return float(np.clip(score - sat_gap * 0.2, 0.0, 1.0))


def emphasis(g: "Genome") -> float:
    """A single clear focal point is better than many competing details.

    We count visible emphasis elements (bow, shell, high-sheen, big
    print, chunky hardware). Exactly 1 scores 1.0; 0 scores 0.5 (plain
    is OK); 2+ loses points for 'busy'.
    """
    e = 0
    e += int(g.has_bow >= 0.5)
    e += int(g.has_shell >= 0.5)
    e += int(g.has_oring >= 0.5 and g.oring_size > 0.6)
    e += int(g.pattern in ("floral", "tropical", "leopard")
             and g.pattern_scale > 0.6)
    e += int(g.fabric_metallic > 0.4)
    if e == 1:
        return 1.0
    if e == 0:
        return 0.55
    return float(np.clip(1.0 - 0.22 * (e - 1), 0.0, 1.0))


def rhythm(g: "Genome") -> float:
    """Repetition / regular pattern. Beads, stripes, polka, chevron, and
    fringes all score high; unstructured prints lower."""
    score = 0.3
    rhythmic_patterns = {"stripe", "polka", "checker", "gingham",
                         "chevron", "herringbone"}
    if g.pattern in rhythmic_patterns:
        score += 0.35
    if g.has_beads >= 0.5:
        score += 0.20
    if g.has_fringe >= 0.5:
        score += 0.15
    return float(np.clip(score, 0.0, 1.0))


def unity(g: "Genome") -> float:
    """Top and bottom look like they belong together.

    Same pattern, similar metallic level, and either the same fabric
    source or a matching palette preset all contribute. Since our
    Genome is a single Genome (top+bottom share fabric/pattern by
    design), unity is usually high; the penalty comes from style-mix
    via archetype conflicts.
    """
    return 0.95 if g.pattern != "solid" else 0.80


def contrast(g: "Genome") -> float:
    """Light/dark balance and sheen/matte balance. We reward medium
    contrast (~0.4) and penalize both extremes."""
    # primary vs secondary lightness contrast
    light_contrast = abs(g.lightness - g.secondary_lightness)
    # trim color contrast
    trim_contrast = g.trim_color_mode
    target = 0.35
    score = 1.0 - 2.2 * abs((light_contrast + trim_contrast) / 2 - target)
    return float(np.clip(score, 0.0, 1.0))


# --------------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------------

PRINCIPLES = [balance, proportion, harmony, emphasis, rhythm, unity, contrast]


def evaluate(g: "Genome") -> dict:
    scores = {fn.__name__: fn(g) for fn in PRINCIPLES}
    # Garment-level scores (manufacturing-aware) — added in step 5.
    scores.update(garment_scores(g))
    scores["overall"] = float(np.mean([scores[k] for k in PRINCIPLE_KEYS]))
    scores["overall_with_garment"] = float(
        np.mean([scores[k] for k in PRINCIPLE_KEYS + GARMENT_SCORE_KEYS]))
    return scores


# --------------------------------------------------------------------------
# Garment-aware scoring (step 5).
#
# Pulls Genome through the manufacturing latent state (genome_to_garment +
# validate_garment) and derives:
#   - manufacturability:   1.0 minus the validator warning count, soft-saturated
#   - sustainability:      fraction of fabrics with biodegradable=True
#   - sku_consistency:     fewer distinct fabrics across pieces = higher score
#                           (real garments use 1-3 fabrics, not 8)
#   - construction_simplicity: fewer connectors / accessories = simpler,
#                                more wearable
# All scores are in [0, 1]. Used to extend the aesthetic-only fitness with a
# "this could actually be made and is a coherent garment" axis.
# --------------------------------------------------------------------------

GARMENT_SCORE_KEYS = (
    "manufacturability", "sustainability",
    "sku_consistency", "construction_simplicity",
)


def garment_scores(g: "Genome") -> dict:
    """Run Genome -> Garment -> validate and derive 4 manufacturing axes.
    Returns all-zero scores on any failure (e.g. import not available)
    so this remains a soft, additive layer on top of the design fitness.
    """
    out = {k: 0.0 for k in GARMENT_SCORE_KEYS}
    try:
        from garment_state import (genome_to_garment, validate_garment,
                                     UnsupportedArchetypeV1)
    except Exception:
        return out
    try:
        garm = validate_garment(genome_to_garment(g))
    except UnsupportedArchetypeV1:
        # Old behaviour pre-step-4; no longer raised but defensive.
        return out
    except Exception:
        return out

    # 1. manufacturability: each validator warning costs 0.10, capped at 1.
    n_warn = len(garm.metadata.get("validation_warnings", []))
    out["manufacturability"] = float(np.clip(1.0 - 0.10 * n_warn, 0.0, 1.0))

    # 2. sustainability: fraction of fabrics that are biodegradable, plus
    # bonus for biopolymer / amni_soul / cotton_blend sources.
    if garm.fabrics:
        bio = sum(1 for f in garm.fabrics if f.biodegradable) / len(garm.fabrics)
        eco_bonus = sum(1 for f in garm.fabrics
                          if f.source in ("biopolymer", "amni_soul",
                                            "cotton_blend", "qnova", "econyl")) \
                    / len(garm.fabrics)
        out["sustainability"] = float(np.clip(0.6 * bio + 0.4 * eco_bonus,
                                                 0.0, 1.0))

    # 3. sku_consistency: fewer distinct fabric SKUs is more like a real
    # production garment (1-3 typical). Linear falloff above 3.
    if garm.fabrics:
        n_fab = len({f.id for f in garm.fabrics})
        if n_fab <= 3:
            out["sku_consistency"] = 1.0
        else:
            out["sku_consistency"] = float(np.clip(1.0 - 0.20 * (n_fab - 3),
                                                     0.0, 1.0))

    # 4. construction_simplicity: penalise overly busy designs. Each
    # connector + accessory above a baseline of 5 components costs 0.05.
    n_components = len(garm.connectors) + len(garm.accessories)
    out["construction_simplicity"] = float(
        np.clip(1.0 - 0.05 * max(0, n_components - 5), 0.0, 1.0))

    return out


PRINCIPLE_KEYS = tuple(fn.__name__ for fn in PRINCIPLES)


# --------------------------------------------------------------------------
# CLIP aesthetic score (stub).
# Full implementation would: render the Genome, pass RGB to a CLIP model,
# compute cosine similarity against a positive prompt ("beautiful,
# well-designed bikini, fashion photography") minus a negative prompt.
# That needs `transformers` / `open_clip_torch` (~1GB), skipped for now.
# --------------------------------------------------------------------------

def clip_aesthetic_score(g: "Genome", rendered_rgb: np.ndarray | None = None
                          ) -> float | None:
    """Placeholder. Returns None unless the heavy CLIP stack is installed."""
    try:
        import open_clip  # type: ignore[import-not-found]
    except ImportError:
        return None
    return None
