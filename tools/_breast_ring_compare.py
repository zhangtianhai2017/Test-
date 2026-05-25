"""Side-by-side comparison: original 'strict' renders vs 'majority' fix
for the same 3 designs the user flagged as having breast rings."""
import os
from PIL import Image, ImageDraw, ImageFont

PAIRS = [
    ("v00 bandeau_back_band SOFTCUP_DEEP_V",
     "tools/output/2026-05-25/p4_showcase/v00/01_front.png",
     "tools/output/2026-05-25/p5_no_breast_ring/_p4v00_majority/01_front.png"),
    ("v02 bralette SOFTCUP_ASYM_NECK",
     "tools/output/2026-05-25/p4_showcase/v02/01_front.png",
     "tools/output/2026-05-25/p5_no_breast_ring/_p4v02_majority/01_front.png"),
    ("v05 one_piece SOFTCUP_DEEP_V",
     "tools/output/2026-05-25/p4_showcase/v05/01_front.png",
     "tools/output/2026-05-25/p5_no_breast_ring/_p4v05_majority/01_front.png"),
]

W, H = 360, 540
PAD = 8
HDR = 30
LBL = 26
COLS = 2
ROWS = len(PAIRS)

cw = COLS * (W + PAD) + PAD
ch = ROWS * (H + LBL + PAD) + HDR + PAD
canvas = Image.new("RGB", (cw, ch), (245, 245, 247))
draw = ImageDraw.Draw(canvas)
try:
    font_b = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
except Exception:
    font_b = font = ImageFont.load_default()

# Top headers
draw.text((PAD + W//2, 8), "BEFORE  (strict 3-of-3 polygon test)",
          font=font_b, fill=(180, 30, 30), anchor="mm")
draw.text((PAD + W + PAD + W//2, 8), "AFTER  (majority 2-of-3 + breast-peak lift)",
          font=font_b, fill=(30, 130, 30), anchor="mm")

for r, (label, p_before, p_after) in enumerate(PAIRS):
    y = HDR + r * (H + LBL + PAD)
    for c, p in enumerate([p_before, p_after]):
        x = PAD + c * (W + PAD)
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((W, H), Image.LANCZOS)
            ox = x + (W - im.width) // 2
            oy = y + (H - im.height) // 2
            canvas.paste(im, (ox, oy))
        else:
            draw.text((x + W//2, y + H//2), "missing", fill=(160, 0, 0),
                      anchor="mm", font=font_b)
    draw.text((PAD, y + H + 4), label, font=font_b, fill=(20, 20, 30))

out = "tools/output/2026-05-25/p5_no_breast_ring/_compare_before_after.png"
canvas.save(out)
print(f"wrote {out} ({cw}x{ch})")
