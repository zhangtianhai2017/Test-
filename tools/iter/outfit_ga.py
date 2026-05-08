"""
GA operators on the Outfit chromosome (v2).

Same conceptual flow as the v1 verify_ga_uv GA (tournament-3 +
2-elitism), but the chromosome is now an Outfit (archetype + slot
assignments + global_design) instead of a flat 44-dim Genome. This
makes the GA operate inside "real component variations" space rather
than abstract polygon parameter space — discrete jumps between cup
shapes etc. happen via library_id resampling, not smooth float morphs.

Operators
---------
crossover(a, b, rng) — both parents must share the same archetype.
  Per slot, child either:
    * inherits the entire SlotAssignment from one parent (50/50), OR
    * if both parents fill the slot with the SAME library_id, BLX-α
      crosses local_params elementwise.
  global_design fields are BLX-α'd as continuous floats (or single
  parent inherits for the discrete pattern_overlay / palette_preset).

mutate(outfit, rng, p_id=0.05, sigma=0.10) —
  * each slot: with probability p_id, resample library_id from the
    matching subset (forces a discrete jump while keeping legality).
  * for kept library_ids, gaussian-perturb local_params (clamped to
    schema bounds).
  * global_design: hue/saturation/lightness gaussian σ=0.05;
    pattern_overlay resample at p=0.04.

Compatibility — every newborn outfit is run through validate_outfit.
If hard rules fail (kind/tag mismatch, missing required slot, etc.),
the offending slot is rolled back to the parent's value.
"""
from __future__ import annotations

import os
import sys
import copy
import random
from typing import Optional

# ensure the parent tools/ directory is on sys.path when the file is
# executed directly (e.g. as a smoke-test). When imported normally the
# sys.path manipulation is harmless.
_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from outfit import Outfit, SlotAssignment, random_outfit
from library import ARCHETYPE_SLOTS, validate_outfit
from library_data import LIBRARY, entries_matching_slot
from outfit_fitness import outfit_evaluate


# ---------------------------------------------------------------------------
# Crossover
# ---------------------------------------------------------------------------

def _blx_alpha(a: float, b: float, alpha: float, rng: random.Random) -> float:
    lo, hi = min(a, b), max(a, b)
    span = hi - lo
    return rng.uniform(lo - alpha * span, hi + alpha * span)


def crossover(a: Outfit, b: Outfit, rng: random.Random,
              alpha: float = 0.25) -> Outfit:
    """Slot-level crossover. Parents must share archetype."""
    if a.archetype != b.archetype:
        # Cross-archetype: pure parent-A inheritance (avoids illegal mixes)
        return copy.deepcopy(a)

    archetype = a.archetype
    slots = ARCHETYPE_SLOTS[archetype]
    a_by_slot: dict[str, list[SlotAssignment]] = {}
    b_by_slot: dict[str, list[SlotAssignment]] = {}
    for sa in a.slot_assignments:
        a_by_slot.setdefault(sa.slot_name, []).append(sa)
    for sa in b.slot_assignments:
        b_by_slot.setdefault(sa.slot_name, []).append(sa)

    child_assignments: list[SlotAssignment] = []
    for spec in slots:
        a_list = a_by_slot.get(spec.name, [])
        b_list = b_by_slot.get(spec.name, [])
        # Strategy: pick parent who has more entries; if tied, 50/50.
        if not a_list and not b_list:
            continue
        if not a_list:
            chosen = [copy.deepcopy(sa) for sa in b_list]
        elif not b_list:
            chosen = [copy.deepcopy(sa) for sa in a_list]
        else:
            # If first entry of each parent has SAME library_id, BLX-α params
            new_list: list[SlotAssignment] = []
            n = max(len(a_list), len(b_list))
            for i in range(n):
                ai = a_list[i] if i < len(a_list) else None
                bi = b_list[i] if i < len(b_list) else None
                if ai and bi and ai.library_id == bi.library_id:
                    entry = LIBRARY.get(ai.library_id)
                    blended = {}
                    if entry is not None:
                        for k, (lo, hi, default) in entry.local_params_schema.items():
                            va = ai.local_params.get(k, default)
                            vb = bi.local_params.get(k, default)
                            blended[k] = max(lo, min(hi,
                                _blx_alpha(va, vb, alpha, rng)))
                    new_list.append(SlotAssignment(
                        slot_name=spec.name, library_id=ai.library_id,
                        local_params=blended))
                else:
                    src = ai if (rng.random() < 0.5 and ai) else bi if bi else ai
                    new_list.append(copy.deepcopy(src))
            chosen = new_list
        child_assignments.extend(chosen)

    # global_design: BLX-α floats, single-parent for discretes
    g = {}
    keys_continuous = ("hue", "saturation", "lightness",
                          "secondary_hue", "secondary_saturation",
                          "secondary_lightness", "pattern_scale", "pattern_angle")
    keys_discrete = ("pattern_overlay", "palette_preset")
    for k in keys_continuous:
        va = a.global_design.get(k, 0.5)
        vb = b.global_design.get(k, 0.5)
        if k.endswith("hue") or k == "pattern_angle":
            v = (_blx_alpha(va, vb, alpha, rng)) % 1.0
        else:
            v = max(0.0, min(1.0, _blx_alpha(va, vb, alpha, rng)))
        g[k] = v
    for k in keys_discrete:
        g[k] = a.global_design.get(k) if rng.random() < 0.5 else b.global_design.get(k, "free")

    child = Outfit(archetype=archetype,
                     slot_assignments=child_assignments,
                     global_design=g)
    return _heal_invalid(child, parent_a=a, parent_b=b, rng=rng)


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------

def mutate(outfit: Outfit, rng: random.Random,
           p_id: float = 0.05, sigma: float = 0.10) -> Outfit:
    """In-place mutation. Each slot: small chance of library_id resample;
    kept entries get gaussian local_params perturbation. global_design
    HSL gaussian σ=0.05; pattern_overlay resampled at p=0.04."""
    archetype = outfit.archetype
    slot_specs = {s.name: s for s in ARCHETYPE_SLOTS[archetype]}
    new_slot_assignments: list[SlotAssignment] = []
    for sa in outfit.slot_assignments:
        spec = slot_specs.get(sa.slot_name)
        if spec is None:
            new_slot_assignments.append(sa)
            continue
        if rng.random() < p_id:
            candidates = entries_matching_slot(spec)
            if candidates:
                chosen = rng.choice(candidates)
                new_slot_assignments.append(SlotAssignment(
                    slot_name=spec.name, library_id=chosen.id,
                    local_params=chosen.sample_local_params(rng)))
                continue
        # Keep library_id, perturb local_params
        entry = LIBRARY.get(sa.library_id)
        if entry is None:
            new_slot_assignments.append(sa)
            continue
        new_lp = {}
        for k, (lo, hi, default) in entry.local_params_schema.items():
            v = sa.local_params.get(k, default)
            v = v + rng.gauss(0.0, sigma * (hi - lo))
            new_lp[k] = max(lo, min(hi, v))
        new_slot_assignments.append(SlotAssignment(
            slot_name=spec.name, library_id=sa.library_id,
            local_params=new_lp))

    # Mutate global_design
    new_global = dict(outfit.global_design)
    for k in ("hue", "saturation", "lightness",
                "secondary_hue", "secondary_saturation", "secondary_lightness",
                "pattern_scale", "pattern_angle"):
        if k in new_global:
            v = new_global[k] + rng.gauss(0.0, 0.05)
            if k.endswith("hue") or k == "pattern_angle":
                new_global[k] = v % 1.0
            else:
                new_global[k] = max(0.0, min(1.0, v))
    if rng.random() < 0.04:
        new_global["pattern_overlay"] = rng.choice(
            ["solid", "stripe", "polka", "gingham", "chevron", "floral",
             "tropical", "leopard", "tie_dye", "ombre", "checker", "herringbone"])

    child = Outfit(archetype=archetype,
                    slot_assignments=new_slot_assignments,
                    global_design=new_global)
    # Resampled library_ids may introduce O5 compatibility violations
    # (e.g. CUP_FOAM_MOLDED_M needs F_FOAM_CUP_3MM); roll back to the
    # pre-mutation outfit on any slot the validator flags.
    return _heal_invalid(child, outfit, outfit, rng)


# ---------------------------------------------------------------------------
# Healing — run validate_outfit; for each invalid slot, fall back to a parent
# ---------------------------------------------------------------------------

def _heal_invalid(child: Outfit, parent_a: Outfit, parent_b: Outfit,
                   rng: random.Random) -> Outfit:
    warnings = validate_outfit(child, LIBRARY)
    if not warnings:
        return child
    a_by_slot: dict[str, list[SlotAssignment]] = {}
    b_by_slot: dict[str, list[SlotAssignment]] = {}
    for sa in parent_a.slot_assignments:
        a_by_slot.setdefault(sa.slot_name, []).append(sa)
    for sa in parent_b.slot_assignments:
        b_by_slot.setdefault(sa.slot_name, []).append(sa)
    a_by_id = {sa.library_id: sa for sa in parent_a.slot_assignments}
    b_by_id = {sa.library_id: sa for sa in parent_b.slot_assignments}

    for w in warnings:
        # O2/O3/O4/O6 messages all carry "slot '<name>'"; O5 carries
        # "'<library_id>' requires partner from..." (no slot pattern,
        # so we look up the offending assignment by library_id).
        if w.startswith("O5"):
            lib_id = w.split("'")[1]
            offending = [sa for sa in child.slot_assignments
                         if sa.library_id == lib_id]
            if not offending:
                continue
            slot_name = offending[0].slot_name
            replacement = a_by_id.get(lib_id) or b_by_id.get(lib_id)
            if replacement is None:
                # parents lacked the partner too — fall back to whichever
                # parent had this slot filled
                for src in (a_by_slot.get(slot_name), b_by_slot.get(slot_name)):
                    if src:
                        child.slot_assignments = [
                            sa for sa in child.slot_assignments
                            if sa.slot_name != slot_name
                        ]
                        child.slot_assignments.extend(copy.deepcopy(src))
                        break
            continue
        if "slot '" not in w:
            continue
        slot_name = w.split("slot '")[1].split("'")[0]
        child.slot_assignments = [
            sa for sa in child.slot_assignments if sa.slot_name != slot_name
        ]
        for src in (a_by_slot.get(slot_name), b_by_slot.get(slot_name)):
            if src:
                child.slot_assignments.extend(copy.deepcopy(src))
                break
    return child


# ---------------------------------------------------------------------------
# GA loop
# ---------------------------------------------------------------------------

def evolve(parent_a: Outfit, parent_b: Outfit,
            pop_size: int = 30, gens: int = 8,
            rng: Optional[random.Random] = None,
            ) -> tuple[list[tuple[Outfit, dict]], list[float], list[float]]:
    """Tournament-3 + 2-elitism GA on Outfits. Selects on outfit_evaluate
    composite (40% aesthetic + 25% manufacturing + 35% outfit-native).
    Returns (ranked_pop_with_fit, mean_traj, max_traj)."""
    rng = rng or random.Random()

    def fit_of(o: Outfit) -> dict:
        return outfit_evaluate(o)

    pop: list[Outfit] = [copy.deepcopy(parent_a), copy.deepcopy(parent_b)]
    while len(pop) < pop_size:
        pop.append(mutate(crossover(parent_a, parent_b, rng), rng))

    mean_t, max_t = [], []
    for gen in range(gens):
        fits = [fit_of(o)["overall"] for o in pop]
        mean_t.append(float(sum(fits) / len(fits)))
        max_t.append(float(max(fits)))

        # tournament-3 selection
        def pick():
            contestants = rng.sample(list(zip(pop, fits)), 3)
            return max(contestants, key=lambda x: x[1])[0]

        ranked = sorted(zip(pop, fits), key=lambda x: x[1], reverse=True)
        next_pop: list[Outfit] = [ranked[0][0], ranked[1][0]]   # 2-elitism
        while len(next_pop) < pop_size:
            a, b = pick(), pick()
            child = mutate(crossover(a, b, rng), rng)
            next_pop.append(child)
        pop = next_pop

    fits = [fit_of(o) for o in pop]
    mean_t.append(float(sum(f["overall"] for f in fits) / len(fits)))
    max_t.append(float(max(f["overall"] for f in fits)))
    ranked = sorted(zip(pop, fits), key=lambda x: x[1]["overall"], reverse=True)
    return ranked, mean_t, max_t


if __name__ == "__main__":
    rng = random.Random(42)
    pa = random_outfit("triangle_string_halter", rng)
    pb = random_outfit("triangle_string_halter", rng)
    print(f"parent A: {len(pa.slot_assignments)} slots; "
          f"parent B: {len(pb.slot_assignments)} slots")
    ranked, mean_t, max_t = evolve(pa, pb, pop_size=15, gens=5, rng=rng)
    print(f"GA done: mean {mean_t[0]:.3f} -> {mean_t[-1]:.3f}, "
          f"max {max_t[0]:.3f} -> {max_t[-1]:.3f}")
    top, top_fit = ranked[0]
    print(f"top outfit: archetype={top.archetype}, "
          f"slots={len(top.slot_assignments)}, fit={top_fit['overall']:.3f}")
    for sa in top.slot_assignments:
        print(f"  {sa.slot_name:18s}  {sa.library_id}")
