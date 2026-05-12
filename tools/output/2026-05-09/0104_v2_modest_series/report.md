# Modest series — both coverage caps = 1.0, side panels pinned to max

Re-runs 1135_v2_strict_both_max with fresh RNG seeds. The point is to
show structured side fabric panels (not strings/ribbons): bottom
local_params front_half_u / back_half_u / front_top_v / back_top_v
all pinned to schema MAX inside `_pin_to_max_coverage`.

## Per outfit

| outfit | cup | bottom | front_half_u | back_half_u | composite |
|---|---|---|---|---|---|
| `triangle_string_halter__rng0` | `CUP_BRAZILIAN_L` | `BOT_CHEEKY_S` | 0.357 | 0.260 | 0.753 |
| `triangle_string_halter__rng1` | `CUP_TRIANGLE_M` | `BOT_CHEEKY_S` | 0.357 | 0.260 | 0.801 |
| `triangle_string_halter__rng2` | `CUP_BRAZILIAN_S` | `BOT_CHEEKY_M` | 0.420 | 0.260 | 0.727 |
| `triangle_string_halter__rng3` | `CUP_TRIANGLE_M` | `BOT_CHEEKY_M` | 0.420 | 0.260 | 0.799 |
| `bandeau_back_band__rng0` | `CUP_FOAM_MOLDED_M` | `BOT_BRIEF_M` | 0.520 | 0.420 | 0.767 |
| `bandeau_back_band__rng1` | `CUP_FOAM_MOLDED_S` | `BOT_BRIEF_M` | 0.520 | 0.420 | 0.853 |
| `bandeau_back_band__rng2` | `CUP_FOAM_MOLDED_S` | `BOT_HIGHWAIST_S` | 0.493 | 0.391 | 0.782 |
| `bandeau_back_band__rng3` | `CUP_FOAM_MOLDED_S` | `BOT_HIGHWAIST_M` | 0.580 | 0.460 | 0.851 |
| `bralette_shoulder_strap__rng0` | `CUP_FOAM_MOLDED_S` | `BOT_BRIEF_S` | 0.442 | 0.420 | 0.881 |
| `bralette_shoulder_strap__rng1` | `CUP_FOAM_MOLDED_M` | `BOT_BRIEF_S` | 0.442 | 0.420 | 0.812 |
| `bralette_shoulder_strap__rng2` | `CUP_FOAM_MOLDED_S` | `BOT_HIGHWAIST_S` | 0.493 | 0.391 | 0.733 |
| `bralette_shoulder_strap__rng3` | `CUP_FOAM_MOLDED_L` | `BOT_HIGHWAIST_S` | 0.493 | 0.391 | 0.779 |
| `one_piece_maillot__rng0` | `CUP_FOAM_MOLDED_S` | `BOT_BRIEF_M` | 0.520 | 0.420 | 0.836 |
| `one_piece_maillot__rng1` | `CUP_FOAM_MOLDED_M` | `BOT_HIGHWAIST_S` | 0.493 | 0.391 | 0.793 |
| `one_piece_maillot__rng2` | `CUP_FOAM_MOLDED_M` | `BOT_HIGHWAIST_M` | 0.580 | 0.460 | 0.791 |
| `one_piece_maillot__rng3` | `CUP_FOAM_MOLDED_L` | `BOT_HIGHWAIST_M` | 0.580 | 0.460 | 0.820 |

## Aggregate

- composite: mean=0.799, std=0.043, range=[0.727, 0.881]
- 16/16 outfits validate clean
