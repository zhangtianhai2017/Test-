"""
Phase A1 self-supervised tag-embedding pretraining (small).

Goal: verify the TagEmbeddingBank dynamics work end-to-end under SGD,
and that EMA-rollback doesn't deadlock learning. Not a long run —
500 iter @ batch 32 takes ~2-3 min on CPU.

Task:
  - Sample N tags from the bank
  - For each, the "positive brief" = the sbert encoding of its
    "{en} / {cn} — {definition}" string (already what we used at init)
  - Compute contrastive InfoNCE-style loss:
      similarity(brief_proj, tag_emb) maximized for the own tag,
      minimized for other tags in the batch
  - Optimize tag_bank.embeddings + brief_bias projection
  - After each step: call step_ema_rollback()
  - Log loss; save trained bank.

Output:
  tools/output/2026-05-27/p19_phase_a1/
    bank_pretrained.pt     trained TagEmbeddingBank state
    loss_curve.png         loss over iters
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
import torch.nn.functional as F

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from design_generator import SentenceTransformerEncoder       # noqa: E402
from tag_embeddings import TagEmbeddingBank, SBERT_DIM         # noqa: E402
from tag_data import TAGS                                       # noqa: E402
from v3.design_generator_v3 import BriefBias                    # noqa: E402


def build_per_tag_brief(t) -> str:
    """The 'positive brief' for tag t — same text used at sbert init."""
    parts = [f"{t.en} / {t.cn}"]
    if t.definition:
        parts.append(t.definition)
    return " — ".join(parts)


def info_nce_loss(brief_proj: torch.Tensor,        # (B, D)
                   tag_emb: torch.Tensor,            # (B, D)
                   tau: float = 0.07) -> torch.Tensor:
    """Symmetric InfoNCE: rows = brief, cols = tag, positives on diagonal."""
    bp = F.normalize(brief_proj, dim=-1)
    te = F.normalize(tag_emb, dim=-1)
    sim = bp @ te.t() / tau                          # (B, B)
    targets = torch.arange(bp.shape[0], device=bp.device)
    loss_b2t = F.cross_entropy(sim, targets)
    loss_t2b = F.cross_entropy(sim.t(), targets)
    return 0.5 * (loss_b2t + loss_t2b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=500)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--latent-dim", type=int, default=128)
    ap.add_argument("--out-dir", default="tools/output/2026-05-27/p19_phase_a1")
    ap.add_argument("--log-every", type=int, default=20)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    torch.manual_seed(0)

    # ─── setup ────────────────────────────────────────────────────────
    print("[setup] sbert (multilingual MiniLM)...")
    sbert_enc = SentenceTransformerEncoder()

    print("[setup] precomputing sbert(brief) for all 692 tags...")
    texts = [build_per_tag_brief(t) for t in TAGS]
    with torch.no_grad():
        all_brief_emb = sbert_enc.encode(texts)
    if not isinstance(all_brief_emb, torch.Tensor):
        all_brief_emb = torch.tensor(all_brief_emb)
    all_brief_emb = all_brief_emb.float()              # (N_TAGS, 384)
    print(f"        all_brief_emb shape: {tuple(all_brief_emb.shape)}")

    print("[setup] TagEmbeddingBank (random init, NOT sbert init)...")
    # NB: deliberately NOT calling init_from_sbert so Phase A1 actually
    # has work to do (otherwise loss is near 0 from step 1).
    bank = TagEmbeddingBank(dim=args.latent_dim, ema_alpha=1e-3)
    # zero out embeddings explicitly — random Parameter init is small std
    nn.init.normal_(bank.embeddings, std=0.05)
    bank.init_anchor.copy_(bank.embeddings.data)   # rollback target = init
    bank.is_initialized.fill_(True)

    print("[setup] BriefBias projection (sbert 384 → 128)...")
    brief_bias = BriefBias(SBERT_DIM, args.latent_dim)

    params = list(bank.parameters()) + list(brief_bias.parameters())
    opt = torch.optim.Adam(params, lr=args.lr)
    n_params = sum(p.numel() for p in params)
    print(f"        trainable params: {n_params:,}")

    # ─── training ─────────────────────────────────────────────────────
    n_tags = len(TAGS)
    losses = []
    t0 = time.time()

    print(f"\n[train] {args.iters} iters @ batch {args.batch} "
          f"on {n_tags} tags, lr={args.lr}")
    for it in range(args.iters):
        # sample distinct tag indices
        idx = torch.randperm(n_tags)[:args.batch]
        brief_emb = all_brief_emb[idx]              # (B, 384)
        tag_emb = bank.embeddings[idx]              # (B, D)

        brief_proj = brief_bias(brief_emb)          # (B, D)
        loss = info_nce_loss(brief_proj, tag_emb, tau=0.07)

        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 5.0)
        opt.step()
        bank.step_ema_rollback()

        losses.append(loss.item())

        if (it + 1) % args.log_every == 0 or it == 0:
            recent = losses[-args.log_every:]
            mean_recent = sum(recent) / len(recent)
            print(f"  iter {it+1:>4}  loss={loss.item():.4f}  "
                  f"(mean[-{len(recent)}] {mean_recent:.4f})")

    elapsed = time.time() - t0
    print(f"\n[train] done in {elapsed:.1f}s  "
          f"({args.iters / elapsed:.1f} iter/s)")
    print(f"  loss[0]    = {losses[0]:.4f}")
    print(f"  loss[mid]  = {losses[len(losses)//2]:.4f}")
    print(f"  loss[last] = {losses[-1]:.4f}")

    # ─── save ─────────────────────────────────────────────────────────
    ckpt_path = os.path.join(args.out_dir, "bank_pretrained.pt")
    torch.save({"bank_state": bank.state_dict(),
                 "brief_bias_state": brief_bias.state_dict(),
                 "losses": losses,
                 "args": vars(args)}, ckpt_path)
    print(f"\nsaved checkpoint -> {ckpt_path}")

    # loss curve png
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(losses, alpha=0.4, label="loss")
        # smoothed
        win = max(10, len(losses) // 50)
        if len(losses) > win:
            import numpy as np
            ker = np.ones(win) / win
            smoothed = np.convolve(losses, ker, mode="valid")
            ax.plot(range(win - 1, len(losses)), smoothed, lw=2,
                     label=f"smooth (w={win})")
        ax.set_xlabel("iter")
        ax.set_ylabel("InfoNCE loss")
        ax.set_title(f"Phase A1 tag pretraining ({n_tags} tags, "
                       f"{args.iters} iter @ B={args.batch})")
        ax.legend()
        ax.grid(alpha=0.3)
        plot_path = os.path.join(args.out_dir, "loss_curve.png")
        fig.savefig(plot_path, bbox_inches="tight", dpi=100)
        plt.close(fig)
        print(f"saved plot       -> {plot_path}")
    except Exception as exc:
        print(f"  (plot skipped: {exc})")

    summary = {
        "iters": args.iters,
        "batch": args.batch,
        "lr": args.lr,
        "elapsed_sec": elapsed,
        "loss_first_5_mean": sum(losses[:5]) / 5,
        "loss_last_5_mean": sum(losses[-5:]) / 5,
        "loss_drop_ratio": (sum(losses[:5]) / 5) / max(1e-6, sum(losses[-5:]) / 5),
        "n_params": n_params,
    }
    summary_path = os.path.join(args.out_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"saved summary    -> {summary_path}")
    print(f"\n  loss dropped {summary['loss_first_5_mean']:.3f} "
          f"-> {summary['loss_last_5_mean']:.3f}  "
          f"(ratio {summary['loss_drop_ratio']:.2f}x)")
    if summary["loss_drop_ratio"] > 2.0:
        print("  ✓ EMA-rollback did NOT deadlock learning")
    else:
        print("  ⚠ loss did not drop ≥2x — investigate")


if __name__ == "__main__":
    main()
