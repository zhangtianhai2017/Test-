"""
Outfit-native fitness — v2 fitness layer that scores Outfits using
library metadata directly (no Genome projection).

Why this exists
---------------
v1 `tools/fitness.py` operates on Genome (44-dim continuous floats).
The v2 GA in `tools/iter/outfit_ga.py` currently scores by going through
`outfit_to_genome(outfit)` then v1 `fitness.evaluate` — a lossy detour
that drops everything Genome can't carry: which library_id was picked,
compatible_with chain density, anatomy_hints completeness, body_jewelry
anchor variety, etc.

This module adds 6 outfit-native scoring axes that read library metadata
straight from the LibraryEntry objects, then provides `outfit_evaluate`
which combines outfit-native + v1 aesthetic + v1 manufacturing into one
composite. The composite is what the v2 GA selects on.

Outfit-native axes (all in [0, 1]):
  slot_richness          — optional slots filled in healthy range
                            (too few = bare, too many = overstuffed)
  library_diversity      — distinct library_ids per total slot count
                            (penalises duplicate body_jewelry choices etc.)
  compatibility_strength — fraction of slot pairs with explicit
                            compatible_with crosswalks (denser = more
                            "real kit" not random catalog grab)
  anatomy_coverage       — for outfits with body_jewelry / accessory:
                            distinct anatomy_anchors (variety; one bracelet
                            + one necklace > two bracelets on same wrist)
  palette_coherence      — global_design hue/sat sanity (no clashing,
                            extreme spreads penalised; presets get bonus)
  manufacturing_realism  — seam type / fabric count plausibility
                            (real garments use 2-4 seam types not 8)

Composite weighting:
  overall = 0.40 aesthetic   (v1 PRINCIPLE_KEYS via outfit_to_genome)
          + 0.25 manufacturing (v1 GARMENT_SCORE_KEYS)
          + 0.35 outfit_native (6 keys above)
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from outfit import Outfit


OUTFIT_SCORE_KEYS = (
    "slot_richness",
    "library_diversity",
    "compatibility_strength",
    "anatomy_coverage",
    "palette_coherence",
    "manufacturing_realism",
)


# ---------------------------------------------------------------------------
# Outfit-native scoring axes
# ---------------------------------------------------------------------------

def _slot_richness(outfit, slot_specs) -> float:
    """Reward outfits that fill optional slots in the healthy 40-70%
    range. <30% feels bare; >85% feels overstuffed (too many accessories /
    body jewelry stacked on top)."""
    optional_specs = [s for s in slot_specs if not s.required]
    if not optional_specs:
        return 1.0
    filled = {a.slot_name for a in outfit.slot_assignments}
    optional_filled = sum(1 for s in optional_specs if s.name in filled)
    frac = optional_filled / len(optional_specs)
    # Triangular kernel peaked at 0.55, falls off to 0 at 0.0 and 1.0
    if frac <= 0.55:
        return frac / 0.55
    return max(0.0, 1.0 - (frac - 0.55) / 0.45)


def _library_diversity(outfit) -> float:
    """Distinct library_ids divided by total slot count. Two body_jewelry
    slots both pointing at BJ_BRACELET_CHAIN drop the score."""
    if not outfit.slot_assignments:
        return 0.0
    n = len(outfit.slot_assignments)
    distinct = len({a.library_id for a in outfit.slot_assignments})
    return distinct / n


def _compatibility_strength(outfit, library) -> float:
    """Density of explicit compatible_with crosswalks. For each slot
    assignment, check how many of its `compatible_with` ids are present
    in the same outfit. Score = (matched / total declared) averaged
    across assignments that declare any compatibility."""
    matches, declared = 0, 0
    selected = {a.library_id for a in outfit.slot_assignments}
    for a in outfit.slot_assignments:
        entry = library.get(a.library_id)
        if entry is None or not entry.compatible_with:
            continue
        for partner in entry.compatible_with:
            declared += 1
            if partner in selected:
                matches += 1
    if declared == 0:
        # No explicit compatibility declared anywhere — neutral score,
        # not a penalty (most slots simply don't constrain partners).
        return 0.7
    # Saturation: 0/declared → 0.5 (fine, just no extra credit),
    # all matched → 1.0. Linear in the fraction.
    return 0.5 + 0.5 * (matches / declared)


def _anatomy_coverage(outfit, library) -> float:
    """For body_jewelry + accessory slots, score by distinct anatomy
    anchors used. One choker + one bracelet (neck + wrist) > two
    bracelets (both wrist). Outfits with no body jewelry / accessories
    get neutral 0.7 (not a penalty for restrained looks)."""
    decorative = []
    for a in outfit.slot_assignments:
        entry = library.get(a.library_id)
        if entry is None:
            continue
        if entry.kind in ("body_jewelry", "accessory"):
            decorative.append(entry)
    if not decorative:
        return 0.7
    anchors = set()
    for e in decorative:
        # anatomy_hints may be a dict {"anchor": "wrist_R"} or list of those
        hints = e.anatomy_hints or {}
        if isinstance(hints, dict):
            anc = hints.get("anchor") or hints.get("anchors")
            if isinstance(anc, str):
                anchors.add(anc)
            elif isinstance(anc, (list, tuple)):
                anchors.update(anc)
        elif isinstance(hints, (list, tuple)):
            for h in hints:
                if isinstance(h, dict):
                    anc = h.get("anchor")
                    if anc:
                        anchors.add(anc)
    n_decorative = len(decorative)
    n_anchors = max(1, len(anchors))
    # 1 anchor for 1 piece is fine; 1 anchor for 3 pieces is bad
    return min(1.0, n_anchors / n_decorative)


def _palette_coherence(outfit) -> float:
    """global_design HSL sanity. Two-color outfits with hues 30°-150°
    apart are pleasing; 180° complementary is bold but high score;
    near-clashing 25° gets penalised. Single-hue outfits get 0.85
    (clean but unsurprising)."""
    gd = outfit.global_design or {}
    h1 = gd.get("hue")
    h2 = gd.get("secondary_hue")
    if h1 is None:
        return 0.7
    # Palette preset overrides — designed combinations get a flat bonus
    if gd.get("palette_preset"):
        return 0.92
    if h2 is None:
        return 0.85
    diff = abs((h1 - h2) % 1.0)
    diff = min(diff, 1.0 - diff)  # 0..0.5 (i.e. 0..180°)
    # 0..15° = clashing-close, penalised
    # 15..50° = analogous, good
    # 50..85° = triadic, very good
    # 85..125° = complementary-ish, very good
    deg = diff * 360.0
    if deg < 15:
        return 0.45
    if deg < 50:
        return 0.85
    if deg < 125:
        return 0.95
    return 0.80


def _manufacturing_realism(outfit, library) -> float:
    """Real production garments use 2-4 distinct fabric SKUs and 1-3
    seam types. Penalise outfits that exceed these typical bounds."""
    fab_ids, seam_ids, hardware_ids = set(), set(), set()
    for a in outfit.slot_assignments:
        entry = library.get(a.library_id)
        if entry is None:
            continue
        if entry.kind == "fabric":
            fab_ids.add(entry.id)
        elif entry.kind == "seam_type":
            seam_ids.add(entry.id)
        elif entry.kind == "hardware":
            hardware_ids.add(entry.id)

    score = 1.0
    # fabric SKUs: ideal 1-3, soft penalty for 4+
    n_fab = len(fab_ids)
    if n_fab > 3:
        score -= 0.15 * (n_fab - 3)
    # seam types: ideal ≤ 3 (most bikinis 2)
    n_seam = len(seam_ids)
    if n_seam > 3:
        score -= 0.10 * (n_seam - 3)
    # hardware: 0-2 is normal, 3+ starts looking like a junk drawer
    n_hw = len(hardware_ids)
    if n_hw > 2:
        score -= 0.10 * (n_hw - 2)

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def outfit_scores(outfit) -> dict:
    """Outfit-native axes only. Pure-Python, ms-fast, no rendering."""
    from library import ARCHETYPE_SLOTS
    from library_data import LIBRARY

    slot_specs = ARCHETYPE_SLOTS.get(outfit.archetype, [])
    return {
        "slot_richness":          _slot_richness(outfit, slot_specs),
        "library_diversity":      _library_diversity(outfit),
        "compatibility_strength": _compatibility_strength(outfit, LIBRARY),
        "anatomy_coverage":       _anatomy_coverage(outfit, LIBRARY),
        "palette_coherence":      _palette_coherence(outfit),
        "manufacturing_realism":  _manufacturing_realism(outfit, LIBRARY),
    }


def outfit_evaluate(outfit) -> dict:
    """Full v2 fitness — outfit-native + v1 aesthetic + v1 manufacturing.

    Returns all individual axes plus three roll-ups:
      overall_outfit  — mean of OUTFIT_SCORE_KEYS only
      overall_v1      — v1 evaluate(outfit_to_genome(outfit))['overall']
      overall         — composite (the number GA selects on)
    """
    import fitness as fitness_mod
    from outfit import outfit_to_genome

    out = dict(outfit_scores(outfit))
    out["overall_outfit"] = sum(out[k] for k in OUTFIT_SCORE_KEYS) / len(OUTFIT_SCORE_KEYS)

    v1 = fitness_mod.evaluate(outfit_to_genome(outfit))
    for k in fitness_mod.PRINCIPLE_KEYS + fitness_mod.GARMENT_SCORE_KEYS:
        out[k] = v1[k]
    out["overall_v1"] = v1["overall"]

    aesthetic = sum(v1[k] for k in fitness_mod.PRINCIPLE_KEYS) / len(fitness_mod.PRINCIPLE_KEYS)
    manufacturing = sum(v1[k] for k in fitness_mod.GARMENT_SCORE_KEYS) / len(fitness_mod.GARMENT_SCORE_KEYS)
    out["overall"] = 0.40 * aesthetic + 0.25 * manufacturing + 0.35 * out["overall_outfit"]
    return out


if __name__ == "__main__":
    import sys, os, random
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from outfit import random_outfit

    rng = random.Random(0)
    for archetype in ("triangle_string_halter", "bandeau_back_band",
                      "bralette_shoulder_strap", "one_piece_maillot"):
        o = random_outfit(archetype, rng)
        s = outfit_evaluate(o)
        print(f"{archetype:28s}  outfit={s['overall_outfit']:.3f}  "
              f"v1={s['overall_v1']:.3f}  composite={s['overall']:.3f}")
        for k in OUTFIT_SCORE_KEYS:
            print(f"    {k:24s} {s[k]:.3f}")
