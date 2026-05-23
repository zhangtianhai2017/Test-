"""Training loop — combines generator + symbolic fitness + vision judge
into the option-D training cycle.

Per docs/design/2026-05-17_option_D_architecture.md:
  - Symbolic fitness pumps real gradient back through autograd
    (cheap, immediate signal on color/proportion/coverage/etc.).
  - Vision judge gives a scalar reward; REINFORCE estimator pushes
    that gradient through the discrete picks (cup_id, fabric_id, ...)
    without needing differentiable rendering.

Two training modes:
  symbolic_only  -- fast bootstrap, no rendering, no judge.  ~1 ms/step.
                    Useful for pretraining the trunk + continuous head.
  full           -- render each variant + call J; combine sym + RL.
                    Real training loop.  Bottleneck: render cost
                    (a few seconds per variant) + J latency
                    (1-2s with local vLLM, ~0 with mock).

Every step appends a JSONL record to a run dir so the (text, config,
sym_score, J_result) tuple becomes training data for future models
(reward model, VAE, etc.).
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import Callable, Optional

import torch
import torch.nn.functional as F
from torch.optim import AdamW

# Make sibling modules importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from symbolic_fitness import total_fitness as sym_fitness, FitnessWeights
from design_generator import DesignGenerator, MockTextEncoder
from vision_judge import VisionJudge, MockVisionJudge, JudgeResult


# ---------------------------------------------------------------------------
# Default brief pool — bilingual, covers main archetypes / moods
# ---------------------------------------------------------------------------

DEFAULT_BRIEFS = [
    # English
    "classic triangle bikini, vibrant red, summer beach",
    "elegant bandeau, gold metallic, mediterranean luxury",
    "sport bralette, dark navy, racerback, high coverage",
    "boho macrame, cream, asymmetric halter neck",
    "minimalist black one-piece, deep V neckline",
    "tropical floral balconette, cheeky bottom",
    "wetsuit-inspired neoprene, matte black, modest cut",
    "vintage high-waist, polka dot, retro vacation",
    "metallic sequin bandeau, silver, evening party",
    "crochet boho bikini, terracotta, festival",
    "sheer mesh overlay, deep emerald, evening",
    "asymmetric one-shoulder maillot, burgundy",
    "sport racerback, electric blue, full coverage",
    "lace floral cutout, soft pink, romantic",
    "fishnet bralette over solid black, edgy",
    # Chinese
    "夏威夷沙滩, 米色调, 经典三角",
    "维秘风格, 深V plunge, 黑金搭配",
    "极简连体, 哑光黑, 高领",
    "复古高腰, 红白条纹, 度假风",
    "波西米亚, 流苏, 燕麦色, 节日风格",
    "运动款, 透气网眼, 深紫, 高强度活动",
    "亮片金属, 银粉色, 派对夜晚",
    "渐变染色, 蓝紫色, 海洋灵感",
    "蕾丝镂空, 浅米色, 浪漫风格",
    "不对称单肩, 酒红, 优雅性感",
    "前卫切割, 黑色橡胶感, 都市未来",
    "钩针手工, 大地色, 自然质朴",
    "薄纱叠层, 香槟色, 隆重场合",
    "几何印花, 撞色, 现代极简",
    "古典抹胸, 象牙白, 法式优雅",
]


# ---------------------------------------------------------------------------
# Per-iteration record
# ---------------------------------------------------------------------------

@dataclass
class IterationRecord:
    iter: int
    briefs:           list[str]
    sym_scores:       list[dict]           # per-variant symbolic fitness axes
    config_continuous: list[dict]         # the continuous output values
    discrete_picks:    list[dict]         # argmax sample of each discrete head
    judge_results:    list[dict]          # JudgeResult.to_dict() if rendered
    loss_sym:         float
    loss_rl:          float
    loss_total:       float
    mean_fitness:     float
    mean_reward:      float
    elapsed_s:        float
    mode:             str


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

class TrainLoop:
    def __init__(self,
                 generator: DesignGenerator,
                 text_encoder,
                 judge: Optional[VisionJudge] = None,
                 lr: float = 1e-3,
                 w_sym: float = 1.0,
                 w_rl: float = 1.0,
                 w_div: float = 0.0,
                 entropy_coef: float = 0.0,
                 kl_uniform_coef: float = 0.0,
                 cont_var_coef: float = 0.0,
                 trunk_var_coef: float = 0.0,
                 baseline_alpha: float = 0.9,
                 device: str = "cpu",
                 run_dir: Optional[str] = None):
        self.gen = generator.to(device)
        self.enc = text_encoder
        self.judge = judge
        self.opt = AdamW(self.gen.parameters(), lr=lr)
        self.w_sym = w_sym
        self.w_rl = w_rl
        # w_div = per-sample diversity bonus weight. When > 0 and render_fn
        # returns outfits alongside paths, each sample's reward gets
        # w_div * (avg Hamming distance to other batch members / 9) added
        # to it. Pushes the generator away from collapsing to a single
        # popular config (the headline failure mode of the 2026-05-20 long
        # run where 85% of samples scored identically at chest=7,pelvic=7).
        self.w_div = w_div
        # Anti-mode-collapse knobs (added 2026-05-20).
        #
        # entropy_coef:    bonus pushing each discrete head's softmax
        #                  toward higher entropy. loss -= ec * mean(H(π)).
        #                  Standard A3C/PPO trick; counteracts the
        #                  generator collapsing all probability onto
        #                  one library_id per head. Typical 0.01-0.1.
        #
        # kl_uniform_coef: penalty pushing each head's softmax toward
        #                  uniform. loss += kc * mean(KL(π || U)).
        #                  Stronger anti-collapse than entropy alone
        #                  because it has a concrete anchor distribution.
        #                  Typical 0.01-0.05.
        #
        # Both default to 0 so older runs reproduce. Set via CLI flags
        # --entropy-coef and --kl-uniform-coef on rl_runner.
        self.entropy_coef = entropy_coef
        self.kl_uniform_coef = kl_uniform_coef
        # cont_var_coef:  bonus pushing the continuous-head outputs
        #                 (hue/saturation/lightness) to have non-zero
        #                 variance across the batch. entropy/KL only
        #                 act on discrete logits; without this term the
        #                 NN happily collapses all continuous outputs
        #                 to sigmoid(0)=0.5 because that's the local
        #                 fitness optimum and Qwen scores it consistently.
        #                 Observed in 2206_rl_run (entropy 0.5, KL 0.2):
        #                 hue stdev was 0.0002 — generator ignoring
        #                 text_emb completely. loss -= cv * (var(hue) +
        #                 var(sat) + var(lit)).
        self.cont_var_coef = cont_var_coef
        # trunk_var_coef: bonus on trunk HIDDEN output batch variance.
        #                 cont_var alone can't backprop through sigmoid
        #                 saturation to push trunk weights away from 0.
        #                 Direct penalty on trunk(emb) variance makes
        #                 "all-zero trunk weights" no longer the optimum.
        #                 loss -= tv * h.std(dim=0).mean(). Typical 1-10.
        self.trunk_var_coef = trunk_var_coef
        self.baseline_R = 0.0
        self.baseline_alpha = baseline_alpha
        self.device = device

        self.run_dir = run_dir
        self.iter = 0
        if run_dir is not None:
            os.makedirs(run_dir, exist_ok=True)
            self.log_path = os.path.join(run_dir, "train_log.jsonl")
        else:
            self.log_path = None

    # ------------------------------------------------------------------
    # Symbolic-only step (fast, no render, no judge)
    # ------------------------------------------------------------------
    def step_symbolic(self, briefs: list[str],
                       fitness_weights: Optional[FitnessWeights] = None,
                       compat_matrices: Optional[dict] = None) -> IterationRecord:
        t0 = time.time()
        emb = self.enc.encode(briefs).to(self.device)
        config = self.gen(emb)

        sym = sym_fitness(config, weights=fitness_weights,
                            compat_matrices=compat_matrices)
        loss_sym = -sym["total"].mean()

        self.opt.zero_grad()
        loss_sym.backward()
        # Gradient-clip is cheap insurance against blowups
        torch.nn.utils.clip_grad_norm_(self.gen.parameters(), max_norm=1.0)
        self.opt.step()

        # Build record
        rec = self._build_record(
            briefs=briefs, config=config, sym=sym,
            judge_results=[],
            loss_sym=loss_sym.item(),
            loss_rl=0.0,
            loss_total=loss_sym.item(),
            reward_mean=0.0,
            mode="symbolic_only",
            elapsed=time.time() - t0,
        )
        self.iter += 1
        self._log_record(rec)
        return rec

    # ------------------------------------------------------------------
    # Full step (symbolic + RL from J)
    # ------------------------------------------------------------------
    def step_full(self, briefs: list[str],
                   render_fn: Callable[[dict, dict], list[str]],
                   fitness_weights: Optional[FitnessWeights] = None,
                   compat_matrices: Optional[dict] = None) -> IterationRecord:
        """`render_fn(config, picks) -> list of image paths`,
        OR a tuple `(list of image paths, list of Outfit instances)`.

        The 2-element-tuple variant unlocks the diversity bonus
        (controlled by `self.w_div`). When `render_fn` returns just a
        list of paths, w_div has no effect."""
        if self.judge is None:
            raise RuntimeError("step_full requires a VisionJudge")
        t0 = time.time()
        emb = self.enc.encode(briefs).to(self.device)
        # Run the trunk separately so we can put a variance penalty on
        # its output (anti-collapse). Generator.forward duplicates this
        # work but keeps the public API simple.
        trunk_out = self.gen.trunk(emb)
        config = self.gen(emb)

        # Symbolic loss (continuous gradient path)
        sym = sym_fitness(config, weights=fitness_weights,
                            compat_matrices=compat_matrices)
        loss_sym = -sym["total"].mean()

        # Sample discrete picks (argmax for the render; log-probs for RL).
        # Also collect entropies + KL-to-uniform per head for the
        # anti-mode-collapse regularizers below.
        picks: dict[str, torch.Tensor] = {}
        log_probs: list[torch.Tensor] = []
        entropies: list[torch.Tensor] = []
        kl_to_uniform: list[torch.Tensor] = []
        for name in self.gen.discrete_sizes:
            logits = config[f"{name}_logits"]
            log_p = F.log_softmax(logits, dim=-1)
            probs = F.softmax(logits, dim=-1)
            sampled = torch.multinomial(probs, num_samples=1).squeeze(-1)
            picks[name] = sampled.detach().cpu()
            log_probs.append(log_p.gather(-1, sampled.unsqueeze(-1)).squeeze(-1))
            # H(π) = -sum_k π_k log π_k, per sample, then mean over batch.
            ent = -(probs * log_p).sum(dim=-1)               # (B,)
            entropies.append(ent)
            # KL(π || uniform) = log(K) - H(π).  K = num actions.
            K = probs.shape[-1]
            log_K = float(torch.log(torch.tensor(float(K))))
            kl_to_uniform.append(log_K - ent)                # (B,)

        # Render + judge. render_fn may return (paths,) or (paths, outfits).
        # Pass `briefs` through to judge so V4 prompt's brief_match dim
        # can score "did this design match the requested brief".
        outfits = None
        try:
            rendered = render_fn(config, picks)
            if (isinstance(rendered, tuple) and len(rendered) == 2):
                image_paths, outfits = rendered
            else:
                image_paths = rendered
            results = self.judge.judge_batch(image_paths, briefs=briefs,
                                              verbose=False)
        except Exception as exc:
            print(f"  render/judge failed: {exc}; using zero reward")
            results = [JudgeResult.from_dict({}, backend="error")
                        for _ in briefs]

        # Reward uses V3's 8 sub-scores. Structural dims (chest/pelvic/
        # anatomy/assembly) carry 60% of the weight — failures here
        # are real defects. The 4 aesthetic dims (aesthetic/color_harmony/
        # proportion/silhouette) carry the other 40% and give the score
        # space room to vary for designs that all pass structural gate.
        # V2 collapsed 85% of renders to identical (chest=7, pelvic=7),
        # so 4 aesthetic axes were added 2026-05-20 specifically to
        # widen the reward distribution.
        #
        # Falls back to legacy (v+a)/20 if sub-scores absent.
        #
        # V4-fixed (2026-05-22): brief_match weight cut 0.25 -> 0.10
        # AND gated by is_valid_swimsuit. The first V4 run rewarded
        # broken designs that Qwen interpreted as "minimal/avant-
        # garde" matches to the brief (pass dropped 70% -> 32% in
        # 50 iters). With structural gate + lower weight + tightened
        # prompt (which now caps brief_match <= 3 for naked designs),
        # the signal is contained.
        #
        # 2026-05-23: CLIP-only mode. When backend is CLIP, the other
        # sub-scores are dummies (CLIP can't judge them); structural
        # quality comes through symbolic_fitness instead. Reward is
        # pure brief_match.
        #
        # 2026-05-23 v2: CV+CLIP mode. CV mask CAN judge structure
        # (it knows skin/bg pixels), so we use the full Qwen-style
        # weighted formula. Aesthetic sub-scores are still neutral 7s
        # from the CV judge, but the structural quadrant + brief_match
        # are real signals. Brief_match weight stays 0.10 + gated.
        def _reward(r) -> float:
            if r.backend == "clip-mclip-vit-b32":
                # CLIP-only: pure brief_match (structure via sym_fitness)
                return r.brief_match / 10.0
            if r.pelvic_coverage or r.chest_coverage:
                w_struct = (
                    0.25 * r.pelvic_coverage
                    + 0.15 * r.chest_coverage
                    + 0.10 * r.anatomy_clean
                    + 0.10 * r.assembly_quality
                )
                w_aesth = (
                    0.08 * r.aesthetic
                    + 0.08 * r.color_harmony
                    + 0.07 * r.proportion
                    + 0.07 * r.silhouette
                )
                # Gated brief bonus: only when structure passes.
                w_brief = (0.10 * r.brief_match
                            if r.is_valid_swimsuit else 0.0)
                return (w_struct + w_aesth + w_brief) / 10.0
            return (r.validity_score + r.aesthetic_score) / 20.0
        base_rewards = [_reward(r) for r in results]

        # Optional diversity bonus per sample: average Hamming distance
        # on 9 perceptual axes to the other batch members, scaled by
        # self.w_div. Skipped when render_fn didn't surface outfits or
        # when w_div == 0.
        #
        # IMPORTANT: bonus is ZERO'd for any sample that fails the
        # structural validity gate (is_valid_swimsuit). Without this
        # mask, the bonus rewards "novel broken designs" (e.g. missing
        # bottom panel = unique bottom_coverage bucket = high Hamming
        # distance from peers), making invalid samples competitive with
        # valid ones. 2026-05-20 smoke at w_div=0.3 saw pass rate drop
        # from 96% to 41% before this gate was added.
        div_bonuses = [0.0] * len(base_rewards)
        if self.w_div > 0 and outfits is not None and len(outfits) > 1:
            try:
                from visual_diversity_audit import batch_diversity_bonuses
                all_bonuses = batch_diversity_bonuses(outfits)
                div_bonuses = [
                    b if (results[i].is_valid_swimsuit
                          and outfits[i] is not None) else 0.0
                    for i, b in enumerate(all_bonuses)
                ]
            except Exception as exc:
                print(f"  diversity bonus failed: {exc}; skipping")

        rewards = torch.tensor(
            [b + self.w_div * d for b, d in zip(base_rewards, div_bonuses)],
            dtype=torch.float32, device=self.device)
        # Baseline subtraction for variance reduction.
        advantages = (rewards - self.baseline_R).detach()
        # Per-batch advantage normalization (PPO-style). Without this,
        # gradient magnitude tracks raw reward scale; with diversity
        # bonus the reward range is ~3x wider than legacy reward and
        # plain REINFORCE updates become unstable (2026-05-20 mid-run
        # at w_div=0.3 saw mean_reward 0.79 -> 0.71 over 30 iters).
        # Normalization keeps update magnitudes roughly constant across
        # iters regardless of reward distribution shape.
        if advantages.numel() > 1 and advantages.std().item() > 1e-6:
            adv = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        else:
            adv = advantages
        # Loss: -E[adv * sum_d log p(sampled_d)]  (advantage-normalized
        # REINFORCE; equivalent to PPO with 1 inner epoch).
        sum_log_p = torch.stack(log_probs, dim=0).sum(dim=0)   # (B,)
        loss_rl = -(adv * sum_log_p).mean()

        # Anti-collapse regularizers. Push the discrete softmax
        # distributions toward higher-entropy / closer-to-uniform.
        # mean over (batch, heads).
        mean_entropy = torch.stack(entropies, dim=0).mean()
        mean_kl_to_u = torch.stack(kl_to_uniform, dim=0).mean()

        # Continuous-output variance bonus.
        if self.cont_var_coef > 0 and config["hue"].numel() > 1:
            cont_var = (config["hue"].var(unbiased=False)
                         + config["saturation"].var(unbiased=False)
                         + config["lightness"].var(unbiased=False))
        else:
            cont_var = torch.zeros((), device=self.device)

        # Trunk-output variance bonus: penalize trunk collapsing to a
        # constant for all inputs. Acts BEFORE sigmoid so the gradient
        # path is cleaner — cont_var has near-zero gradient through
        # sigmoid when its output is already squashed.
        if self.trunk_var_coef > 0 and trunk_out.shape[0] > 1:
            trunk_var = trunk_out.std(dim=0).mean()
        else:
            trunk_var = torch.zeros((), device=self.device)

        loss_total = (self.w_sym * loss_sym
                       + self.w_rl * loss_rl
                       - self.entropy_coef * mean_entropy
                       + self.kl_uniform_coef * mean_kl_to_u
                       - self.cont_var_coef * cont_var
                       - self.trunk_var_coef * trunk_var)

        self.opt.zero_grad()
        loss_total.backward()
        torch.nn.utils.clip_grad_norm_(self.gen.parameters(), max_norm=1.0)
        self.opt.step()

        # Update running baseline (EMA of rewards)
        r_mean = rewards.mean().item()
        self.baseline_R = (self.baseline_alpha * self.baseline_R +
                            (1 - self.baseline_alpha) * r_mean)

        rec = self._build_record(
            briefs=briefs, config=config, sym=sym,
            judge_results=[r.to_dict() for r in results],
            loss_sym=loss_sym.item(),
            loss_rl=loss_rl.item(),
            loss_total=loss_total.item(),
            reward_mean=r_mean,
            mode="full",
            elapsed=time.time() - t0,
            picks=picks,
        )
        self.iter += 1
        self._log_record(rec)
        return rec

    # ------------------------------------------------------------------
    # Multi-step convenience
    # ------------------------------------------------------------------
    def train_symbolic(self, n_steps: int, batch_size: int = 16,
                        brief_pool: Optional[list[str]] = None,
                        verbose: bool = True,
                        fitness_weights: Optional[FitnessWeights] = None,
                        ) -> list[IterationRecord]:
        pool = brief_pool or DEFAULT_BRIEFS
        rng = random.Random(self.iter)
        history = []
        for _ in range(n_steps):
            briefs = rng.choices(pool, k=batch_size)
            rec = self.step_symbolic(briefs, fitness_weights=fitness_weights)
            history.append(rec)
            if verbose and (self.iter % 10 == 0 or self.iter == 1):
                print(f"  step {self.iter:4d}  "
                      f"loss={rec.loss_total:.4f}  "
                      f"fitness={rec.mean_fitness:.3f}  "
                      f"({rec.elapsed_s*1000:.0f}ms)")
        return history

    # ------------------------------------------------------------------
    # Save / load checkpoint
    # ------------------------------------------------------------------
    def save(self, path: str) -> None:
        torch.save({
            "iter": self.iter,
            "gen_state":  self.gen.state_dict(),
            "opt_state":  self.opt.state_dict(),
            "baseline_R": self.baseline_R,
        }, path)

    def load(self, path: str) -> None:
        ckpt = torch.load(path, map_location=self.device)
        self.gen.load_state_dict(ckpt["gen_state"])
        self.opt.load_state_dict(ckpt["opt_state"])
        self.baseline_R = ckpt["baseline_R"]
        self.iter = ckpt["iter"]

    # ------------------------------------------------------------------
    # Internal: build per-iter record, write to JSONL
    # ------------------------------------------------------------------
    def _build_record(self, briefs, config, sym, judge_results,
                       loss_sym, loss_rl, loss_total, reward_mean,
                       mode, elapsed, picks=None):
        B = len(briefs)
        cont_keys = [k for k, v in config.items()
                     if not k.endswith("_logits")]
        cont_per_variant = []
        for i in range(B):
            cont_per_variant.append(
                {k: float(config[k][i].detach().cpu().item())
                 for k in cont_keys})
        discrete_per_variant = []
        if picks is not None:
            for i in range(B):
                discrete_per_variant.append(
                    {k: int(v[i].item()) for k, v in picks.items()})
        else:
            # argmax inference if not given
            for i in range(B):
                d = {}
                for name in self.gen.discrete_sizes:
                    logits = config[f"{name}_logits"][i]
                    d[name] = int(logits.argmax().item())
                discrete_per_variant.append(d)
        sym_per_variant = []
        for i in range(B):
            sym_per_variant.append(
                {k: float(v[i].item()) for k, v in sym.items()
                 if k != "total"})
        return IterationRecord(
            iter=self.iter,
            briefs=briefs,
            sym_scores=sym_per_variant,
            config_continuous=cont_per_variant,
            discrete_picks=discrete_per_variant,
            judge_results=judge_results,
            loss_sym=loss_sym,
            loss_rl=loss_rl,
            loss_total=loss_total,
            mean_fitness=float(sym["total"].mean().item()),
            mean_reward=reward_mean,
            elapsed_s=elapsed,
            mode=mode,
        )

    def _log_record(self, rec: IterationRecord) -> None:
        if self.log_path is None:
            return
        with open(self.log_path, "a") as f:
            f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

def _smoke_symbolic_only() -> None:
    """Just train_symbolic for a few steps, watch loss/fitness improve."""
    print("=== smoke: symbolic-only training (50 steps, batch 16) ===\n")
    torch.manual_seed(0)
    enc = MockTextEncoder(dim=384)
    gen = DesignGenerator(text_dim=384, hidden_dim=128)
    loop = TrainLoop(gen, enc, lr=3e-3)

    history = loop.train_symbolic(n_steps=50, batch_size=16)
    first = history[0].mean_fitness
    last  = history[-1].mean_fitness
    print(f"\nfitness {first:.3f} -> {last:.3f}  (improvement {last - first:+.3f})")
    assert last >= first - 0.05, "training should not get dramatically worse"


def _smoke_full_step_mock_render() -> None:
    """One step of step_full with a fake renderer + mock judge."""
    print("\n=== smoke: full step with mock render + mock judge ===\n")
    torch.manual_seed(1)
    enc = MockTextEncoder(dim=384)
    gen = DesignGenerator(text_dim=384, hidden_dim=128)
    judge = MockVisionJudge()
    loop = TrainLoop(gen, enc, judge=judge, lr=1e-3)

    # Stub renderer that returns made-up image paths -- mock judge
    # consumes only path strings.
    def fake_render(config, picks):
        B = next(iter(picks.values())).shape[0]
        return [f"/tmp/render_{i}.png" for i in range(B)]

    rec = loop.step_full(["pink triangle", "elegant bandeau",
                           "sport racerback", "boho crochet"],
                          render_fn=fake_render)
    print(f"  loss_sym={rec.loss_sym:.4f}  loss_rl={rec.loss_rl:.4f}  "
          f"loss_total={rec.loss_total:.4f}  reward={rec.mean_reward:.3f}")
    print(f"  baseline_R after step: {loop.baseline_R:.3f}")
    n_pass = sum(1 for r in rec.judge_results if r["is_valid_swimsuit"])
    print(f"  judge: {n_pass}/4 pass")

    # Verify ALL trainable params got gradients (continuous + every
    # discrete head should now have signal, via sym or RL)
    n_with, n_without = 0, 0
    for name, p in gen.named_parameters():
        if p.grad is not None and p.grad.abs().sum().item() > 0:
            n_with += 1
        else:
            n_without += 1
    print(f"  params with grad: {n_with}/{n_with + n_without}")
    if n_without > 0:
        print("  parameters NOT updated:")
        for name, p in gen.named_parameters():
            if p.grad is None or p.grad.abs().sum().item() == 0:
                print(f"    {name}")


def _smoke_with_log_dir() -> None:
    """Verify JSONL logging works -- this is the data flywheel."""
    print("\n=== smoke: 5 logged steps to disk ===\n")
    import tempfile
    tmp = tempfile.mkdtemp(prefix="train_loop_test_")
    enc = MockTextEncoder(dim=384)
    gen = DesignGenerator(text_dim=384, hidden_dim=64)
    loop = TrainLoop(gen, enc, lr=3e-3, run_dir=tmp)
    loop.train_symbolic(n_steps=5, batch_size=4, verbose=False)
    with open(loop.log_path) as f:
        lines = f.readlines()
    print(f"  wrote {len(lines)} JSONL records to {loop.log_path}")
    sample = json.loads(lines[0])
    print(f"  record keys: {sorted(sample.keys())}")
    print(f"  one record's sym_scores keys: {sorted(sample['sym_scores'][0].keys())[:5]}...")


if __name__ == "__main__":
    _smoke_symbolic_only()
    _smoke_full_step_mock_render()
    _smoke_with_log_dir()
