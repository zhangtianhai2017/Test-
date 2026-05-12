# Verify run for two fixes

## 1. "horizontal bar with end-lobe between the thighs" — gusset arc tube

**Root cause**: `tools/render3d_uv.py::_build_strap_meshes_garment` was tracing
an `_arc_tube` from `u=0` (front center) to `u=1.0` (back center) at
`y=y_crotch+1`. That sweeps a half-circle around the torso at crotch height.

What you saw in the front view = the visible arc segments:
- Front-center bit (u≈0): a short forward-pointing tube between the legs
- Right-side bit (u≈0.5): the tube terminus at the right hip — the
  small "lobe"
- Back-center bit (u≈1.0): hidden behind the body, invisible

Real swimwear gussets are flat fabric panels on the inside of the bottom,
NOT a strap around the hips. The front_bottom + back_bottom PatternPieces
already meet visibly at the inseam without any extra surface geometry,
so this rendering was deleted.

`fringe_after/diverse_*` shows 5 of the 9 originally-affected seeds
re-rendered with the gusset removed — clean garment outlines, no bar
between thighs.

## 2. `bottom_coverage_strict` hyperparameter

`library.BOTTOM_COVERAGE_STRICT` (and `IterParams.bottom_coverage_strict`):

| value | semantic |
|---|---|
| 0.0 | unconstrained — current behavior |
| 0.33+ | drop minimal coverage tier, prefer medium+full |
| 0.66+ | only `coverage_class=full`; falls back to medium then minimal if archetype's slot tags don't allow full |
| 1.0 | strict: same as 0.66+ plus front/back coverage local_params pinned to schema max |

Sample renders in `strict_0/` and `strict_10/` (same RNG seeds, same archetypes):

| archetype | strict=0.0 | strict=1.0 |
|---|---|---|
| triangle_string_halter (RNG 101) | BOT_BRAZILIAN_M | BOT_CHEEKY_S |
| bralette_shoulder_strap (RNG 202) | BOT_BRAZILIAN_M | BOT_HIGHWAIST_M |
| one_piece_maillot (RNG 303) | BOT_BRIEF_M | BOT_HIGHWAIST_M |

Triangle archetype's slot only allows `("thong","brazilian","cheeky")`,
none of which are `coverage_class="full"` — so strict=1.0 falls back to
the most-covering tier the archetype permits (medium = cheeky). Bralette
and one_piece allow `("brief","high_waisted")` so they jump to high-waist.

`tools/iter/capture.py` calls `library.set_bottom_coverage_strict(
params.bottom_coverage_strict)` before each render so the constraint
flows through the v2 outfit cascade automatically.
