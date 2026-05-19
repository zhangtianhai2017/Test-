"""WSL2 wrapper for tools/rl_runner.py.

The Linux Open3D Filament backend segfaults when multiple OffscreenRenderer
instances are created in the same process (Mesa OSMesa limitation). The
upstream code in iter/capture.py constructs a new OffscreenRenderer per
render_views() call, which means the SECOND batch item of the FIRST iter
takes the process down.

Fix without touching iter/capture.py: monkey-patch _setup_renderer to
memoize a single OffscreenRenderer per (W, H). render_views already calls
R.scene.clear_geometry() between view loops, so re-use is safe — background,
sun light, indirect light are scene-level and survive between renders.

Usage: same args as tools/rl_runner.py.

  python tools/rl_runner_wsl.py --iters 8 --batch 4 --judge vllm --lr 5e-4
"""
from __future__ import annotations

import os
import sys

# Force OSMesa headless before any open3d import
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

# Make tools/ imports work the same way rl_runner.py does
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Monkey-patch BEFORE rl_runner imports capture (rl_runner does
# `import iter.capture as cap` at top-level)
import iter.capture as cap

_renderer_cache: dict = {}
_orig_setup_renderer = cap._setup_renderer


def _setup_renderer_singleton(W: int, H: int):
    key = (W, H)
    R = _renderer_cache.get(key)
    if R is None:
        R = _orig_setup_renderer(W, H)
        _renderer_cache[key] = R
        print(f"[wsl-patch] created OffscreenRenderer {W}x{H} (cached)",
              flush=True)
    return R


cap._setup_renderer = _setup_renderer_singleton

# Now hand off to the real runner
import rl_runner  # noqa: E402

if __name__ == "__main__":
    rl_runner.main()
