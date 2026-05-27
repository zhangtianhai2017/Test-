"""
End-to-end v3 smoke test: brief → NN → strokes → PNG.

Pipeline:
  1. Build DesignGeneratorV3, init tag bank from sbert
  2. Encode 8 SHOWCASE_BRIEFS with the same multilingual sbert
  3. Forward pass with tag_axis_weights (some art_style + cultural + silhouette)
  4. Decode stroke_tensor → list[list[Stroke]]
  5. Serialize each design to JSON
  6. Subprocess-call _render_one_v3.py per design → 8 PNGs
  7. Build a simple README + index.html for review

Goal: prove the entire v3 pipeline works end-to-end with random-init weights.
Output quality is irrelevant — only "no crashes, all 8 designs render" matters.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import torch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from design_generator import SentenceTransformerEncoder        # noqa: E402
from v3.design_generator_v3 import DesignGeneratorV3            # noqa: E402
from v3.stroke_schema import stroke_to_dict                      # noqa: E402
from tag_data import AXES                                         # noqa: E402


SHOWCASE_BRIEFS = [
    "古典抹胸, 象牙白, 法式优雅",
    "metallic sequin bandeau, silver, evening party",
    "高腰复古比基尼, 海军蓝白圆点, 50年代风",
    "minimalist black one-piece, deep V neckline",
    "tropical floral string bikini, hot pink and orange, beach festival",
    "光泽缎面三角杯, 翡翠绿, 高级感",
    "asymmetric one-shoulder cutout, burgundy, sophisticated evening",
    "athletic sports bikini, neon yellow, surf-ready",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="tools/output/2026-05-27/p18_v3_e2e_smoke")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--noise-sigma", type=float, default=1.0)
    ap.add_argument("--use-tag-mix", action="store_true",
                    help="Enable Dirichlet tag mixing (default: brief-only)")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    os.makedirs(args.out_dir, exist_ok=True)

    print("== v3 end-to-end smoke ==")
    print(f"out_dir: {args.out_dir}")
    print(f"seed: {args.seed}  noise_sigma: {args.noise_sigma}  "
          f"tag_mix: {args.use_tag_mix}")

    # 1. sbert encoder (multilingual, matches tag_embeddings)
    print("\n[1/6] loading multilingual sbert...")
    enc = SentenceTransformerEncoder()
    sbert_dim = enc.dim

    # 2. generator
    print("[2/6] building DesignGeneratorV3...")
    gen = DesignGeneratorV3(sbert_dim=sbert_dim, latent_dim=128)
    n_params = sum(p.numel() for p in gen.parameters())
    print(f"      params: {n_params:,}")
    print("[3/6] init tag bank from sbert (~10s)...")
    gen.init_tag_bank(sbert=enc.model)
    gen.eval()

    # 3. encode briefs
    print(f"[4/6] encoding {len(SHOWCASE_BRIEFS)} briefs...")
    brief_emb = enc.encode(SHOWCASE_BRIEFS)
    # encode() may return numpy → convert
    if not isinstance(brief_emb, torch.Tensor):
        brief_emb = torch.tensor(brief_emb)
    brief_emb = brief_emb.float()
    print(f"      brief_emb: {tuple(brief_emb.shape)}")

    # 4. forward
    axis_weights = None
    if args.use_tag_mix:
        # heavier weight on the higher-leverage axes
        axis_weights = {
            "art_style": 0.30, "cultural": 0.20, "silhouette": 0.15,
            "costume_convention": 0.15, "material_vfx": 0.15,
            "archetype": 0.05,
        }
    print(f"[5/6] forward pass (axis_weights={axis_weights})")
    with torch.no_grad():
        out = gen(brief_emb,
                  axis_weights=axis_weights,
                  noise_sigma=args.noise_sigma)
    print(f"      stroke_tensor: {tuple(out.stroke_tensor.shape)}")
    print(f"      anchor_plan (mean activation per anchor):")
    ap_mean = torch.sigmoid(out.anchor_plan).mean(dim=0)
    for i, v in enumerate(ap_mean.tolist()):
        from v3.stroke_schema import Anchor
        try:
            print(f"        {Anchor(i).name:<14} {v:.3f}")
        except ValueError:
            pass

    # 5. decode
    designs = gen.decode_strokes(out.stroke_tensor, enforce_anchored=True)
    print(f"      decoded {len(designs)} designs")
    for i, strokes in enumerate(designs):
        end_at = next((j + 1 for j, s in enumerate(strokes) if s.is_end),
                      len(strokes))
        designs[i] = strokes[:end_at]
        print(f"        design {i}: {len(designs[i])} strokes  "
              f"(brief: {SHOWCASE_BRIEFS[i][:50]})")

    # 6. render each (UV sketch fallback; 3D crashed due to vLLM-GPU
    #    contention — see STATUS_2026-05-27_10h_autonomous.md §Issues)
    print(f"[6/6] rendering {len(designs)} designs (2D UV sketch)")
    from v3.stroke_renderer import render_uv_sketch
    paths = []
    t0 = time.time()
    for i, strokes in enumerate(designs):
        vid = f"v{i:02d}"
        design_dir = os.path.join(args.out_dir, vid)
        os.makedirs(design_dir, exist_ok=True)
        strokes_json = os.path.join(design_dir, "strokes.json")
        with open(strokes_json, "w", encoding="utf-8") as f:
            json.dump({"brief": SHOWCASE_BRIEFS[i],
                       "strokes": [stroke_to_dict(s) for s in strokes]},
                       f, ensure_ascii=False, indent=2)
        png_out = os.path.join(design_dir, "uv_sketch.png")
        try:
            render_uv_sketch(strokes, png_out,
                              title=f"{vid}: {SHOWCASE_BRIEFS[i][:60]}")
            paths.append(png_out)
            print(f"  ✓ {vid}  {os.path.getsize(png_out):>7} bytes  "
                  f"({len(strokes)} strokes)")
        except Exception as exc:
            print(f"  ✗ {vid}  exception: {exc}")
    print(f"\n  rendered {len(paths)}/{len(designs)} in {time.time()-t0:.1f}s")

    # 7. README
    readme = os.path.join(args.out_dir, "README.md")
    with open(readme, "w", encoding="utf-8") as f:
        f.write(f"# v3 end-to-end smoke ({args.out_dir.split('/')[-1]})\n\n")
        f.write(f"Random-init DesignGeneratorV3. {len(paths)}/{len(designs)} "
                 f"designs rendered.\n\n")
        f.write(f"- seed={args.seed} noise_sigma={args.noise_sigma} "
                 f"tag_mix={args.use_tag_mix}\n")
        f.write(f"- params={n_params:,}\n\n")
        f.write("| brief | strokes | png |\n|---|---|---|\n")
        for i, strokes in enumerate(designs):
            png_exists = os.path.exists(os.path.join(args.out_dir,
                                                      f"v{i:02d}/01_front.png"))
            f.write(f"| {SHOWCASE_BRIEFS[i]} | {len(strokes)} | "
                    f"{'✓' if png_exists else '✗'} |\n")
    print(f"\nwrote {readme}")
    print(f"\n== smoke OK ({len(paths)}/{len(designs)} rendered) ==")


if __name__ == "__main__":
    main()
