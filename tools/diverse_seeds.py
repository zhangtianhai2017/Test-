"""
Autonomous diverse-seed synthesizer.

Stratified random sampling across the 4 v1 archetypes (each gets a
guaranteed slot); within each archetype the discrete + continuous
Genome fields are sampled to spread coverage. Each candidate runs
through validate_garment + fitness. We keep the highest-fitness
candidates per archetype, with a greedy farthest-point selection over
the discrete-enum space so the final 20 seeds aren't 20 minor
variations of one config.

Why this exists: prior seed sources were either (a) hand-authored from
real swimsuit photos, or (b) hand-authored gallery variants by the
operator. Both are bottlenecks on the operator's imagination. This
script samples from a much wider Genome distribution and uses fitness +
diversity criteria to pick the survivors.
"""
from __future__ import annotations

import argparse, json, os, random, sys
from dataclasses import asdict
from typing import Any

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verify_ga_uv import (
    Genome, _enforce_constraints, CONT_FIELDS, _DISCRETE_ENUMS,
    PATTERNS, FABRIC_WEAVES, PALETTE_PRESETS, FABRIC_SOURCES,
    STYLE_ARCHETYPES, HARDWARE_METALS,
)
from garment_state import (genome_to_garment, validate_garment,
                              UnsupportedArchetypeV1)
import fitness as fitness_mod


SEEDS_DIR = "assets/seeds"


# Archetype templates: required fields that force the dispatcher into
# the desired branch. All other fields are randomized.
ARCHETYPE_TEMPLATES = {
    "triangle_string_halter": {
        "top_neck_strap":     ("uniform", 0.55, 0.95),
        "top_inner_u":        ("uniform", 0.06, 0.16),
        "top_shoulder_strap": ("uniform", 0.0, 0.20),
        "top_back_coverage":  ("uniform", 0.02, 0.20),
    },
    "bandeau_back_band": {
        "top_neck_strap":     ("uniform", 0.0, 0.15),
        "top_shoulder_strap": ("uniform", 0.0, 0.20),
        "top_inner_u":        ("uniform", 0.0, 0.04),
        "top_half_u":         ("uniform", 0.18, 0.24),
        "top_back_coverage":  ("uniform", 0.40, 0.70),
    },
    "bralette_shoulder_strap": {
        "top_shoulder_strap": ("uniform", 0.6, 0.95),
        "top_neck_strap":     ("uniform", 0.0, 0.15),
        "top_inner_u":        ("uniform", 0.04, 0.14),
        "top_back_coverage":  ("uniform", 0.30, 0.60),
    },
    "one_piece_maillot": {
        "top_back_coverage":  ("uniform", 0.80, 1.00),
        "top_shoulder_strap": ("uniform", 0.0, 0.95),  # halter or shoulder
        "top_neck_strap":     ("uniform", 0.0, 0.85),
        "bot_front_top_v":    ("uniform", 0.55, 0.70),
        "bot_front_half_u":   ("uniform", 0.18, 0.24),
    },
}


def _random_genome(rng: random.Random, archetype_template: dict) -> Genome:
    """Sample one Genome by mixing template constraints + uniform random
    over remaining fields."""
    d: dict[str, Any] = {}

    # Continuous fields: uniform [0, 1] unless overridden.
    for k in CONT_FIELDS:
        if k in archetype_template:
            kind, lo, hi = archetype_template[k]
            d[k] = rng.uniform(lo, hi)
        else:
            d[k] = rng.uniform(0.0, 1.0)

    # Special-case Genome fields with non-uniform priors:
    #   - lightness: keep in [0.15, 0.95] so colors aren't pure black/white
    #     except by explicit choice
    #   - saturation: bimodal — half the time near [0.05] (neutral),
    #     half [0.45, 0.85] (saturated)
    if rng.random() < 0.30:
        d["saturation"] = rng.uniform(0.0, 0.15)         # near-neutral
    else:
        d["saturation"] = rng.uniform(0.45, 0.85)        # saturated

    # Hardware bools: 30% chance each, except has_oring 50% chance
    d["has_oring"]   = 1.0 if rng.random() < 0.50 else 0.0
    d["has_bow"]     = 1.0 if rng.random() < 0.30 else 0.0
    d["has_fringe"]  = 1.0 if rng.random() < 0.25 else 0.0
    d["has_beads"]   = 1.0 if rng.random() < 0.25 else 0.0
    d["has_shell"]   = 1.0 if rng.random() < 0.20 else 0.0
    d["biodegradable"]   = 1.0 if rng.random() < 0.40 else 0.0
    d["single_material"] = 1.0 if rng.random() < 0.70 else 0.0

    # Discrete fields: weighted random
    d["pattern"] = rng.choice(PATTERNS)
    d["fabric_weave"] = rng.choice(FABRIC_WEAVES)
    d["palette_preset"] = rng.choice(PALETTE_PRESETS)
    d["fabric_source"] = rng.choice(FABRIC_SOURCES)
    d["style_archetype"] = rng.choice(STYLE_ARCHETYPES)
    d["hardware_metal"] = rng.choice(HARDWARE_METALS) if d["has_oring"] > 0.5 else "none"

    # Build + clip + enforce privacy / topology constraints
    g = Genome(**d).clipped()
    return _enforce_constraints(g)


def _discrete_signature(g: Genome) -> tuple:
    """A short discrete fingerprint used by the diversity selector.
    Two seeds with the same signature are essentially the same archetype
    + same fabric + same pattern."""
    return (g.style_archetype, g.pattern, g.fabric_weave,
            g.fabric_source, g.palette_preset,
            int(g.has_oring > 0.5), int(g.has_bow > 0.5),
            int(g.has_fringe > 0.5), int(g.has_beads > 0.5),
            int(g.has_shell > 0.5))


def _hue_bucket(hue: float, n: int = 6) -> int:
    return int(hue * n) % n


def _diversity_pick(candidates: list[tuple[Genome, dict]],
                    target_count: int) -> list[tuple[Genome, dict]]:
    """Greedy farthest-point selection. Start with the highest-fitness
    candidate; each subsequent pick maximizes minimum (Hamming + hue
    bucket) distance to the already-selected set."""
    if not candidates:
        return []
    sorted_cand = sorted(candidates, key=lambda x: -x[1]["overall_with_garment"])
    chosen = [sorted_cand[0]]
    sigs = [_discrete_signature(sorted_cand[0][0])]
    hues = [_hue_bucket(sorted_cand[0][0].hue)]

    while len(chosen) < target_count and len(chosen) < len(sorted_cand):
        best_idx, best_dist = -1, -1
        for i, (g, fit) in enumerate(sorted_cand):
            if (g, fit) in chosen:
                continue
            sig = _discrete_signature(g)
            hue_b = _hue_bucket(g.hue)
            min_dist = 999
            for s, h in zip(sigs, hues):
                hamming = sum(1 for a, b in zip(sig, s) if a != b)
                hue_pen = 0 if hue_b == h else 1
                d = hamming + hue_pen + 0.4 * fit["overall_with_garment"]
                min_dist = min(min_dist, d)
            if min_dist > best_dist:
                best_dist = min_dist
                best_idx = i
        if best_idx < 0:
            break
        g, fit = sorted_cand[best_idx]
        chosen.append((g, fit))
        sigs.append(_discrete_signature(g))
        hues.append(_hue_bucket(g.hue))
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=100,
                    help="candidate count per archetype")
    ap.add_argument("--keep", type=int, default=5,
                    help="diverse seeds to keep per archetype")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed")
    ap.add_argument("--write", action="store_true",
                    help="write JSON seed files for the diverse picks")
    ap.add_argument("--floor", type=float, default=0.55,
                    help="minimum overall fitness for a candidate to qualify")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    archetype_classes = list(ARCHETYPE_TEMPLATES.keys())
    print(f"sampling {args.samples} per archetype, keeping top {args.keep} "
          f"diverse per archetype, floor overall >= {args.floor}")
    print()

    chosen_all: list[tuple[Genome, dict, str]] = []
    for arch_name in archetype_classes:
        template = ARCHETYPE_TEMPLATES[arch_name]
        kept_candidates: list[tuple[Genome, dict]] = []
        for i in range(args.samples):
            g = _random_genome(rng, template)
            try:
                garm = validate_garment(genome_to_garment(g))
            except UnsupportedArchetypeV1:
                continue
            except Exception:
                continue
            if garm.archetype != arch_name:
                # dispatcher sent it elsewhere; skip
                continue
            fit = fitness_mod.evaluate(g)
            if fit["overall"] < args.floor:
                continue
            kept_candidates.append((g, fit))

        diverse = _diversity_pick(kept_candidates, args.keep)
        print(f"  {arch_name:24s} candidates={len(kept_candidates):>4} "
              f"-> picked {len(diverse)} diverse")
        for g, fit in diverse:
            chosen_all.append((g, fit, arch_name))

    print(f"\nfinal: {len(chosen_all)} diverse seeds")
    print(f"\n{'name':40s} {'archetype':24s} {'overall':>7s} {'+garm':>6s} "
          f"{'pattern':12s} {'fabric_src':14s} {'arch_style':18s}")

    if args.write:
        os.makedirs(SEEDS_DIR, exist_ok=True)

    for i, (g, fit, arch) in enumerate(chosen_all):
        name = f"diverse_{arch.split('_')[0]}_{i:02d}"
        print(f"{name:40s} {arch:24s} {fit['overall']:>7.3f} "
              f"{fit['overall_with_garment']:>6.3f} "
              f"{g.pattern:12s} {g.fabric_source:14s} {g.style_archetype:18s}")

        if args.write:
            seed = {
                "meta": {
                    "name": name,
                    "source_views": {},
                    "analysis_notes": (
                        f"Auto-synthesized via diverse_seeds.py "
                        f"(rng={args.seed}, archetype={arch}, "
                        f"pattern={g.pattern}, fabric_source={g.fabric_source}, "
                        f"style_archetype={g.style_archetype}). "
                        f"Selected by fitness × diversity from "
                        f"{args.samples}-sample stratified random pool."),
                    "confidence": {"shape": 0.6, "color": 0.6, "pattern": 0.6,
                                     "fabric": 0.6, "hardware": 0.6,
                                     "style_archetype": 0.6},
                },
                "genome": asdict(g),
            }
            with open(os.path.join(SEEDS_DIR, f"{name}.json"), "w") as f:
                json.dump(seed, f, indent=2)

    if args.write:
        print(f"\nwrote {len(chosen_all)} seeds to {SEEDS_DIR}/")
    return chosen_all


if __name__ == "__main__":
    main()
