# Perceptual diversity audit — 120 variants

## Per-axis coverage
| axis | seen / universe | distribution |
|---|---|---|
| archetype | 4/4 | triangle_string_halter:30, bandeau_back_band:30, bralette_shoulder_strap:30, one_piece_maillot:30 |
| cup_family | 2/5 | foam:90, triangle:30 |
| hue | 8/8 | cyan:25, orange:25, yellow:21, green:18, pink:15, red:14, purple:1, blue:1 |
| lightness | 3/3 | mid:53, dark:49, light:18 |
| saturation | 2/2 | vivid:77, muted:43 |
| pattern_family | 4/4 | geometric:51, organic:38, gradient:22, solid:9 |
| weave_family | 6/6 | textured:40, lace_open:22, structured:19, plain:19, mesh_open:13, lustrous:7 |
| bottom_coverage | 2/3 | full:90, medium:30 |
| symmetry | 2/2 | mirror:80, dramatic_asym:40 |

## Pairwise Hamming distance histogram (max=9)
| dist | pairs | % |
|---|---|---|
| 0 | 9 | 0.1% |
| 1 | 79 | 1.1% |
| 2 | 352 | 4.9% |
| 3 | 676 | 9.5% |
| 4 | 1121 | 15.7% |
| 5 | 1383 | 19.4% |
| 6 | 1466 | 20.5% |
| 7 | 1263 | 17.7% |
| 8 | 658 | 9.2% |
| 9 | 133 | 1.9% |

## Verdict
- Near-duplicate pairs (Hamming <= 1):  **88**  (1.2%)
- Clearly-distinct pairs (Hamming >= 5): **4903**  (68.7%)

Some near-duplicate examples (the first 10):
- d=1  `v2_00_triangle_string_halter_b0/01` ↔ `v2_00_triangle_string_halter_b0/08`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'organic', 'structured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'organic', 'mesh_open', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/01` ↔ `v2_00_triangle_string_halter_b0/09`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'organic', 'structured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'organic', 'mesh_open', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/01` ↔ `v2_00_triangle_string_halter_b0/13`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'organic', 'structured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'cyan', 'mid', 'muted', 'organic', 'structured', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/02` ↔ `v2_00_triangle_string_halter_b0/03`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'structured', 'medium', 'dramatic_asym')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'lustrous', 'medium', 'dramatic_asym')
- d=1  `v2_00_triangle_string_halter_b0/04` ↔ `v2_00_triangle_string_halter_b0/06`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'plain', 'medium', 'mirror')
- d=0  `v2_00_triangle_string_halter_b0/04` ↔ `v2_00_triangle_string_halter_b0/07`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/04` ↔ `v2_00_triangle_string_halter_b0/10`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'gradient', 'textured', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/04` ↔ `v2_00_triangle_string_halter_b0/14`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'cyan', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/06` ↔ `v2_00_triangle_string_halter_b0/07`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'plain', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_b0/07` ↔ `v2_00_triangle_string_halter_b0/10`
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'geometric', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'green', 'mid', 'muted', 'gradient', 'textured', 'medium', 'mirror')
