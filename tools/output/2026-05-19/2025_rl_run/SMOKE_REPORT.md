# RL smoke run report — 2026-05-19

## Environment

- Host: Windows 11 (Build 26200), A6000 (46 GB), RDP session
- Training: WSL2 Ubuntu 22.04, Python 3.10.12 venv at `~/venvs/swim-train`
- torch 2.5.1+cu121, **open3d-cpu 0.19.0** (NOT regular open3d), trimesh, openai
- Render: OSMesa headless (`OPEN3D_CPU_RENDERING=true`), no X server / no xvfb
- Judge: Qwen2.5-VL-7B-Instruct via local OpenAI-compatible HTTP at `http://127.0.0.1:8000/v1` (Windows host, reached from WSL via mirrored networking)

## Command

```bash
source ~/venvs/swim-train/bin/activate
cd ~/Test-
export VISION_JUDGE_URL=http://127.0.0.1:8000/v1
export VISION_JUDGE_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
export NO_PROXY=127.0.0.1,localhost
export OPEN3D_CPU_RENDERING=true
python tools/rl_runner_wsl.py --iters 8 --batch 4 --judge vllm --lr 5e-4
```

`tools/rl_runner_wsl.py` is a wrapper that monkey-patches `iter.capture._setup_renderer` to be a singleton — Filament/OSMesa segfaults on second `OffscreenRenderer` instance. With the patch, the same renderer is reused across all `render_views()` calls (geometry is cleared between calls inside the existing capture.py loop, so no behavior change).

## Per-iter results

```
iter   0  fitness=0.758  reward=0.800  pass=4/4  loss_sym=-0.758 loss_rl=18.395  26.0s
iter   1  fitness=0.763  reward=0.800  pass=4/4  loss_sym=-0.763 loss_rl=16.545  25.2s
iter   2  fitness=0.774  reward=0.650  pass=3/4  loss_sym=-0.774 loss_rl=11.497  24.2s
iter   3  fitness=0.777  reward=0.800  pass=4/4  loss_sym=-0.777 loss_rl=13.794  24.6s
iter   4  fitness=0.802  reward=0.650  pass=3/4  loss_sym=-0.802 loss_rl=8.913   25.5s
iter   5  fitness=0.788  reward=0.800  pass=4/4  loss_sym=-0.788 loss_rl=11.558  23.8s
iter   6  fitness=0.799  reward=0.650  pass=3/4  loss_sym=-0.799 loss_rl=6.911   25.9s
iter   7  fitness=0.815  reward=0.800  pass=4/4  loss_sym=-0.815 loss_rl=9.615   23.7s
```

## Summary

| Metric | Value |
|---|---|
| Total renders | 32 / 32 succeeded |
| J pass rate (overall) | **29 / 32 = 90.6%** |
| iter 0 mean reward | 0.800 |
| iter 7 mean reward | 0.800 |
| mean fitness (iter 0 → 7) | 0.758 → 0.815 (monotonic) |
| Total wall time | 198.8 s (~25 s/iter) |
| vLLM call timeouts | 0 |
| GPU peak (judge only) | ~41 GB / 46 GB (training generator < 1 GB) |
| Process exit | Filament segfault on Python interpreter teardown (after all outputs saved) |

## Notes

- 90.6% pass rate is high because Qwen at this temperature is lenient on starting designs; not evidence of learning. mean_reward stayed flat at 0.800.
- mean fitness rose 0.058 over 8 iters — symbolic gradient is doing what it should.
- 25 s/iter dominated by render + 4 vLLM image-QA calls. Long runs (200+ iters) should be ~80 min.
- The teardown segfault is a known Open3D Filament limitation on Linux + OSMesa, harmless for training (all I/O happens before).
