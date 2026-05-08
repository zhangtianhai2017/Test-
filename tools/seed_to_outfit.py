"""
v1 → v2 seed migration: convert every assets/seeds/*.json (legacy
Genome) into an Outfit JSON under assets/seeds_v2/.

The v1 seed format stores Genome fields directly. Each Outfit JSON
preserves the original Genome (for fitness compat) but adds the
v2 outfit field with archetype + slot_assignments + global_design.

Usage:
    python3 tools/seed_to_outfit.py            # migrate all
    python3 tools/seed_to_outfit.py composite_red  # one seed
"""
from __future__ import annotations

import argparse, glob, json, os, sys
from dataclasses import asdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from outfit import genome_to_outfit
from library import validate_outfit
from library_data import LIBRARY
from seed_loader import load_seed, seed_to_genome


SEEDS_V1 = "assets/seeds"
SEEDS_V2 = "assets/seeds_v2"


def migrate(name: str, verbose: bool = True) -> dict:
    seed = load_seed(name)
    g = seed_to_genome(seed)
    outfit = genome_to_outfit(g)
    warnings = validate_outfit(outfit, LIBRARY)

    out = {
        "meta": dict(seed.get("meta", {})),
        "genome": dict(seed.get("genome", {})),
        "outfit": {
            "archetype": outfit.archetype,
            "slot_assignments": [
                {"slot_name": a.slot_name,
                 "library_id": a.library_id,
                 "local_params": dict(a.local_params)}
                for a in outfit.slot_assignments
            ],
            "global_design": dict(outfit.global_design),
        },
        "outfit_validation": {
            "valid": len(warnings) == 0,
            "warnings": warnings,
        },
    }
    out["meta"]["migrated_to_v2"] = "2026-04-29"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", nargs="?", help="single seed name (without .json)")
    ap.add_argument("--out-dir", default=SEEDS_V2)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    paths = ([os.path.join(SEEDS_V1, args.seed + ".json")]
             if args.seed else sorted(glob.glob(os.path.join(SEEDS_V1, "*.json"))))

    n_total = 0
    n_valid = 0
    for p in paths:
        if not os.path.isfile(p):
            print(f"skip (missing): {p}")
            continue
        name = os.path.basename(p)[:-5]
        out = migrate(name)
        out_path = os.path.join(args.out_dir, name + ".json")
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
        n_total += 1
        if out["outfit_validation"]["valid"]:
            n_valid += 1
        flag = "OK" if out["outfit_validation"]["valid"] else "WARN"
        print(f"  [{flag}] {name:42s} -> {out['outfit']['archetype']:24s} "
              f"slots={len(out['outfit']['slot_assignments'])}")

    print(f"\nmigrated {n_total} seeds; {n_valid} valid; "
          f"{n_total - n_valid} with warnings")


if __name__ == "__main__":
    main()
