"""
256-color palette for v3 stroke output.

Composition (per docs/design/2026-05-27_schema_redesign_v3.md §9 D8 +
2026-05-27 chat decision):

  Slots 0-31:   named anchor colors (commercially distinct vocab)
                — covers SHOWCASE_BRIEFS color names + common fashion vocab
                — sbert(name) is the brief-side handle for these
  Slots 32-255: CIELAB-uniform fill (~32 hues × 7 lightness/saturation
                grid points) — ensures the palette densely covers the
                color space, not just the named-color clusters

Each slot has:
    name_en: str       (CSS-name or descriptive)
    name_cn: str       (Chinese)
    rgb:     (r, g, b) ∈ [0, 1]
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os


@dataclass(frozen=True)
class PaletteEntry:
    name_en: str
    name_cn: str
    rgb:     tuple[float, float, float]


# ─── 32 anchor colors ─────────────────────────────────────────────────

NAMED_ANCHORS: list[PaletteEntry] = [
    # 1-9: SHOWCASE_BRIEFS color names + black/white
    PaletteEntry("ivory",        "象牙白",     (0.95, 0.92, 0.88)),
    PaletteEntry("black",        "黑",         (0.10, 0.10, 0.12)),
    PaletteEntry("white",        "白",         (0.98, 0.98, 0.98)),
    PaletteEntry("silver",       "银",         (0.82, 0.82, 0.85)),
    PaletteEntry("navy",         "海军蓝",     (0.08, 0.18, 0.45)),
    PaletteEntry("hot pink",     "亮粉",       (0.95, 0.25, 0.50)),
    PaletteEntry("orange",       "橙",         (0.98, 0.50, 0.10)),
    PaletteEntry("emerald",      "翡翠绿",     (0.10, 0.65, 0.40)),
    PaletteEntry("burgundy",     "酒红",       (0.50, 0.10, 0.20)),
    PaletteEntry("neon yellow",  "荧光黄",     (0.95, 0.95, 0.20)),

    # 10-19: common nuanced fashion colors
    PaletteEntry("nude",         "裸色",       (0.85, 0.70, 0.65)),
    PaletteEntry("dusty rose",   "豆沙粉",     (0.80, 0.55, 0.58)),
    PaletteEntry("sage",         "鼠尾草绿",   (0.60, 0.72, 0.55)),
    PaletteEntry("mauve",        "藕粉",       (0.62, 0.45, 0.58)),
    PaletteEntry("coral",        "珊瑚",       (0.97, 0.55, 0.45)),
    PaletteEntry("mint",         "薄荷",       (0.55, 0.88, 0.78)),
    PaletteEntry("taupe",        "灰褐",       (0.55, 0.45, 0.40)),
    PaletteEntry("champagne",    "香槟金",     (0.94, 0.85, 0.70)),
    PaletteEntry("blush",        "腮红粉",     (0.95, 0.78, 0.78)),
    PaletteEntry("plum",         "李子紫",     (0.45, 0.25, 0.45)),

    # 20-27: game / sci-fi accent palette
    PaletteEntry("cyber teal",   "赛博青",     (0.10, 0.85, 0.95)),
    PaletteEntry("neon magenta", "荧光品红",   (1.00, 0.10, 0.85)),
    PaletteEntry("violet",       "紫罗兰",     (0.55, 0.10, 0.85)),
    PaletteEntry("blood crimson","血红",       (0.65, 0.05, 0.10)),
    PaletteEntry("void black",   "虚空黑",     (0.04, 0.04, 0.08)),
    PaletteEntry("gold",         "金",         (0.90, 0.78, 0.20)),
    PaletteEntry("copper",       "紫铜",       (0.72, 0.45, 0.25)),
    PaletteEntry("jade",         "玉",         (0.30, 0.60, 0.50)),

    # 28-31: extra cultural / mood
    PaletteEntry("imperial red", "国旗红",     (0.85, 0.12, 0.20)),
    PaletteEntry("ink",          "墨黑",       (0.13, 0.15, 0.20)),
    PaletteEntry("pearl",        "珍珠白",     (0.94, 0.93, 0.92)),
    PaletteEntry("obsidian",     "黑曜石",     (0.18, 0.12, 0.22)),
]
N_ANCHORS = len(NAMED_ANCHORS)


# ─── 224 CIELAB-uniform fill ──────────────────────────────────────────

def _hsl_to_rgb(h: float, s: float, L: float) -> tuple[float, float, float]:
    """h ∈ [0,1] hue, s ∈ [0,1] saturation, L ∈ [0,1] lightness."""
    if s == 0:
        return (L, L, L)
    def hue2rgb(p, q, t):
        if t < 0: t += 1
        if t > 1: t -= 1
        if t < 1/6: return p + (q - p) * 6 * t
        if t < 1/2: return q
        if t < 2/3: return p + (q - p) * (2/3 - t) * 6
        return p
    q = L * (1 + s) if L < 0.5 else L + s - L * s
    p = 2 * L - q
    return (hue2rgb(p, q, h + 1/3),
            hue2rgb(p, q, h),
            hue2rgb(p, q, h - 1/3))


def _build_fill(n: int) -> list[PaletteEntry]:
    """Approximate CIELAB-uniform fill via HSL grid sampling.

    32 hues × 7 (sat, light) grid points = 224. We don't have CIELAB
    here without skimage/colormath; HSL grid is the simple proxy that
    still gives a roughly perceptually-spread set.
    """
    out = []
    n_hues = 32
    sl_grid = [
        (0.85, 0.30), (0.85, 0.50), (0.85, 0.70),     # bright row
        (0.60, 0.40), (0.60, 0.60),                    # medium row
        (0.35, 0.45), (0.35, 0.65),                    # muted row
    ]
    for i in range(n):
        h_idx = i % n_hues
        sl_idx = i // n_hues
        if sl_idx >= len(sl_grid):
            break
        h = h_idx / n_hues
        s, L = sl_grid[sl_idx]
        rgb = _hsl_to_rgb(h, s, L)
        name_en = f"fill_h{h_idx:02d}_sl{sl_idx}"
        out.append(PaletteEntry(name_en, name_en, rgb))
    return out


PALETTE: list[PaletteEntry] = NAMED_ANCHORS + _build_fill(256 - N_ANCHORS)
assert len(PALETTE) == 256, f"palette has {len(PALETTE)} entries, expected 256"


# ─── public API ────────────────────────────────────────────────────────

def rgb_array():
    """Return the palette as a (256, 3) numpy float32 array."""
    import numpy as np
    return np.array([e.rgb for e in PALETTE], dtype=np.float32)


def get(idx: int) -> PaletteEntry:
    return PALETTE[max(0, min(255, idx))]


def find_by_name(name: str) -> int | None:
    """Find a palette index by EN or CN name. Returns None if not found."""
    name_low = name.strip().lower()
    for i, e in enumerate(PALETTE):
        if e.name_en.lower() == name_low or e.name_cn == name.strip():
            return i
    return None


# ─── smoke ────────────────────────────────────────────────────────────

def _smoke():
    print("─── palette smoke ───")
    print(f"total = {len(PALETTE)}")
    print(f"named anchors = {N_ANCHORS}")
    print(f"fill         = {len(PALETTE) - N_ANCHORS}")
    print("\nfirst 10:")
    for i in range(10):
        e = PALETTE[i]
        print(f"  [{i:>3}] {e.name_en:<14} {e.name_cn:<10}  rgb=({e.rgb[0]:.2f},{e.rgb[1]:.2f},{e.rgb[2]:.2f})")
    # find by name
    idx_ivory = find_by_name("ivory")
    idx_xy = find_by_name("象牙白")
    idx_sage = find_by_name("sage")
    idx_neon = find_by_name("荧光黄")
    print(f"\nfind_by_name('ivory') = {idx_ivory}")
    print(f"find_by_name('象牙白') = {idx_xy}")
    print(f"find_by_name('sage') = {idx_sage}")
    print(f"find_by_name('荧光黄') = {idx_neon}")
    arr = rgb_array()
    print(f"\nrgb_array shape = {arr.shape}, dtype = {arr.dtype}")

    # save preview swatch png
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(16, 4), dpi=100)
        cols = 32
        rows = 8
        for i in range(256):
            r, c = i // cols, i % cols
            ax.add_patch(plt.Rectangle(
                (c, rows - 1 - r), 1, 1, facecolor=PALETTE[i].rgb))
            if i < N_ANCHORS:
                ax.text(c + 0.5, rows - 1 - r + 0.4,
                         PALETTE[i].name_en, ha='center', va='center',
                         fontsize=4, color='black' if sum(PALETTE[i].rgb) > 1.5 else 'white')
        ax.set_xlim(0, cols); ax.set_ylim(0, rows)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_aspect('equal')
        out_path = "/mnt/c/Users/Administrator/Test-/tools/output/2026-05-27/p21_palette/palette_swatch.png"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        fig.savefig(out_path, bbox_inches='tight', dpi=120)
        plt.close(fig)
        print(f"\nswatch -> {out_path}")
    except Exception as exc:
        print(f"(swatch skipped: {exc})")


if __name__ == "__main__":
    _smoke()
