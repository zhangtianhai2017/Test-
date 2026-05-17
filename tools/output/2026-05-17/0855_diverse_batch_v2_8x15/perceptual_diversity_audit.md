# Perceptual diversity audit — 120 variants

## Per-axis coverage
| axis | seen / universe | distribution |
|---|---|---|
| archetype | 4/4 | triangle_string_halter:30, bandeau_back_band:30, bralette_shoulder_strap:30, one_piece_maillot:30 |
| cup_family | 4/5 | triangle:43, balconette:37, foam:30, bandeau:10 |
| hue | 8/8 | yellow:33, red:27, pink:17, blue:15, orange:11, green:7, cyan:5, purple:5 |
| lightness | 3/3 | mid:71, dark:35, light:14 |
| saturation | 2/2 | vivid:106, muted:14 |
| pattern_family | 4/4 | geometric:62, organic:34, gradient:14, solid:10 |
| weave_family | 6/6 | textured:41, plain:24, lace_open:22, lustrous:13, structured:10, mesh_open:10 |
| bottom_coverage | 3/3 | full:64, medium:40, minimal:16 |
| symmetry | 2/2 | mirror:87, dramatic_asym:33 |

## Pairwise Hamming distance histogram (max=9)
| dist | pairs | % |
|---|---|---|
| 0 | 5 | 0.1% |
| 1 | 66 | 0.9% |
| 2 | 203 | 2.8% |
| 3 | 514 | 7.2% |
| 4 | 975 | 13.7% |
| 5 | 1594 | 22.3% |
| 6 | 1832 | 25.7% |
| 7 | 1379 | 19.3% |
| 8 | 517 | 7.2% |
| 9 | 55 | 0.8% |

## Verdict
- Near-duplicate pairs (Hamming <= 1):  **71**  (1.0%)
- Clearly-distinct pairs (Hamming >= 5): **5377**  (75.3%)

Some near-duplicate examples (the first 10):
- d=1  `v2_00_triangle_string_halter_M020/00` ↔ `v2_00_triangle_string_halter_M020/09`
     ('triangle_string_halter', 'triangle', 'pink', 'mid', 'vivid', 'organic', 'structured', 'minimal', 'mirror')
     ('triangle_string_halter', 'triangle', 'red', 'mid', 'vivid', 'organic', 'structured', 'minimal', 'mirror')
- d=1  `v2_00_triangle_string_halter_M020/00` ↔ `v2_06_bralette_shoulder_strap_M020/06`
     ('triangle_string_halter', 'triangle', 'pink', 'mid', 'vivid', 'organic', 'structured', 'minimal', 'mirror')
     ('bralette_shoulder_strap', 'triangle', 'pink', 'mid', 'vivid', 'organic', 'structured', 'minimal', 'mirror')
- d=1  `v2_00_triangle_string_halter_M020/03` ↔ `v2_00_triangle_string_halter_M020/04`
     ('triangle_string_halter', 'triangle', 'pink', 'mid', 'vivid', 'geometric', 'lace_open', 'minimal', 'mirror')
     ('triangle_string_halter', 'triangle', 'pink', 'mid', 'vivid', 'geometric', 'textured', 'minimal', 'mirror')
- d=1  `v2_00_triangle_string_halter_M020/04` ↔ `v2_00_triangle_string_halter_M020/06`
     ('triangle_string_halter', 'triangle', 'pink', 'mid', 'vivid', 'geometric', 'textured', 'minimal', 'mirror')
     ('triangle_string_halter', 'triangle', 'red', 'mid', 'vivid', 'geometric', 'textured', 'minimal', 'mirror')
- d=1  `v2_00_triangle_string_halter_M020/05` ↔ `v2_02_triangle_string_halter_M080/00`
     ('triangle_string_halter', 'triangle', 'red', 'mid', 'vivid', 'geometric', 'mesh_open', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'orange', 'mid', 'vivid', 'geometric', 'mesh_open', 'medium', 'mirror')
- d=1  `v2_00_triangle_string_halter_M020/08` ↔ `v2_01_triangle_string_halter_M050/00`
     ('triangle_string_halter', 'triangle', 'red', 'mid', 'vivid', 'geometric', 'lace_open', 'medium', 'dramatic_asym')
     ('triangle_string_halter', 'triangle', 'cyan', 'mid', 'vivid', 'geometric', 'lace_open', 'medium', 'dramatic_asym')
- d=1  `v2_01_triangle_string_halter_M050/03` ↔ `v2_01_triangle_string_halter_M050/06`
     ('triangle_string_halter', 'triangle', 'blue', 'mid', 'vivid', 'solid', 'plain', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'blue', 'mid', 'vivid', 'geometric', 'plain', 'medium', 'mirror')
- d=1  `v2_01_triangle_string_halter_M050/03` ↔ `v2_01_triangle_string_halter_M050/08`
     ('triangle_string_halter', 'triangle', 'blue', 'mid', 'vivid', 'solid', 'plain', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'blue', 'mid', 'vivid', 'solid', 'lace_open', 'medium', 'mirror')
- d=0  `v2_01_triangle_string_halter_M050/05` ↔ `v2_01_triangle_string_halter_M050/07`
     ('triangle_string_halter', 'triangle', 'blue', 'light', 'vivid', 'geometric', 'textured', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'blue', 'light', 'vivid', 'geometric', 'textured', 'medium', 'mirror')
- d=1  `v2_01_triangle_string_halter_M050/06` ↔ `v2_02_triangle_string_halter_M080/01`
     ('triangle_string_halter', 'triangle', 'blue', 'mid', 'vivid', 'geometric', 'plain', 'medium', 'mirror')
     ('triangle_string_halter', 'triangle', 'orange', 'mid', 'vivid', 'geometric', 'plain', 'medium', 'mirror')
