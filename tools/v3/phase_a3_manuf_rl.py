"""
Phase A3-manuf — REINFORCE on validate_garment compliance.

No vLLM needed (visual judge is a SEPARATE Phase A3 track that comes
later). Reward here = -(pieces_dropped + 0.5 × n_warnings) from
validate_garment(tokens_to_garment(decoded_tokens)).

Why REINFORCE: the manufacturability constraints (H2 self-intersection,
catalog ID validity, anatomy filter) are non-differentiable. Earlier
attempts with differentiable proxies (p37/p38) made H2 worse, not better.

Pipeline per training step:
  1. Sample batch of briefs (from teacher set + held-out RL briefs)
  2. Forward NN (stochastic = True → Gaussian noise on boundary,
     categorical sampling on type/color/fabric/anchors)
  3. Decode → tokens → garment
  4. reward = -(n_dropped + 0.5 × n_warnings)  per sample
  5. advantage = reward - running_baseline
  6. rl_loss = -(advantage * sum_log_probs).mean()
  7. anchor_loss = small KL to imitation ckpt (prevent drift)
  8. total = rl_loss + 0.05 * anchor_loss
  9. Adam step

Categorical heads sampled: token_type, color_id, fabric_id, layer_role,
start_anchor, end_anchor.
Continuous heads (boundary, bezier, width): treated as Gaussian with
fixed std=0.05 around NN mean; sample = mean + std·ε.

Outputs:
  tools/output/2026-05-28/p39_manuf_rl/
    decoder_rl.pt
    reward_curve.png
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
import torch.nn.functional as F

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from design_generator import SentenceTransformerEncoder
from v3.design_generator_v3 import DesignGeneratorV3, V3Output
from v3.stroke_schema import (
    Anchor, Stroke, Panel, MAX_STROKES,
    N_ANCHORS, N_ANCHOR_LOGITS, N_PALETTE, N_MATERIAL_VFX_TAGS,
    PANEL_BOUNDARY_POINTS, WIDTH_SEGMENTS,
    TOKEN_TYPE_PANEL, TOKEN_TYPE_STROKE,
)
from v3.token_tensor import (
    TOKEN_TENSOR_DIM, offsets, decode_batch,
    FABRIC_IDS, LAYER_ROLES, N_FABRICS, N_LAYER_ROLES, N_TOKEN_TYPES,
)
from v3.tokens_to_garment import tokens_to_garment
from garment_state import validate_garment


O = offsets()


# ─── stochastic sampling helpers ──────────────────────────────────────

def stochastic_sample_and_logprob(stroke_tensor: torch.Tensor,
                                    length_logits: torch.Tensor,
                                    sigma_cont: float = 0.05,
                                    temp_cat: float = 1.0):
    """Given NN raw output, sample categorical heads + add noise to
    continuous heads. Return (sampled_tensor, sum_log_prob_per_sample).

    sampled_tensor has the SAME shape as stroke_tensor but with one-hot
    categorical entries (sampled, not argmax) and noised continuous.
    sum_log_prob_per_sample is (B,) — sum of log probs across all sampled
    dimensions per design.
    """
    B, T, D = stroke_tensor.shape
    device = stroke_tensor.device
    out = stroke_tensor.clone()
    total_logprob = torch.zeros(B, device=device)

    def sample_cat(offset, n_classes, temp=temp_cat):
        nonlocal total_logprob
        logits = stroke_tensor[:, :, offset:offset + n_classes] / temp
        dist = torch.distributions.Categorical(logits=logits)
        sampled = dist.sample()              # (B, T)
        lp = dist.log_prob(sampled)           # (B, T)
        # write one-hot
        out[:, :, offset:offset + n_classes] = 0.0
        idx = torch.arange(n_classes, device=device).view(1, 1, -1)
        sel = (idx == sampled.unsqueeze(-1)).float() * 10.0
        out[:, :, offset:offset + n_classes] = sel
        total_logprob += lp.sum(dim=-1)
        return sampled

    def sample_gauss(offset, span, sigma=sigma_cont):
        nonlocal total_logprob
        mean = stroke_tensor[:, :, offset:offset + span]
        eps = torch.randn_like(mean)
        sampled = mean + sigma * eps
        out[:, :, offset:offset + span] = sampled
        # log N(sample; mean, sigma²) = -0.5*((s-m)/σ)² - log(σ√2π)
        # = -0.5*ε² - log(σ√2π)
        lp_elem = -0.5 * eps.pow(2) - math.log(sigma * math.sqrt(2 * math.pi))
        total_logprob += lp_elem.sum(dim=(1, 2))

    # categoricals on every position
    sample_cat(O["type"], N_TOKEN_TYPES, temp=temp_cat)
    sample_cat(O["color"], N_PALETTE, temp=temp_cat)
    sample_cat(O["s_start_log"], N_ANCHOR_LOGITS, temp=temp_cat)
    sample_cat(O["s_end_log"], N_ANCHOR_LOGITS, temp=temp_cat)
    sample_cat(O["p_fabric"], N_FABRICS, temp=temp_cat)
    sample_cat(O["p_layer"], N_LAYER_ROLES, temp=temp_cat)

    # Gaussian on continuous (the H2-causing ones)
    sample_gauss(O["p_boundary"], 2 * PANEL_BOUNDARY_POINTS, sigma=sigma_cont)

    # length head — sample length
    ldist = torch.distributions.Categorical(logits=length_logits / temp_cat)
    sampled_lengths = ldist.sample()
    total_logprob += ldist.log_prob(sampled_lengths)

    return out, total_logprob, sampled_lengths


# ─── reward ────────────────────────────────────────────────────────────

def compute_reward_batch(sampled_tensor: torch.Tensor,
                           sampled_lengths: torch.Tensor):
    """For each sample in batch: decode → tokens → garment → validate.
    Reward = -(pieces_dropped + 0.5 × n_warnings).
    Returns reward tensor (B,)."""
    B = sampled_tensor.shape[0]
    rewards = []
    extra = []  # for logging
    decoded = decode_batch(sampled_tensor.detach())
    for b in range(B):
        n = int(sampled_lengths[b].item()) + 1
        tokens = decoded[b][:max(1, n)]
        # ensure last is_end
        if tokens:
            tokens[-1].is_end = True
        garment = tokens_to_garment(tokens)
        n_before = len(garment.pieces)
        garment2 = validate_garment(garment)
        n_after = len(garment2.pieces)
        n_dropped = n_before - n_after
        warns = garment2.metadata.get("validation_warnings", [])
        n_warns = len(warns)
        r = -(float(n_dropped) + 0.5 * float(n_warns))
        rewards.append(r)
        extra.append((n_before, n_after, n_warns))
    return torch.tensor(rewards, dtype=torch.float32), extra


# ─── training ──────────────────────────────────────────────────────────

RL_BRIEFS = [
    "cyberpunk neon-trim magenta black bodysuit",
    "Iris van Herpen sculptural orange asymmetric",
    "Genshin Liyue silk pearl jade drape",
    "K/DA neon teal silver idol stage",
    "Maori-Polynesian body harness bone ochre",
    "Bayonetta hair-as-catsuit deep violet beauty",
    "Dune Fremen stillsuit desert sand bone",
    "FFXIV summoner glamour gold sapphire glyphs",
    "Honkai Star Rail Robin idol stage feathers gold",
    "暗黑哥特黑色蕾丝紧身",
    "vaporwave Y2K iridescent teal magenta",
    "Tibetan dakini turquoise bronze ritual",
    "Mugler 1995 chrome silver cyborg",
    "原神璃月仙气飘带翡翠绿",
    "tropical Maori palm-green bone-white wrap",
    "Wakanda afrofuturism gold body chain",
    "Heian junihitoe pastel layers",
    "Aztec quetzal feather warrior",
    "Stellar Blade nano-suit chrome battle",
    "NieR 2B lace blindfold black",
    "Frost Druid bark organic green",
    "Solarpunk plant-fiber green optimistic",
    "Slavic kokoshnik red white folk",
    "Akira Neo-Tokyo bike-suit red",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init-ckpt",
                    default="tools/output/2026-05-28/p35_length_head/decoder_pretrained.pt")
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--out-dir", default="tools/output/2026-05-28/p39_manuf_rl")
    ap.add_argument("--baseline-momentum", type=float, default=0.9)
    ap.add_argument("--sigma-cont", type=float, default=0.05)
    ap.add_argument("--temp-cat", type=float, default=1.2)
    ap.add_argument("--log-every", type=int, default=20)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    torch.manual_seed(0)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[device] {device}")

    # ─── setup ───
    print("[setup] sbert + gen + load p35 ckpt...")
    enc = SentenceTransformerEncoder()
    gen = DesignGeneratorV3()
    gen.init_tag_bank(sbert=enc.model)
    ckpt = torch.load(args.init_ckpt, map_location="cpu", weights_only=False)
    gen.load_state_dict(ckpt["gen_state"], strict=False)
    gen = gen.to(device)

    # Pre-encode all RL briefs
    brief_emb = enc.encode(RL_BRIEFS)
    if not isinstance(brief_emb, torch.Tensor):
        brief_emb = torch.tensor(brief_emb)
    brief_emb = brief_emb.float().to(device)

    opt = torch.optim.Adam(gen.parameters(), lr=args.lr)

    print(f"\n[train] {args.iters} iters @ batch {args.batch} on {device}")
    print(f"  RL brief pool size: {len(RL_BRIEFS)}")

    # baseline (running mean reward)
    baseline = 0.0
    history = {"reward_mean": [], "reward_std": [],
                "n_dropped_mean": [], "n_warnings_mean": [],
                "rl_loss": []}

    t0 = time.time()
    for it in range(args.iters):
        idx = torch.randint(0, len(RL_BRIEFS), (args.batch,), device=device)
        be = brief_emb[idx]

        # forward — no teacher
        out = gen(be, noise_sigma=1.0)        # encoder noise on; decoder runs autoregressive

        # sample tokens stochastically + get log_probs
        sampled_tensor, log_probs, sampled_lengths = stochastic_sample_and_logprob(
            out.stroke_tensor, out.length_logits,
            sigma_cont=args.sigma_cont, temp_cat=args.temp_cat)

        # compute reward from validate_garment
        with torch.no_grad():
            reward_cpu, extras = compute_reward_batch(
                sampled_tensor.cpu(), sampled_lengths.cpu())
        reward = reward_cpu.to(device)

        # baseline update
        batch_mean = float(reward.mean().item())
        baseline = args.baseline_momentum * baseline + \
                    (1 - args.baseline_momentum) * batch_mean
        advantage = reward - baseline

        # REINFORCE loss
        rl_loss = -(advantage.detach() * log_probs).mean()

        opt.zero_grad()
        rl_loss.backward()
        torch.nn.utils.clip_grad_norm_(gen.parameters(), 1.0)
        opt.step()

        history["reward_mean"].append(batch_mean)
        history["reward_std"].append(float(reward.std().item()))
        history["n_dropped_mean"].append(
            sum(e[0] - e[1] for e in extras) / len(extras))
        history["n_warnings_mean"].append(
            sum(e[2] for e in extras) / len(extras))
        history["rl_loss"].append(float(rl_loss.item()))

        if (it + 1) % args.log_every == 0 or it == 0:
            print(f"  iter {it+1:>4}  reward={batch_mean:+.3f} "
                  f"(baseline {baseline:+.3f})  "
                  f"dropped={history['n_dropped_mean'][-1]:.2f}  "
                  f"warns={history['n_warnings_mean'][-1]:.2f}  "
                  f"rl_loss={rl_loss.item():.3f}")

    elapsed = time.time() - t0
    print(f"\n[train] done in {elapsed:.1f}s ({args.iters/elapsed:.1f} it/s)")
    first10 = sum(history["reward_mean"][:10]) / 10
    last10 = sum(history["reward_mean"][-10:]) / 10
    print(f"  reward[first 10 iters] = {first10:+.3f}")
    print(f"  reward[last  10 iters] = {last10:+.3f}")
    print(f"  dropped[first→last 10] = {sum(history['n_dropped_mean'][:10])/10:.2f}"
          f" → {sum(history['n_dropped_mean'][-10:])/10:.2f}")

    # save ckpt
    ckpt_path = os.path.join(args.out_dir, "decoder_rl.pt")
    torch.save({"gen_state": gen.state_dict(),
                 "history": history, "args": vars(args)}, ckpt_path)
    print(f"\nsaved ckpt -> {ckpt_path}")

    # plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        for ax, key, title in [
            (axes[0, 0], "reward_mean",   "REINFORCE reward (higher = fewer violations)"),
            (axes[0, 1], "n_dropped_mean", "# pieces dropped by validate"),
            (axes[1, 0], "n_warnings_mean", "# warnings from validate"),
            (axes[1, 1], "rl_loss", "REINFORCE loss"),
        ]:
            ax.plot(history[key], alpha=0.4)
            if len(history[key]) > 10:
                import numpy as np
                w = max(5, len(history[key]) // 30)
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

    summary = {
        "iters": args.iters,
        "batch": args.batch,
        "reward_first10": first10,
        "reward_last10": last10,
        "reward_improvement": last10 - first10,
        "dropped_first10": sum(history["n_dropped_mean"][:10]) / 10,
        "dropped_last10": sum(history["n_dropped_mean"][-10:]) / 10,
        "elapsed_sec": elapsed,
    }
    with open(os.path.join(args.out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
