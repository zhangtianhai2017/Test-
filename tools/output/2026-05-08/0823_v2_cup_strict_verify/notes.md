# `cup_coverage_strict` hyperparameter — visual verification

Mirrors the `bottom_coverage_strict` pattern from commit b24e709, but on the
chest. Same RNG seed per archetype, same other slot picks, only `cup_strict`
differs.

| value | semantic |
|---|---|
| 0.0 | unconstrained (current default) |
| 0.33+ | drop pure triangle cups; prefer balconette / bandeau / molded foam |
| 0.66+ | only molded_foam / softcup; falls back through balconette/bandeau if archetype's slot tags don't allow molded |
| 1.0 | strict: same as 0.66+ plus cup local_params pinned (half_u/half_v → schema max, inner_u → schema min so cups close in toward sternum) |

## Same-RNG comparison (each row = same seed, same archetype)

| archetype | strict=0 | strict=1 |
|---|---|---|
| triangle_string_halter (rng 111) | CUP_BRAZILIAN_S | CUP_BRAZILIAN_S |
| bandeau_back_band (rng 222)      | CUP_BANDEAU_S   | CUP_FOAM_MOLDED_S |
| bralette_shoulder_strap (rng 333)| CUP_TRIANGLE_L  | CUP_FOAM_MOLDED_L |
| one_piece_maillot (rng 444)      | CUP_TRIANGLE_M  | CUP_FOAM_MOLDED_M |

triangle_string_halter's slot only allows `("triangle","brazilian")` —
neither geometry is `_CUP_FULL_GEOS` ("molded_foam","softcup_squareneck") —
so the graduated fallback returns the same minimal-coverage tier.
Triangle is by archetype-design a minimal-coverage style; the strict
parameter can't override the archetype.

The other three archetypes all upgrade to molded foam at strict=1, with
cup local_params pinned to wider/taller cups closer to the sternum.

## Implementation

- `tools/library.py::CUP_COVERAGE_STRICT` (module global) +
  `set_cup_coverage_strict()` setter
- `tools/library.py::filter_cups_by_coverage()` mirrors
  `filter_bottoms_by_coverage` but indexes off `geometry_kind` instead of
  `coverage_class` (cups don't carry an explicit coverage_class field;
  geometry_kind is the natural proxy)
- `tools/outfit.py::_pin_to_max_cup_coverage()` pins `half_u` / `half_v`
  to schema MAX and `inner_u` to schema MIN at strict=1
- `random_outfit` and `genome_to_outfit` accept new `cup_coverage_strict`
  kwarg (None = use module global)
- `outfit_ga.mutate` filters cup resamples by `library.CUP_COVERAGE_STRICT`
- `tools/iter/params.py::IterParams.cup_coverage_strict` (default 0.0);
  capture.py forwards to library before each render
- `bandeau_back_band` and `bralette_shoulder_strap` archetypes get a
  `lining_fabric` SlotSpec so molded foam's `compatible_with=
  ("F_FOAM_CUP_3MM",)` resolves cleanly without overriding the primary
  swim fabric

Validation: 0/300 outfits invalid across every {bottom_strict,
cup_strict} ∈ {0,1}² combination.
