"""
Stitch a single overview PNG for an existing seed_batch_20x6 run.

Lays out one row per seed, 20 thumbnail front-views per row, so the
full 120-variant set is visible side-by-side without clicking into
each contact sheet. Also rewrites INDEX.md so the overview + per-seed
contact sheets all render inline on GitHub.

Usage:
    python3 tools/build_batch_overview.py <batch_dir>
    python3 tools/build_batch_overview.py           # auto-pick newest
"""
from __future__ import annotations

import os, sys, glob, json
from PIL import Image, ImageDraw, ImageFont


THUMB_W, THUMB_H = 160, 240   # one front-view thumbnail
PAD = 4
ROW_LABEL_W = 220             # space for seed name on the left
COLS = 20                     # 20 variants per seed
HEADER_H = 26                 # column index strip
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools", "output")


def newest_batch_dir() -> str:
    candidates = sorted(glob.glob(os.path.join(
        ROOT, "*", "*_seed_batch_20x6")))
    if not candidates:
        raise SystemExit("no seed_batch_20x6 dirs under tools/output/")
    return candidates[-1]


def build_overview(batch_dir: str) -> str:
    seeds = sorted(d for d in os.listdir(batch_dir)
                   if os.path.isdir(os.path.join(batch_dir, d)))
    if not seeds:
        raise SystemExit(f"no seed dirs in {batch_dir}")

    W = ROW_LABEL_W + COLS * (THUMB_W + PAD) + PAD
    H = HEADER_H + len(seeds) * (THUMB_H + PAD) + PAD
    canvas = Image.new("RGB", (W, H), (245, 245, 247))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        font_b = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    except Exception:
        font = font_b = ImageFont.load_default()

    # header row: 00..19
    for c in range(COLS):
        x = ROW_LABEL_W + c * (THUMB_W + PAD) + THUMB_W // 2
        draw.text((x, 6), f"#{c:02d}", fill=(60, 60, 70), font=font,
                  anchor="mm")

    for r, seed in enumerate(seeds):
        y = HEADER_H + r * (THUMB_H + PAD)
        # seed label on left
        draw.text((8, y + 6), seed.replace("_", "\n", 1),
                  fill=(20, 20, 30), font=font_b)
        # try to surface archetype too
        src = os.path.join(batch_dir, seed, "_source_seed.json")
        if os.path.isfile(src):
            try:
                meta = json.load(open(src))
                draw.text((8, y + THUMB_H - 20),
                          meta.get("archetype", "")[:24],
                          fill=(110, 110, 120), font=font)
            except Exception:
                pass
        for c in range(COLS):
            p = os.path.join(batch_dir, seed, f"{c:02d}", "01_front.png")
            x = ROW_LABEL_W + c * (THUMB_W + PAD)
            if os.path.isfile(p):
                img = Image.open(p).convert("RGB").resize(
                    (THUMB_W, THUMB_H), Image.LANCZOS)
                canvas.paste(img, (x, y))
            else:
                draw.rectangle([x, y, x + THUMB_W, y + THUMB_H],
                               outline=(200, 100, 100), width=2)
                draw.text((x + THUMB_W // 2, y + THUMB_H // 2),
                          "missing", fill=(150, 50, 50), font=font,
                          anchor="mm")

    out = os.path.join(batch_dir, "overview.png")
    canvas.save(out, optimize=True)
    return out


def rewrite_index(batch_dir: str) -> str:
    seeds = sorted(d for d in os.listdir(batch_dir)
                   if os.path.isdir(os.path.join(batch_dir, d)))

    lines: list[str] = []
    lines.append("# Diverse-seed batch — 20 outfits × 6 seeds")
    lines.append("")
    lines.append("All 120 variants in one frame (rows = seeds, columns = "
                 "variant index 00..19, front view only):")
    lines.append("")
    lines.append("![overview](overview.png)")
    lines.append("")
    lines.append("## Per-seed contact sheets (front + label)")
    lines.append("")
    for s in seeds:
        meta_path = os.path.join(batch_dir, s, "_source_seed.json")
        arch = ""
        if os.path.isfile(meta_path):
            try:
                arch = json.load(open(meta_path)).get("archetype", "")
            except Exception:
                pass
        lines.append(f"### `{s}`  —  *{arch}*")
        lines.append("")
        lines.append(f"![{s}]({s}/contact.png)")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Each variant directory `<seed>/NN/` contains "
                 "`outfit.json`, `01_front.png`, `04_back.png`. "
                 "Source seeds live under `<seed>/_source_seed.json`. "
                 "Full slot picks per variant: see `summary.json`.")
    out = os.path.join(batch_dir, "INDEX.md")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out


def main() -> None:
    batch_dir = sys.argv[1] if len(sys.argv) > 1 else newest_batch_dir()
    batch_dir = os.path.abspath(batch_dir)
    print(f"batch_dir = {batch_dir}")
    o = build_overview(batch_dir)
    i = rewrite_index(batch_dir)
    print(f"  overview = {o}  ({os.path.getsize(o)//1024} KiB)")
    print(f"  INDEX.md = {i}")


if __name__ == "__main__":
    main()
