"""
Phase A3 FULL — REINFORCE on manuf + vLLM Qwen visual judge.

Combines:
  - validate_garment compliance (manuf reward, free)
  - Qwen2.5-VL-7B aesthetic + brief_match (visual reward, ~1.5s/call)

Per-sample pipeline:
  tokens → garment → render PNG → judge → reward

reward = -manuf_violations + α * (judge_aesthetic + judge_brief_match) / 20

Why two terms:
  - manuf signal is dense (every sample evaluable in microseconds)
  - judge signal is sparse + slow but anchors aesthetic/semantic quality
  - α balances: high α = aesthetic focus, low α = compliance focus

Pipeline reuses tools/v3/full_chain_render.py and tools/vision_judge.py.

Output:
  tools/output/2026-05-28/p42_full_rl/
    decoder_rl.pt
    reward_curve.png
    sample_renders/iter_NNN/v00..vK.png  (every N iters)
    summary.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import torch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

from design_generator import SentenceTransformerEncoder
from v3.design_generator_v3 import DesignGeneratorV3
from v3.tokens_to_garment import tokens_to_garment
from v3.full_chain_render import render_design_3d
from v3.phase_a3_manuf_rl import (
    stochastic_sample_and_logprob, RL_BRIEFS,
)
from garment_state import validate_garment
from vision_judge import make_judge


def reward_one_design(tokens, brief: str, judge, png_dir: str,
                       sample_idx: int,
                       judge_weight: float = 0.5) -> tuple[float, dict]:
    """Render + judge one design. Return (reward, breakdown_dict)."""
    # validate_garment for manuf reward
    g = tokens_to_garment(tokens)
    g_before = len(g.pieces)
    g2 = validate_garment(g)
    g_after = len(g2.pieces)
    n_dropped = g_before - g_after
    warns = g2.metadata.get("validation_warnings", [])
    manuf_reward = -(float(n_dropped) + 0.5 * float(len(warns)))

    # render + judge
    png_path = os.path.join(png_dir, f"v{sample_idx:02d}.png")
    try:
        render_design_3d(tokens, png_path, verbose=False)
        if os.path.exists(png_path) and os.path.getsize(png_path) > 1000:
            jr = judge.judge(png_path, brief=brief)
            # combine aesthetic + brief_match (each 0-10)
            judge_score = 0.5 * (jr.aesthetic_score + jr.brief_match)
            judge_reward = (judge_score - 5.0) / 5.0   # remap to [-1, +1]
        else:
            judge_score = 0.0
            judge_reward = -1.0   # render failure penalty
    except Exception as e:
        judge_score = 0.0
        judge_reward = -1.0
        jr = None

    total = manuf_reward + judge_weight * judge_reward
    return total, {
        "manuf": manuf_reward,
        "judge_score_raw": judge_score,
        "judge_reward": judge_reward,
        "n_dropped": n_dropped,
        "n_warnings": len(warns),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init-ckpt",
                    default="tools/output/2026-05-28/p40_phase_a2_v2lib/decoder_pretrained.pt")
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--out-dir", default="tools/output/2026-05-28/p42_full_rl")
    ap.add_argument("--baseline-momentum", type=float, default=0.9)
    ap.add_argument("--sigma-cont", type=float, default=0.05)
    ap.add_argument("--temp-cat", type=float, default=1.2)
    ap.add_argument("--judge-weight", type=float, default=0.5)
    ap.add_argument("--save-sample-every", type=int, default=10)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    torch.manual_seed(0)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[device] {device}")

    print("[setup] sbert + gen + load ckpt...")
    enc = SentenceTransformerEncoder()
    gen = DesignGeneratorV3()
    gen.init_tag_bank(sbert=enc.model)
    ckpt = torch.load(args.init_ckpt, map_location="cpu", weights_only=False)
    gen.load_state_dict(ckpt["gen_state"], strict=False)
    gen = gen.to(device)

    print("[setup] vLLM judge...")
    judge = make_judge("vllm")

    brief_emb = enc.encode(RL_BRIEFS)
    if not isinstance(brief_emb, torch.Tensor):
        brief_emb = torch.tensor(brief_emb)
    brief_emb = brief_emb.float().to(device)

    opt = torch.optim.Adam(gen.parameters(), lr=args.lr)

    print(f"\n[train] {args.iters} iters @ batch {args.batch} (slow: ~{args.batch * 2}s/iter)")
    print(f"  judge_weight = {args.judge_weight}")

    baseline = 0.0
    history = {"reward_mean": [], "manuf_mean": [], "judge_raw_mean": [],
                "n_dropped_mean": [], "rl_loss": []}
    t0 = time.time()

    for it in range(args.iters):
        # sample briefs for this iter
        idx = torch.randint(0, len(RL_BRIEFS), (args.batch,), device=device)
        be = brief_emb[idx]
        briefs_this_iter = [RL_BRIEFS[i] for i in idx.cpu().tolist()]

        # forward + stochastic sample
        out = gen(be, noise_sigma=1.0)
        sampled_tensor, log_probs, sampled_lengths = stochastic_sample_and_logprob(
            out.stroke_tensor, out.length_logits,
            sigma_cont=args.sigma_cont, temp_cat=args.temp_cat)

        # decode to token lists
        from v3.token_tensor import decode_batch
        decoded = decode_batch(sampled_tensor.detach().cpu())
        token_lists = []
        for b in range(args.batch):
            n = int(sampled_lengths[b].item()) + 1
            tlist = decoded[b][:max(1, n)]
            if tlist:
                tlist[-1].is_end = True
            token_lists.append(tlist)

        # save renders this iter?
        sample_dir = (os.path.join(args.out_dir, f"sample_renders/iter_{it+1:03d}")
                       if (it + 1) % args.save_sample_every == 0 or it == 0
                       else os.path.join(args.out_dir, "_tmp_render"))
        os.makedirs(sample_dir, exist_ok=True)

        # compute reward per sample (render + judge sequentially)
        rewards = []
        manuf_vals = []
        judge_vals = []
        dropped_vals = []
        for b in range(args.batch):
            r, bd = reward_one_design(token_lists[b], briefs_this_iter[b],
                                       judge, sample_dir, b,
                                       judge_weight=args.judge_weight)
            rewards.append(r)
            manuf_vals.append(bd["manuf"])
            judge_vals.append(bd["judge_score_raw"])
            dropped_vals.append(bd["n_dropped"])
        reward = torch.tensor(rewards, dtype=torch.float32, device=device)

        # baseline + advantage
        batch_mean = float(reward.mean().item())
        baseline = args.baseline_momentum * baseline + \
                    (1 - args.baseline_momentum) * batch_mean
        advantage = reward - baseline

        rl_loss = -(advantage.detach() * log_probs).mean()
        opt.zero_grad()
        rl_loss.backward()
        torch.nn.utils.clip_grad_norm_(gen.parameters(), 1.0)
        opt.step()

        history["reward_mean"].append(batch_mean)
        history["manuf_mean"].append(sum(manuf_vals) / len(manuf_vals))
        history["judge_raw_mean"].append(sum(judge_vals) / len(judge_vals))
        history["n_dropped_mean"].append(sum(dropped_vals) / len(dropped_vals))
        history["rl_loss"].append(float(rl_loss.item()))

        elapsed = time.time() - t0
        print(f"  iter {it+1:>3}  reward={batch_mean:+.2f}  "
              f"manuf={history['manuf_mean'][-1]:+.2f}  "
              f"judge_raw={history['judge_raw_mean'][-1]:.2f}/10  "
              f"dropped={history['n_dropped_mean'][-1]:.1f}  "
              f"({elapsed:.0f}s elapsed)",
              flush=True)

    total_elapsed = time.time() - t0
    print(f"\n[train] done in {total_elapsed:.0f}s")
    n_first = min(5, len(history["reward_mean"]))
    n_last = min(5, len(history["reward_mean"]))
    print(f"  reward[first {n_first}]  = {sum(history['reward_mean'][:n_first])/n_first:+.2f}")
    print(f"  reward[last {n_last}]   = {sum(history['reward_mean'][-n_last:])/n_last:+.2f}")
    print(f"  judge[first {n_first}]   = {sum(history['judge_raw_mean'][:n_first])/n_first:.2f}/10")
    print(f"  judge[last {n_last}]    = {sum(history['judge_raw_mean'][-n_last:])/n_last:.2f}/10")

    # save ckpt + history
    torch.save({"gen_state": gen.state_dict(), "history": history,
                 "args": vars(args)},
                os.path.join(args.out_dir, "decoder_rl.pt"))
    print(f"\nsaved ckpt -> {args.out_dir}/decoder_rl.pt")

    # plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        for ax, key, title in [
            (axes[0, 0], "reward_mean",   "Total reward (manuf + judge)"),
            (axes[0, 1], "judge_raw_mean", "Qwen judge score (0-10, higher better)"),
            (axes[1, 0], "manuf_mean",    "Manuf reward (0 = clean)"),
            (axes[1, 1], "n_dropped_mean","Pieces dropped per design"),
        ]:
            ax.plot(history[key], alpha=0.5)
            if len(history[key]) > 5:
                import numpy as np
                w = max(3, len(history[key]) // 10)
                k = np.ones(w) / w
                smooth = np.convolve(history[key], k, mode="valid")
                ax.plot(range(w-1, len(history[key])), smooth, lw=2)
            ax.set_title(title); ax.grid(alpha=0.3)
            ax.set_xlabel("iter")
        plt.savefig(os.path.join(args.out_dir, "reward_curve.png"),
                    bbox_inches="tight", dpi=100)
        plt.close(fig)
        print(f"saved plot -> {args.out_dir}/reward_curve.png")
    except Exception as e:
        print(f"  (plot skipped: {e})")

    with open(os.path.join(args.out_dir, "summary.json"), "w") as f:
        json.dump({"iters": args.iters, "batch": args.batch,
                    "elapsed_sec": total_elapsed,
                    "reward_first": sum(history["reward_mean"][:n_first])/n_first,
                    "reward_last": sum(history["reward_mean"][-n_last:])/n_last,
                    "judge_first": sum(history["judge_raw_mean"][:n_first])/n_first,
                    "judge_last": sum(history["judge_raw_mean"][-n_last:])/n_last}, f, indent=2)


if __name__ == "__main__":
    main()
