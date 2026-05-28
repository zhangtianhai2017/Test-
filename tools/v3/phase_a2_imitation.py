"""
Phase A2 imitation learning smoke.

Teacher: the 2 hand-crafted reference designs (classical_bikini +
avant_garde_harness) — augmented with brief paraphrases to give the
decoder some variety to condition on.

Goal: verify the StrokeTransformerDecoder can learn to reproduce
teacher stroke sequences when given the corresponding brief. This
is the Phase A2 milestone from docs/design/2026-05-27_schema_redesign_v3.md
§5 — a critical validation before Phase A3 (RL fine-tune).

Output:
  tools/output/2026-05-27/p20_phase_a2/
    decoder_pretrained.pt
    loss_curve.png
    teacher_vs_decoder.png   (side-by-side UV sketches)
    summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import torch
import torch.nn as nn

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from design_generator import SentenceTransformerEncoder         # noqa: E402
from v3.design_generator_v3 import DesignGeneratorV3              # noqa: E402
from v3.stroke_schema import (                                     # noqa: E402
    all_reference_designs, Stroke, MAX_STROKES,
)
from v3.stroke_tensor import encode_design, STROKE_TENSOR_DIM      # noqa: E402
from v3.stroke_renderer import render_uv_sketch                    # noqa: E402


# Teacher brief paraphrases — 4 per reference design = 28 total pairs
TEACHER_BRIEFS_BY_NAME: dict[str, list[str]] = {
    "classical_bikini": [
        "classic triangle bikini, simple, ivory white",
        "古典三角比基尼, 象牙白, 经典款",
        "minimalist white triangle two-piece, beach",
        "ivory classical 4-stroke bikini, French elegant",
    ],
    "avant_garde_harness": [
        "avant-garde black cross-body harness, two diagonals",
        "前卫风黑色交叉束带, 双肩到反侧胯",
        "BDSM-inspired black multi-strap harness",
        "Mugler-inspired diagonal harness, dramatic black",
    ],
    "sculptural_one_piece": [
        "sculptural orange one-piece, swooping curves, van Herpen style",
        "雕塑感橙色连体, Iris van Herpen 风, 大幅曲线",
        "biomorphic orange monokini, sculpted silhouette",
        "high-art orange one-piece with bone-form swoops",
    ],
    "cyberpunk_cage": [
        "cyberpunk magenta + black cage harness, multi-strap",
        "赛博朋克紫红+黑色多绳笼形束带",
        "neon-pink BDSM cage swim, multi-axis straps",
        "cybergoth cage bikini, magenta + void black",
    ],
    "athletic_sports": [
        "athletic sports bikini, neon yellow, full-coverage",
        "运动型比基尼, 荧光黄, 高覆盖",
        "high-performance sport swim, neon yellow, thick straps",
        "race-ready neon yellow sport bikini, boyshort bottom",
    ],
    "ethnic_body_chain": [
        "ethnic gold body chain + burgundy triangle cups",
        "民族风金色身链+酒红三角杯",
        "Berber-inspired gold body jewelry with burgundy bikini",
        "Aztec body chain swim, gold + blood-red triangles",
    ],
    "draped_wrap": [
        "draped one-shoulder mauve wrap, sari-inspired, asymmetric",
        "单肩垂坠藕紫色围裹, 莎丽风, 不对称",
        "asymmetric mauve draped wrap, single shoulder",
        "ethereal mauve toga drape across body, single shoulder",
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--kl-weight", type=float, default=1e-3)
    ap.add_argument("--out-dir", default="tools/output/2026-05-27/p20_phase_a2")
    ap.add_argument("--log-every", type=int, default=50)
    ap.add_argument("--device", default="auto",
                    choices=["auto", "cuda", "cpu"])
    args = ap.parse_args()

    device = (("cuda" if torch.cuda.is_available() else "cpu")
              if args.device == "auto" else args.device)
    print(f"[device] {device}")

    os.makedirs(args.out_dir, exist_ok=True)
    torch.manual_seed(0)

    # ─── setup ────────────────────────────────────────────────────────
    print("[setup] sbert...")
    enc = SentenceTransformerEncoder()

    print("[setup] DesignGeneratorV3 + init tag bank...")
    gen = DesignGeneratorV3()
    gen.init_tag_bank(sbert=enc.model)
    gen = gen.to(device)

    # ─── teacher data ────────────────────────────────────────────────
    print("[data] encoding teacher designs...")
    refs = all_reference_designs()
    print(f"        {len(refs)} reference designs:")
    encoded_by_name = {}
    for name, strokes in refs.items():
        et, em = encode_design(strokes)
        encoded_by_name[name] = (et, em)
        print(f"          {name:<22} {len(strokes)} strokes")

    # Build paired (brief, target_tensor, target_mask) dataset
    all_briefs, all_targets, all_masks, all_names = [], [], [], []
    for name, briefs in TEACHER_BRIEFS_BY_NAME.items():
        et, em = encoded_by_name[name]
        for b in briefs:
            all_briefs.append(b)
            all_targets.append(et)
            all_masks.append(em)
            all_names.append(name)
    target_stack = torch.stack(all_targets).to(device)     # (N, MAX_STROKES, D)
    mask_stack = torch.stack(all_masks).to(device)         # (N, MAX_STROKES)
    print(f"        teacher set: {len(all_briefs)} (brief, design) pairs "
          f"({len(refs)} designs × ~4 paraphrases each)")

    # Pre-encode all teacher briefs
    print("[data] encoding teacher briefs via sbert...")
    brief_embs = enc.encode(all_briefs)
    if not isinstance(brief_embs, torch.Tensor):
        brief_embs = torch.tensor(brief_embs)
    brief_embs = brief_embs.float().to(device)        # (N, 384)

    N = brief_embs.shape[0]
    n_params = sum(p.numel() for p in gen.parameters() if p.requires_grad)
    print(f"[setup] trainable params: {n_params:,}")
    opt = torch.optim.Adam(gen.parameters(), lr=args.lr)

    # ─── training ─────────────────────────────────────────────────────
    print(f"\n[train] {args.iters} iters @ batch {args.batch}  lr={args.lr}")
    losses = []
    losses_decomp = {k: [] for k in [
        "total", "start", "end", "color", "uv_free", "bezier",
        "width", "tension", "material", "decoration", "is_end", "kl",
    ]}
    t0 = time.time()
    gen.train()
    for it in range(args.iters):
        # sample a batch from teacher set
        idx = torch.randperm(N, device=device)[:args.batch]
        be = brief_embs[idx]
        tt = target_stack[idx]
        tm = mask_stack[idx]

        out = gen(be, teacher_tokens=tt, noise_sigma=0.5)
        loss_d = gen.imitation_loss(out.stroke_tensor, tt, tm)
        kl = gen.kl_loss(out.style_mu, out.style_logvar)
        loss = loss_d["total"] + args.kl_weight * kl

        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(gen.parameters(), 2.0)
        opt.step()
        gen.tag_bank.step_ema_rollback()

        losses.append(loss.item())
        for k, v in loss_d.items():
            losses_decomp[k].append(v.item())
        losses_decomp["kl"].append(kl.item())

        if (it + 1) % args.log_every == 0 or it == 0:
            print(f"  iter {it+1:>4}  total={loss.item():.3f}  "
                  f"start={loss_d['start'].item():.2f}  "
                  f"end={loss_d['end'].item():.2f}  "
                  f"color={loss_d['color'].item():.2f}  "
                  f"is_end={loss_d['is_end'].item():.2f}  "
                  f"kl={kl.item():.2f}")

    elapsed = time.time() - t0
    print(f"\n[train] done in {elapsed:.1f}s "
          f"({args.iters / elapsed:.1f} iter/s)")
    print(f"  total[0]    = {losses[0]:.3f}")
    print(f"  total[mid]  = {losses[len(losses)//2]:.3f}")
    print(f"  total[last] = {losses[-1]:.3f}")

    # ─── eval: have the (now-trained) decoder produce designs for the
    # first brief of each reference, and compare ─────────────────────
    print("\n[eval] generating trained decoder output for all teachers...")
    gen.eval()
    eval_briefs = [briefs[0] for briefs in TEACHER_BRIEFS_BY_NAME.values()]
    eval_names = list(TEACHER_BRIEFS_BY_NAME.keys())
    eval_emb = enc.encode(eval_briefs)
    if not isinstance(eval_emb, torch.Tensor):
        eval_emb = torch.tensor(eval_emb)
    eval_emb = eval_emb.float().to(device)
    with torch.no_grad():
        out_eval = gen(eval_emb, noise_sigma=0.0)   # deterministic for eval
    decoded_eval = gen.decode_strokes(out_eval.stroke_tensor.cpu())
    for i, (b, strokes) in enumerate(zip(eval_briefs, decoded_eval)):
        end_at = next((j + 1 for j, s in enumerate(strokes) if s.is_end),
                      len(strokes))
        decoded_eval[i] = strokes[:end_at]
        print(f"  {b[:50]:<50}  {len(decoded_eval[i])} strokes")

    # render comparison: teacher (left) vs decoder (right) for all 7
    print("[eval] rendering teacher-vs-decoder UV sketches for all refs...")
    for name, brief, decoder_strokes in zip(eval_names, eval_briefs, decoded_eval):
        teacher_strokes = refs[name]
        out_teacher = os.path.join(args.out_dir, f"{name}_teacher.png")
        out_decoder = os.path.join(args.out_dir, f"{name}_decoder.png")
        render_uv_sketch(teacher_strokes, out_teacher,
                          title=f"{name} TEACHER ({len(teacher_strokes)} strokes)")
        render_uv_sketch(decoder_strokes, out_decoder,
                          title=f"{name} DECODER ({len(decoder_strokes)} strokes)\n{brief[:50]}")
        print(f"  ✓ {name}: T={len(teacher_strokes)}  D={len(decoder_strokes)}")

    # ─── save ────────────────────────────────────────────────────────
    ckpt = os.path.join(args.out_dir, "decoder_pretrained.pt")
    torch.save({"gen_state": gen.state_dict(),
                 "losses": losses, "losses_decomp": losses_decomp,
                 "args": vars(args)}, ckpt)
    print(f"\nsaved ckpt -> {ckpt}")

    # loss plots
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 2, figsize=(14, 8))
        ax = axes[0, 0]
        ax.plot(losses_decomp["total"], alpha=0.5)
        ax.set_title("total loss"); ax.set_yscale("log")
        ax.grid(alpha=0.3)
        ax = axes[0, 1]
        for k in ("start", "end", "color"):
            ax.plot(losses_decomp[k], label=k, alpha=0.7)
        ax.set_title("categorical CE losses"); ax.legend()
        ax.set_yscale("log"); ax.grid(alpha=0.3)
        ax = axes[1, 0]
        for k in ("bezier", "width", "tension", "uv_free"):
            ax.plot(losses_decomp[k], label=k, alpha=0.7)
        ax.set_title("continuous MSE losses"); ax.legend()
        ax.set_yscale("log"); ax.grid(alpha=0.3)
        ax = axes[1, 1]
        for k in ("material", "decoration", "is_end", "kl"):
            ax.plot(losses_decomp[k], label=k, alpha=0.7)
        ax.set_title("mixture/binary/KL losses"); ax.legend()
        ax.set_yscale("log"); ax.grid(alpha=0.3)
        for a in axes.flat:
            a.set_xlabel("iter")
        fig.suptitle(
            f"Phase A2 imitation learning ({args.iters} iter @ B={args.batch})")
        plot_path = os.path.join(args.out_dir, "loss_curve.png")
        fig.savefig(plot_path, bbox_inches="tight", dpi=100)
        plt.close(fig)
        print(f"saved plot -> {plot_path}")
    except Exception as exc:
        print(f"  (plot skipped: {exc})")

    summary = {
        "iters": args.iters,
        "batch": args.batch,
        "lr": args.lr,
        "elapsed_sec": elapsed,
        "loss_first_5_mean": sum(losses[:5]) / 5,
        "loss_last_5_mean": sum(losses[-5:]) / 5,
        "loss_drop_ratio": sum(losses[:5]) / max(1e-6, sum(losses[-5:])),
        "n_teachers": len(refs),
        "n_paired": len(all_briefs),
        "decoded_strokes_per_ref": {
            name: len(d) for name, d in zip(eval_names, decoded_eval)
        },
        "teacher_strokes_per_ref": {
            name: len(s) for name, s in refs.items()
        },
    }
    with open(os.path.join(args.out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nloss {summary['loss_first_5_mean']:.2f} -> "
          f"{summary['loss_last_5_mean']:.2f}  "
          f"(ratio {summary['loss_drop_ratio']:.1f}x)")


if __name__ == "__main__":
    main()
