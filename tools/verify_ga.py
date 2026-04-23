"""
2D front-view bikini GA verifier.

Takes two hand-defined parent genomes (Parent-A, Parent-B), runs the
crossover + mutation operators from docs/bikini-ga-algorithm.md, and
renders parents + N offspring as a single PNG grid so a human can
eyeball whether the offspring look like plausible bikini variants.

Pure stdlib + numpy + matplotlib. Run: `python3 tools/verify_ga.py`.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, asdict, field
from typing import Callable

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, PathPatch, Rectangle
from matplotlib.path import Path
from matplotlib.colors import hsv_to_rgb

SEED = 42
N_OFFSPRING = 8
BLX_ALPHA = 0.3
MUT_SIGMA = 0.08
MUT_PROB_CAT = 0.10
OUT_DIR = os.path.join(os.path.dirname(__file__), "output")


# --------------------------------------------------------------------------
# Genome
# --------------------------------------------------------------------------

TOP_STYLES = ["triangle", "bandeau", "halter", "bralette"]
BOTTOM_STYLES = ["thong", "cheeky", "brief", "high_waist"]
PATTERNS = ["solid", "stripe", "polka", "checker"]

CONT_FIELDS = [
    "cup_width", "cup_height", "neckline_depth", "underband_y", "strap_width",
    "rise", "side_width", "leg_curve",
    "hue", "saturation",
]


@dataclass
class Genome:
    top_style: str
    bottom_style: str
    pattern: str
    cup_width: float
    cup_height: float
    neckline_depth: float
    underband_y: float
    strap_width: float
    rise: float
    side_width: float
    leg_curve: float
    hue: float
    saturation: float

    def as_dict(self) -> dict:
        return asdict(self)

    def clipped(self) -> "Genome":
        d = self.as_dict()
        for k in CONT_FIELDS:
            d[k] = float(np.clip(d[k], 0.0, 1.0))
        return Genome(**d)


# --------------------------------------------------------------------------
# GA operators
# --------------------------------------------------------------------------

def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    """Single-point for discrete fields; BLX-alpha for continuous ones.

    Hue is treated as a circular value: cross on the shorter arc.
    """
    d = {}
    for field_name in ("top_style", "bottom_style", "pattern"):
        d[field_name] = rng.choice([getattr(a, field_name), getattr(b, field_name)])

    for k in CONT_FIELDS:
        va, vb = getattr(a, k), getattr(b, k)
        if k == "hue":
            d[k] = _blx_circular(va, vb, BLX_ALPHA, rng)
        else:
            d[k] = _blx(va, vb, BLX_ALPHA, rng)
    return Genome(**d).clipped()


def mutate(g: Genome, rng: random.Random) -> Genome:
    d = g.as_dict()
    if rng.random() < MUT_PROB_CAT:
        d["top_style"] = rng.choice(TOP_STYLES)
    if rng.random() < MUT_PROB_CAT:
        d["bottom_style"] = rng.choice(BOTTOM_STYLES)
    if rng.random() < MUT_PROB_CAT:
        d["pattern"] = rng.choice(PATTERNS)
    for k in CONT_FIELDS:
        noise = rng.gauss(0, MUT_SIGMA)
        if k == "hue":
            d[k] = (d[k] + noise) % 1.0
        else:
            d[k] = d[k] + noise
    g2 = Genome(**d).clipped()
    return _enforce_constraints(g2)


def _blx(a: float, b: float, alpha: float, rng: random.Random) -> float:
    lo, hi = (a, b) if a <= b else (b, a)
    d = hi - lo
    return rng.uniform(lo - alpha * d, hi + alpha * d)


def _blx_circular(a: float, b: float, alpha: float, rng: random.Random) -> float:
    # pick the shorter arc on the hue circle, then blx on the straight segment
    diff = (b - a) % 1.0
    if diff > 0.5:
        b_adj = b - 1.0
    else:
        b_adj = b
    out = _blx(a, b_adj, alpha, rng)
    return out % 1.0


def _enforce_constraints(g: Genome) -> Genome:
    """Hard rules from §4.2 of the research doc, adapted to 2D."""
    d = g.as_dict()
    # bandeau has no real straps
    if d["top_style"] == "bandeau":
        d["strap_width"] = 0.0
    # cup_height + neckline_depth must not collapse the top
    if d["cup_height"] + d["neckline_depth"] > 1.15:
        d["neckline_depth"] = max(0.0, 1.15 - d["cup_height"])
    # high_waist wants a meaningful rise
    if d["bottom_style"] == "high_waist" and d["rise"] < 0.55:
        d["rise"] = 0.55
    # thong is incompatible with full side coverage
    if d["bottom_style"] == "thong" and d["side_width"] > 0.3:
        d["side_width"] = 0.3
    return Genome(**d)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _color(g: Genome) -> tuple[float, float, float]:
    # saturation from genome, fix value high so it stays visible
    s = 0.3 + 0.6 * g.saturation
    return tuple(hsv_to_rgb([g.hue, s, 0.90]).tolist())


def _draw_torso(ax):
    """Draw a very stylized front-view female torso silhouette as background."""
    # A simple hourglass outline, 1.0 wide, 2.4 tall, centered at x=0
    verts = [
        (-0.38, 1.20),   # right shoulder
        (-0.48, 0.90),   # bust outer
        (-0.30, 0.35),   # waist
        (-0.42, -0.20),  # hip
        (-0.32, -0.95),  # upper thigh
        ( 0.32, -0.95),
        ( 0.42, -0.20),
        ( 0.30, 0.35),
        ( 0.48, 0.90),
        ( 0.38, 1.20),
        (-0.38, 1.20),
    ]
    poly = Polygon(verts, closed=True, facecolor="#f3d9c0", edgecolor="#9c7a5c", linewidth=1.0, zorder=1)
    ax.add_patch(poly)
    # a soft line at the bust apex
    ax.plot([0, 0], [0.4, 0.95], color="#c9a98a", linewidth=0.6, zorder=1.5, alpha=0.6)


def _apply_pattern(ax, path_verts, color, pattern, zorder=3):
    """Draw the fill plus a pattern overlay clipped to the garment path."""
    path = Path(path_verts)
    patch = PathPatch(path, facecolor=color, edgecolor="#222", linewidth=0.8, zorder=zorder)
    ax.add_patch(patch)

    if pattern == "solid":
        return
    # overlay a secondary pattern, clipped to the patch
    xs = [v[0] for v in path_verts]
    ys = [v[1] for v in path_verts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    overlay_color = (1.0, 1.0, 1.0, 0.55)

    if pattern == "stripe":
        n = 8
        for i in range(n):
            y = y0 + (i + 0.5) * (y1 - y0) / n
            h = (y1 - y0) / (n * 2.2)
            r = Rectangle((x0, y - h / 2), x1 - x0, h, facecolor=overlay_color, edgecolor=None, zorder=zorder + 0.1)
            r.set_clip_path(patch)
            ax.add_patch(r)
    elif pattern == "polka":
        rng = np.random.default_rng(0)
        n = 24
        for _ in range(n):
            cx = rng.uniform(x0, x1)
            cy = rng.uniform(y0, y1)
            dot = plt.Circle((cx, cy), 0.018, facecolor=overlay_color, zorder=zorder + 0.1)
            dot.set_clip_path(patch)
            ax.add_patch(dot)
    elif pattern == "checker":
        n = 10
        dx = (x1 - x0) / n
        dy = (y1 - y0) / n
        for i in range(n):
            for j in range(n):
                if (i + j) % 2 == 0:
                    r = Rectangle((x0 + i * dx, y0 + j * dy), dx, dy,
                                  facecolor=overlay_color, edgecolor=None, zorder=zorder + 0.1)
                    r.set_clip_path(patch)
                    ax.add_patch(r)


def _top_paths(g: Genome) -> list[list[tuple[float, float]]]:
    """Return one or more closed polygons for the top garment in front view.

    Most styles return a single polygon; the triangle/halter styles return
    two separate cup polygons so each cup reads as a triangle rather than
    a rectangle-with-a-notch.
    """
    w = 0.18 + 0.35 * g.cup_width                 # half-width of outer cup edge
    h = 0.18 + 0.28 * g.cup_height                # vertical extent of the cup
    nd = 0.02 + 0.22 * g.neckline_depth           # V-neck drop from apex
    band_y = 0.35 + 0.20 * g.underband_y          # underband height
    apex_y = band_y + h                           # top edge
    center_gap = 0.02
    style = g.top_style

    if style == "triangle":
        # two separate triangular cups meeting at a V
        right = [
            (center_gap, apex_y - nd),            # inner top (neckline V apex)
            (w,          apex_y + 0.04),          # outer top (shoulder strap attach)
            (w - 0.02,   band_y + 0.02),          # outer bottom
            (center_gap, band_y),                 # inner bottom
            (center_gap, apex_y - nd),
        ]
        left = [(-x, y) for (x, y) in right]
        return [right, left]
    if style == "bandeau":
        band_h = 0.08 + 0.12 * g.cup_height
        y0 = band_y
        y1 = band_y + band_h
        return [[( w, y0), ( w, y1), (-w, y1), (-w, y0), ( w, y0)]]
    if style == "halter":
        # triangular cups that pinch toward the neck strap at the center top
        r_out_x = w * 0.9
        right = [
            (center_gap, apex_y - nd * 0.6),
            (0.03,       apex_y + 0.06),          # pinched up toward the neck
            (r_out_x,    apex_y - nd * 0.1),      # outer upper
            (r_out_x - 0.02, band_y + 0.02),
            (center_gap, band_y),
            (center_gap, apex_y - nd * 0.6),
        ]
        left = [(-x, y) for (x, y) in right]
        return [right, left]
    if style == "bralette":
        # fuller coverage with a softer curved neckline (still a single piece)
        full_h = h + 0.06
        top_y = band_y + full_h
        return [[
            ( w, top_y - nd * 0.2),
            ( w, band_y),
            (-w, band_y),
            (-w, top_y - nd * 0.2),
            (-center_gap, top_y - nd),
            ( center_gap, top_y - nd),
            ( w, top_y - nd * 0.2),
        ]]
    raise ValueError(f"unknown top style: {style}")


def _bottom_paths(g: Genome) -> list[list[tuple[float, float]]]:
    return [_bottom_path(g)]


def _bottom_path(g: Genome) -> list[tuple[float, float]]:
    rise = -0.15 + 0.55 * g.rise                  # waist line y, roughly [-0.15, 0.40]
    sw = 0.10 + 0.30 * g.side_width               # half-width at hip
    leg = 0.15 + 0.30 * g.leg_curve               # how high the leg cut is
    crotch_y = -0.75                              # fixed bottom
    crotch_half = 0.08
    style = g.bottom_style

    if style == "thong":
        # very narrow
        sw = min(sw, 0.18)
        return [
            ( sw, rise),
            ( crotch_half, crotch_y),
            (-crotch_half, crotch_y),
            (-sw, rise),
            ( sw, rise),
        ]
    if style == "cheeky":
        # moderate, slight leg curve
        mid_y = (rise + crotch_y) / 2 + leg * 0.15
        return [
            ( sw, rise),
            ( sw * 0.75, mid_y),
            ( crotch_half + 0.05, crotch_y),
            (-crotch_half - 0.05, crotch_y),
            (-sw * 0.75, mid_y),
            (-sw, rise),
            ( sw, rise),
        ]
    if style == "brief":
        mid_y = (rise + crotch_y) / 2 + leg * 0.05
        return [
            ( sw, rise),
            ( sw, mid_y),
            ( crotch_half + 0.10, crotch_y),
            (-crotch_half - 0.10, crotch_y),
            (-sw, mid_y),
            (-sw, rise),
            ( sw, rise),
        ]
    if style == "high_waist":
        rise = max(rise, 0.25)
        mid_y = (rise + crotch_y) / 2 + leg * 0.05
        return [
            ( sw, rise),
            ( sw, mid_y),
            ( crotch_half + 0.12, crotch_y),
            (-crotch_half - 0.12, crotch_y),
            (-sw, mid_y),
            (-sw, rise),
            ( sw, rise),
        ]
    raise ValueError(f"unknown bottom style: {style}")


def _draw_straps(ax, g: Genome, color):
    """Shoulder/neck straps for styles that have them."""
    style = g.top_style
    sw = max(0.008, 0.01 + 0.03 * g.strap_width)
    band_y = 0.35 + 0.20 * g.underband_y
    apex_y = band_y + 0.18 + 0.28 * g.cup_height
    w = 0.18 + 0.35 * g.cup_width
    if style == "triangle":
        for sign in (-1, 1):
            ax.plot([sign * w, sign * 0.38], [apex_y + 0.04, 1.20],
                    color=color, linewidth=sw * 120, solid_capstyle="round", zorder=3.2)
    elif style == "halter":
        ax.plot([0.03, 0], [apex_y + 0.06, 1.25],
                color=color, linewidth=sw * 140, solid_capstyle="round", zorder=3.2)
        ax.plot([-0.03, 0], [apex_y + 0.06, 1.25],
                color=color, linewidth=sw * 140, solid_capstyle="round", zorder=3.2)
    elif style == "bralette":
        full_top_y = band_y + (0.18 + 0.28 * g.cup_height) + 0.06
        for sign in (-1, 1):
            ax.plot([sign * 0.28, sign * 0.38], [full_top_y, 1.20],
                    color=color, linewidth=sw * 120, solid_capstyle="round", zorder=3.2)
    # bandeau: no straps


def render_one(ax, g: Genome, title: str):
    ax.set_xlim(-0.9, 0.9)
    ax.set_ylim(-1.1, 1.4)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("left", "right", "top", "bottom"):
        ax.spines[side].set_visible(False)

    _draw_torso(ax)
    color = _color(g)
    _draw_straps(ax, g, color)
    for poly in _top_paths(g):
        _apply_pattern(ax, poly, color, g.pattern, zorder=3)
    for poly in _bottom_paths(g):
        _apply_pattern(ax, poly, color, g.pattern, zorder=3)
    ax.set_title(title, fontsize=9)


# --------------------------------------------------------------------------
# Parents + pipeline
# --------------------------------------------------------------------------

def make_parents() -> tuple[Genome, Genome]:
    parent_a = Genome(
        top_style="triangle", bottom_style="thong", pattern="solid",
        cup_width=0.35, cup_height=0.55, neckline_depth=0.55,
        underband_y=0.35, strap_width=0.30,
        rise=0.20, side_width=0.20, leg_curve=0.70,
        hue=0.97, saturation=0.75,
    )
    parent_b = Genome(
        top_style="bandeau", bottom_style="high_waist", pattern="stripe",
        cup_width=0.85, cup_height=0.45, neckline_depth=0.10,
        underband_y=0.40, strap_width=0.0,
        rise=0.80, side_width=0.70, leg_curve=0.25,
        hue=0.57, saturation=0.85,
    )
    return parent_a.clipped(), parent_b.clipped()


def run_ga(parent_a: Genome, parent_b: Genome, n: int, rng: random.Random) -> list[Genome]:
    offspring = []
    for _ in range(n):
        child = crossover(parent_a, parent_b, rng)
        child = mutate(child, rng)
        offspring.append(child)
    return offspring


def save_figure(parents: tuple[Genome, Genome], offspring: list[Genome], out_path: str):
    n = len(offspring)
    cols = 5
    rows = (2 + n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.2, rows * 3.0), facecolor="white")
    axes = np.array(axes).reshape(-1)

    render_one(axes[0], parents[0], "Parent A")
    render_one(axes[1], parents[1], "Parent B")
    for i, child in enumerate(offspring):
        render_one(axes[2 + i], child, f"Child {i + 1}")
    for j in range(2 + n, len(axes)):
        axes[j].axis("off")

    fig.suptitle("Bikini GA — front-view 2D verification", fontsize=12, y=0.995)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def dump_genomes(parents, offspring, out_path: str):
    payload = {
        "seed": SEED,
        "blx_alpha": BLX_ALPHA,
        "mut_sigma": MUT_SIGMA,
        "mut_prob_cat": MUT_PROB_CAT,
        "parent_a": parents[0].as_dict(),
        "parent_b": parents[1].as_dict(),
        "offspring": [g.as_dict() for g in offspring],
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = random.Random(SEED)
    parents = make_parents()
    offspring = run_ga(parents[0], parents[1], N_OFFSPRING, rng)

    png_path = os.path.join(OUT_DIR, "ga_verification.png")
    json_path = os.path.join(OUT_DIR, "ga_verification.json")
    save_figure(parents, offspring, png_path)
    dump_genomes(parents, offspring, json_path)

    print(f"wrote {png_path}")
    print(f"wrote {json_path}")
    print("parents:")
    print("  A:", parents[0])
    print("  B:", parents[1])
    print(f"offspring ({len(offspring)}):")
    for i, g in enumerate(offspring):
        print(f"  {i + 1}: top={g.top_style:>9s}  bottom={g.bottom_style:>10s}  pattern={g.pattern:>7s}")


if __name__ == "__main__":
    main()
