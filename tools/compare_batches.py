"""
A/B compare two seed_batch_20x6 runs that share identical RNG_MASTER,
so the same (seed, variant) index refers to the same outfit but
rendered with different code paths.

Produces a single PNG where every cell is a (pre | post) diptych so
visual diffs (e.g. the armpit-bleed fix) read at a glance.

Usage:
    python3 tools/compare_batches.py <pre_task_dir> <post_task_dir>
"""
from __future__ import annotations

import os, sys
from PIL import Image, ImageDraw, ImageFont


THUMB_W, THUMB_H = 140, 210   # one front-view thumbnail
GAP = 2                       # inside a diptych
CELL_GAP = 6                  # between diptychs
ROW_GAP = 10                  # between rows
ROW_LABEL_W = 220
HEADER_H = 30
COLS = 20


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: compare_batches.py <pre_task_dir> <post_task_dir>")
    pre, post = (os.path.abspath(p) for p in sys.argv[1:3])
    seeds = sorted(d for d in os.listdir(pre)
                   if os.path.isdir(os.path.join(pre, d))
                   and os.path.isdir(os.path.join(post, d)))
    if not seeds:
        raise SystemExit("no overlapping seed dirs")

    cell_w = THUMB_W * 2 + GAP
    W = ROW_LABEL_W + COLS * (cell_w + CELL_GAP) + CELL_GAP
    H = HEADER_H + len(seeds) * (THUMB_H + ROW_GAP) + ROW_GAP
    canvas = Image.new("RGB", (W, H), (245, 245, 247))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
        font_b = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        font_h = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except Exception:
        font = font_b = font_h = ImageFont.load_default()

    draw.text((12, 6), f"A/B  left = pre-fix  ({os.path.basename(pre)})  "
                       f"|  right = post-fix  ({os.path.basename(post)})",
              fill=(20, 20, 30), font=font_h)

    for c in range(COLS):
        x = ROW_LABEL_W + c * (cell_w + CELL_GAP) + cell_w // 2
        draw.text((x, HEADER_H - 4), f"#{c:02d}",
                  fill=(60, 60, 70), font=font, anchor="ms")

    n_pre_ok = n_post_ok = 0
    for r, seed in enumerate(seeds):
        y = HEADER_H + r * (THUMB_H + ROW_GAP)
        draw.text((8, y + 4), seed.replace("_", "\n", 1),
                  fill=(20, 20, 30), font=font_b)
        for ci in range(COLS):
            x = ROW_LABEL_W + ci * (cell_w + CELL_GAP)
            for side, root in [("pre", pre), ("post", post)]:
                p = os.path.join(root, seed, f"{ci:02d}", "01_front.png")
                xi = x if side == "pre" else x + THUMB_W + GAP
                if os.path.isfile(p):
                    img = Image.open(p).convert("RGB").resize(
                        (THUMB_W, THUMB_H), Image.LANCZOS)
                    canvas.paste(img, (xi, y))
                    if side == "pre":
                        n_pre_ok += 1
                    else:
                        n_post_ok += 1
                else:
                    draw.rectangle([xi, y, xi + THUMB_W, y + THUMB_H],
                                   outline=(200, 100, 100), width=1)

    out = os.path.join(post, "_compare_pre_post.png")
    canvas.save(out, optimize=True)
    print(f"compare image -> {out}  ({os.path.getsize(out)//1024} KiB)")
    print(f"pre cells filled: {n_pre_ok}/{COLS*len(seeds)}  "
          f"post: {n_post_ok}/{COLS*len(seeds)}")


if __name__ == "__main__":
    main()
