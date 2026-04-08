"""Master randomizer: the creative heart of the system.

Randomly selects styles, parameters, and combinations to produce
unique and imaginative bikini designs.
"""

import numpy as np
from dataclasses import dataclass, field
from .assembly import GarmentAssembly, AttachmentConstraint
from .patch import GarmentPatch
from .top.cups import CUP_STYLES
from .top.connectors import CONNECTOR_STYLES
from .top.straps_top import STRAP_STYLES, BAND_STYLES
from .bottom.panels import FRONT_STYLES, BACK_STYLES
from .bottom.straps_bottom import BOTTOM_STRAP_STYLES
from .decorations import DECORATION_TYPES
from ..body.landmarks import get_landmarks


@dataclass
class DesignDescription:
    """Human-readable description of the generated design."""
    cup_style: str = ""
    connector_style: str = ""
    strap_style: str = ""
    band_style: str = ""
    front_style: str = ""
    back_style: str = ""
    bottom_strap_style: str = ""
    decorations: list[str] = field(default_factory=list)
    asymmetric: bool = False
    coverage_params: dict = field(default_factory=dict)
    color_hints: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        parts = [
            f"Top: {self.cup_style} cups",
            f"Connector: {self.connector_style}",
            f"Straps: {self.strap_style}",
        ]
        if self.band_style != "none":
            parts.append(f"Band: {self.band_style}")
        parts.extend([
            f"Bottom front: {self.front_style}",
            f"Bottom back: {self.back_style}",
            f"Bottom straps: {self.bottom_strap_style}",
        ])
        if self.asymmetric:
            parts.append("Asymmetric design")
        if self.decorations:
            parts.append(f"Decorations: {', '.join(self.decorations)}")
        return " | ".join(parts)


def _choose(options: dict, rng: np.random.Generator, weights: dict | None = None):
    """Weighted random choice from a style dictionary."""
    keys = list(options.keys())
    if weights:
        w = np.array([weights.get(k, 1.0) for k in keys])
        w = w / w.sum()
        return rng.choice(keys, p=w)
    return rng.choice(keys)


def generate_random_bikini(
    seed: int | None = None,
    ai_params: dict | None = None,
) -> tuple[GarmentAssembly, DesignDescription]:
    """Generate a random bikini assembly.

    Args:
        seed: random seed for reproducibility
        ai_params: optional dict from AI with style suggestions

    Returns:
        (assembly, description) tuple
    """
    rng = np.random.default_rng(seed)
    lm = get_landmarks()
    desc = DesignDescription()
    assembly = GarmentAssembly()

    # --- Use AI suggestions or randomize ---
    if ai_params:
        cup_style = ai_params.get("cup_style", _choose(CUP_STYLES, rng))
        connector_style = ai_params.get("connector_style", _choose(CONNECTOR_STYLES, rng))
        strap_style = ai_params.get("strap_style", _choose(STRAP_STYLES, rng))
        front_style = ai_params.get("front_style", _choose(FRONT_STYLES, rng))
        back_style = ai_params.get("back_style", _choose(BACK_STYLES, rng))
        bottom_strap_style = ai_params.get("bottom_strap_style", _choose(BOTTOM_STRAP_STYLES, rng))
    else:
        cup_style = _choose(CUP_STYLES, rng)
        connector_style = _choose(CONNECTOR_STYLES, rng)
        strap_style = _choose(STRAP_STYLES, rng)
        front_style = _choose(FRONT_STYLES, rng)
        back_style = _choose(BACK_STYLES, rng)
        bottom_strap_style = _choose(BOTTOM_STRAP_STYLES, rng)

    # Strapless + bandeau logic: bandeau needs back_band
    band_style = "none"
    if strap_style == "strapless" or cup_style == "bandeau":
        strap_style = "strapless"
        cup_style = "bandeau"
        band_style = "back_band"

    desc.cup_style = cup_style
    desc.connector_style = connector_style
    desc.strap_style = strap_style
    desc.band_style = band_style
    desc.front_style = front_style
    desc.back_style = back_style
    desc.bottom_strap_style = bottom_strap_style

    # --- Randomize parameters ---
    coverage_top = float(rng.uniform(0.4, 0.95))
    coverage_front = float(rng.uniform(0.4, 0.9))
    coverage_back = float(rng.uniform(0.3, 0.9))
    asymmetric = bool(rng.random() < 0.15)  # 15% chance

    desc.asymmetric = asymmetric
    desc.coverage_params = {
        "coverage_top": coverage_top,
        "coverage_front": coverage_front,
        "coverage_back": coverage_back,
    }

    # --- Generate top ---
    cup_func = CUP_STYLES[cup_style]

    if asymmetric:
        # Different coverage per side
        left_coverage = float(rng.uniform(0.35, 0.9))
        right_coverage = float(rng.uniform(0.35, 0.9))
        left_cup = cup_func(side="left", coverage=left_coverage)
        right_cup = cup_func(side="right", coverage=right_coverage)
    else:
        left_cup = cup_func(side="left", coverage=coverage_top)
        right_cup = cup_func(side="right", coverage=coverage_top)

    assembly.add_patch(left_cup)
    assembly.add_patch(right_cup)

    # Connector
    connector_func = CONNECTOR_STYLES[connector_style]
    connector = connector_func()
    if connector is not None:
        assembly.add_patch(connector)

    # Straps
    strap_func = STRAP_STYLES[strap_style]
    straps = strap_func()
    for s in straps:
        assembly.add_patch(s)

    # Band
    if band_style != "none":
        band_func = BAND_STYLES[band_style]
        bands = band_func()
        for b in bands:
            assembly.add_patch(b)

    # --- Generate bottom ---
    front_func = FRONT_STYLES[front_style]
    front_patch = front_func(coverage=coverage_front)
    assembly.add_patch(front_patch)

    back_func = BACK_STYLES[back_style]
    if back_style == "thong":
        back_patch = back_func()
    else:
        back_patch = back_func(coverage=coverage_back)
    assembly.add_patch(back_patch)

    # Bottom straps
    bottom_strap_func = BOTTOM_STRAP_STYLES[bottom_strap_style]
    bottom_straps = bottom_strap_func()
    for s in bottom_straps:
        assembly.add_patch(s)

    # --- Decorations (random chance) ---
    n_decorations = rng.integers(0, 4)
    if n_decorations > 0:
        deco_types = list(DECORATION_TYPES.keys())
        possible_points = [
            lm["sternum_center"],
            lm["left_breast_apex"] + np.array([0, -0.02, 0.01]),
            lm["right_breast_apex"] + np.array([0, -0.02, 0.01]),
            lm["hip_left"] + np.array([0, 0, 0.03]),
            lm["hip_right"] + np.array([0, 0, 0.03]),
        ]

        for _ in range(n_decorations):
            deco_type = rng.choice(deco_types)
            point = possible_points[rng.integers(0, len(possible_points))]
            desc.decorations.append(deco_type)

            if deco_type == "chain":
                deco = DECORATION_TYPES[deco_type](point, length=float(rng.uniform(0.02, 0.06)))
            elif deco_type == "bow":
                deco = DECORATION_TYPES[deco_type](point, size=float(rng.uniform(0.01, 0.03)))
            elif deco_type == "tassel":
                deco = DECORATION_TYPES[deco_type](point, length=float(rng.uniform(0.02, 0.05)))
            elif deco_type == "ring":
                deco = DECORATION_TYPES[deco_type](point, radius=float(rng.uniform(0.008, 0.02)))
            else:
                continue
            assembly.add_patch(deco)

    # --- Store design metadata ---
    assembly.metadata = {
        "description": desc.to_text(),
        "seed": seed,
        "styles": {
            "cup": cup_style,
            "connector": connector_style,
            "strap": strap_style,
            "band": band_style,
            "front": front_style,
            "back": back_style,
            "bottom_strap": bottom_strap_style,
        },
    }

    return assembly, desc
