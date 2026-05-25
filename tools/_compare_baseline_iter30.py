"""Side-by-side: baseline 2050 ckpt (p6_clean) vs iter30 fitness-only (p7_iter30)."""
import os
from PIL import Image, ImageDraw, ImageFont

BASE = "tools/output/2026-05-25/p6_clean"
ITER = "tools/output/2026-05-25/p7_iter30"

W, H, PAD, HDR, LBL = 280, 420, 6, 28, 18
N = 8
cw = 2 * (W + PAD) + PAD
ch = HDR + N * (H + LBL + PAD) + PAD
canvas = Image.new("RGB", (cw, ch), (245, 245, 247))
draw = ImageDraw.Draw(canvas)
try:
    font_b = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
except Exception:
    font_b = font = ImageFont.load_default()

draw.text((PAD + W // 2, 8), "BASELINE 2050 ckpt", font=font_b,
          fill=(60, 60, 60), anchor="mm")
draw.text((PAD + W + PAD + W // 2, 8), "ITER 30 (fitness-only retrain)",
          font=font_b, fill=(20, 100, 20), anchor="mm")

for i in range(N):
    vid = f"v{i:02d}"
    y = HDR + i * (H + LBL + PAD)
    for c, root in enumerate([BASE, ITER]):
        p = os.path.join(root, vid, "01_front.png")
        x = PAD + c * (W + PAD)
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((W, H), Image.LANCZOS)
            ox = x + (W - im.width) // 2
            oy = y + (H - im.height) // 2
            canvas.paste(im, (ox, oy))
    draw.text((PAD, y + H + 2), vid, font=font_b, fill=(20, 20, 30))

out = "tools/output/2026-05-25/p7_iter30/_compare_baseline_vs_iter30.png"
canvas.save(out)
print(f"wrote {out} ({cw}x{ch})")
