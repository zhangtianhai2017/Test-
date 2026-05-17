"""Self-iterating diversity search.

The audit only needs an outfit's (archetype, slot_assignments,
global_design) tuple -- no rendering required.  So we can generate
~120 outfits per strategy in well under a second, score them by the
9-axis Hamming audit, and iterate through strategies that progressively
unstick the perceptual-diversity score.

Each iteration prints its audit metrics and saves a brief.  After 10
strategies the winner (by combined "clearly-distinct >= 5 Hamming"
fraction MINUS "near-duplicate <= 1 Hamming" fraction) is emitted as
JSON; a separate render pass can then re-build it visually.

Run:  python3 tools/diversity_self_iterate.py
"""
from __future__ import annotations

import os, sys, json, math, random, time, copy
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from outfit import random_outfit
from library import (ARCHETYPE_SLOTS,
                       filter_cups_by_coverage, filter_bottoms_by_coverage)
from library_data import (LIBRARY as _LIB, entries_matching_slot)
import library as lib
from visual_diversity_audit import (
    variant_features, hamming, HUE_BUCKETS, AXIS_NAMES, AXIS_UNIVERSE,
)


ARCHETYPES = ["triangle_string_halter", "bandeau_back_band",
              "bralette_shoulder_strap", "one_piece_maillot"]


# Outfit -> outfit_json shape matching what visual_diversity_audit expects
def _outfit_to_json(o) -> dict:
    return {
        "archetype": o.archetype,
        "slot_assignments": [
            {"slot_name": a.slot_name, "library_id": a.library_id,
             "local_params": dict(a.local_params)}
            for a in o.slot_assignments
        ],
        "global_design": dict(o.global_design),
    }


# ------------------------------------------------------------------------
# Strategy configuration -- 9 toggles compose 10 strategies
# ------------------------------------------------------------------------

class Strategy:
    def __init__(self, name, *,
                  decouple_modesty=False,    # bottom 0.95, cup varies
                  stratify_hue=False,         # force one variant per hue bucket
                  stratify_saturation=False,
                  stratify_lightness=False,
                  stratify_pattern=False,
                  stratify_weave=False,       # force balanced primary_fabric weave_family
                  stratify_archetype=False,   # force N variants per archetype
                  wide_form=False,            # 30% of variants escape library schema
                  farthest_point=False,       # pick from a big candidate pool
                  fp_pool_size=400,
                  ):
        self.name = name
        self.decouple_modesty = decouple_modesty
        self.stratify_hue = stratify_hue
        self.stratify_saturation = stratify_saturation
        self.stratify_lightness = stratify_lightness
        self.stratify_pattern = stratify_pattern
        self.stratify_weave = stratify_weave
        self.stratify_archetype = stratify_archetype
        self.wide_form = wide_form
        self.farthest_point = farthest_point
        self.fp_pool_size = fp_pool_size


STRATEGIES = [
    Strategy("01_baseline_M095"),
    Strategy("02_decouple_modesty",
              decouple_modesty=True),
    Strategy("03_archetype_stratified",
              decouple_modesty=True, stratify_archetype=True),
    Strategy("04_hue_stratified",
              decouple_modesty=True, stratify_archetype=True,
              stratify_hue=True),
    Strategy("05_sat_light_stratified",
              decouple_modesty=True, stratify_archetype=True,
              stratify_hue=True, stratify_saturation=True,
              stratify_lightness=True),
    Strategy("06_pattern_stratified",
              decouple_modesty=True, stratify_archetype=True,
              stratify_hue=True, stratify_saturation=True,
              stratify_lightness=True, stratify_pattern=True),
    Strategy("07_weave_stratified",
              decouple_modesty=True, stratify_archetype=True,
              stratify_hue=True, stratify_saturation=True,
              stratify_lightness=True, stratify_pattern=True,
              stratify_weave=True),
    Strategy("08_wide_form_only",
              decouple_modesty=True, stratify_archetype=True,
              wide_form=True),
    Strategy("09_farthest_point",
              decouple_modesty=True, stratify_archetype=True,
              farthest_point=True, fp_pool_size=400),
    Strategy("10_full_stack",
              decouple_modesty=True, stratify_archetype=True,
              stratify_hue=True, stratify_saturation=True,
              stratify_lightness=True, stratify_pattern=True,
              stratify_weave=True, wide_form=True,
              farthest_point=True, fp_pool_size=600),
]


# ------------------------------------------------------------------------
# Generation per strategy
# ------------------------------------------------------------------------

# Hue bucket centres in [0,1)
HUE_CENTRES = [(b + 0.5) / len(HUE_BUCKETS) for b in range(len(HUE_BUCKETS))]

PATTERN_BY_FAMILY = {
    "solid":     ["solid"],
    "geometric": ["stripe", "chevron", "checker", "gingham", "herringbone", "polka"],
    "organic":   ["floral", "tropical", "leopard"],
    "gradient":  ["tie_dye", "ombre"],
}

WEAVE_FAMILY_TO_FABRICS: dict[str, list[str]] = {}
def _build_weave_family_index() -> None:
    from visual_diversity_audit import WEAVE_FAMILY
    fams: dict[str, list[str]] = {}
    for fid, e in _LIB.items():
        if e.kind != "fabric":
            continue
        fam = WEAVE_FAMILY.get(e.weave, "plain")
        fams.setdefault(fam, []).append(fid)
    WEAVE_FAMILY_TO_FABRICS.clear()
    WEAVE_FAMILY_TO_FABRICS.update(fams)

_build_weave_family_index()


def _override_global(o, *, hue=None, saturation=None, lightness=None,
                      pattern=None, weave_fam=None, rng=None):
    """Mutate outfit in place to honour stratified controls.  Pattern and
    weave_family overrides may shuffle slot library ids."""
    if hue is not None:
        o.global_design["hue"] = hue
    if saturation is not None:
        o.global_design["saturation"] = saturation
    if lightness is not None:
        o.global_design["lightness"] = lightness
    if pattern is not None:
        o.global_design["pattern_overlay"] = pattern
    if weave_fam is not None and rng is not None:
        cands = WEAVE_FAMILY_TO_FABRICS.get(weave_fam, [])
        if cands:
            chosen = rng.choice(cands)
            # replace primary_fabric slot
            for sa in o.slot_assignments:
                if sa.slot_name == "primary_fabric":
                    sa.library_id = chosen
                    e = _LIB[chosen]
                    sa.local_params = e.sample_local_params(rng)
                    break


def _apply_wide_form_mode(o, rng) -> None:
    """Override cup local_params with WIDER ranges that escape the
    library entry's schema -- explores L1+L2 (entry + geometry kind)
    beyond what any one entry can express.  Bottom stays library-bound
    (modesty hard floor)."""
    WIDE = {
        # name -> (lo, hi)
        "half_u":         (0.07, 0.30),
        "half_v":         (0.04, 0.16),
        "inner_u":        (-0.06, 0.28),
        "apex_lift":      (-0.20, 0.55),
        "underband_dip":  (-0.15, 0.20),
    }
    for sa in o.slot_assignments:
        if sa.slot_name == "cup":
            new_lp = {k: rng.uniform(*v) for k, v in WIDE.items()}
            sa.local_params = new_lp


def generate_outfits(strat: Strategy, rng: random.Random,
                      n: int = 120) -> list:
    """Generate a list of Outfit objects per `strat`."""
    # ---- pre-compute stratification queues if requested ----
    arch_queue = []
    if strat.stratify_archetype:
        per = n // len(ARCHETYPES)
        for a in ARCHETYPES:
            arch_queue.extend([a] * per)
        arch_queue += [rng.choice(ARCHETYPES) for _ in range(n - len(arch_queue))]
        rng.shuffle(arch_queue)
    else:
        arch_queue = [rng.choice(ARCHETYPES) for _ in range(n)]

    hue_queue = []
    if strat.stratify_hue:
        per = n // len(HUE_CENTRES)
        for c in HUE_CENTRES:
            hue_queue.extend([c] * per)
        hue_queue += [rng.random() for _ in range(n - len(hue_queue))]
        rng.shuffle(hue_queue)

    sat_queue = []
    if strat.stratify_saturation:
        half = n // 2
        sat_queue = [rng.uniform(0.15, 0.45)] * half + [rng.uniform(0.55, 0.90)] * (n - half)
        rng.shuffle(sat_queue)

    light_queue = []
    if strat.stratify_lightness:
        third = n // 3
        light_queue = (
            [rng.uniform(0.18, 0.35)] * third +
            [rng.uniform(0.40, 0.60)] * third +
            [rng.uniform(0.70, 0.88)] * (n - 2 * third)
        )
        rng.shuffle(light_queue)

    pattern_queue = []
    if strat.stratify_pattern:
        fams = list(PATTERN_BY_FAMILY.keys())
        per = n // len(fams)
        for f in fams:
            pattern_queue.extend([f] * per)
        pattern_queue += [rng.choice(fams) for _ in range(n - len(pattern_queue))]
        rng.shuffle(pattern_queue)

    weave_queue = []
    if strat.stratify_weave:
        fams = list(WEAVE_FAMILY_TO_FABRICS.keys())
        per = n // len(fams)
        for f in fams:
            weave_queue.extend([f] * per)
        weave_queue += [rng.choice(fams) for _ in range(n - len(weave_queue))]
        rng.shuffle(weave_queue)

    # ---- candidate pool size depends on whether we use farthest-point ----
    pool_size = strat.fp_pool_size if strat.farthest_point else n

    def make_one(i: int):
        arch = arch_queue[i % len(arch_queue)]
        if strat.decouple_modesty:
            cup_strict_arg = 0.30 + (i % 3) * 0.25   # 0.30 / 0.55 / 0.80
            bot_strict_arg = 0.95
        else:
            cup_strict_arg = 0.95
            bot_strict_arg = 0.95
        lib.set_bottom_coverage_strict(bot_strict_arg)
        lib.set_cup_coverage_strict(cup_strict_arg)
        try:
            o = random_outfit(arch, rng,
                               cup_strict=cup_strict_arg,
                               bottom_strict=bot_strict_arg)
        except TypeError:
            o = random_outfit(arch, rng)
        # apply stratified overrides
        overrides = {}
        if hue_queue:   overrides["hue"]        = hue_queue[i % len(hue_queue)]
        if sat_queue:   overrides["saturation"] = sat_queue[i % len(sat_queue)]
        if light_queue: overrides["lightness"]  = light_queue[i % len(light_queue)]
        if pattern_queue:
            fam = pattern_queue[i % len(pattern_queue)]
            overrides["pattern"] = rng.choice(PATTERN_BY_FAMILY[fam])
        if weave_queue:
            overrides["weave_fam"] = weave_queue[i % len(weave_queue)]
        if overrides:
            _override_global(o, rng=rng, **overrides)
        if strat.wide_form and rng.random() < 0.30:
            _apply_wide_form_mode(o, rng)
        return o

    pool = [make_one(i) for i in range(pool_size)]

    if not strat.farthest_point:
        return pool[:n]

    # Farthest-point greedy: pick n by maximising min Hamming distance.
    pool_feats = [variant_features(_outfit_to_json(o)) for o in pool]
    seed_i = rng.randrange(len(pool))
    selected_idx = [seed_i]
    min_d = [hamming(pool_feats[seed_i], pf) for pf in pool_feats]
    min_d[seed_i] = -1
    while len(selected_idx) < n:
        # pick the candidate with largest current min-distance
        nxt = max(range(len(pool)), key=lambda j: min_d[j])
        if min_d[nxt] <= 0 and len(selected_idx) < n:
            # all remaining are duplicates -- give up
            break
        selected_idx.append(nxt)
        new_feat = pool_feats[nxt]
        for j in range(len(pool)):
            if j in selected_idx:
                min_d[j] = -1
                continue
            d = hamming(pool_feats[j], new_feat)
            if d < min_d[j]:
                min_d[j] = d
    return [pool[i] for i in selected_idx[:n]]


# ------------------------------------------------------------------------
# Audit
# ------------------------------------------------------------------------

def audit_outfits(outfits) -> dict:
    feats = [variant_features(_outfit_to_json(o)) for o in outfits]
    n = len(feats)
    counts = [Counter(f[i] for f in feats) for i in range(9)]
    pair_hist = Counter()
    for i in range(n):
        for j in range(i + 1, n):
            pair_hist[hamming(feats[i], feats[j])] += 1
    total_pairs = n * (n - 1) // 2
    near = sum(c for d, c in pair_hist.items() if d <= 1)
    far  = sum(c for d, c in pair_hist.items() if d >= 5)
    # axis flatness: ratio of (seen unique) / (universe), times entropy-ish
    flatness = []
    for i, cnt in enumerate(counts):
        seen = len(cnt)
        universe = len(AXIS_UNIVERSE[AXIS_NAMES[i]])
        # normalised entropy
        total = sum(cnt.values())
        H = -sum((c / total) * math.log(c / total + 1e-9) for c in cnt.values())
        H_max = math.log(universe) if universe > 1 else 1
        flatness.append({"axis": AXIS_NAMES[i],
                         "seen": seen, "universe": universe,
                         "entropy_norm": H / H_max if H_max else 0,
                         "dist": dict(cnt)})
    return {
        "n": n,
        "near_dup_pairs": near,
        "near_dup_pct":   100 * near / total_pairs,
        "clearly_distinct_pairs": far,
        "clearly_distinct_pct":   100 * far / total_pairs,
        "pair_hist": dict(pair_hist),
        "axis_flatness": flatness,
        "score": (100 * far / total_pairs) - (100 * near / total_pairs),
    }


# ------------------------------------------------------------------------
# Driver
# ------------------------------------------------------------------------

def run() -> None:
    rng = random.Random(20260521)
    print(f"{'strategy':30s}  N  clear>=5    near<=1    score    axes_seen")
    history = []
    for strat in STRATEGIES:
        s_rng = random.Random(rng.randrange(1 << 31))
        t0 = time.time()
        outs = generate_outfits(strat, s_rng, n=120)
        a = audit_outfits(outs)
        dt = time.time() - t0
        axes_seen = sum(1 for f in a["axis_flatness"] if f["seen"] == f["universe"])
        print(f"{strat.name:30s}  {a['n']:3d}  {a['clearly_distinct_pct']:5.1f}%  "
              f"{a['near_dup_pct']:5.2f}%  {a['score']:+5.1f}  {axes_seen}/9  ({dt:.1f}s)")
        history.append({
            "strategy": strat.name,
            "metrics":  {k: v for k, v in a.items() if k != "pair_hist"},
            "pair_hist": a["pair_hist"],
            "outfits_repr": [_outfit_to_json(o) for o in outs],
        })

    # winner = max by score
    winner = max(history, key=lambda h: h["metrics"]["score"])
    print(f"\nwinner: {winner['strategy']}  score={winner['metrics']['score']:+.1f}")

    # save history
    out_path = os.path.join(ROOT, "tools", "output",
                              "_diversity_self_iterate.json")
    with open(out_path, "w") as f:
        json.dump({"history": [
            {k: v for k, v in h.items() if k != "outfits_repr"}
            for h in history
        ], "winner": winner["strategy"]}, f, indent=2)
    print(f"history saved -> {out_path}")

    # save winner outfits for downstream render
    win_path = os.path.join(ROOT, "tools", "output",
                              "_diversity_winner_outfits.json")
    with open(win_path, "w") as f:
        json.dump(winner["outfits_repr"], f, indent=2)
    print(f"winner outfits saved -> {win_path}")


if __name__ == "__main__":
    run()
