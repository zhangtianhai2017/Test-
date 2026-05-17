"""High-diversity test batch — addresses the user's two observations:

  (1) "下身经常完全没有布料的输出" — the new SHELL_UV_MARGIN was
      shrinking bottom polygons; fix lives in render3d_uv.py
      (margin only applies above CUP_V_THRESHOLD now). This batch
      validates that bottoms always render across modesty range.

  (2) "上身有基础型影子" — modesty 0.80 collapsed the cup pool to
      "full coverage only" (foam_molded). This batch distributes 8
      seeds across BOTH archetype AND modesty (0.30, 0.50, 0.70)
      so the cup pool stays varied for half the seeds and only
      tightens for the high-modesty ones.

8 seeds × 15 variants = 120 outfits, ~10 min runtime expected.
"""
from __future__ import annotations

import os, sys, json, time, random, colorsys, traceback

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


N_PER_SEED = 10
RNG_MASTER = 20260519
BOTTOM_STRICT = 0.95   # user-requested: bottoms pinned to full coverage

# 12 (archetype, cup_strict) cells -- bottom_strict always 0.95.  10
# variants per cell = 120 total.  Cup modesty varies so the cup pool
# isn't filtered to one geometry family per cell.
SEED_SPEC: list[tuple[str, float]] = [
    ("triangle_string_halter",  0.20),
    ("triangle_string_halter",  0.50),
    ("triangle_string_halter",  0.80),
    ("bandeau_back_band",       0.20),
    ("bandeau_back_band",       0.50),
    ("bandeau_back_band",       0.80),
    ("bralette_shoulder_strap", 0.20),
    ("bralette_shoulder_strap", 0.50),
    ("bralette_shoulder_strap", 0.80),
    ("one_piece_maillot",       0.20),
    ("one_piece_maillot",       0.50),
    ("one_piece_maillot",       0.80),
]


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def run() -> None:
    out_root = dated_dir("diverse_batch_v2_8x15")
    print(f"OUT = {out_root}")
    body = load_body_mesh()

    master = random.Random(RNG_MASTER)
    summary = []
    t_total = time.time()

    for idx, (arch, modesty) in enumerate(SEED_SPEC):
        sid = f"v2_{idx:02d}_{arch}_M{int(modesty*100):03d}"
        seed_dir = os.path.join(out_root, sid)
        os.makedirs(seed_dir, exist_ok=True)

        lib.set_bottom_coverage_strict(modesty)
        lib.set_cup_coverage_strict(modesty)

        # Per-seed RNG branch off master so each cell is independent
        # but the master seed pins the whole batch.
        rng = random.Random(RNG_MASTER * 10007 + idx * 31)
        # Pick a random colour palette anchor for this seed
        H = master.random()
        S = 0.45 + master.random() * 0.45
        L = 0.30 + master.random() * 0.40

        t0 = time.time()
        n_ok = 0
        variants: list[dict] = []
        for i in range(N_PER_SEED):
            try:
                o = random_outfit(arch, rng,
                                    cup_strict=modesty,
                                    bottom_strict=modesty)
            except TypeError:
                # older random_outfit signature without modesty kwargs
                o = random_outfit(arch, rng)
            # Slight per-variant colour jitter so the batch reads varied
            jH = (H + (i / N_PER_SEED) * 0.12) % 1.0
            jS = max(0.20, min(0.95, S + (rng.random() - 0.5) * 0.15))
            jL = max(0.25, min(0.75, L + (rng.random() - 0.5) * 0.18))
            o.global_design["hue"] = jH
            o.global_design["saturation"] = jS
            o.global_design["lightness"] = jL

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
                    "modesty": {"bottom_coverage_strict": modesty,
                                "cup_coverage_strict": modesty},
                }, f, indent=2)

            p = IterParams()
            p.outfit = o
            p.bottom_coverage_strict = modesty
            p.cup_coverage_strict = modesty
            g = outfit_to_genome(o)
            try:
                cap.render_views(g, p, sub, body_mesh=body)
                n_ok += 1
            except Exception as exc:
                print(f"  [{sid}#{i:02d}] render fail: {exc}")
            variants.append({
                "index": i,
                "slots": [(a.slot_name, a.library_id) for a in o.slot_assignments],
            })

        B.make_contact_sheet(sid, seed_dir, n=N_PER_SEED)
        dt = time.time() - t0
        print(f"[{sid}]  rendered {n_ok}/{N_PER_SEED}  dt={dt:.1f}s")
        summary.append({
            "seed": sid, "archetype": arch, "modesty": modesty,
            "n_rendered": n_ok, "elapsed_s": round(dt, 1),
            "variants": variants,
        })

    with open(os.path.join(out_root, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nDONE  out={out_root}  total={time.time()-t_total:.1f}s")


if __name__ == "__main__":
    run()
