# v2 audit-fix comparison — pre vs post

This run was generated immediately after commit `8284018` (v2 audit fixes:
7 critical bugs + 4 medium + dead code cleanup). Same script, same RNG seeds,
same library catalog as the pre-fix run at `0352_v2_ga_demo/`.

## GA composite trajectories (max per archetype, last gen)

| archetype | pre-fix (0352) | post-fix (0657) | Δ |
|---|---|---|---|
| triangle_string_halter   | 0.875 | **0.888** | +0.013 |
| bandeau_back_band        | 0.812 | **0.888** | **+0.076** |
| bralette_shoulder_strap  | 0.877 | **0.939** | **+0.062** |
| one_piece_maillot        | 0.869 | **0.901** | +0.032 |

Bralette gains the most (+0.062) because hardware (sliders, O-rings) used
to be silently dropped at deploy_to_body and is now preserved through to
the renderer and through compatibility scoring.

## Outfit-native axis behavior (12 winners across 4 archetypes)

| axis | pre min/max/std | post min/max/std | finding |
|---|---|---|---|
| slot_richness          | 0.00 / 0.74 / **0.32** | 0.56 / 0.91 / 0.17 | Pre had 3 outfits at 0.00 (bandeau hadn't filled any optional slots); post stays in healthy range |
| library_diversity      | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.00 | Always saturated (mutate doesn't pick same id twice) |
| compatibility_strength | 0.70 / 1.00 / 0.14 | 0.70 / 0.70 / 0.00 | Pre value of 1.0 was a coincidence (hardware silently dropped → no compat partners declared in remaining set) |
| anatomy_coverage       | 0.33 / 1.00 / 0.26 | 0.70 / 1.00 / 0.14 | Pre had `1/n_decorative` collapse (anatomy_hints type bug); post correctly reads `tuple[str,...]` |
| palette_coherence      | 0.92 / 0.92 / **0.00** | 0.80 / 0.95 / 0.05 | Pre constant 0.92 (truthy "free" preset short-circuit); post varies on actual hue distance |
| manufacturing_realism  | 1.00 / 1.00 / 0.00 | 1.00 / 1.00 / 0.00 | Always saturated; current library has few SKU-stacking configurations |

`compatibility_strength` dropping from 0.77 mean to 0.70 is **expected and correct** — the
audit found that the pre-fix run was getting bonus credit for entries whose declared
compatible_with was satisfied "by accident" because matching hardware partners had
been dropped from the outfit before scoring. Post-fix the score correctly reflects
"no explicit constraint was matched".

## style_archetype distribution after `outfit_to_genome` (200 random outfits)

Pre-fix: **all 200 outfits → "brazilian"** (hardcoded). Post-fix:

```
  brazilian          50  (triangle_string_halter)
  eres_architect     52  (one_piece_maillot)
  hunzag_crinkle     55  (bandeau_back_band)
  sporty_chromat     43  (bralette_shoulder_strap)
```

Each v2 archetype now maps to a distinct v1 enum, so v1 fitness's style scoring
(harmony / unity) actually evaluates against the correct style basis.

## Hardware survival through deploy

```
108/108 outfits with hardware kept it through deploy_to_body
```

Pre-fix: HARDWARE entries lacked `anatomy_hints` → `deploy_to_body` issued
D3 warnings and dropped every selected ring/slider/buckle/hook-eye. Look at
the post-fix top-3 bralette winners — the slot picks now include
`slider=HW_SLIDER_10MM_NICKEL` / `HW_SLIDER_20MM_GOLD`, which means those
parts actually rendered onto the body.

## Validation

- 37/37 v1 seeds re-migrate cleanly through `seed_to_outfit.py`
- 500/500 random outfits across 4 archetypes pass `validate_outfit`
- IterParams.outfit survives `clamped()` / `with_delta()` round-trips as
  `Outfit` (was: silently degraded to `dict`)

Generated `0657_v2_ga_demo/` (12 winner renders) +
`0657_v2_full_batch/` (37 seed renders × 8 views = 296 PNGs).
