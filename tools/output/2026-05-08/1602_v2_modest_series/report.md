# Modest series — both coverage caps = 1.0, side panels pinned to max

Re-runs 1135_v2_strict_both_max with fresh RNG seeds. The point is to
show structured side fabric panels (not strings/ribbons): bottom
local_params front_half_u / back_half_u / front_top_v / back_top_v
all pinned to schema MAX inside `_pin_to_max_coverage`.

## Per outfit

| outfit | cup | bottom | front_half_u | back_half_u | composite |
|---|---|---|---|---|---|
| `triangle_string_halter__rng0` | `CUP_BRAZILIAN_S` | `BOT_CHEEKY_M` | 0.220 | 0.160 | 0.832 |
| `triangle_string_halter__rng1` | `CUP_BRAZILIAN_S` | `BOT_CHEEKY_S` | 0.187 | 0.160 | 0.835 |
| `triangle_string_halter__rng2` | `CUP_TRIANGLE_S` | `BOT_CHEEKY_M` | 0.220 | 0.160 | 0.789 |
| `triangle_string_halter__rng3` | `CUP_BRAZILIAN_S` | `BOT_CHEEKY_S` | 0.187 | 0.160 | 0.834 |
| `bandeau_back_band__rng0` | `CUP_FOAM_MOLDED_S` | `BOT_HIGHWAIST_M` | 0.260 | 0.260 | 0.784 |
| `bandeau_back_band__rng1` | `CUP_FOAM_MOLDED_L` | `BOT_HIGHWAIST_S` | 0.221 | 0.260 | 0.826 |
| `bandeau_back_band__rng2` | `CUP_FOAM_MOLDED_L` | `BOT_HIGHWAIST_M` | 0.260 | 0.260 | 0.819 |
| `bandeau_back_band__rng3` | `CUP_FOAM_MOLDED_S` | `BOT_BRIEF_M` | 0.260 | 0.240 | 0.838 |
| `bralette_shoulder_strap__rng0` | `CUP_FOAM_MOLDED_L` | `BOT_BRIEF_M` | 0.260 | 0.240 | 0.805 |
| `bralette_shoulder_strap__rng1` | `CUP_FOAM_MOLDED_M` | `BOT_HIGHWAIST_S` | 0.221 | 0.260 | 0.784 |
| `bralette_shoulder_strap__rng2` | `CUP_FOAM_MOLDED_M` | `BOT_HIGHWAIST_S` | 0.221 | 0.260 | 0.820 |
| `bralette_shoulder_strap__rng3` | `CUP_FOAM_MOLDED_S` | `BOT_BRIEF_S` | 0.221 | 0.240 | 0.828 |
| `one_piece_maillot__rng0` | `CUP_FOAM_MOLDED_M` | `BOT_BRIEF_M` | 0.260 | 0.240 | 0.798 |
| `one_piece_maillot__rng1` | `CUP_FOAM_MOLDED_L` | `BOT_BRIEF_S` | 0.221 | 0.240 | 0.803 |
| `one_piece_maillot__rng2` | `CUP_FOAM_MOLDED_M` | `BOT_HIGHWAIST_M` | 0.260 | 0.260 | 0.840 |
| `one_piece_maillot__rng3` | `CUP_FOAM_MOLDED_M` | `BOT_BRIEF_S` | 0.221 | 0.240 | 0.765 |

## Aggregate

- composite: mean=0.812, std=0.023, range=[0.765, 0.840]
- 16/16 outfits validate clean
