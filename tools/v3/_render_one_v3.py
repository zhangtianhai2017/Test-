"""Subprocess-isolated single-design renderer for v3 strokes.

Why subprocess: Filament+OSMesa leaks state across renders. The v2
pipeline already uses this pattern (_render_one_outfit.py). Calling
this in a fresh interpreter avoids the leak.

Usage:
    python tools/v3/_render_one_v3.py <strokes_json> <out_png> [view]
"""
import json
import os
import sys

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STROKES_JSON = sys.argv[1]
OUT_PNG = sys.argv[2]
VIEW = sys.argv[3] if len(sys.argv) > 3 else "front"

with open(STROKES_JSON, encoding="utf-8") as f:
    data = json.load(f)

from v3.stroke_schema import stroke_from_dict   # noqa: E402
from v3.stroke_renderer import render_design_png  # noqa: E402

strokes = [stroke_from_dict(d) for d in data["strokes"]]
print(f"loaded {len(strokes)} strokes from {STROKES_JSON}")
render_design_png(strokes, OUT_PNG, view=VIEW)
print(f"OK rendered → {OUT_PNG}")
