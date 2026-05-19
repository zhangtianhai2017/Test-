# Session summary — 2026-05-19 → 2026-05-20

A6000 / Windows host. User handed me the GPU + sandbox-AI role.
~12 h of work, four git commits on branch `claude/add-diverse-seeds-handover-sBSs3`.

## Commits in this session

```
4fc45214 rl smoke: 8 iters x 4 batch, real Qwen2.5-VL judge
de9371e7 judge: V2 multi-dim rubric prompt + score-based reward
8eb9e39a judge: max_tokens 800, JSON repair, sub-score capture, pelvic-weighted reward
b6e283dc mid-run 50 iter x 8 batch: fitness 0.756->0.930 monotonic, reward flat 0.70
```

## What works end-to-end

| Layer | Status | Notes |
|---|---|---|
| Repo + branch | ✓ | clone in WSL ~/Test-, remote `local`=/mnt/c, `origin`=GitHub |
| Vision judge service | ✓ | `127.0.0.1:8000/v1`, Qwen2.5-VL-7B, maintained by sibling AI |
| WSL2 + CUDA passthrough | ✓ | A6000 visible in WSL via mirrored networking + Windows driver |
| Python training env | ✓ | `~/venvs/swim-train`, Python 3.10.12, torch 2.5.1+cu121 |
| Open3D OSMesa headless | ✓ | `open3d-cpu==0.19.0` + `OPEN3D_CPU_RENDERING=true` |
| Filament multi-renderer | ✓ via singleton | `tools/rl_runner_wsl.py` monkey-patches `_setup_renderer` |
| Network: WSL→Windows judge | ✓ | `~/.wslconfig` `networkingMode=mirrored` |
| Judge JSON parsing | ✓ | `max_tokens=800` + `_repair_json` + `_safe_int` = 0% parse error |
| Multi-dim reward | ✓ | pelvic-weighted, sub-scores captured in JudgeResult |
| RL training loop | ✓ | 800 judge calls / 144 min, no errors |

## What we proved

- Qwen2.5-VL-7B is **not the bottleneck** — given V2 prompt + parseable
  JSON, it correctly identifies missing-bottom renders (pelvic=0) and
  scores normal bikinis (pelvic=7). Verified by direct judge_diag tests
  and by 800-sample distribution showing 30 (~3.8 %) zero-pelvic cases.
- Renderer is **not** systematically stripping bottoms either (only ~3.8 %
  of renders end up bottomless, not the 50 % I'd guessed from a tiny
  manual label set).
- Symbolic gradient does the lifting for fitness: 0.756 → 0.93 in 30
  iters, then saturates.
- REINFORCE signal exists (parse errors gone, sub-scores graded) but
  reward stays flat at 0.76 across 100 iters because Qwen rewards
  85 % of renders identically (chest=7, pelvic=7).

## The real bottleneck

**Population uniformity**. Generator settles in a narrow region of
design space; Qwen scores that region uniformly; RL has no gradient
to climb.

## Headline experiments

| Run | When | Iters × batch | Fitness Δ | Reward Δ | Pass rate |
|---|---|---|---|---|---|
| smoke (first WSL pass) | 20:25 | 8 × 4 | 0.758 → 0.815 | flat 0.80 | 29/32 (90.6%) |
| V2 smoke | 22:31 | 8 × 4 | 0.758 → 0.816 | 0.70 (bouncy) | 32/32 (100%) |
| mid-run | 22:44 | 50 × 8 | 0.756 → 0.930 | 0.72 → 0.70 | 370/400 (92.5%) |
| **long-run** | 00:01 | **100 × 8** | **0.756 → 0.934** | **0.76 → 0.77** | **767/800 (95.9%)** |

## Permanent fixes shipped (in branch)

- `tools/rl_runner_wsl.py` — WSL entry-point with Filament singleton patch
- `tools/vision_judge.py` — V2 prompt, max_tokens 800, sub-score capture, JSON repair, _safe_int
- `tools/train_loop.py` — reward formula 0.35·pelvic + 0.20·chest + 0.15·anatomy + 0.15·assembly + 0.15·aesthetic
- `tools/judge_eval.py` — standalone A/B harness for prompt experiments

## Recommended next session priorities

In rough order of expected payoff:

1. **Diversity-aware sampling** — push softmax temperature up in the
   generator's discrete heads, or wire `tools/visual_diversity_audit.py`
   into the loss as a regularizer. Goal: more varied outfit configs
   → more varied Qwen scores → real RL gradient.

2. **Multi-aspect prompt** — V3 prompt asking 8-10 dimensions (color
   harmony, proportion, style coherence, surface texture, weave,
   hardware, …) so Qwen's score space has more axes to vary.

3. **PPO instead of REINFORCE** — handover doc flags this as a known
   next move. Advantage normalization handles narrow reward
   distributions better than REINFORCE.

4. **Image resolution up to 768×1152** — current `max_image_dim=480`
   in `VLLMVisionJudge._encode_image` halves the Qwen visual-token
   count. Bumping to 768 (max_image_dim ~= 768) might recover
   discrimination on fine texture / proportion details. Costs ~50 %
   more judge latency.

5. **Bottom-stripping fix** — `body_region_classifier` does over-prune
   in ~3.8 % of cases. A/B test (strict vs majority vs lowered
   leg_y_slack) is set up at `inner_render_persistent.py` but
   segfaults on this WSL setup; needs more investigation. Lower priority
   given it's only 3.8 % of cases.

## Operational notes

- WSL → Windows local push requires `git config receive.denyCurrentBranch updateInstead`
  on the Windows clone (already set). WSL has no GitHub credentials —
  push chain is WSL → Windows local → Windows → GitHub.
- Filament/OSMesa: never create a 2nd `OffscreenRenderer` in the same
  process. Always use the singleton via `rl_runner_wsl.py`. Cross-process
  also conflicts when the first process is mid-render — defer renderer
  experiments until the training run finishes.
- Bash through git-bash mangles WSL paths (`/home/...` → `C:/Program Files/Git/home/...`).
  Use PowerShell `wsl.exe -- ...` for anything path-dependent.
- Always quote heredoc-style multi-line strings, but PowerShell here-strings
  end-token (`'@`) must be at column 0.
- Process exit segfault during Python interpreter shutdown is normal for
  Filament teardown on OSMesa. All training I/O completes before that.
  Just expect EXIT=139 on every run.
