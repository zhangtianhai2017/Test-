# Long-run report — 100 iter × 8 batch with NEW judge code

Run with `tools/rl_runner_wsl.py` after commit `8eb9e39a` which fixed
JSON parsing, captured sub-scores, and switched reward to a pelvic-
weighted formula. Took 144 min wall, 800 renders, all judged.

## Headline numbers

| Metric | iter 0 | iter 99 | change |
|---|---|---|---|
| mean fitness (symbolic loss) | 0.756 | 0.934 | **+0.178 (monotonic, saturates ~iter 30)** |
| mean reward (pelvic-weighted) | 0.760 | 0.768 | **+0.008 (flat)** |
| Qwen pass rate | 8/8 | 8/8 | — |

Overall: 767/800 = 95.9 % Qwen-valid.

## What the judge actually returned (the headline finding)

Distribution across all 800 samples:

```
pelvic_coverage:
   0:  30 ( 3.8%)
   3:   3 ( 0.4%)
   5:  80 (10.0%)
   7: 687 (85.9%)  ← almost everything
chest_coverage:
   0:  32 ( 4.0%)
   5:   8 ( 1.0%)
   7: 758 (94.8%)  ← almost everything
   9:   2 ( 0.2%)
aesthetic_score:
   1:  24
   5: 265
   8:  76
   9: 434
parse_errors: 0/800 (0.0 %)  -- max_tokens=800 + JSON repair fixed it
```

This **disproves** the renderer-bottom-stripping hypothesis from the
previous report. Only 3.8 % of renders show pelvic=0 ("no bottom").
The 50 % top-only rate I estimated from a 13-sample manual label set
was unrepresentative.

But it reveals the **real bottleneck**: Qwen returns `(chest=7,
pelvic=7)` for ~85 % of renders. The reward signal collapses to a
narrow band even though it's structurally informative. REINFORCE has
no gradient to climb when most samples get the same score.

## Reward trajectory

```
iter   0: reward=0.760  fitness=0.756
iter  10: reward=0.775  fitness=0.850
iter  20: reward=0.745  fitness=0.912
iter  30: reward=0.757  fitness=0.926
iter  40: reward=0.751  fitness=0.931
iter  50: reward=0.767  fitness=0.932   ← fitness saturates here
iter  60: reward=0.691  fitness=0.932
iter  70: reward=0.759  fitness=0.934
iter  80: reward=0.756  fitness=0.934
iter  90: reward=0.766  fitness=0.935
iter  99: reward=0.768  fitness=0.934
```

- First 20 iters reward mean 0.752
- Last 20 iters reward mean 0.760
- Net RL improvement: +0.008 over 100 iters

That's noise, not learning. Symbolic loss does the actual work
(fitness rises monotonically to 0.93), then everything plateaus.

## What this means

The system is **structurally complete**:

- WSL2 + CUDA passthrough working
- open3d-cpu + OSMesa headless renders 800/800 successfully
- iter.capture._setup_renderer singleton pattern prevents Filament re-init crash
- Qwen2.5-VL judge reachable via mirrored network, 144-min run hit it 800 times with 0 timeouts and 0 parse errors
- V2 prompt + sub-score capture + strict Python-side is_valid gate working
- pelvic-weighted reward formula running, giving graded signal where it can
- REINFORCE + symbolic loss combined trainer running stable

But it has a **diversity problem**:

- Population of generated outfits hits a narrow region of design space
- Qwen rewards that region uniformly
- Without diverse samples that get diverse scores, RL gradient is too
  weak to push the generator into new territory

## Where to go from here (recommended priority)

1. **Diversity-aware sampling** — push the generator's softmax temperature
   up, or add an explicit diversity term to the loss. Visual diversity
   audit already exists at `tools/visual_diversity_audit.py` — could
   feed back into the loss directly.

2. **Multi-aspect Qwen judging** — current prompt asks 5 sub-dimensions.
   Could expand to ~10 (color harmony, proportion, style coherence,
   surface texture, weave consistency, hardware presence, …) to spread
   scores wider.

3. **Better RL algorithm** — REINFORCE is high variance. PPO with
   advantage normalization (CLAUDE.md mentions this as a fallback)
   would handle the narrow reward distribution more gracefully.

4. **Generator capacity** — current hidden_dim=256. The "narrow
   solution" the network has settled on might just be the ceiling
   of its expressivity. Wider would let it explore further.

5. **Image cropping / resolution** — the original handover question.
   Currently we send 480×720 down-sampled to max 480 on long side
   (so 320×480 effective). Qwen's training distribution favors larger
   images. Sending 768×1152 might recover ~50 % more visual tokens
   and help Qwen discriminate finer texture/proportion differences.

The lowest-cost first step is (1) + (2). Both are prompt/sampling
changes, no architectural surgery.

## Files

- `train_log.jsonl` — 100 iter records, 800 judge results with full sub-scores
- `generator_final.pt` — checkpoint at iter 99
- `iter_NNNN/vNN/01_front.png` — 800 renders (not committed, big)
- `iter_NNNN/vNN/outfit.json` — 800 outfit configs (not committed, big)
- `LONG_RUN_REPORT.md` — this file
