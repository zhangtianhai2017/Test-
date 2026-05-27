"""
v3 Audit — visual comparison of random-init vs Phase-A2-trained
decoder outputs on a panel of UNSEEN briefs (not in the teacher set).

This is the smoke evidence that the architecture has learned something
transferable — when fed novel briefs, the trained decoder should
produce different outputs from random init (and ideally outputs that
correlate with brief semantics).

Output:
  tools/output/2026-05-28/p22_v3_audit/
    audit_grid.png          (2-col × N-row: random vs trained)
    designs/v{NN}/strokes_random.json
    designs/v{NN}/strokes_trained.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import torch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from design_generator import SentenceTransformerEncoder         # noqa: E402
from v3.design_generator_v3 import DesignGeneratorV3              # noqa: E402
from v3.stroke_schema import stroke_to_dict                        # noqa: E402
from v3.stroke_renderer import render_uv_sketch                    # noqa: E402


# 8 UNSEEN briefs that span the design space — none of these appear in
# the Phase A2 teacher set, so any non-random output proves transfer
AUDIT_BRIEFS = [
    "cyberpunk neon-trim crop top, magenta + black",
    "Iris van Herpen sculptural one-piece, translucent shards",
    "Genshin Liyue silk drape with 披帛, pearl + jade",
    "K/DA-style idol stage micro-bikini, neon teal + silver",
    "Maori-inspired body harness with bone pendants, ochre",
    "Bayonetta hair-as-catsuit, deep violet, beauty mark",
    "Dune Fremen stillsuit-bikini hybrid, desert sand + bone",
    "FFXIV summoner glamour with floating glyphs, gold + sapphire",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt",
                    default="tools/output/2026-05-28/p20b_phase_a2_isend/"
                            "decoder_pretrained.pt")
    ap.add_argument("--out-dir",
                    default="tools/output/2026-05-28/p22_v3_audit")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    designs_dir = os.path.join(args.out_dir, "designs")
    os.makedirs(designs_dir, exist_ok=True)

    print("[1/5] loading sbert...")
    enc = SentenceTransformerEncoder()

    print("[2/5] building two DesignGeneratorV3 instances...")
    torch.manual_seed(args.seed)
    gen_random = DesignGeneratorV3()
    gen_random.init_tag_bank(sbert=enc.model)
    gen_random.eval()

    torch.manual_seed(args.seed)
    gen_trained = DesignGeneratorV3()
    gen_trained.init_tag_bank(sbert=enc.model)
    if not os.path.exists(args.ckpt):
        print(f"!!! ckpt {args.ckpt} not found — using random for both !!!")
    else:
        ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
        gen_trained.load_state_dict(ckpt["gen_state"])
        print(f"        loaded trained ckpt: {args.ckpt}")
    gen_trained.eval()

    print(f"[3/5] encoding {len(AUDIT_BRIEFS)} unseen briefs...")
    brief_emb = enc.encode(AUDIT_BRIEFS)
    if not isinstance(brief_emb, torch.Tensor):
        brief_emb = torch.tensor(brief_emb)
    brief_emb = brief_emb.float()

    print("[4/5] generating designs from both models...")
    torch.manual_seed(args.seed)
    with torch.no_grad():
        out_r = gen_random(brief_emb, noise_sigma=0.0)
    torch.manual_seed(args.seed)
    with torch.no_grad():
        out_t = gen_trained(brief_emb, noise_sigma=0.0)

    designs_r = gen_random.decode_strokes(out_r.stroke_tensor)
    designs_t = gen_trained.decode_strokes(out_t.stroke_tensor)
    for arr in (designs_r, designs_t):
        for i, strokes in enumerate(arr):
            end_at = next((j + 1 for j, s in enumerate(strokes) if s.is_end),
                          len(strokes))
            arr[i] = strokes[:end_at]

    print("[5/5] rendering UV sketches + grid...")
    paths_r, paths_t = [], []
    for i, brief in enumerate(AUDIT_BRIEFS):
        d_dir = os.path.join(designs_dir, f"v{i:02d}")
        os.makedirs(d_dir, exist_ok=True)
        # save JSON
        with open(os.path.join(d_dir, "strokes_random.json"), "w",
                   encoding="utf-8") as f:
            json.dump({"brief": brief,
                        "strokes": [stroke_to_dict(s) for s in designs_r[i]]},
                       f, ensure_ascii=False, indent=2)
        with open(os.path.join(d_dir, "strokes_trained.json"), "w",
                   encoding="utf-8") as f:
            json.dump({"brief": brief,
                        "strokes": [stroke_to_dict(s) for s in designs_t[i]]},
                       f, ensure_ascii=False, indent=2)
        # UV sketches
        pr = os.path.join(d_dir, "random.png")
        pt = os.path.join(d_dir, "trained.png")
        render_uv_sketch(designs_r[i], pr,
                          title=f"RANDOM | {brief[:48]}")
        render_uv_sketch(designs_t[i], pt,
                          title=f"TRAINED | {brief[:48]}")
        paths_r.append(pr)
        paths_t.append(pt)
        print(f"  v{i:02d}: random={len(designs_r[i])} trained={len(designs_t[i])}  "
              f"strokes  brief='{brief[:48]}'")

    # composite grid
    try:
        from PIL import Image, ImageDraw, ImageFont
        N = len(AUDIT_BRIEFS)
        # load sample to get size
        sample = Image.open(paths_r[0])
        W, H = sample.size
        W_thumb, H_thumb = 280, 420
        pad = 6
        col_h = H_thumb + pad
        cols = 2
        canvas_w = cols * (W_thumb + pad) + pad
        canvas_h = N * col_h + 30 + pad
        canvas = Image.new("RGB", (canvas_w, canvas_h), (245, 245, 247))
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        except Exception:
            font = ImageFont.load_default()
        draw.text((pad + W_thumb // 2, 8), "RANDOM (untrained)",
                  font=font, fill=(150, 60, 60), anchor="mm")
        draw.text((pad + W_thumb + pad + W_thumb // 2, 8), "TRAINED (Phase A2)",
                  font=font, fill=(60, 130, 60), anchor="mm")
        for i in range(N):
            y = 30 + i * col_h
            for c, p in enumerate([paths_r[i], paths_t[i]]):
                im = Image.open(p).convert("RGB")
                im.thumbnail((W_thumb, H_thumb), Image.LANCZOS)
                x = pad + c * (W_thumb + pad)
                ox = x + (W_thumb - im.width) // 2
                oy = y + (H_thumb - im.height) // 2
                canvas.paste(im, (ox, oy))
        grid_path = os.path.join(args.out_dir, "audit_grid.png")
        canvas.save(grid_path)
        print(f"\nwrote grid -> {grid_path}  ({canvas_w}x{canvas_h})")
    except Exception as exc:
        print(f"  (grid skipped: {exc})")

    # summary diff: how different are random vs trained outputs?
    print("\n[diff] random vs trained:")
    for i in range(len(AUDIT_BRIEFS)):
        n_diff_anchors = 0
        n_diff_colors = 0
        n = min(len(designs_r[i]), len(designs_t[i]))
        for j in range(n):
            if designs_r[i][j].start_anchor != designs_t[i][j].start_anchor:
                n_diff_anchors += 1
            if designs_r[i][j].color_id != designs_t[i][j].color_id:
                n_diff_colors += 1
        print(f"  v{i:02d}: in first {n} strokes — "
              f"diff start_anchors: {n_diff_anchors}/{n}, "
              f"diff colors: {n_diff_colors}/{n}")

    print("\n✓ audit complete")


if __name__ == "__main__":
    main()
