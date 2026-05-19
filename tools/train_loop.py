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
                 baseline_alpha: float = 0.9,
                 device: str = "cpu",
                 run_dir: Optional[str] = None):
        self.gen = generator.to(device)
        self.enc = text_encoder
        self.judge = judge
        self.opt = AdamW(self.gen.parameters(), lr=lr)
        self.w_sym = w_sym
        self.w_rl = w_rl
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
        """`render_fn(config, picks) -> list of image paths`.
        Must accept a config dict (with continuous tensors + sampled
        discrete picks as ints) and produce a render per variant."""
        if self.judge is None:
            raise RuntimeError("step_full requires a VisionJudge")
        t0 = time.time()
        emb = self.enc.encode(briefs).to(self.device)
        config = self.gen(emb)

        # Symbolic loss (continuous gradient path)
        sym = sym_fitness(config, weights=fitness_weights,
                            compat_matrices=compat_matrices)
        loss_sym = -sym["total"].mean()

        # Sample discrete picks (argmax for the render; log-probs for RL)
        picks: dict[str, torch.Tensor] = {}
        log_probs: list[torch.Tensor] = []
        for name in self.gen.discrete_sizes:
            logits = config[f"{name}_logits"]
            log_p = F.log_softmax(logits, dim=-1)
            # Sample stochastically so RL gets exploration
            probs = F.softmax(logits, dim=-1)
            sampled = torch.multinomial(probs, num_samples=1).squeeze(-1)
            picks[name] = sampled.detach().cpu()
            log_probs.append(log_p.gather(-1, sampled.unsqueeze(-1)).squeeze(-1))

        # Render + judge
        try:
            image_paths = render_fn(config, picks)
            results = self.judge.judge_batch(image_paths, verbose=False)
        except Exception as exc:
            print(f"  render/judge failed: {exc}; using zero reward")
            results = [JudgeResult.from_dict({}, backend="error")
                        for _ in briefs]

        # Reward uses BOTH validity + aesthetic so the judge's graded
        # multi-dim rubric (V2 prompt, 2026-05-19) produces continuous
        # RL signal instead of binary 0.2/0.8. Empirically gives
        # ~2.5x more sample-to-sample variance on the same renders.
        rewards = torch.tensor(
            [(r.validity_score + r.aesthetic_score) / 20.0 for r in results],
            dtype=torch.float32, device=self.device)
        # Baseline subtraction for variance reduction
        advantages = (rewards - self.baseline_R).detach()
        # REINFORCE loss: -E[advantage * sum_d log p(sampled_d)]
        sum_log_p = torch.stack(log_probs, dim=0).sum(dim=0)   # (B,)
        loss_rl = -(advantages * sum_log_p).mean()

        loss_total = self.w_sym * loss_sym + self.w_rl * loss_rl

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
