# Tie-side (挂带) bikini series — 12 outfits

Pinned factors:
- archetype = `triangle_string_halter` (only archetype with `side_tie` slot)
- bottom_front ∈ ['BOT_BRAZILIAN_S', 'BOT_BRAZILIAN_M'] (only library entries tagged `tie-side`)
- side_tie always filled, ∈ ['STR_TIE_CORD_3MM', 'STR_TIE_CORD_5MM', 'STR_TIE_RIBBON_15MM']
- `genome.bot_tie_dangle ∈ U(0.65, 0.95)` (renderer's `_build_strap_meshes`   draws a `dangle_len = 2 + 14·dangle` cm visible tail per side; default   outfit_to_genome value 0.40 ⇒ ~7cm, our range ⇒ 11–15 cm)

Other factors (cup, fabric, hardware, accessories, color) stay RNG-free.

## Per-outfit

| # | bottom | side_tie | cup | dangle (cm) | composite |
|---|---|---|---|---|---|
| tieside_00 | `BOT_BRAZILIAN_S` | `STR_TIE_RIBBON_15MM` | `CUP_BRAZILIAN_M` | 11.3 | 0.745 |
| tieside_01 | `BOT_BRAZILIAN_M` | `STR_TIE_CORD_5MM` | `CUP_TRIANGLE_S` | 14.8 | 0.754 |
| tieside_02 | `BOT_BRAZILIAN_S` | `STR_TIE_RIBBON_15MM` | `CUP_TRIANGLE_S` | 13.7 | 0.823 |
| tieside_03 | `BOT_BRAZILIAN_M` | `STR_TIE_CORD_3MM` | `CUP_BRAZILIAN_S` | 15.0 | 0.762 |
| tieside_04 | `BOT_BRAZILIAN_M` | `STR_TIE_RIBBON_15MM` | `CUP_TRIANGLE_L` | 13.8 | 0.822 |
| tieside_05 | `BOT_BRAZILIAN_M` | `STR_TIE_CORD_3MM` | `CUP_BRAZILIAN_S` | 11.3 | 0.801 |
| tieside_06 | `BOT_BRAZILIAN_M` | `STR_TIE_CORD_3MM` | `CUP_BRAZILIAN_L` | 13.7 | 0.778 |
| tieside_07 | `BOT_BRAZILIAN_S` | `STR_TIE_RIBBON_15MM` | `CUP_TRIANGLE_L` | 11.4 | 0.796 |
| tieside_08 | `BOT_BRAZILIAN_S` | `STR_TIE_RIBBON_15MM` | `CUP_BRAZILIAN_M` | 13.6 | 0.757 |
| tieside_09 | `BOT_BRAZILIAN_S` | `STR_TIE_CORD_3MM` | `CUP_BRAZILIAN_L` | 15.2 | 0.772 |
| tieside_10 | `BOT_BRAZILIAN_S` | `STR_TIE_RIBBON_15MM` | `CUP_TRIANGLE_M` | 12.2 | 0.802 |
| tieside_11 | `BOT_BRAZILIAN_S` | `STR_TIE_RIBBON_15MM` | `CUP_BRAZILIAN_M` | 12.6 | 0.811 |

## Aggregate

- composite: mean=0.785, std=0.027, range=[0.745, 0.823]
- 12/12 outfits use a tie-side BRAZILIAN bottom + a TIE strap_piece (by construction)
