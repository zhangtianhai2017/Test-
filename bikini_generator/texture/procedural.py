"""Procedural texture generation.

Generates patterns using noise functions, mathematical patterns,
and compositing techniques.
"""

import numpy as np
from PIL import Image
from opensimplex import OpenSimplex


def simplex_noise_2d(
    width: int, height: int, scale: float = 10.0, seed: int = 0
) -> np.ndarray:
    """Generate 2D simplex noise array in [0, 1]."""
    gen = OpenSimplex(seed=seed)
    arr = np.zeros((height, width), dtype=np.float32)
    for y in range(height):
        for x in range(width):
            val = gen.noise2(x / scale, y / scale)
            arr[y, x] = (val + 1) / 2  # normalize to [0, 1]
    return arr


def fbm_noise(
    width: int, height: int, octaves: int = 4,
    scale: float = 10.0, seed: int = 0,
) -> np.ndarray:
    """Fractal Brownian Motion noise — layered simplex noise."""
    result = np.zeros((height, width), dtype=np.float32)
    amplitude = 1.0
    frequency = 1.0
    max_val = 0.0

    for i in range(octaves):
        noise = simplex_noise_2d(width, height, scale / frequency, seed + i * 100)
        result += noise * amplitude
        max_val += amplitude
        amplitude *= 0.5
        frequency *= 2.0

    return result / max_val


def stripes(
    width: int, height: int, angle: float = 0.0,
    frequency: float = 10.0, duty: float = 0.5,
) -> np.ndarray:
    """Generate stripe pattern."""
    y_coords, x_coords = np.mgrid[0:height, 0:width]
    x_norm = x_coords / width
    y_norm = y_coords / height

    cos_a = np.cos(np.radians(angle))
    sin_a = np.sin(np.radians(angle))
    projected = x_norm * cos_a + y_norm * sin_a

    pattern = ((projected * frequency) % 1.0 < duty).astype(np.float32)
    return pattern


def dots(
    width: int, height: int, radius: float = 0.03,
    spacing: float = 0.1, offset_alternate: bool = True,
) -> np.ndarray:
    """Generate polka dot pattern."""
    pattern = np.zeros((height, width), dtype=np.float32)
    y_coords, x_coords = np.mgrid[0:height, 0:width]
    x_norm = x_coords / width
    y_norm = y_coords / height

    rows = int(1.0 / spacing)
    cols = int(1.0 / spacing)

    for r in range(rows + 1):
        for c in range(cols + 1):
            cx = c * spacing
            cy = r * spacing
            if offset_alternate and r % 2 == 1:
                cx += spacing / 2

            dist = np.sqrt((x_norm - cx) ** 2 + (y_norm - cy) ** 2)
            pattern = np.maximum(pattern, (dist < radius).astype(np.float32))

    return pattern


def chevron(
    width: int, height: int, frequency: float = 8.0, thickness: float = 0.3,
) -> np.ndarray:
    """Generate chevron/zigzag pattern."""
    y_coords, x_coords = np.mgrid[0:height, 0:width]
    x_norm = x_coords / width
    y_norm = y_coords / height

    wave = np.abs((x_norm * frequency) % 2.0 - 1.0)
    pattern = (np.abs(y_norm - wave) < thickness / frequency).astype(np.float32)
    return pattern


def animal_print(
    width: int, height: int, scale: float = 15.0, seed: int = 0,
) -> np.ndarray:
    """Generate leopard/animal print using Voronoi-like noise."""
    noise1 = fbm_noise(width, height, octaves=3, scale=scale, seed=seed)
    noise2 = fbm_noise(width, height, octaves=3, scale=scale * 0.7, seed=seed + 42)

    # Create spots by thresholding noise difference
    diff = np.abs(noise1 - noise2)
    spots = (diff < 0.15).astype(np.float32)

    # Add ring effect
    edge = (diff > 0.1) & (diff < 0.2)
    result = spots * 0.2 + edge.astype(np.float32) * 0.8
    return np.clip(result, 0, 1)


def floral(
    width: int, height: int, n_flowers: int = 5, seed: int = 0,
) -> np.ndarray:
    """Generate simple floral pattern."""
    rng = np.random.default_rng(seed)
    pattern = np.zeros((height, width), dtype=np.float32)
    y_coords, x_coords = np.mgrid[0:height, 0:width]
    x_norm = x_coords / width
    y_norm = y_coords / height

    for _ in range(n_flowers):
        cx = rng.uniform(0, 1)
        cy = rng.uniform(0, 1)
        n_petals = rng.integers(4, 9)
        size = rng.uniform(0.05, 0.15)

        dist = np.sqrt((x_norm - cx) ** 2 + (y_norm - cy) ** 2)
        angle = np.arctan2(y_norm - cy, x_norm - cx)

        petal = np.cos(n_petals * angle) * 0.5 + 0.5
        flower = ((dist < size * petal) & (dist > size * petal * 0.3)).astype(np.float32)
        # Center
        center = (dist < size * 0.15).astype(np.float32)
        pattern = np.maximum(pattern, flower * 0.7 + center)

    return np.clip(pattern, 0, 1)


def geometric(
    width: int, height: int, shape: str = "triangles",
    scale: float = 8.0, seed: int = 0,
) -> np.ndarray:
    """Generate geometric pattern (triangles, hexagons, diamonds)."""
    y_coords, x_coords = np.mgrid[0:height, 0:width]
    x_norm = x_coords / width * scale
    y_norm = y_coords / height * scale

    if shape == "triangles":
        pattern = ((x_norm + y_norm).astype(int) % 2).astype(np.float32)
    elif shape == "diamonds":
        pattern = ((np.abs(x_norm % 2 - 1) + np.abs(y_norm % 2 - 1)) < 0.8).astype(np.float32)
    elif shape == "hexagons":
        # Approximate hexagonal grid
        row = y_norm
        col = x_norm + (np.floor(y_norm) % 2) * 0.5
        pattern = ((col % 1 > 0.15) & (row % 1 > 0.15)).astype(np.float32)
    else:
        pattern = stripes(width, height, angle=45, frequency=scale)

    return pattern


def gradient(
    width: int, height: int, direction: str = "vertical",
    colors: int = 2,
) -> np.ndarray:
    """Generate gradient pattern."""
    y_coords, x_coords = np.mgrid[0:height, 0:width]

    if direction == "vertical":
        pattern = y_coords / height
    elif direction == "horizontal":
        pattern = x_coords / width
    elif direction == "radial":
        cx, cy = width / 2, height / 2
        pattern = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
        pattern = pattern / pattern.max()
    elif direction == "diagonal":
        pattern = (x_coords / width + y_coords / height) / 2
    else:
        pattern = y_coords / height

    return pattern.astype(np.float32)


# Registry
PATTERN_TYPES = {
    "noise": lambda w, h, **kw: fbm_noise(w, h, **kw),
    "stripes": stripes,
    "dots": dots,
    "chevron": chevron,
    "animal_print": animal_print,
    "floral": floral,
    "geometric": geometric,
    "gradient": gradient,
}
