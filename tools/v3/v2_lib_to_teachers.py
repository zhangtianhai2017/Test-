"""
v2 library → v3 teacher converter.

Generate v3.1 Panel+Stroke teacher designs by calling v2's polygon
recipes on different cup/bottom variants and combining with straps.

Why: Phase A2 only has 12 hand-crafted teachers (48 brief pairs).
The v2 library is 86 entries embodying years of real swimwear
parametrization. Tapping it gives the NN ~10x more polygon shape
vocabulary without manual hand-crafting.

Strategy:
  - Each teacher = (cup_recipe, bottom_recipe, strap_pattern, palette)
  - cup_recipe ∈ {triangle, balconette, bandeau, sweetheart, wrap, corset_bands}
    × {S, M, L size variants} via local_params perturbation
  - bottom_recipe ∈ {thong, brief} × {S, M, L coverage}
  - strap_pattern ∈ {halter, shoulder, racerback, cross_back, x_chest,
    none-bandeau, side_tie} mapped to v3 stroke anchors
  - palette = randomized over named palette
  - brief paraphrases auto-generated from recipe names

Output: dict[name → list[Token]] augmenting all_reference_designs_v31.
"""
from __future__ import annotations

import os
import sys
import random

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from polygon_recipes import call_recipe
from v3.stroke_schema import Panel, Stroke, Anchor


# ─── UV space conversion ──────────────────────────────────────────────

def v2_to_v3_uv(poly_v2: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """v2 Genome UV [-1,1]×[0,1] → v3 UV [0,1]×[0,1].
    Drop closing duplicate. Clamp to [0,1]."""
    if poly_v2 and poly_v2[0] == poly_v2[-1]:
        poly_v2 = poly_v2[:-1]
    out = []
    for u, v in poly_v2:
        u_v3 = max(0.0, min(1.0, (u + 1.0) * 0.5))
        v_v3 = max(0.0, min(1.0, v))
        out.append((u_v3, v_v3))
    return out


def resample_to_n(poly: list[tuple[float, float]], n: int = 6
                   ) -> list[tuple[float, float]]:
    """Uniform-arclength resample to exactly n vertices."""
    import math
    # closed perimeter
    pts = poly + [poly[0]]
    edges = [(pts[i], pts[i+1]) for i in range(len(pts) - 1)]
    lens = [math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in edges]
    total = sum(lens)
    if total < 1e-6:
        return [poly[0]] * n
    target_step = total / n
    out = []
    acc = 0.0
    edge_i = 0
    for k in range(n):
        target = k * target_step
        while edge_i < len(edges) - 1 and acc + lens[edge_i] < target:
            acc += lens[edge_i]
            edge_i += 1
        # interpolate
        a, b = edges[edge_i]
        seg_t = (target - acc) / max(lens[edge_i], 1e-6)
        u = a[0] + seg_t * (b[0] - a[0])
        v = a[1] + seg_t * (b[1] - a[1])
        out.append((u, v))
    return out


# ─── color & material random pickers ─────────────────────────────────

PALETTE_POOL = [
    0,  # ivory
    1,  # black
    3,  # silver
    4,  # navy
    5,  # hot pink
    6,  # orange
    7,  # emerald
    8,  # burgundy
    9,  # neon yellow
    11, # dusty rose
    12, # sage
    13, # mauve
    14, # coral
    15, # mint
    20, # cyber teal
    21, # neon magenta
    22, # violet
    25, # gold
    27, # jade
    30, # pearl
]

FABRIC_POOL = [
    "F_ECONYL_PLAIN_LIGHT",
    "F_QNOVA_RIBBED",
    "F_VIRGIN_VELVET",
    "F_HUNZA_CRINKLE",
    "F_MISSONI_SHINY_KNIT",
    "F_CROCHET_COTTON",
    "F_AMNI_SOUL_RIBBED",
]


def random_color(rng: random.Random) -> int:
    return rng.choice(PALETTE_POOL)


def random_fabric(rng: random.Random) -> str:
    return rng.choice(FABRIC_POOL)


# ─── strap pattern → Stroke list ──────────────────────────────────────

def strap_strokes(pattern: str, color_id: int, rng: random.Random
                   ) -> list[Stroke]:
    """Generate stroke(s) for a strap pattern."""
    w = (1.5, 1.0, 1.5)  # default thin strap
    if pattern == "halter":
        return [Stroke(start_anchor=Anchor.SHOULDER_L,
                        end_anchor=Anchor.NECK_BACK,
                        width_profile=w, color_id=color_id),
                 Stroke(start_anchor=Anchor.SHOULDER_R,
                        end_anchor=Anchor.NECK_BACK,
                        width_profile=w, color_id=color_id)]
    if pattern == "shoulder":
        return [Stroke(start_anchor=Anchor.SHOULDER_L,
                        end_anchor=Anchor.UNDERBUST,
                        width_profile=w, color_id=color_id),
                 Stroke(start_anchor=Anchor.SHOULDER_R,
                        end_anchor=Anchor.UNDERBUST,
                        width_profile=w, color_id=color_id)]
    if pattern == "racerback":
        return [Stroke(start_anchor=Anchor.SHOULDER_L,
                        end_anchor=Anchor.NECK_BACK,
                        width_profile=(2.5, 2.0, 2.5), color_id=color_id),
                 Stroke(start_anchor=Anchor.SHOULDER_R,
                        end_anchor=Anchor.NECK_BACK,
                        width_profile=(2.5, 2.0, 2.5), color_id=color_id)]
    if pattern == "cross_back":
        return [Stroke(start_anchor=Anchor.SHOULDER_L,
                        end_anchor=Anchor.WAIST_R,
                        width_profile=w, color_id=color_id),
                 Stroke(start_anchor=Anchor.SHOULDER_R,
                        end_anchor=Anchor.WAIST_L,
                        width_profile=w, color_id=color_id)]
    if pattern == "x_chest":
        return [Stroke(start_anchor=Anchor.SHOULDER_L,
                        end_anchor=Anchor.STERNUM,
                        width_profile=w, color_id=color_id),
                 Stroke(start_anchor=Anchor.SHOULDER_R,
                        end_anchor=Anchor.STERNUM,
                        width_profile=w, color_id=color_id)]
    if pattern == "side_tie":
        return [Stroke(start_anchor=Anchor.WAIST_L, end_anchor=Anchor.HIP_L,
                        width_profile=(0.8, 0.6, 0.8), color_id=color_id),
                 Stroke(start_anchor=Anchor.WAIST_R, end_anchor=Anchor.HIP_R,
                        width_profile=(0.8, 0.6, 0.8), color_id=color_id)]
    if pattern == "bandeau":
        return [Stroke(start_anchor=Anchor.WAIST_L, end_anchor=Anchor.WAIST_R,
                        width_profile=(3.0, 3.0, 3.0), color_id=color_id)]
    # "none" → empty
    return []


# ─── recipe combinations ─────────────────────────────────────────────

CUP_RECIPES = ["cup_triangle", "cup_balconette", "cup_bandeau",
                "cup_sweetheart", "cup_wrap", "cup_corset_bands"]
BOTTOM_RECIPES = ["bottom_thong", "bottom_brief"]
STRAP_PATTERNS = ["halter", "shoulder", "racerback",
                   "cross_back", "x_chest", "side_tie", "bandeau", "none"]

# Per-recipe parameter sample sets (3 size variants each)
CUP_PARAM_SETS = {
    "cup_triangle":   [{}, {"half_u": 0.20, "half_v": 0.09},
                         {"half_u": 0.13, "half_v": 0.05}],
    "cup_balconette": [{}, {"half_u": 0.24, "half_v": 0.10},
                         {"half_u": 0.17, "half_v": 0.07}],
    "cup_bandeau":    [{}, {"half_u": 0.28, "half_v": 0.12},
                         {"half_u": 0.18, "half_v": 0.09}],
    "cup_sweetheart": [{}, {"half_u": 0.22, "apex_lift": 0.25},
                         {"half_u": 0.18, "apex_lift": 0.15}],
    "cup_wrap":       [{}, {"half_u": 0.30}, {"half_u": 0.20}],
    "cup_corset_bands": [{}, {"half_u": 0.26}, {"half_u": 0.20}],
}
BOTTOM_PARAM_SETS = {
    "bottom_thong":   [{}, {"hip_half_u": 0.30}, {"hip_half_u": 0.40}],
    "bottom_brief":   [{}, {"hip_half_u": 0.35}, {"hip_half_u": 0.45}],
}


def make_panel_from_recipe(recipe_name: str, params: dict,
                            color_id: int, fabric_id: str,
                            is_cup: bool) -> Panel | None:
    """Call recipe, convert UV, build Panel. None if recipe fails."""
    try:
        poly_v2 = call_recipe(recipe_name, params)
    except Exception:
        return None
    if not poly_v2 or len(poly_v2) < 3:
        return None
    poly_v3 = v2_to_v3_uv(poly_v2)
    poly_v3 = resample_to_n(poly_v3, n=6)
    anchors = ([Anchor.SHOULDER_L, Anchor.STERNUM, Anchor.UNDERBUST]
               if is_cup else [Anchor.HIP_L, Anchor.HIP_R])
    return Panel(
        boundary_uv=poly_v3, anchors=anchors,
        color_id=color_id, fabric_id=fabric_id,
    )


# ─── main: build N teachers ───────────────────────────────────────────

def make_v2_lib_teachers(n: int = 40, seed: int = 7
                          ) -> dict[str, list]:
    """Generate N teacher designs from v2 library combinations."""
    rng = random.Random(seed)
    out = {}
    attempts = 0
    while len(out) < n and attempts < n * 4:
        attempts += 1
        cup_r = rng.choice(CUP_RECIPES)
        bot_r = rng.choice(BOTTOM_RECIPES)
        strap = rng.choice(STRAP_PATTERNS)
        cup_p = rng.choice(CUP_PARAM_SETS[cup_r])
        bot_p = rng.choice(BOTTOM_PARAM_SETS[bot_r])
        color = random_color(rng)
        fabric = random_fabric(rng)

        cup_panel = make_panel_from_recipe(cup_r, cup_p,
                                             color, fabric, is_cup=True)
        bot_panel = make_panel_from_recipe(bot_r, bot_p,
                                             color, fabric, is_cup=False)
        if cup_panel is None or bot_panel is None:
            continue

        straps = strap_strokes(strap, color, rng)
        tokens = [cup_panel, bot_panel] + straps
        # mark last is_end
        tokens[-1].is_end = True

        name = f"v2lib_{cup_r}_{bot_r}_{strap}_{rng.randint(0, 999)}"
        if name not in out:
            out[name] = tokens

    return out


def make_teacher_brief(name: str, palette_color_id: int) -> list[str]:
    """Generate 3 brief paraphrases for a v2-lib teacher.
    Briefs are auto-built from the design's color + recipe semantics."""
    from v3.palette import get
    color_name = get(palette_color_id).name_en
    color_cn = get(palette_color_id).name_cn

    # name = "v2lib_cup_{kind}_bottom_{kind}_{strap}_{seed}"
    parts = name.split("_")
    cup_kind = parts[2] if len(parts) > 2 else "cup"
    strap = parts[5] if len(parts) > 5 else "none"

    cup_desc = {
        "triangle": "triangle string", "balconette": "balconette molded",
        "bandeau": "strapless bandeau", "sweetheart": "sweetheart neckline",
        "wrap": "wrap front", "corset": "corset-band structured",
    }.get(cup_kind, "bikini")

    strap_desc = {
        "halter": "halter neck", "shoulder": "shoulder strap",
        "racerback": "racerback", "cross_back": "cross-back straps",
        "x_chest": "X-chest straps", "side_tie": "side-tie hip",
        "bandeau": "back-band", "none": "minimal",
    }.get(strap, "")

    base = f"{color_name} {cup_desc} bikini with {strap_desc}"
    return [
        base,
        f"{cup_desc} swimwear, {color_name} color, {strap_desc}",
        f"{color_cn}色{cup_desc.split()[0]}比基尼, {strap_desc}",
    ]


# ─── smoke ────────────────────────────────────────────────────────────

def _smoke():
    print("─── v2_lib_to_teachers smoke ───")
    teachers = make_v2_lib_teachers(n=40)
    print(f"\ngenerated {len(teachers)} teachers")
    # show a few examples
    for i, (name, tokens) in enumerate(list(teachers.items())[:6]):
        n_p = sum(1 for t in tokens if isinstance(t, Panel))
        n_s = sum(1 for t in tokens if isinstance(t, Stroke))
        print(f"  {i}: {name}  ({n_p}P/{n_s}S)")
        briefs = make_teacher_brief(name, tokens[0].color_id)
        print(f"      briefs: {briefs[0]}")
    # verify all teachers convert cleanly via tokens_to_garment
    from v3.tokens_to_garment import tokens_to_garment
    from garment_state import validate_garment
    n_clean = 0
    n_warns_total = 0
    for name, tokens in teachers.items():
        g = tokens_to_garment(tokens)
        g2 = validate_garment(g)
        warns = g2.metadata.get("validation_warnings", [])
        n_warns_total += len(warns)
        if not warns:
            n_clean += 1
    print(f"\nvalidate_garment: {n_clean}/{len(teachers)} clean, "
          f"avg warnings = {n_warns_total/len(teachers):.2f}")


if __name__ == "__main__":
    _smoke()
