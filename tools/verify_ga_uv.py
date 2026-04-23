"""
UV-unwrap bikini GA verifier.

Represents the torso as a flat UV rectangle (like a world-map projection):
    u in [-1, 1]   angular position:  -1 = back seam, 0 = front center, +1 = back seam (wraps)
    v in [ 0, 1]   vertical:          0 = groin, 1 = neck

A bikini is a set of 2D polygons in this plane. The GA operates directly
on the polygon-control-point parameters, so shapes like triangle / bandeau /
halter / bralette emerge from a single continuous space instead of being
discrete archetypes.

Run: `python3 tools/verify_ga_uv.py`.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, asdict

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
from matplotlib.colors import hsv_to_rgb

SEED = 42
N_OFFSPRING = 8
BLX_ALPHA = 0.3
MUT_SIGMA = 0.08
MUT_PROB_CAT = 0.08
OUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Body landmarks in UV space (fixed, used for rendering guides)
LANDMARKS_V = {
    "neck":      0.96,
    "bust":      0.78,
    "underbust": 0.70,
    "waist":     0.48,
    "hip":       0.22,
    "crotch":    0.06,
}
PATTERNS = ["solid", "stripe", "polka", "checker"]

# Privacy seeds: minimum-coverage rectangles in UV space. Every Genome's
# polygons must CONTAIN these — `_enforce_constraints` clamps the Genome
# parameters so the trapezoidal cups and front panel grow to at least
# this size. They are not overlays painted on top; they're a lower bound
# baked into the parameter ranges, so the bikini smoothly grows from them.
#   (u_lo, u_hi, v_lo, v_hi)
PRIVACY_SEEDS = {
    "right_nipple": (0.10, 0.18, 0.74, 0.82),
    "left_nipple":  (-0.18, -0.10, 0.74, 0.82),
    "pelvic_front": (-0.08, 0.08, 0.06, 0.14),
}

# Continuous Genome fields. Kept flat so GA operators are uniform.
CONT_FIELDS = [
    # TOP
    "top_center_v",        # vertical position of cup centroid (bust area ~0.75)
    "top_half_v",          # vertical half-size of each cup
    "top_half_u",          # horizontal half-size of each cup (in u units)
    "top_inner_u",         # inner edge distance from u=0 (0 -> bandeau, big -> split V)
    "top_apex_lift",       # concave top edge: +ve = V at center (triangle), -ve = bandeau flat
    "top_underband_dip",   # concave bottom edge: +ve pushes bottom inward under bust
    "top_back_coverage",   # 0 = back strap only, 1 = full back panel
    # BOTTOM
    "bot_front_top_v",     # waistline height at front
    "bot_front_half_u",    # half-width of front panel around u=0
    "bot_front_leg_curve", # concavity of front leg opening
    "bot_back_top_v",      # waistline height at back
    "bot_back_half_u",     # half-width of back panel around u=±1 (small -> thong)
    # COLOR
    "hue",
    "saturation",
]


@dataclass
class Genome:
    pattern: str
    top_center_v: float
    top_half_v: float
    top_half_u: float
    top_inner_u: float
    top_apex_lift: float
    top_underband_dip: float
    top_back_coverage: float
    bot_front_top_v: float
    bot_front_half_u: float
    bot_front_leg_curve: float
    bot_back_top_v: float
    bot_back_half_u: float
    hue: float
    saturation: float

    def as_dict(self) -> dict:
        return asdict(self)

    def clipped(self) -> "Genome":
        d = self.as_dict()
        for k in CONT_FIELDS:
            if k == "hue":
                d[k] = d[k] % 1.0
            else:
                d[k] = float(np.clip(d[k], 0.0, 1.0))
        return Genome(**d)


# --------------------------------------------------------------------------
# GA operators — same flavour as the front-view version but much simpler
# because every geometric field is now just a scalar.
# --------------------------------------------------------------------------

def _blx(a: float, b: float, rng: random.Random) -> float:
    lo, hi = (a, b) if a <= b else (b, a)
    d = hi - lo
    return rng.uniform(lo - BLX_ALPHA * d, hi + BLX_ALPHA * d)


def _blx_circular(a: float, b: float, rng: random.Random) -> float:
    diff = (b - a) % 1.0
    b_adj = b - 1.0 if diff > 0.5 else b
    return _blx(a, b_adj, rng) % 1.0


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    d = {"pattern": rng.choice([a.pattern, b.pattern])}
    for k in CONT_FIELDS:
        va, vb = getattr(a, k), getattr(b, k)
        d[k] = _blx_circular(va, vb, rng) if k == "hue" else _blx(va, vb, rng)
    return Genome(**d).clipped()


def mutate(g: Genome, rng: random.Random) -> Genome:
    d = g.as_dict()
    if rng.random() < MUT_PROB_CAT:
        d["pattern"] = rng.choice(PATTERNS)
    for k in CONT_FIELDS:
        noise = rng.gauss(0, MUT_SIGMA)
        if k == "hue":
            d[k] = (d[k] + noise) % 1.0
        else:
            d[k] = d[k] + noise
    return _enforce_constraints(Genome(**d).clipped())


def _enforce_constraints(g: Genome) -> Genome:
    """Hard rules: keep polygons non-degenerate AND guarantee they contain
    the PRIVACY_SEEDS. Each clamp below is derived analytically from the
    polygon shape — never paints over the result, just constrains parameters
    so the trapezoidal cups / front panel grow at least to the seed extent.
    """
    d = g.as_dict()

    # --- privacy seeds for the cup (right nipple drives both due to symmetry)
    s_u_lo, s_u_hi, s_v_lo, s_v_hi = PRIVACY_SEEDS["right_nipple"]

    # cup must straddle the seed vertically: cv+hv >= s_v_hi, cv-hv <= s_v_lo
    # so cv ∈ [s_v_hi - hv_min, s_v_lo + hv_min] and hv >= max(s_v_hi-cv, cv-s_v_lo)
    # we anchor cv into a band centered on the seed midline first, then enlarge hv.
    seed_mid_v = (s_v_lo + s_v_hi) / 2
    seed_half_v = (s_v_hi - s_v_lo) / 2
    d["top_center_v"] = float(np.clip(d["top_center_v"],
                                       seed_mid_v - 0.04,
                                       seed_mid_v + 0.04))
    needed_hv = max(seed_half_v + 0.01,
                    abs(d["top_center_v"] - s_v_hi),
                    abs(d["top_center_v"] - s_v_lo))
    d["top_half_v"] = max(d["top_half_v"], needed_hv)

    # cup must cover the seed in u: inner edge <= s_u_lo, outer edge >= s_u_hi
    d["top_inner_u"] = min(d["top_inner_u"], s_u_lo - 0.005)
    d["top_inner_u"] = max(d["top_inner_u"], 0.0)
    needed_hu = max(0.05, (s_u_hi - d["top_inner_u"] + 0.01) / 2.0)
    d["top_half_u"] = max(d["top_half_u"], needed_hu)

    # apex_lift drops the inner-top edge by apex*0.6 — cap so it stays
    # above the seed top: cv + hv - apex*0.6 >= s_v_hi
    apex_max = (d["top_center_v"] + d["top_half_v"] - s_v_hi) / 0.6
    d["top_apex_lift"] = min(d["top_apex_lift"], max(0.0, apex_max))

    # underband_dip raises the inner-bottom edge by dip*0.3 — cap so it stays
    # below the seed bottom: cv - hv + dip*0.3 <= s_v_lo
    dip_max = (s_v_lo - d["top_center_v"] + d["top_half_v"]) / 0.3
    d["top_underband_dip"] = min(d["top_underband_dip"], max(0.0, dip_max))

    # --- privacy seed for the front panel (pelvic_front)
    p_u_lo, p_u_hi, p_v_lo, p_v_hi = PRIVACY_SEEDS["pelvic_front"]
    # panel top must be at or above the seed top
    d["bot_front_top_v"] = max(d["bot_front_top_v"], p_v_hi + 0.04)
    # at the polygon's narrowest point (midline) width = hu*(1 - leg/2);
    # require this to cover the seed half-width comfortably
    needed_front_hu = max((p_u_hi + 0.01) / max(1e-3, 1 - 0.5 * d["bot_front_leg_curve"]),
                          p_u_hi + 0.01)
    d["bot_front_half_u"] = max(d["bot_front_half_u"], needed_front_hu)
    # if leg curve is too aggressive given hu, reduce it
    max_leg = 2 * (1 - (p_u_hi + 0.01) / d["bot_front_half_u"])
    d["bot_front_leg_curve"] = min(d["bot_front_leg_curve"], max(0.0, max_leg))

    # --- minimum back coverage so back panels never collapse to nothing
    d["bot_back_half_u"] = max(d["bot_back_half_u"], 0.04)

    # --- non-degeneracy guards (kept from before)
    d["top_half_v"] = max(d["top_half_v"], 0.05)
    d["top_half_u"] = max(d["top_half_u"], 0.05)
    d["bot_front_half_u"] = max(d["bot_front_half_u"], 0.05)

    # front panel top must sit below the cup bottom
    cup_bottom_v = d["top_center_v"] - d["top_half_v"]
    if d["bot_front_top_v"] > cup_bottom_v - 0.02:
        d["bot_front_top_v"] = max(p_v_hi + 0.04, cup_bottom_v - 0.05)

    return Genome(**d)


# --------------------------------------------------------------------------
# Genome -> polygons in UV space
# --------------------------------------------------------------------------

def _cup_polygon(g: Genome, side: int) -> list[tuple[float, float]]:
    """One cup as a 4-point polygon with a concave top (V) and slight concave bottom.

    side: +1 = right (u > 0), -1 = left (u < 0).
    When top_inner_u is 0 the two cups touch in the middle -> effective bandeau.
    """
    cv = g.top_center_v
    hv = g.top_half_v
    hu = g.top_half_u
    inner_u = g.top_inner_u
    apex = g.top_apex_lift * 0.6
    dip = g.top_underband_dip * 0.3

    inner = side * inner_u
    outer = side * (inner_u + 2 * hu)

    top_v_outer = cv + hv
    top_v_inner = cv + hv - apex        # V apex if apex>0
    bot_v_outer = cv - hv
    bot_v_inner = cv - hv + dip

    # traverse: inner-top -> outer-top -> outer-bottom -> inner-bottom
    return [
        (inner, top_v_inner),
        (outer, top_v_outer),
        (outer, bot_v_outer),
        (inner, bot_v_inner),
        (inner, top_v_inner),
    ]


def _back_top_polygons(g: Genome) -> list[list[tuple[float, float]]]:
    """Optional back band. Two separate strips (one on each seam), not a single
    polygon with a zero-area bridge — that would draw a hairline across."""
    if g.top_back_coverage < 0.05:
        return []
    cv = g.top_center_v
    band_h = 0.04 + 0.30 * g.top_back_coverage
    reach = 0.10 + 0.45 * g.top_back_coverage
    v0 = cv - band_h / 2
    v1 = cv + band_h / 2
    left = [(-1.0, v0), (-1.0 + reach, v0), (-1.0 + reach, v1), (-1.0, v1), (-1.0, v0)]
    right = [(1.0 - reach, v0), (1.0, v0), (1.0, v1), (1.0 - reach, v1), (1.0 - reach, v0)]
    return [left, right]


def _bottom_front_polygon(g: Genome) -> list[tuple[float, float]]:
    """Front panel of the bottom, centered on u=0."""
    top_v = g.bot_front_top_v
    hu = g.bot_front_half_u
    crotch_v = LANDMARKS_V["crotch"]
    leg = g.bot_front_leg_curve * 0.5
    return [
        (-hu, top_v),
        ( hu, top_v),
        ( hu * (1 - 0.5 * leg), (top_v + crotch_v) / 2),
        ( max(0.05, hu * 0.25), crotch_v),
        (-max(0.05, hu * 0.25), crotch_v),
        (-hu * (1 - 0.5 * leg), (top_v + crotch_v) / 2),
        (-hu, top_v),
    ]


def _bottom_back_polygons(g: Genome) -> list[list[tuple[float, float]]]:
    """Back panel as two strips on either side of the seam."""
    top_v = g.bot_back_top_v
    hu = g.bot_back_half_u
    crotch_v = LANDMARKS_V["crotch"]
    left = [
        (-1.0, top_v), (-1.0 + hu, top_v),
        (-1.0 + hu * 0.6, crotch_v), (-1.0, crotch_v), (-1.0, top_v),
    ]
    right = [
        (1.0 - hu, top_v), (1.0, top_v),
        (1.0, crotch_v), (1.0 - hu * 0.6, crotch_v), (1.0 - hu, top_v),
    ]
    return [left, right]


def _side_tie_polygons(g: Genome) -> list[list[tuple[float, float]]]:
    """Thin side connectors between front and back bottom panels at u = ±0.5."""
    top_v = min(g.bot_front_top_v, g.bot_back_top_v)
    strap_h = 0.015 + 0.05 * g.top_back_coverage
    v_center = top_v - 0.02
    v0, v1 = v_center - strap_h / 2, v_center + strap_h / 2
    w = 0.06
    return [
        [(-0.5 - w, v0), (-0.5 + w, v0), (-0.5 + w, v1), (-0.5 - w, v1), (-0.5 - w, v0)],
        [( 0.5 - w, v0), ( 0.5 + w, v0), ( 0.5 + w, v1), ( 0.5 - w, v1), ( 0.5 - w, v0)],
    ]


def genome_polygons(g: Genome) -> list[list[tuple[float, float]]]:
    polys: list[list[tuple[float, float]]] = []
    polys.append(_cup_polygon(g,  1))
    polys.append(_cup_polygon(g, -1))
    polys.extend(_back_top_polygons(g))
    polys.append(_bottom_front_polygon(g))
    polys.extend(_bottom_back_polygons(g))
    polys.extend(_side_tie_polygons(g))
    return polys


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _color(g: Genome) -> tuple[float, float, float]:
    s = 0.3 + 0.6 * g.saturation
    return tuple(hsv_to_rgb([g.hue, s, 0.90]).tolist())


def _draw_uv_canvas(ax):
    """Paint skin tone + body landmark guide lines on a UV rectangle."""
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect("auto")
    # skin background
    ax.add_patch(Rectangle((-1, 0), 2, 1, facecolor="#f3d9c0", edgecolor="#9c7a5c",
                           linewidth=1.0, zorder=1))
    # horizontal landmark lines
    for name, v in LANDMARKS_V.items():
        ax.axhline(v, color="#b38c6e", linewidth=0.5, linestyle=":", zorder=1.5, alpha=0.7)
        ax.text(-1.04, v, name, fontsize=6, color="#8a6a50", va="center", ha="right")
    # vertical landmarks: back seam (u=±1), sides (u=±0.5), front center (u=0)
    for u, name in [(-1.0, "back"), (-0.5, "side"), (0.0, "front"), (0.5, "side"), (1.0, "back")]:
        ax.axvline(u, color="#b38c6e", linewidth=0.5, linestyle=":", zorder=1.5, alpha=0.6)
        ax.text(u, 1.04, name, fontsize=6, color="#8a6a50", ha="center")
    # privacy seeds: dashed outlines that all genome polygons must enclose
    for name, (u0, u1, v0, v1) in PRIVACY_SEEDS.items():
        ax.add_patch(Rectangle((u0, v0), u1 - u0, v1 - v0,
                               fill=False, edgecolor="#c0392b", linewidth=0.7,
                               linestyle="--", zorder=2.0))
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("left", "right", "top", "bottom"):
        ax.spines[side].set_visible(False)


def _fill_polygon(ax, verts, color, pattern, zorder=3):
    if len(verts) < 3:
        return
    patch = Polygon(verts, closed=True, facecolor=color, edgecolor="#222",
                    linewidth=0.6, zorder=zorder)
    ax.add_patch(patch)
    if pattern == "solid":
        return
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    overlay = (1.0, 1.0, 1.0, 0.55)
    if pattern == "stripe":
        n = 7
        for i in range(n):
            y = y0 + (i + 0.5) * (y1 - y0) / n
            h = (y1 - y0) / (n * 2.4)
            r = Rectangle((x0, y - h / 2), x1 - x0, h, facecolor=overlay,
                          edgecolor=None, zorder=zorder + 0.1)
            r.set_clip_path(patch)
            ax.add_patch(r)
    elif pattern == "polka":
        rng = np.random.default_rng(0)
        for _ in range(20):
            cx = rng.uniform(x0, x1)
            cy = rng.uniform(y0, y1)
            dot = plt.Circle((cx, cy), 0.012, facecolor=overlay, zorder=zorder + 0.1)
            dot.set_clip_path(patch)
            ax.add_patch(dot)
    elif pattern == "checker":
        n = 8
        dx = (x1 - x0) / n
        dy = (y1 - y0) / n
        for i in range(n):
            for j in range(n):
                if (i + j) % 2 == 0:
                    r = Rectangle((x0 + i * dx, y0 + j * dy), dx, dy,
                                  facecolor=overlay, edgecolor=None, zorder=zorder + 0.1)
                    r.set_clip_path(patch)
                    ax.add_patch(r)


def render_one(ax, g: Genome, title: str):
    _draw_uv_canvas(ax)
    color = _color(g)
    for poly in genome_polygons(g):
        _fill_polygon(ax, poly, color, g.pattern, zorder=3)
    ax.set_title(title, fontsize=9)


# --------------------------------------------------------------------------
# Parents + pipeline
# --------------------------------------------------------------------------

def make_parents() -> tuple[Genome, Genome]:
    # Parent A: triangle-ish top + thong + solid red
    a = Genome(
        pattern="solid",
        top_center_v=0.76, top_half_v=0.09, top_half_u=0.18,
        top_inner_u=0.12, top_apex_lift=0.10, top_underband_dip=0.08,
        top_back_coverage=0.12,
        bot_front_top_v=0.22, bot_front_half_u=0.25, bot_front_leg_curve=0.60,
        bot_back_top_v=0.20, bot_back_half_u=0.12,
        hue=0.97, saturation=0.75,
    )
    # Parent B: bandeau top + high-waist + striped blue
    b = Genome(
        pattern="stripe",
        top_center_v=0.74, top_half_v=0.08, top_half_u=0.45,
        top_inner_u=0.0,  top_apex_lift=-0.03, top_underband_dip=0.02,
        top_back_coverage=0.55,
        bot_front_top_v=0.42, bot_front_half_u=0.55, bot_front_leg_curve=0.20,
        bot_back_top_v=0.42, bot_back_half_u=0.55,
        hue=0.57, saturation=0.85,
    )
    return a.clipped(), b.clipped()


def run_ga(a: Genome, b: Genome, n: int, rng: random.Random) -> list[Genome]:
    return [mutate(crossover(a, b, rng), rng) for _ in range(n)]


def save_figure(parents, offspring, out_path: str):
    n = len(offspring)
    cols = 5
    rows = (2 + n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.8, rows * 2.2), facecolor="white")
    axes = np.array(axes).reshape(-1)
    render_one(axes[0], parents[0], "Parent A")
    render_one(axes[1], parents[1], "Parent B")
    for i, child in enumerate(offspring):
        render_one(axes[2 + i], child, f"Child {i + 1}")
    for j in range(2 + n, len(axes)):
        axes[j].axis("off")
    fig.suptitle("Bikini GA on UV-unwrapped torso (u: back-front-back, v: hip-neck)",
                 fontsize=11, y=0.995)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def dump_genomes(parents, offspring, out_path):
    payload = {
        "seed": SEED,
        "representation": "uv_unwrap",
        "u_range": [-1.0, 1.0],
        "v_range": [0.0, 1.0],
        "landmarks_v": LANDMARKS_V,
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
    png = os.path.join(OUT_DIR, "ga_verification_uv.png")
    js  = os.path.join(OUT_DIR, "ga_verification_uv.json")
    save_figure(parents, offspring, png)
    dump_genomes(parents, offspring, js)
    print(f"wrote {png}")
    print(f"wrote {js}")


if __name__ == "__main__":
    main()
