"""Programmatic inspector for the 2-row composite swimsuit image.

We don't view the file ourselves — we slice it into a small grid and dump
per-cell statistics (dominant fabric color, coverage shape) so we can hand-
craft two genome seeds from numbers rather than from looking at pixels.
"""
from __future__ import annotations
import argparse, json, os
from collections import Counter
from PIL import Image
import numpy as np

ASSETS = "assets"
OUT_DIR = "tools/output/composite_probe"


def load() -> Image.Image:
    p = os.path.join(ASSETS, "2-swimsuits-2row.png")
    return Image.open(p).convert("RGBA")


def split_rows(img: Image.Image) -> list[Image.Image]:
    """Top half / bottom half as two rows."""
    w, h = img.size
    return [img.crop((0, 0, w, h // 2)), img.crop((0, h // 2, w, h))]


def split_cells(row: Image.Image, n: int) -> list[Image.Image]:
    w, h = row.size
    cw = w // n
    return [row.crop((i * cw, 0, (i + 1) * cw, h)) for i in range(n)]


def _bg_mask(arr: np.ndarray) -> np.ndarray:
    """Detect studio backdrop. The composite uses a near-uniform grey/white
    background; we treat any pixel that's both low-saturation AND mid-to-high
    luminance as background.
    """
    r, g, b = arr[..., 0].astype(np.int32), arr[..., 1].astype(np.int32), arr[..., 2].astype(np.int32)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    # near-grey
    grey = (mx - mn) < 14
    # bright-ish (skin is brighter but more saturated)
    bright = mx > 110
    return grey & bright


def _skin_mask(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = arr.max(axis=-1).astype(np.int32)
    mn = arr.min(axis=-1).astype(np.int32)
    return (r > 140) & (g > 90) & (g < 200) & (b > 70) & (b < 180) & \
           (r > b) & (r >= g) & ((mx - mn) < 90)


def dominant_fabric_color(cell: Image.Image,
                          bg_thresh: int = 230) -> tuple[float, float, float] | None:
    """Find the dominant non-background, non-skin color in a cell."""
    arr = np.asarray(cell.convert("RGB"), dtype=np.uint8)
    bg = _bg_mask(arr)
    skin = _skin_mask(arr)

    fabric = (~bg) & (~skin)
    if fabric.sum() < 200:
        return None
    pix = arr[fabric]
    # quantize to 6-bit per channel and pick the most common bucket
    q = (pix // 16) * 16 + 8
    keys = [tuple(p) for p in q]
    (rr, gg, bb), _ = Counter(keys).most_common(1)[0]
    return float(rr) / 255.0, float(gg) / 255.0, float(bb) / 255.0


def coverage_metrics(cell: Image.Image) -> dict:
    """Where in the cell is the fabric? Use it to guess top/bottom shapes."""
    arr = np.asarray(cell.convert("RGB"), dtype=np.uint8)
    bg = _bg_mask(arr)
    skin = _skin_mask(arr)
    fabric = (~bg) & (~skin)
    h, w = fabric.shape
    if fabric.sum() < 200:
        return {"area_frac": 0.0}

    # vertical fabric distribution -> v in [0,1] from neckline (0) to ankles (1)
    rows_with_fabric = fabric.any(axis=1)
    ys = np.where(rows_with_fabric)[0]
    y_top = float(ys.min() / h)
    y_bot = float(ys.max() / h)
    band_density = fabric.sum(axis=1) / w

    # split fabric in upper / lower half of body region
    body_top = ys.min()
    body_bot = ys.max()
    mid = (body_top + body_bot) / 2.0
    top_mask = fabric.copy()
    top_mask[int(mid):, :] = False
    bot_mask = fabric.copy()
    bot_mask[: int(mid), :] = False
    top_h = top_mask.any(axis=0).sum() / w  # horizontal width fraction
    bot_h = bot_mask.any(axis=0).sum() / w

    # vertical bands of the top piece — how tall is it?
    if top_mask.sum() > 50:
        ys_t = np.where(top_mask.any(axis=1))[0]
        top_height_frac = float((ys_t.max() - ys_t.min()) / h)
    else:
        top_height_frac = 0.0
    if bot_mask.sum() > 50:
        ys_b = np.where(bot_mask.any(axis=1))[0]
        bot_height_frac = float((ys_b.max() - ys_b.min()) / h)
    else:
        bot_height_frac = 0.0

    return {
        "area_frac": float(fabric.sum() / fabric.size),
        "y_top": y_top,
        "y_bot": y_bot,
        "top_width_frac": float(top_h),
        "bot_width_frac": float(bot_h),
        "top_height_frac": top_height_frac,
        "bot_height_frac": bot_height_frac,
    }


def rgb_to_hsl(r: float, g: float, b: float) -> tuple[float, float, float]:
    import colorsys
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, s, l


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ncols", type=int, default=3,
                    help="how many swimsuits per row")
    ap.add_argument("--save-cells", action="store_true",
                    help="write per-cell crops for visual confirmation")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    img = load()
    rows = split_rows(img)
    print(f"composite size = {img.size}, splitting into 2x{args.ncols}")

    report = []
    for ri, row in enumerate(rows):
        cells = split_cells(row, args.ncols)
        for ci, cell in enumerate(cells):
            tag = f"r{ri}c{ci}"
            col = dominant_fabric_color(cell)
            cov = coverage_metrics(cell)
            entry = {"cell": tag, "size": cell.size,
                     "rgb": col, "cov": cov}
            if col is not None:
                h, s, l = rgb_to_hsl(*col)
                entry["hsl"] = (round(h, 3), round(s, 3), round(l, 3))
            report.append(entry)
            if args.save_cells:
                cell.save(os.path.join(OUT_DIR, f"cell_{tag}.png"))

    out_json = os.path.join(OUT_DIR, "report.json")
    with open(out_json, "w") as f:
        json.dump(report, f, indent=2)
    print(f"wrote {out_json}")
    for e in report:
        print(json.dumps(e, default=str))


if __name__ == "__main__":
    main()
