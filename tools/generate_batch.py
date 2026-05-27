"""Inference-only generator: load a trained checkpoint and render a
batch of designs. No training, no judge, no RL.

Usage:
    python tools/generate_batch.py \
        --checkpoint tools/output/2026-05-20/1527_rl_run/generator_final.pt \
        --out-dir /tmp/showcase \
        --n 8

Briefs default to a mix from DEFAULT_BRIEFS spanning archetypes/styles
so you see variety, not 8 of the same thing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch

# We do NOT import iter.capture here — each design is rendered in a fresh
# subprocess via tools/_render_one_outfit.py to dodge Filament+OSMesa
# state leakage on multi-view + multi-design same-process runs.
import subprocess

from outfit import outfit_to_genome
from iter.params import IterParams
from design_generator import (DesignGenerator, MockTextEncoder,
                                 SentenceTransformerEncoder)
from train_loop import DEFAULT_BRIEFS
from rl_runner import ConfigToOutfit, get_id_lists

# View(s) rendered per design. Simplified back to 1-view 2026-05-23
# — 4-view subprocess isolation worked but added ~20s/design and made
# debugging harder. Front view is enough for the current iteration
# loop. Training path already uses 1-view via rl_runner_wsl.py.
VIEW_NAMES = ["01_front"]


# A curated 8-brief showcase spanning archetypes, palettes, and styles.
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
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--hidden-dim", type=int, default=256)
    ap.add_argument("--n-trunk-layers", type=int, default=8,
                    help="Number of trunk ResidualMLPBlocks. Must match "
                         "the checkpoint (8 = old runs, 12 = 2026-05-27 "
                         "deeper-trunk experiment).")
    ap.add_argument("--text-dim", type=int, default=384)
    ap.add_argument("--encoder", choices=["mock", "sbert"], default="mock",
                    help="Must match the encoder used during training. "
                         "Old checkpoints (before 2026-05-20 18:00) = mock; "
                         "anti-collapse runs = sbert.")
    # Default to stochastic: argmax hides any softmax spread the
    # entropy + KL anti-collapse machinery created during training.
    # An 8-iter A/B at 1820_rl_run / 2026-05-20 showed argmax giving
    # 8 identical designs but stochastic giving 5 distinct ones from
    # the SAME checkpoint.
    ap.add_argument("--argmax", dest="stochastic", action="store_false",
                    default=True,
                    help="Use argmax for discrete picks (deterministic, "
                         "but hides softmax spread). Default: stochastic.")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    print(f"checkpoint: {args.checkpoint}")
    print(f"out_dir:    {args.out_dir}")
    print(f"n:          {args.n}")
    print(f"stochastic: {args.stochastic}")

    # Build generator + load weights. Encoder MUST match the one used
    # during the checkpoint's training, else brief->embed mapping
    # differs and the generator is fed nonsense.
    if args.encoder == "sbert":
        enc = SentenceTransformerEncoder()
        text_dim = enc.dim
        print(f"encoder:    SentenceTransformer (dim={text_dim})")
    else:
        text_dim = args.text_dim
        enc = MockTextEncoder(dim=text_dim)
        print(f"encoder:    MockTextEncoder (sha256, dim={text_dim})")
    gen = DesignGenerator(text_dim=text_dim, hidden_dim=args.hidden_dim,
                          n_hidden_layers=args.n_trunk_layers)
    ckpt = torch.load(args.checkpoint, map_location="cpu")
    sd = ckpt.get("gen_state") or ckpt.get("generator_state") or ckpt
    # Try strict first; on shape mismatch (head expansion) fall back
    # to per-tensor load skipping mismatched heads (they reinitialize
    # to random — softmax stays roughly uniform on those dims).
    try:
        gen.load_state_dict(sd, strict=True)
        load_mode = "strict"
        skipped = []
    except RuntimeError:
        own = gen.state_dict()
        skipped = []
        filtered = {}
        for k, v in sd.items():
            if k in own and own[k].shape == v.shape:
                filtered[k] = v
            else:
                skipped.append(
                    f"{k} (ckpt={tuple(v.shape) if hasattr(v,'shape') else '?'} "
                    f"vs model={tuple(own[k].shape) if k in own else 'missing'})")
        gen.load_state_dict(filtered, strict=False)
        load_mode = f"partial — {len(skipped)} tensor(s) reinitialized"
    gen.eval()
    print(f"loaded checkpoint (was iter {ckpt.get('iter', '?')}; {load_mode})")
    for s in skipped[:8]:
        print(f"  reinit: {s}")

    # Pick briefs
    briefs = (SHOWCASE_BRIEFS * ((args.n + 7) // 8))[: args.n]
    print(f"\nbriefs:")
    for i, b in enumerate(briefs):
        print(f"  {i}: {b}")

    # Generate config
    emb = enc.encode(briefs)
    with torch.no_grad():
        config = gen(emb)
        picks: dict[str, torch.Tensor] = {}
        for name in gen.discrete_sizes:
            logits = config[f"{name}_logits"]
            if args.stochastic:
                import torch.nn.functional as F
                probs = F.softmax(logits, dim=-1)
                sampled = torch.multinomial(probs, num_samples=1).squeeze(-1)
            else:
                sampled = logits.argmax(dim=-1)
            picks[name] = sampled.detach().cpu()

    # Render — each design in its own subprocess to avoid Filament leak
    id_lists = get_id_lists()
    converter = ConfigToOutfit(id_lists)
    inner = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "_render_one_outfit.py")

    paths: list[str] = []
    t0 = time.time()
    for i in range(args.n):
        sub = os.path.join(args.out_dir, f"v{i:02d}")
        os.makedirs(sub, exist_ok=True)
        outfit = converter(config, picks, i)
        outfit_path = os.path.join(sub, "outfit.json")
        with open(outfit_path, "w", encoding="utf-8") as f:
            json.dump({
                "brief": briefs[i],
                "archetype": outfit.archetype,
                "slot_assignments": [
                    {"slot_name": a.slot_name,
                     "library_id": a.library_id,
                     "local_params": dict(a.local_params)}
                    for a in outfit.slot_assignments],
                "global_design": dict(outfit.global_design),
            }, f, indent=2, ensure_ascii=False)
        # Spawn fresh subprocess (clean Filament state)
        proc = subprocess.run(
            [sys.executable, inner, outfit_path, sub] + VIEW_NAMES,
            capture_output=True, text=True, timeout=120)
        # NOTE: ignore exit code. Filament+OSMesa segfaults on Python
        # interpreter teardown but the renders finish first. We trust
        # the PNG files on disk, not the exit status.
        from PIL import Image, ImageDraw
        view_pngs = [os.path.join(sub, f"{v}.png") for v in VIEW_NAMES]
        view_pngs = [p for p in view_pngs if os.path.isfile(p)]
        if not view_pngs:
            print(f"  v{i:02d}  no PNGs produced; subprocess exit "
                  f"{proc.returncode}, stderr: {proc.stderr[-300:]}")
            paths.append("")
            continue
        if len(view_pngs) == 1:
            # Single view — no contact sheet, just use the PNG directly.
            paths.append(view_pngs[0])
            print(f"  v{i:02d}  {briefs[i][:40]:40s}  ->  {view_pngs[0]}")
            continue
        if view_pngs:
            imgs = [Image.open(p).convert("RGB") for p in view_pngs]
            thumb_w = 360
            thumb_h = int(thumb_w * imgs[0].size[1] / imgs[0].size[0])
            cols = 2
            rows = (len(imgs) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * thumb_w,
                                       rows * (thumb_h + 24)), (24, 24, 24))
            draw = ImageDraw.Draw(sheet)
            for j, (im, p) in enumerate(zip(imgs, view_pngs)):
                r, c = divmod(j, cols)
                x0, y0 = c * thumb_w, r * (thumb_h + 24)
                draw.text((x0 + 6, y0 + 4),
                          os.path.basename(p).replace(".png", ""),
                          fill=(255, 220, 100))
                sheet.paste(im.resize((thumb_w, thumb_h)), (x0, y0 + 22))
            sheet_path = os.path.join(sub, "contact_sheet.png")
            sheet.save(sheet_path)
            paths.append(sheet_path)
            print(f"  v{i:02d}  {briefs[i][:40]:40s}  -> "
                  f"{len(view_pngs)} views, sheet {sheet_path}")
        else:
            print(f"  v{i:02d}  no view PNGs produced")
            paths.append("")
    dt = time.time() - t0
    print(f"\nrendered {sum(1 for p in paths if p)}/{args.n} in {dt:.1f}s")


if __name__ == "__main__":
    main()
