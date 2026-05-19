# Mid-run report — 50 iter × 8 batch with V2 prompt (legacy reward)

Ran with `tools/rl_runner_wsl.py` against the local Qwen2.5-VL judge.
This was the first non-trivial RL training. Took 73 min wall (~88 s/iter).

## Headline numbers

| Metric | iter 0 | iter 49 | change |
|---|---|---|---|
| mean fitness (symbolic loss) | 0.756 | 0.930 | **+0.174 (monotonic)** |
| mean reward (legacy v+a / 20) | 0.719 | 0.700 | **~flat** |
| pass rate (Qwen self-judged) | 8/8 | 7/8 | — |

Total: 400 renders, 370 (92.5%) Qwen-marked valid. Total wall 4389.9 s.

## Per-iter shape

Fitness climbed monotonically until ~iter 30, then saturated near 0.93.
Reward bounced 0.55–0.81 throughout. RL did not push reward upward over
50 iters under the legacy (validity+aesthetic)/20 formula.

Notable iters:
- iter 5:  2 parse_error in batch → mean_reward 0.581 (artificial dip)
- iter 23: 4 parse_error in batch → mean_reward 0.331, loss_rl -7.64
- iter 24: recovered to mean_reward 0.800

Parse-error rate across the whole run: 7 / 224 = 3.1 %. Concentrated in
3 iters and disproportionately hurt those iters' signal.

## Why reward stayed flat

Two reasons, both addressed by the follow-up commit:

1. **Legacy reward is essentially binary**. With V2 prompt Qwen mostly
   answers validity_score=7 or 8 and aesthetic_score=5 or 9, giving
   only ~6 distinct (v,a) combinations. (validity+aesthetic)/20 ends
   up in [0.55, 0.85] with most batches near 0.75. Not much for
   REINFORCE to grip.

2. **max_tokens=400 truncated ~3 % of Qwen responses**, dropping them
   to (0, 0) defaults. Those negative rewards muddied gradient
   updates without reflecting real design quality.

Direct re-judge of iter 23's 4 parse_error samples with the new
vision_judge.py (commit `8eb9e39a`):
- b2 → pelvic_coverage=0 ("completely bare") — was top-only, correctly identified
- b3, b4, b6 → pelvic_coverage=7 ("standard bikini brief") — real 2-pieces

So Qwen *was* seeing correctly; we just lost the data.

## What the new commit (`8eb9e39a`) changes

- max_tokens 400 → 800 (eliminates response truncation)
- JudgeResult captures chest/pelvic/anatomy/assembly/aesthetic sub-scores
- is_valid_swimsuit Python-derived as (chest≥5 AND pelvic≥5 AND
  anatomy≥5 AND assembly≥5) — stricter than Qwen self-judgement
- _safe_int rejects runaway numbers (>15 → 0 instead of clamp-to-10)
- _repair_json fixes the specific Qwen JSON errors we observed
- train_loop reward: 0.35·pelvic + 0.20·chest + 0.15·anatomy +
  0.15·assembly + 0.15·aesthetic (when sub-scores present)

Pelvic gets the heaviest weight because the dominant render-pipeline
failure mode is the body_region_classifier stripping bottom triangles
(deferred upstream fix, see task #15 in session notes).

## Next: 100-iter long run with new code

Same wrapper, same env. Goal: see whether the new sub-score reward
formula actually moves reward upward (vs flat as here). If yes, the
generator is learning to avoid "no bottom panel" configs. If still
flat, the renderer bottom-stripping bug is too dominant to overcome
via RL alone, and we have to fix `tools/render3d_uv.py`'s call to
`classify_triangles_strict`.

## Files in this dir

- `train_log.jsonl` — per-iter records (400 judge results)
- `generator_final.pt` — checkpoint after 50 iters
- `iter_NNNN/vNN/01_front.png` — 400 renders
- `iter_NNNN/vNN/outfit.json` — 400 outfit configs (slot_assignments + global_design)
- `MID_RUN_REPORT.md` — this file
