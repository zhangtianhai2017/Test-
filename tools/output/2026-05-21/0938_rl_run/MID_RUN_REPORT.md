# Mid-run report — skip + cv=50 finally breaks mode collapse

50 iter × 8 batch with the full anti-collapse stack at high gradient
weight. First run where reward trends meaningfully UP and visual
diversification is observable.

## Hyperparams

```
--w-div 1.0 --w-rl 1.0
--entropy-coef 0.5 --kl-uniform-coef 0.2
--cont-var-coef 50.0 --trunk-var-coef 5.0
--encoder sbert
```

## Headline numbers

| Metric | iter 0 | iter 49 | change |
|---|---|---|---|
| mean reward | 1.036 | **1.292** | **+0.256** (first clear upward trend) |
| mean fitness | 0.755 | 0.886 | +0.131 |
| pass rate | n/a per-iter | 281/400 = 70.2% | — |

Previous mid-runs maxed out at ~+0.008 reward gain over 50 iters. This
is **30× larger gain**. RL signal is now actually shaping the policy.

## Generator output diversity at iter 50

8 distinct briefs, sbert encoder, generator forward (no inference noise):

| brief | hue | sat | lit |
|---|---|---|---|
| 古典法式 ivory | 0.601 | 0.704 | **0.741** (highest, "ivory" → light ✓) |
| silver sequin | 0.581 | 0.685 | 0.675 |
| 50s navy polka | 0.554 | 0.685 | 0.673 |
| minimalist black | 0.590 | 0.643 | 0.700 |
| tropical pink+orange | 0.585 | 0.700 | 0.692 |
| **emerald high-end** | **0.612** | **0.728** | 0.732 (peak hue+sat, "emerald" ✓) |
| burgundy asymmetric | 0.563 | 0.612 | 0.637 |
| **neon yellow athletic** | **0.515** | 0.629 | 0.606 (lowest hue ✓) |

Batch stdev: hue 0.0305, sat 0.0408, lit 0.0454. Ranges are 0.10 wide,
above the 0.05 perceptual threshold.

vs the same probe before skip + cv=50: hue stdev was 0.0002, range
0.001 wide — utterly collapsed.

## Visual outcome (8 stochastic renders)

- 7/8 designs cluster as "blue-toned 2-piece" (NN settled on this as
  the high-reward shape)
- 1/8 (the neon yellow athletic) renders distinctly more green-cyan
- So we have not 8/8 mode collapse anymore; just one off-mode
  exemplar. Architecture changes (skip) plus continuous variance
  bonus (cv_coef=50) plus 50 iters of training got us past the
  "8 identical teals" baseline.

## What's still wrong

- 7 of 8 designs visually identical — generator found a different
  single-mode local optimum, not a true brief→design mapping
- Color cluster moved from teal to blue but didn't spread
- discrete picks (archetype, cup, bot, pattern) at iter 50 still
  mostly homogeneous per probe

## Next-step candidates (in priority order from this run's evidence)

1. **Brief-conditioned reward** — bake the brief into the judge prompt,
   ask Qwen "does this design match the brief?". Currently judge has
   no knowledge of brief, so reward can't reward brief→design fidelity.
   This is the only fix that addresses the root issue.

2. **cv_coef 50 → 200** — if 50 broke collapse on one brief, more
   gradient force might break it on more. Risk: at some point
   variance bonus dominates and reward dives.

3. **200-iter long run with current settings** — see if the slow
   trend continues or plateaus.

## Files

- `train_log.jsonl` — 50 iter records with full sub-scores
- `generator_final.pt` — checkpoint (skip-connection architecture,
  needs sbert encoder at inference)
- `MID_RUN_REPORT.md` — this file
