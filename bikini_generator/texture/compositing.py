"""Texture compositing: layer patterns, apply colors, create final texture images."""

import numpy as np
from PIL import Image, ImageFilter
from .procedural import PATTERN_TYPES
from .palette import ColorPalette, random_palette


def apply_palette(
    pattern: np.ndarray,
    palette: ColorPalette,
    use_accent: bool = False,
) -> np.ndarray:
    """Apply a color palette to a grayscale pattern.

    Returns (H, W, 3) uint8 array.
    """
    h, w = pattern.shape
    result = np.zeros((h, w, 3), dtype=np.uint8)

    primary = np.array(palette.primary, dtype=np.float32)
    secondary = np.array(palette.secondary, dtype=np.float32)

    # Lerp between primary and secondary based on pattern value
    for c in range(3):
        result[:, :, c] = (
            primary[c] * (1 - pattern) + secondary[c] * pattern
        ).astype(np.uint8)

    if use_accent:
        # Add accent color at high-value areas
        accent = np.array(palette.accent, dtype=np.float32)
        mask = pattern > 0.8
        for c in range(3):
            result[:, :, c] = np.where(mask, accent[c], result[:, :, c])

    return result


def blend_layers(
    base: np.ndarray,
    overlay: np.ndarray,
    mode: str = "multiply",
    opacity: float = 0.5,
) -> np.ndarray:
    """Blend two (H, W, 3) uint8 arrays."""
    base_f = base.astype(np.float32) / 255.0
    over_f = overlay.astype(np.float32) / 255.0

    if mode == "multiply":
        blended = base_f * over_f
    elif mode == "screen":
        blended = 1.0 - (1.0 - base_f) * (1.0 - over_f)
    elif mode == "overlay":
        mask = base_f < 0.5
        blended = np.where(
            mask,
            2 * base_f * over_f,
            1 - 2 * (1 - base_f) * (1 - over_f),
        )
    elif mode == "add":
        blended = np.clip(base_f + over_f, 0, 1)
    else:
        blended = over_f

    result = base_f * (1 - opacity) + blended * opacity
    return (np.clip(result, 0, 1) * 255).astype(np.uint8)


def add_material_effect(
    texture: np.ndarray,
    effect: str = "none",
    seed: int = 0,
) -> np.ndarray:
    """Apply material-like effects to texture."""
    img = Image.fromarray(texture)

    if effect == "sheen":
        # Metallic sheen: add diagonal bright streak
        h, w = texture.shape[:2]
        from .procedural import gradient
        streak = gradient(w, h, direction="diagonal")
        streak_rgb = np.stack([streak * 80] * 3, axis=-1).astype(np.uint8)
        texture = blend_layers(texture, streak_rgb, mode="add", opacity=0.3)

    elif effect == "lace":
        # Simulate lace with transparency pattern
        from .procedural import dots
        h, w = texture.shape[:2]
        lace_mask = dots(w, h, radius=0.02, spacing=0.06)
        # Darken where lace holes are
        hole_overlay = np.zeros_like(texture)
        texture = blend_layers(texture, hole_overlay, mode="multiply",
                               opacity=0.4 * (1 - lace_mask[:, :, np.newaxis].repeat(3, axis=2).mean(axis=2) / 255 if False else 0.3))
        # Simplify: just darken dots
        for c in range(3):
            texture[:, :, c] = (texture[:, :, c].astype(np.float32) * (0.5 + 0.5 * lace_mask)).astype(np.uint8)

    elif effect == "velvet":
        # Soft blur + slight darkening
        img = Image.fromarray(texture)
        img = img.filter(ImageFilter.GaussianBlur(radius=1))
        texture = np.array(img)
        texture = (texture.astype(np.float32) * 0.9).astype(np.uint8)

    elif effect == "satin":
        # Smooth with bright highlights
        img = Image.fromarray(texture)
        img = img.filter(ImageFilter.SMOOTH_MORE)
        texture = np.array(img)
        h, w = texture.shape[:2]
        from .procedural import simplex_noise_2d
        highlights = simplex_noise_2d(w, h, scale=30.0, seed=seed)
        highlight_mask = (highlights > 0.7).astype(np.float32) * 40
        for c in range(3):
            texture[:, :, c] = np.clip(
                texture[:, :, c].astype(np.float32) + highlight_mask, 0, 255
            ).astype(np.uint8)

    elif effect == "embossed":
        img = Image.fromarray(texture)
        img = img.filter(ImageFilter.EMBOSS)
        texture = np.array(img)

    return texture


def generate_texture(
    width: int = 1024,
    height: int = 1024,
    pattern_name: str = "noise",
    palette: ColorPalette | None = None,
    material_effect: str = "none",
    seed: int = 0,
    pattern_params: dict | None = None,
) -> Image.Image:
    """Generate a complete texture image.

    Args:
        width, height: texture resolution
        pattern_name: key from PATTERN_TYPES
        palette: color palette (random if None)
        material_effect: effect to apply (sheen, lace, velvet, satin, embossed, none)
        seed: random seed
        pattern_params: additional params for pattern generator

    Returns:
        PIL Image
    """
    if palette is None:
        palette = random_palette(seed)

    params = pattern_params or {}
    params["seed"] = seed

    # Generate base pattern
    if pattern_name in PATTERN_TYPES:
        pattern_func = PATTERN_TYPES[pattern_name]
        # Filter params to match function signature
        import inspect
        sig = inspect.signature(pattern_func)
        valid_params = {k: v for k, v in params.items() if k in sig.parameters}
        pattern = pattern_func(width, height, **valid_params)
    else:
        pattern = PATTERN_TYPES["noise"](width, height, seed=seed)

    # Apply colors
    colored = apply_palette(pattern, palette, use_accent=True)

    # Apply material effect
    colored = add_material_effect(colored, material_effect, seed)

    return Image.fromarray(colored)


def random_texture(
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
) -> tuple[Image.Image, dict]:
    """Generate a fully randomized texture with metadata."""
    rng = np.random.default_rng(seed)
    actual_seed = int(rng.integers(0, 2**31))

    pattern_name = rng.choice(list(PATTERN_TYPES.keys()))
    palette = random_palette(actual_seed)
    effect = rng.choice(["none", "none", "sheen", "velvet", "satin", "embossed"])

    img = generate_texture(
        width, height, pattern_name, palette, effect, actual_seed,
    )

    metadata = {
        "pattern": pattern_name,
        "palette": palette.name,
        "effect": effect,
        "seed": actual_seed,
        "primary_color": palette.primary,
        "secondary_color": palette.secondary,
    }

    return img, metadata
