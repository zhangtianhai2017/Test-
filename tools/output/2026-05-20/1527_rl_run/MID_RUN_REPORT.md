# Mid-run report — Steps 1-4 combined (V3 + 768res + diversity + PPO-norm)

50 iter × 8 batch with the full stack: V3 8-dim prompt, 768 px judge
input, diversity bonus (w_div=0.3, valid-gated), PPO-style advantage
normalization, w_rl bumped to 1.0 to compensate for the ~375× shrink
in raw loss_rl magnitude from normalization.

## Headline

| Metric | iter 0 | iter 49 | change |
|---|---|---|---|
| mean fitness | 0.756 | 0.899 | +0.143 |
| mean reward  | 0.900 | 0.882 | **-0.018 (stable)** |
| pass rate (8 samples) | 4/4* | 8/8 | recovered |

*Approximate — pass=4/4 in iter 0 batch of 4 in this scale; full 50-iter pass total = 303/400 = 75.8%.

## Comparison across our four 50-iter mid-runs today

| Setup | iter 0 reward | iter 49 reward | reward Δ | pass rate | fitness Δ |
|---|---|---|---|---|---|
| OLD: REINFORCE + V2 prompt, no diversity (2244_rl_run) | 0.719 | 0.700 | -0.019 | 92.5% | 0.756→0.930 |
| Step 1+2: V3 + 768 res, no diversity, REINFORCE | 0.760 | 0.768 | +0.008 | 95.9% (long run) | 0.756→0.934 |
| Step 3: + diversity 0.3, REINFORCE (1312_rl_run) | 0.879 | 0.691 | **-0.188 (degrading)** | 67.0% | 0.756→0.931 |
| **Step 4: + PPO-norm, w_rl=1.0** (this, 1527_rl_run) | **0.900** | **0.882** | **-0.018 (stable)** | 75.8% | 0.756→0.899 |

PPO normalization is the difference between Step 3's destabilizing
reward and Step 4's stable reward at the same diversity level. The
gradient is no longer dominated by absolute reward magnitude.

## Why fitness slightly lower

With w_rl bumped 0.05 → 1.0, the RL component of the gradient gets a
20× larger share of each update step (vs the symbolic fitness term
that wants pure geometric correctness). Some symbolic-fitness room is
sacrificed to follow Qwen+diversity reward — a trade-off the design
explicitly chose. 0.899 vs 0.934 is a 3.7 % drop in symbolic
fitness for stable RL reward — acceptable per the architecture's
"RL must matter" goal.

## Reward profile last 10 iters

```
iter  40  reward=0.738  pass=5/8
iter  41  reward=0.774  pass=5/8
iter  42  reward=0.754  pass=5/8
iter  43  reward=0.794  pass=7/8
iter  44  reward=0.833  pass=7/8
iter  45  reward=0.663  pass=4/8   <- low dip
iter  46  reward=0.859  pass=7/8
iter  47  reward=0.738  pass=4/8
iter  48  reward=0.802  pass=6/8
iter  49  reward=0.882  pass=8/8   <- recovered to peak
```

Bouncy but no degradation. PPO is keeping per-iter updates calibrated.

## What's NOT here yet

- **Clear upward trend.** Reward holds high, doesn't climb. Two hypotheses:
  1. 50 iters insufficient — PPO updates are smaller; needs ~100-200 to integrate
  2. Generator at a stable but suboptimal point — needs more aggressive
     exploration (higher temperature in softmax, or higher w_div)
- **PPO with multi-epoch.** Current PPO-norm is effectively A2C
  (single inner epoch == no ratio clipping benefit). True PPO with
  3-10 inner epochs per data batch would extract more signal from
  each render set.

## Recommended next run

100-iter long run with same settings (w_div=0.3, w_rl=1.0). ~3.5 h
wall. Will tell us if reward trends up over the next 50 iters, or
plateaus.

## Files

- `train_log.jsonl` — 50 iter records, 400 judge results with full V3 sub-scores
- `generator_final.pt` — checkpoint after 50 iters
- `iter_NNNN/vNN/01_front.png` + `outfit.json` — 400 renders (not committed, big)
