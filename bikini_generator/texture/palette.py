"""Color palette generation and randomization."""

import numpy as np
from dataclasses import dataclass


@dataclass
class ColorPalette:
    """A set of colors for the bikini."""
    primary: tuple[int, int, int]      # RGB
    secondary: tuple[int, int, int]
    accent: tuple[int, int, int]
    name: str = ""


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    """Convert HSV (0-360, 0-1, 0-1) to RGB (0-255)."""
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c

    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


def random_palette(seed: int | None = None) -> ColorPalette:
    """Generate a random harmonious color palette."""
    rng = np.random.default_rng(seed)
    scheme = rng.choice([
        "complementary", "analogous", "triadic", "monochrome",
        "neon", "pastel", "earth", "metallic",
    ])

    base_hue = float(rng.uniform(0, 360))
    base_sat = float(rng.uniform(0.5, 1.0))
    base_val = float(rng.uniform(0.6, 1.0))

    if scheme == "complementary":
        primary = _hsv_to_rgb(base_hue, base_sat, base_val)
        secondary = _hsv_to_rgb((base_hue + 180) % 360, base_sat * 0.8, base_val)
        accent = _hsv_to_rgb((base_hue + 90) % 360, base_sat * 0.6, base_val * 0.9)
    elif scheme == "analogous":
        primary = _hsv_to_rgb(base_hue, base_sat, base_val)
        secondary = _hsv_to_rgb((base_hue + 30) % 360, base_sat, base_val * 0.9)
        accent = _hsv_to_rgb((base_hue - 30) % 360, base_sat * 0.8, base_val)
    elif scheme == "triadic":
        primary = _hsv_to_rgb(base_hue, base_sat, base_val)
        secondary = _hsv_to_rgb((base_hue + 120) % 360, base_sat, base_val)
        accent = _hsv_to_rgb((base_hue + 240) % 360, base_sat, base_val)
    elif scheme == "monochrome":
        primary = _hsv_to_rgb(base_hue, base_sat, base_val)
        secondary = _hsv_to_rgb(base_hue, base_sat * 0.5, base_val * 0.8)
        accent = _hsv_to_rgb(base_hue, base_sat * 0.3, base_val * 0.95)
    elif scheme == "neon":
        primary = _hsv_to_rgb(base_hue, 1.0, 1.0)
        secondary = _hsv_to_rgb((base_hue + 60) % 360, 1.0, 1.0)
        accent = _hsv_to_rgb((base_hue + 180) % 360, 0.9, 0.95)
    elif scheme == "pastel":
        primary = _hsv_to_rgb(base_hue, 0.3, 0.95)
        secondary = _hsv_to_rgb((base_hue + 40) % 360, 0.25, 0.95)
        accent = _hsv_to_rgb((base_hue + 180) % 360, 0.35, 0.9)
    elif scheme == "earth":
        primary = _hsv_to_rgb(30 + rng.uniform(-10, 10), 0.6, 0.5)
        secondary = _hsv_to_rgb(45 + rng.uniform(-10, 10), 0.5, 0.6)
        accent = _hsv_to_rgb(15 + rng.uniform(-10, 10), 0.7, 0.4)
    elif scheme == "metallic":
        primary = _hsv_to_rgb(45, 0.3, 0.85)  # gold
        secondary = _hsv_to_rgb(0, 0.0, 0.75)  # silver
        accent = _hsv_to_rgb(30, 0.5, 0.6)     # bronze
    else:
        primary = _hsv_to_rgb(base_hue, base_sat, base_val)
        secondary = _hsv_to_rgb(base_hue, base_sat * 0.5, base_val)
        accent = (255, 255, 255)

    return ColorPalette(
        primary=primary,
        secondary=secondary,
        accent=accent,
        name=scheme,
    )


# Preset palettes
PRESET_PALETTES = {
    "tropical": ColorPalette((255, 87, 51), (255, 189, 51), (51, 255, 189), "tropical"),
    "ocean": ColorPalette((0, 105, 148), (0, 168, 198), (255, 255, 255), "ocean"),
    "sunset": ColorPalette((255, 94, 77), (255, 167, 38), (255, 241, 118), "sunset"),
    "midnight": ColorPalette((25, 25, 112), (72, 61, 139), (186, 85, 211), "midnight"),
    "coral": ColorPalette((255, 127, 80), (255, 160, 122), (255, 228, 196), "coral"),
    "black_gold": ColorPalette((20, 20, 20), (212, 175, 55), (255, 223, 0), "black_gold"),
}
