"""Build an 8-up 2x4 montage with brief + cutout_mode labels.

Usage: python tools/_make_showcase_overview.py <dir>
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

base = sys.argv[1]
THUMB_W, THUMB_H = 360, 540
PAD = 8
LBL_H = 44
COLS = 4
ROWS = 2

# briefs may not be saved per-design; pull cutout + archetype from outfit.json
items = []
for d in sorted(os.listdir(base)):
    p = os.path.join(base, d, "01_front.png")
    j = os.path.join(base, d, "outfit.json")
    if not (os.path.exists(p) and os.path.exists(j)):
        continue
    o = json.load(open(j, encoding="utf-8"))
    items.append((
        d,
        p,
        o.get("archetype", "?"),
        o.get("global_design", {}).get("cutout_mode", "?"),
    ))

W = COLS * (THUMB_W + PAD) + PAD
H = ROWS * (THUMB_H + LBL_H + PAD) + PAD
canvas = Image.new("RGB", (W, H), (245, 245, 247))
draw = ImageDraw.Draw(canvas)

try:
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    font_b = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
except Exception:
    font = font_b = ImageFont.load_default()

ALIASED = {"side_left_circle", "side_right_circle", "under_bust_band",
           "navel_circle", "navel_diamond", "collar_keyhole", "collar_o",
           "waist_diagonal", "hip_window"}

for i, (vid, p, arch, cut) in enumerate(items[:COLS * ROWS]):
    r, c = divmod(i, COLS)
    x = PAD + c * (THUMB_W + PAD)
    y = PAD + r * (THUMB_H + LBL_H + PAD)
    im = Image.open(p).convert("RGB")
    im.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
    # center-paste
    ox = x + (THUMB_W - im.width) // 2
    oy = y + (THUMB_H - im.height) // 2
    canvas.paste(im, (ox, oy))
    # label
    tag = " (no-op)" if cut in ALIASED else (" *" if cut != "none" else "")
    color = (90, 90, 110) if cut in ALIASED or cut == "none" else (200, 30, 30)
    draw.text((x + 6, y + THUMB_H + 4), f"{vid}  {arch}",
              font=font_b, fill=(20, 20, 30))
    draw.text((x + 6, y + THUMB_H + 22), f"cutout: {cut}{tag}",
              font=font, fill=color)

out = os.path.join(base, "overview.png")
canvas.save(out)
print(f"wrote {out}  ({W}x{H})")
