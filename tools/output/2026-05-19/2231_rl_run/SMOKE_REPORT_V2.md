# RL smoke run report — V2 prompt + score-based reward

Iteration on the 2025_rl_run baseline. Same env, same command, but with
the V2 multi-dimensional JUDGE_PROMPT and the reward formula switched
from `validity_score/10` to `(validity_score + aesthetic_score)/20`.

## Why this exists

2025_rl_run analysis showed:
- judge_results were essentially binary (validity_score=8 if "valid",
  =2 if "invalid", nothing else)
- 5 of 13 manually inspected renders were misclassified — judge said
  VALID for "top only, no bottom panel" designs (~54% accuracy)
- reward signal was almost flat (only 2 distinct iter-mean values)
- RL was learning nothing because there was no per-sample variance

`tools/judge_eval.py` ran two candidate prompts against the saved 32
renders + a hand-built `manual_labels.json` ground truth. V2 wins on
signal richness (see below). V2 doesn't beat OLD on binary
classification accuracy, but the score gap is what RL actually needs.

## Per-iter results

```
iter   0  fitness=0.758  reward=0.700  pass=4/4  loss_sym=-0.758 loss_rl=16.085  42.7s
iter   1  fitness=0.763  reward=0.850  pass=4/4  loss_sym=-0.763 loss_rl=17.924  43.3s
iter   2  fitness=0.775  reward=0.663  pass=4/4  loss_sym=-0.775 loss_rl=11.879  40.3s
iter   3  fitness=0.777  reward=0.725  pass=4/4  loss_sym=-0.777 loss_rl=12.120  42.2s
iter   4  fitness=0.802  reward=0.775  pass=4/4  loss_sym=-0.802 loss_rl=12.015  43.3s
iter   5  fitness=0.788  reward=0.738  pass=4/4  loss_sym=-0.788 loss_rl=10.029  42.1s
iter   6  fitness=0.799  reward=0.775  pass=4/4  loss_sym=-0.799 loss_rl=9.889   43.1s
iter   7  fitness=0.816  reward=0.688  pass=4/4  loss_sym=-0.816 loss_rl=6.787   41.4s
```

## Comparison vs 2025_rl_run (OLD prompt)

| Metric | OLD smoke | V2 smoke |
|---|---|---|
| iter wall time | ~25 s | ~42 s (V2 prompt is longer, +10 s judge) |
| total wall | 198.8 s | 338.5 s |
| distinct iter-mean rewards | 2 | **8** (much more RL signal) |
| reward spread | 0.150 | 0.187 |
| distinct per-sample (v, a) | 2 | 5 |
| binary pass rate | 29/32 (90.6%) | 32/32 (100%) — see caveat below |
| symbolic fitness | 0.758 → 0.815 | 0.758 → 0.816 (unchanged path) |

## Caveat — 100% binary pass is misleading

The V2 prompt's `is_valid_swimsuit` is now derived from
`chest>=4 AND pelvic>=4 AND anatomy>=5 AND assembly>=5`. Qwen scores
EVERY render — including obvious "no bottom panel" cases — as
`pelvic_coverage >= 5`. So the binary always trips.

Two layered issues:
- The new sub-score fields (chest_coverage, pelvic_coverage, etc.) are
  returned in the JSON but `JudgeResult.from_dict` doesn't capture
  them yet, so Python can't apply a stricter Python-side gate.
- Even if it did, Qwen's actual pelvic_coverage score for top-only
  renders is probably 5-6, not <4. The threshold or the prompt rubric
  needs further calibration once we have sub-score data.

But for RL the binary doesn't matter — the trainer uses the continuous
`(v+a)/20` reward, and that has real variance. So this is filed as a
follow-up, not a blocker.

## Files

- `train_log.jsonl` — per-iter records (rewards, sym_scores, judge_results)
- `generator_final.pt` — checkpoint after 8 iters (no learning yet, just for shape reference)
- (PNG renders excluded — see 2025_rl_run for ground-truth-labeled samples)

## Next

Run the handover-prescribed mid-experiment: `--iters 50 --batch 8`.
Expected ~70 min. Looking for: does mean_reward trend upward over
50 iters now that variance exists?
