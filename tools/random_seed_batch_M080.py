"""
Random-initial-seed batch at modesty=0.80.

Step 1: invent 6 random v2 seed JSONs by sampling random_outfit() under
        pinned modesty 0.80 (both bottom + cup). Each seed is saved
        to assets/seeds_v2/random_samples_M080/ for reproducibility.

Step 2: for each seed, generate 20 random_outfit() variants of the
        same archetype with the seed's primary color/HSL applied as
        a style hint. Render front + back per variant.

Step 3: contact sheets per seed (4x5 thumbnails) + overview + indexes
        are produced via the existing helpers so the run drops into
        the same browsing UX as previous batches.

Reproducibility: master RNG seed is fixed (RNG_MASTER below), so the
six "random" seeds and their variants are stable across reruns.
"""
from __future__ import annotations

import os, sys, json, time, random, colorsys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import iter.capture as cap
cap.VIEWS = [v for v in cap.VIEWS if v.name in ("01_front", "04_back")]

from outfit import random_outfit, outfit_to_genome
from iter.params import IterParams
from render3d_uv import load_body_mesh
from output_paths import dated_dir
import library as lib
import batch_from_diverse_seeds as B   # reuse make_contact_sheet


ARCHETYPES = ["triangle_string_halter", "bandeau_back_band",
              "bralette_shoulder_strap", "one_piece_maillot"]
N_SEEDS = 6
N_PER_SEED = 20
MODESTY = 0.80
RNG_MASTER = 20260513

SEED_OUT_DIR = os.path.join(ROOT, "assets", "seeds_v2", "random_samples_M080")


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def pick_archetypes(rng: random.Random, n: int) -> list[str]:
    """Cover all 4 archetypes at least once when n >= 4; fill the rest
    by random pick from the same pool."""
    base = list(ARCHETYPES) if n >= len(ARCHETYPES) else []
    extra = [rng.choice(ARCHETYPES) for _ in range(n - len(base))]
    out = base + extra
    rng.shuffle(out)
    return out


def make_random_seed(idx: int, archetype: str,
                     rng: random.Random) -> tuple[dict, tuple[float, float, float]]:
    """Sample one random outfit + a random primary color; return the
    serializable seed dict plus the HSL primary so the variant loop
    can reapply it."""
    lib.set_bottom_coverage_strict(MODESTY)
    lib.set_cup_coverage_strict(MODESTY)
    o = random_outfit(archetype, rng)
    H, S, L = rng.random(), 0.40 + rng.random() * 0.55, 0.30 + rng.random() * 0.45
    primary_hex = hsl_to_hex(H, S, L)
    sec_H = (H + 0.5) % 1.0
    secondary_hex = hsl_to_hex(sec_H, 0.30, 0.50)
    seed_id = f"random_M080_{idx:02d}_{archetype}"
    seed_json = {
        "schema_version": "v2",
        "outfit_id": seed_id,
        "archetype": archetype,
        "slot_assignments": {
            a.slot_name: {"library_id": a.library_id,
                          "local_params": dict(a.local_params)}
            for a in o.slot_assignments
        },
        "global_design": {
            "primary_color": primary_hex,
            "secondary_color": secondary_hex,
            "pattern": "solid",
            "pattern_scale": 0.5,
            "_hsl": {"hue": H, "saturation": S, "lightness": L},
        },
        "modesty": {"bottom_coverage_strict": MODESTY,
                    "cup_coverage_strict": MODESTY},
        "generator": {"master_rng_seed": RNG_MASTER, "seed_index": idx},
    }
    return seed_json, (H, S, L)


def run() -> None:
    master = random.Random(RNG_MASTER)
    archetypes = pick_archetypes(master, N_SEEDS)

    os.makedirs(SEED_OUT_DIR, exist_ok=True)
    seeds: list[tuple[dict, tuple[float, float, float]]] = []
    for i, arch in enumerate(archetypes):
        # Per-seed RNG so each seed is independent but reproducible.
        srng = random.Random(RNG_MASTER * 7919 + i)
        seed_json, hsl = make_random_seed(i, arch, srng)
        out_p = os.path.join(SEED_OUT_DIR, seed_json["outfit_id"] + ".json")
        with open(out_p, "w") as f:
            json.dump(seed_json, f, indent=2)
        seeds.append((seed_json, hsl))
        print(f"  seed {i}: {seed_json['outfit_id']}  "
              f"primary={seed_json['global_design']['primary_color']}")

    out_root = dated_dir("seed_batch_random_M080_20x6")
    print(f"OUT = {out_root}")

    body = load_body_mesh()
    summary: list[dict] = []
    t_total = time.time()

    for seed_json, (H, S, L) in seeds:
        sid = seed_json["outfit_id"]
        arch = seed_json["archetype"]
        seed_dir = os.path.join(out_root, sid)
        os.makedirs(seed_dir, exist_ok=True)
        with open(os.path.join(seed_dir, "_source_seed.json"), "w") as f:
            json.dump(seed_json, f, indent=2)

        # Re-pin modesty (cap.render_views may have touched library state).
        lib.set_bottom_coverage_strict(MODESTY)
        lib.set_cup_coverage_strict(MODESTY)

        rng = random.Random(hash(sid) & 0xFFFFFFFF)
        t0 = time.time()
        n_ok = 0
        variants: list[dict] = []
        for i in range(N_PER_SEED):
            o = random_outfit(arch, rng)
            o.global_design["hue"] = H
            o.global_design["saturation"] = S
            o.global_design["lightness"] = L
            sec_h = (H + 0.5) % 1.0
            o.global_design["secondary_hue"] = sec_h
            o.global_design["secondary_saturation"] = 0.30
            o.global_design["secondary_lightness"] = 0.50
            o.global_design["pattern_overlay"] = "solid"
            o.global_design["pattern_scale"] = 0.5

            sub = os.path.join(seed_dir, f"{i:02d}")
            os.makedirs(sub, exist_ok=True)
            with open(os.path.join(sub, "outfit.json"), "w") as f:
                json.dump({
                    "archetype": o.archetype,
                    "slot_assignments": [
                        {"slot_name": a.slot_name, "library_id": a.library_id,
                         "local_params": dict(a.local_params)}
                        for a in o.slot_assignments
                    ],
                    "global_design": dict(o.global_design),
                    "source_seed": sid, "variant_index": i,
                    "modesty": {"bottom_coverage_strict": MODESTY,
                                "cup_coverage_strict": MODESTY},
                }, f, indent=2)

            p = IterParams()
            p.outfit = o
            p.bottom_coverage_strict = MODESTY
            p.cup_coverage_strict = MODESTY
            g = outfit_to_genome(o)
            try:
                cap.render_views(g, p, sub, body_mesh=body)
                n_ok += 1
            except Exception as e:
                print(f"  [{sid}#{i:02d}] render fail: {e}")
            variants.append({
                "index": i,
                "slots": [(a.slot_name, a.library_id) for a in o.slot_assignments],
            })

        B.make_contact_sheet(sid, seed_dir, n=N_PER_SEED)
        dt = time.time() - t0
        print(f"[{sid}] arch={arch}  rendered {n_ok}/{N_PER_SEED}  dt={dt:.1f}s")
        summary.append({
            "seed": sid, "archetype": arch,
            "modesty": {"bottom": MODESTY, "cup": MODESTY},
            "primary_hsl": [H, S, L],
            "n_rendered": n_ok, "elapsed_s": round(dt, 1),
            "variants": variants,
        })

    with open(os.path.join(out_root, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nDONE  out={out_root}  total={time.time()-t_total:.1f}s")


if __name__ == "__main__":
    run()
