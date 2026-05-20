"""Visual / perceptual diversity audit for a generated batch.

Maps each variant to a 9-dim categorical "perceptual feature vector"
on the axes a viewer notices first (archetype, cup family, hue cluster,
lightness band, saturation band, pattern family, weave family, bottom
coverage tier, symmetry mode).  Reports:

  - per-axis unique-value coverage (e.g. cup_family 5/5 represented)
  - distribution of pairwise Hamming distances over the batch
  - near-duplicate pair count (Hamming <= 1)
  - clearly-distinct pair count (Hamming >= 5)
  - the actual representative variants per axis bucket

The point of the report is to answer "does this batch hit perceptual
diversity?" with a single glance, not detail-level diversity.
"""
from __future__ import annotations

import os, sys, json, glob, math
from collections import Counter, defaultdict


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from library_data import LIBRARY


# 9 perceptual axes.  Discrete buckets so two variants are either in
# the same bucket (visually similar on that axis) or not.
#
# Bucket counts were widened 2026-05-20 to give the RL diversity bonus
# more room to register small color/lightness/saturation differences.
# Coarser buckets meant 8 different briefs all collapsed into the same
# "cyan-mid-muted" bucket and the bonus was always 0. With these finer
# buckets, near-by colors are still distinct, so the bonus has a real
# signal to gradient through.
HUE_BUCKETS = [f"h{i:02d}" for i in range(24)]            # 15° each
LIGHTNESS_BUCKETS = [f"l{i}" for i in range(6)]            # ~17% each
SATURATION_BUCKETS = [f"s{i}" for i in range(4)]           # 25% each

PATTERN_FAMILY = {
    "solid":      "solid",
    "stripe":     "geometric",
    "chevron":    "geometric",
    "checker":    "geometric",
    "gingham":    "geometric",
    "herringbone":"geometric",
    "polka":      "geometric",
    "floral":     "organic",
    "tropical":   "organic",
    "leopard":    "organic",
    "tie_dye":    "gradient",
    "ombre":      "gradient",
}

WEAVE_FAMILY = {
    # plain / textured / mesh-open / lace-open / lustrous / structured
    "plain":      "plain",
    "ribbed":     "textured",
    "crinkle":    "textured",
    "slub":       "textured",
    "terry":      "textured",
    "seersucker": "textured",
    "jacquard":   "textured",
    "mesh":       "mesh_open",
    "fishnet":    "mesh_open",
    "lace":       "lace_open",
    "crochet":    "lace_open",
    "velvet":     "lustrous",
    "shiny_knit": "lustrous",
    "sequined":   "lustrous",
    "neoprene":   "structured",
    "foam":       "structured",
}

CUP_FAMILY_NORMALISE = {
    "triangle":         "triangle",
    "brazilian":        "triangle",
    "balconette":       "balconette",
    "bandeau_unified":  "bandeau",
    "bandeau":          "bandeau",
    "molded_foam":      "foam",
    "softcup_squareneck": "softcup",
}

COVERAGE_TIER = {"minimal": "minimal", "medium": "medium", "full": "full"}


def hue_bucket(h: float) -> str:
    h = h % 1.0
    return HUE_BUCKETS[int(h * len(HUE_BUCKETS)) % len(HUE_BUCKETS)]


def lightness_bucket(l: float) -> str:
    idx = int(max(0.0, min(0.9999, l)) * len(LIGHTNESS_BUCKETS))
    return LIGHTNESS_BUCKETS[idx]


def saturation_bucket(s: float) -> str:
    idx = int(max(0.0, min(0.9999, s)) * len(SATURATION_BUCKETS))
    return SATURATION_BUCKETS[idx]


def variant_features(outfit_json: dict) -> tuple:
    """Return a 9-tuple of categorical perceptual features."""
    gd = outfit_json.get("global_design", {})
    arch = outfit_json.get("archetype", "?")
    # cup family
    cup_id = next((a["library_id"] for a in outfit_json["slot_assignments"]
                   if a["slot_name"] == "cup"), None)
    cup_geom = ""
    if cup_id:
        e = LIBRARY.get(cup_id)
        cup_geom = CUP_FAMILY_NORMALISE.get(e.geometry_kind, e.geometry_kind) if e else ""
    # bottom coverage tier
    bot_id = next((a["library_id"] for a in outfit_json["slot_assignments"]
                   if a["slot_name"].startswith("bottom")), None)
    cov = ""
    if bot_id:
        e = LIBRARY.get(bot_id)
        cov = COVERAGE_TIER.get(e.coverage_class, e.coverage_class) if e else ""
    # primary fabric weave
    fab_id = next((a["library_id"] for a in outfit_json["slot_assignments"]
                   if a["slot_name"] == "primary_fabric"), None)
    weave_fam = ""
    if fab_id:
        e = LIBRARY.get(fab_id)
        if e:
            weave_fam = WEAVE_FAMILY.get(e.weave, e.weave)
    pattern_fam = PATTERN_FAMILY.get(gd.get("pattern_overlay", "solid"), "other")

    return (
        arch,
        cup_geom,
        hue_bucket(gd.get("hue", 0.5)),
        lightness_bucket(gd.get("lightness", 0.5)),
        saturation_bucket(gd.get("saturation", 0.5)),
        pattern_fam,
        weave_fam,
        cov,
        gd.get("symmetry_mode", "mirror"),
    )


AXIS_NAMES = ("archetype", "cup_family", "hue", "lightness", "saturation",
              "pattern_family", "weave_family", "bottom_coverage", "symmetry")
AXIS_UNIVERSE = {
    "archetype":     {"triangle_string_halter", "bandeau_back_band",
                       "bralette_shoulder_strap", "one_piece_maillot"},
    "cup_family":    {"triangle", "balconette", "bandeau", "foam", "softcup"},
    "hue":           set(HUE_BUCKETS),       # 24 buckets, 15° each
    "lightness":     set(LIGHTNESS_BUCKETS), # 6 buckets, ~17% each
    "saturation":    set(SATURATION_BUCKETS),# 4 buckets, 25% each
    "pattern_family":{"solid", "geometric", "organic", "gradient"},
    "weave_family":  {"plain", "textured", "mesh_open", "lace_open",
                       "lustrous", "structured"},
    "bottom_coverage":{"minimal", "medium", "full"},
    "symmetry":      {"mirror", "dramatic_asym"},
}


def hamming(a: tuple, b: tuple) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


def batch_diversity_bonuses(outfits) -> list[float]:
    """For an iterable of Outfit-like objects, compute each item's
    average Hamming distance (normalized to [0, 1]) from every other
    item in the batch, on the 9 perceptual axes.

    Returned values plug straight into the RL reward as a "be different"
    bonus. With B variants, each bonus is in [0, 1]:
      0.0 = identical features to every other batch member
      1.0 = all 9 features differ from every other member

    Accepts either Outfit dataclass instances OR pre-converted dicts
    that look like the outfit.json schema (archetype, slot_assignments,
    global_design).
    """
    items = list(outfits)
    n = len(items)
    if n < 2:
        return [0.0] * n
    feats = []
    for o in items:
        if hasattr(o, "archetype"):  # Outfit dataclass
            d = {
                "archetype": o.archetype,
                "slot_assignments": [
                    {"slot_name": sa.slot_name,
                     "library_id": sa.library_id,
                     "local_params": dict(sa.local_params)}
                    for sa in o.slot_assignments
                ],
                "global_design": dict(o.global_design),
            }
        else:
            d = o
        feats.append(variant_features(d))
    bonuses = []
    for i in range(n):
        d_sum = sum(hamming(feats[i], feats[j]) for j in range(n) if j != i)
        bonuses.append(d_sum / ((n - 1) * 9))
    return bonuses


def audit(batch_dir: str) -> dict:
    variants = []
    for sd in sorted(os.listdir(batch_dir)):
        full = os.path.join(batch_dir, sd)
        if not os.path.isdir(full):
            continue
        for v in sorted(os.listdir(full)):
            if not v.isdigit():
                continue
            p = os.path.join(full, v, "outfit.json")
            if not os.path.isfile(p):
                continue
            with open(p) as f:
                outfit = json.load(f)
            variants.append({
                "seed": sd, "variant": v,
                "features": variant_features(outfit),
            })

    n = len(variants)
    feats = [v["features"] for v in variants]
    counts_per_axis = [Counter(f[i] for f in feats) for i in range(9)]

    # pairwise Hamming distribution (sampled if n is large)
    pair_hist = Counter()
    near_dups = []
    for i in range(n):
        for j in range(i + 1, n):
            d = hamming(feats[i], feats[j])
            pair_hist[d] += 1
            if d <= 1:
                near_dups.append((variants[i], variants[j], d))

    return {
        "n_variants": n,
        "axis_coverage": [
            (AXIS_NAMES[i], len(counts_per_axis[i]),
              len(AXIS_UNIVERSE[AXIS_NAMES[i]]), dict(counts_per_axis[i]))
            for i in range(9)
        ],
        "pair_hist": dict(pair_hist),
        "near_dup_pairs": near_dups[:20],   # only the first 20 for the report
        "total_near_dups": len(near_dups),
    }


def render_report(rep: dict) -> str:
    out = []
    n = rep["n_variants"]
    out.append(f"# Perceptual diversity audit — {n} variants\n")
    out.append("## Per-axis coverage")
    out.append("| axis | seen / universe | distribution |")
    out.append("|---|---|---|")
    for name, seen, universe, dist in rep["axis_coverage"]:
        # sort distribution by count desc
        d_items = sorted(dist.items(), key=lambda kv: -kv[1])
        d_str = ", ".join(f"{k}:{v}" for k, v in d_items)
        out.append(f"| {name} | {seen}/{universe} | {d_str} |")
    out.append("")
    out.append("## Pairwise Hamming distance histogram (max=9)")
    out.append("| dist | pairs | % |")
    out.append("|---|---|---|")
    total_pairs = n * (n - 1) // 2
    for d in range(0, 10):
        c = rep["pair_hist"].get(d, 0)
        pct = 100 * c / total_pairs if total_pairs else 0
        out.append(f"| {d} | {c} | {pct:.1f}% |")
    out.append("")
    out.append(f"## Verdict")
    near = rep["total_near_dups"]
    far  = sum(c for d, c in rep["pair_hist"].items() if d >= 5)
    pct_near = 100 * near / total_pairs if total_pairs else 0
    pct_far  = 100 * far / total_pairs if total_pairs else 0
    out.append(f"- Near-duplicate pairs (Hamming <= 1):  **{near}**  ({pct_near:.1f}%)")
    out.append(f"- Clearly-distinct pairs (Hamming >= 5): **{far}**  ({pct_far:.1f}%)")
    out.append("")
    if rep["near_dup_pairs"]:
        out.append("Some near-duplicate examples (the first 10):")
        for a, b, d in rep["near_dup_pairs"][:10]:
            out.append(f"- d={d}  `{a['seed']}/{a['variant']}` ↔ `{b['seed']}/{b['variant']}`")
            out.append(f"     {a['features']}")
            out.append(f"     {b['features']}")
    return "\n".join(out) + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: visual_diversity_audit.py <batch_dir>")
    batch = os.path.abspath(sys.argv[1])
    rep = audit(batch)
    txt = render_report(rep)
    out_path = os.path.join(batch, "perceptual_diversity_audit.md")
    with open(out_path, "w") as f:
        f.write(txt)
    print(txt)
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    main()
