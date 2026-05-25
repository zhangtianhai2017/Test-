"""Build visual catalogs from regression render output.

For each kind (cup/bottom/accessory/hardware): walk the per-entry
01_front.png files and stitch into one big labeled grid. Failing
entries get a red 'BROKEN' tile so the grid stays aligned.

Usage:  python tools/_build_library_catalog.py <regression_out_dir>
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

base = sys.argv[1]
report_path = os.path.join(base, "regression_report.json")
if not os.path.isfile(report_path):
    sys.exit(f"no regression_report.json in {base}")
report = json.load(open(report_path))

# Sort entries within each kind by status (ok first, then broken last)
RANK = {"ok": 0, "crashed_w_png": 1, "empty_png": 2,
        "crashed_no_png": 3, "timeout": 4, "exception": 5}


def status_rank(s):
    for prefix, r in RANK.items():
        if s.startswith(prefix):
            return r
    return 9


THUMB_W, THUMB_H = 200, 300
PAD = 4
LBL = 22
TITLE = 36

try:
    font_b = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
except Exception:
    font_b = font = ImageFont.load_default()

for kind in sorted({r["kind"] for r in report.values()}):
    entries = sorted(
        [(eid, r) for eid, r in report.items() if r["kind"] == kind],
        key=lambda x: (status_rank(x[1]["status"]), x[0]),
    )
    n = len(entries)
    cols = min(8, max(4, int(math.ceil(math.sqrt(n * THUMB_H / THUMB_W)))))
    rows = math.ceil(n / cols)
    W = cols * (THUMB_W + PAD) + PAD
    H = TITLE + rows * (THUMB_H + LBL + PAD) + PAD
    canvas = Image.new("RGB", (W, H), (250, 250, 252))
    draw = ImageDraw.Draw(canvas)
    n_ok = sum(1 for _, r in entries
                if r["status"] in ("ok", "crashed_w_png"))
    title = f"{kind} catalog — {n_ok}/{n} ok, {cols} cols × {rows} rows"
    draw.text((PAD, 6), title, font=font_b, fill=(20, 20, 30))

    for i, (eid, rep) in enumerate(entries):
        r, c = divmod(i, cols)
        x = PAD + c * (THUMB_W + PAD)
        y = TITLE + r * (THUMB_H + LBL + PAD)
        png = os.path.join(base, kind, eid, "01_front.png")
        status = rep["status"]
        broken = status not in ("ok", "crashed_w_png")
        if os.path.exists(png) and os.path.getsize(png) > 1000:
            im = Image.open(png).convert("RGB")
            im.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
            ox = x + (THUMB_W - im.width) // 2
            oy = y + (THUMB_H - im.height) // 2
            canvas.paste(im, (ox, oy))
        else:
            draw.rectangle([x, y, x + THUMB_W, y + THUMB_H],
                           fill=(255, 220, 220), outline=(180, 30, 30))
            draw.text((x + THUMB_W // 2, y + THUMB_H // 2), "NO PNG",
                      font=font_b, fill=(180, 30, 30), anchor="mm")
        # label
        label_color = (30, 30, 30) if not broken else (160, 30, 30)
        draw.text((x + 4, y + THUMB_H + 2), eid[:30],
                  font=font, fill=label_color)
        draw.text((x + 4, y + THUMB_H + 12), f"[{status[:18]}]",
                  font=font, fill=label_color)

    out = os.path.join(base, f"_catalog_{kind}.png")
    canvas.save(out)
    print(f"wrote {out} ({W}x{H}; {n_ok}/{n} ok)")

# Build a death list JSON
deaths = {eid: r for eid, r in report.items()
          if r["status"] not in ("ok", "crashed_w_png")}
death_path = os.path.join(base, "_death_list.json")
with open(death_path, "w") as f:
    json.dump(deaths, f, indent=2)
print(f"\nwrote {death_path}  ({len(deaths)} broken entries)")
if deaths:
    print("first 15 broken:")
    for eid, r in list(deaths.items())[:15]:
        print(f"  {eid:40s} {r['status']:20s} {(r.get('error') or '')[:80]}")
