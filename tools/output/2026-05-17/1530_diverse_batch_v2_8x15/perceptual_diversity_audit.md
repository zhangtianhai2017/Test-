# Perceptual diversity audit — 120 variants

## Per-axis coverage
| axis | seen / universe | distribution |
|---|---|---|
| archetype | 4/4 | triangle_string_halter:30, bandeau_back_band:30, bralette_shoulder_strap:30, one_piece_maillot:30 |
| cup_family | 3/5 | softcup:72, triangle:30, foam:18 |
| hue | 8/8 | cyan:25, orange:25, yellow:21, green:18, pink:15, red:14, purple:1, blue:1 |
| lightness | 3/3 | mid:52, dark:47, light:21 |
| saturation | 2/2 | vivid:82, muted:38 |
| pattern_family | 4/4 | geometric:65, organic:26, gradient:19, solid:10 |
| weave_family | 6/6 | textured:32, lace_open:28, plain:23, mesh_open:14, structured:13, lustrous:10 |
| bottom_coverage | 2/3 | full:90, medium:30 |
| symmetry | 2/2 | mirror:76, dramatic_asym:44 |

## Pairwise Hamming distance histogram (max=9)
| dist | pairs | % |
|---|---|---|
| 0 | 8 | 0.1% |
| 1 | 66 | 0.9% |
| 2 | 276 | 3.9% |
| 3 | 596 | 8.3% |
| 4 | 1054 | 14.8% |
| 5 | 1325 | 18.6% |
| 6 | 1522 | 21.3% |
| 7 | 1469 | 20.6% |
| 8 | 700 | 9.8% |
| 9 | 124 | 1.7% |

## Verdict
- Near-duplicate pairs (Hamming <= 1):  **74**  (1.0%)
- Clearly-distinct pairs (Hamming >= 5): **5140**  (72.0%)

Some near-duplicate examples (the first 10):
- d=1  `v2_00_triangle_string_halter_b0/02` ↔ `v2_00_triangle_string_halter_b0/05`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'lace_open', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
- d=0  `v2_00_triangle_string_halter_b0/02` ↔ `v2_00_triangle_string_halter_b0/07`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'lace_open', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'lace_open', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/02` ↔ `v2_00_triangle_string_halter_b0/10`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'lace_open', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'plain', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/03` ↔ `v2_00_triangle_string_halter_b0/05`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'organic', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/03` ↔ `v2_00_triangle_string_halter_b0/08`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'organic', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'organic', 'mesh_open', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/04` ↔ `v2_00_triangle_string_halter_b0/06`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'gradient', 'plain', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'gradient', 'lustrous', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/04` ↔ `v2_00_triangle_string_halter_b0/09`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'gradient', 'plain', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'gradient', 'mesh_open', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/04` ↔ `v2_00_triangle_string_halter_b0/10`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'gradient', 'plain', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'plain', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/05` ↔ `v2_00_triangle_string_halter_b0/07`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'lace_open', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/05` ↔ `v2_00_triangle_string_halter_b0/10`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'plain', 'medium', 'mirror')
