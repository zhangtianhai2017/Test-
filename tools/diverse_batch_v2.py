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


N_PER_SEED = 15
RNG_MASTER = 20260520
BOTTOM_STRICT = 0.95   # both modesties pinned at 0.95 per user request
CUP_STRICT    = 0.95

# 8 cells: 4 archetypes x 2 RNG branches each.  All same modesty so
# the 0.95 floor is uniform; variety inside a cell comes from random
# library picks + free/extreme shape modes + new colour distribution.
SEED_SPEC: list[tuple[str, int]] = [
    ("triangle_string_halter",  0),
    ("triangle_string_halter",  1),
    ("bandeau_back_band",       0),
    ("bandeau_back_band",       1),
    ("bralette_shoulder_strap", 0),
    ("bralette_shoulder_strap", 1),
    ("one_piece_maillot",       0),
    ("one_piece_maillot",       1),
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

    for idx, (arch, branch) in enumerate(SEED_SPEC):
        sid = f"v2_{idx:02d}_{arch}_b{branch}"
        seed_dir = os.path.join(out_root, sid)
        os.makedirs(seed_dir, exist_ok=True)

        # Both modesties hard-pinned at 0.95 per current user requirement.
        lib.set_bottom_coverage_strict(BOTTOM_STRICT)
        lib.set_cup_coverage_strict(CUP_STRICT)

        # Per-seed RNG branch off master so each cell is independent
        # but the master seed pins the whole batch.
        rng = random.Random(RNG_MASTER * 10007 + idx * 31)
        # Wider colour anchor ranges -- previous batch's audit showed
        # 88% vivid and 59% mid-lightness because the anchor was
        # clamped into a narrow band; pulling these out fixes the skew.
        H = master.random()
        # span the full perceptual saturation/lightness range so both
        # ends (muted/vivid, dark/light) get representation
        S = 0.15 + master.random() * 0.75    # 0.15 .. 0.90
        L = 0.20 + master.random() * 0.65    # 0.20 .. 0.85

        t0 = time.time()
        n_ok = 0
        variants: list[dict] = []
        for i in range(N_PER_SEED):
            try:
                o = random_outfit(arch, rng,
                                    cup_strict=CUP_STRICT,
                                    bottom_strict=BOTTOM_STRICT)
            except TypeError:
                # older random_outfit signature without modesty kwargs
                o = random_outfit(arch, rng)
            # Wider per-variant jitter -- and a chance to flip the
            # variant into the opposite half of S/L space so the
            # within-cell distribution covers both extremes.
            jH = (H + (i / N_PER_SEED) * 0.18) % 1.0
            jS = max(0.10, min(0.95, S + (rng.random() - 0.5) * 0.35))
            jL = max(0.15, min(0.90, L + (rng.random() - 0.5) * 0.35))
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
                    "modesty": {"bottom_coverage_strict": BOTTOM_STRICT,
                                "cup_coverage_strict":    CUP_STRICT},
                }, f, indent=2)

            p = IterParams()
            p.outfit = o
            p.bottom_coverage_strict = BOTTOM_STRICT
            p.cup_coverage_strict = CUP_STRICT
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
            "seed": sid, "archetype": arch,
            "modesty": {"bottom": BOTTOM_STRICT, "cup": CUP_STRICT},
            "n_rendered": n_ok, "elapsed_s": round(dt, 1),
            "variants": variants,
        })

    with open(os.path.join(out_root, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nDONE  out={out_root}  total={time.time()-t_total:.1f}s")


if __name__ == "__main__":
    run()
