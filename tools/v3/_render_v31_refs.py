"""Render all 7 v3.1 hand-crafted (Panel+Stroke) references through
the v2 full chain. Composite into a grid PNG."""
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from v3.stroke_schema import all_reference_designs_v31
from v3.full_chain_render import render_design_3d
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = "tools/output/2026-05-28/p29_v31_refs"
os.makedirs(OUT_DIR, exist_ok=True)

refs = all_reference_designs_v31()
paths = []
for name, tokens in refs.items():
    p = os.path.join(OUT_DIR, f"{name}.png")
    print(f"rendering {name} ({len(tokens)} tokens)...")
    render_design_3d(tokens, p, verbose=True)
    paths.append((name, p))
    print(f"  ✓ {os.path.getsize(p):,} bytes\n")

# Composite grid
W, H = 200, 320
pad = 8
cols = 4
rows = (len(paths) + cols - 1) // cols
cw = cols * (W + pad) + pad
ch = rows * (H + 24 + pad) + pad + 30
canvas = Image.new("RGB", (cw, ch), (245, 245, 247))
draw = ImageDraw.Draw(canvas)
try:
    font_t = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
except:
    font_t = font = ImageFont.load_default()
draw.text((cw // 2, 14),
          "v3.1 hand-crafted Panel+Stroke references → v2 full chain rendering",
          font=font_t, fill=(40, 40, 40), anchor="mm")
for i, (name, path) in enumerate(paths):
    r, c = i // cols, i % cols
    im = Image.open(path).convert("RGB")
    im.thumbnail((W, H), Image.LANCZOS)
    x = pad + c * (W + pad)
    y = 30 + pad + r * (H + 24 + pad)
    ox = x + (W - im.width) // 2
    canvas.paste(im, (ox, y))
    draw.text((x + W // 2, y + H + 4), name, font=font, fill=(40, 40, 40), anchor="mt")
out = os.path.join(OUT_DIR, "grid.png")
canvas.save(out)
print(f"\nwrote grid -> {out} ({cw}x{ch})")
