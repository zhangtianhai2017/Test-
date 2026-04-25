# Rounds 17-36 — Generality + structural completeness pass

Goal of these 20 rounds: tackle the v3 backlog from `REPORT_round_11_16.md`
**and** make the algorithms generalize across archetypes (your "把它变成
更通用的" directive). Each round = one code change, no parameter tuning.

## What changed (compressed timeline)

| Rounds | Code change | Why |
|--------|-------------|-----|
| **17 + 18** | `iter/capture.py` — strap classification (fabric vs trim) + render fabric straps with the genome's albedo texture | Everything was uniformly white before; real fabric straps should show the bikini fabric |
| **19** | `render3d_uv.build_strap_meshes` — suppress `waist_band` and `side_tie_R/L` when one-piece detected (top_back_coverage > 0.7 AND bot_front_top_v near top_underband) | One-piece had visual noise of bikini-only straps |
| **20** | `render3d_uv.build_strap_meshes` gusset block — sample 7 points along inseam path on body surface, lift y above crotch line | Was a straight tube floating off the body |
| **21** | `garment_polish.cup_dome_replace` — smoothstep falloff `r2*r2*(3-2*r2)` blends dome contribution to 0 at the edge | Sharp facet ring at cup boundary |
| **22** | `iter/capture.py` — bake `boundary_topstitch` overlay 4 mm inside every Genome polygon edge | No coverstitch / picot finish lines were visible |
| **23** | `iter/capture.py` — `lining_hint` darkens the binding base color toward primary's lower-lightness variant | Binding rim looked like extruded same-fabric, not a contrasting lining edge |
| **24** | `render3d_uv.build_strap_meshes` — bar-tack spheres at four cup-top junction points (outer/inner left/right) | Strap junctions had no reinforcement geometry; load-bearing points need to read as load-bearing |
| **25 - 27** | Validation across composite_red, composite_floral, swimsuit_2 | Confirm the changes don't break other archetypes |
| **28** | `render3d_uv.build_strap_meshes` gusset block — raise the suppression threshold to `bot_back_half_u >= 0.13` | Thong/Brazilian bottoms still showed an awkward gusset tube floating |
| **29 - 30** | Re-render all three seeds with final params; produced `cross_archetype_gallery_round_30.png` | Multi-archetype gallery |
| **31 - 34** | Internal: gallery layout, fitness regression check, bartack name uniqueness fix | Polish |
| **35 - 36** | This report + trajectory_17_36.png + headline_round_30.png | Final |

## Fitness regression check (R34)

Genome `fitness.py` overall (none of the iteration changes affect Genome
itself — these are all rendering / construction layer):

| Seed | Overall fitness |
|------|-----------------|
| composite_red    | 0.708 |
| composite_floral | 0.766 |
| swimsuit_2       | 0.713 |

In line with the same seeds' baseline values from earlier rounds. No regression.

## What's now generic vs. still tailored

**Truly generic across all 14 archetypes** (drives off Genome fields any
genome has):
- spline boundary fit (R11)
- analytic cup half-ellipsoid (R12)
- shoulder-strap full route (R13)
- underbust band (R14)
- gusset radius scaling + thong suppression (R15+R28)
- side-seam top-stitch overlay (R16)
- strap material classification (R17+R18)
- waist-tie suppression for one-pieces (R19)
- cup smoothstep blend (R21)
- boundary top-stitch overlay (R22)
- lining color hint at binding (R23)
- bar-tack reinforcements at junctions (R24)

**Still tailored to this NPC mesh** (numerical offsets):
- Shoulder ridge apex offset `(0.4 cm forward, 4 cm up)` in R13 — should
  be derived from local mesh curvature for true mesh-independence
- Gusset path mid-control (`+0.8 cm Y rise, 7 samples`) — works on this
  body but a heavier or differently-proportioned avatar would need
  re-tuning

These two are the **next-pass items** to remove the body-mesh dependency.

## What "is this clothing?" looks like now

After 36 total rounds (10 param + 1 bug fix + 6 first code pass +
20 here), the renders read as:

- **Has structural elements**: cup as molded dome, underbust support,
  shoulder straps with anchor points, gusset connecting front-back,
  bar-tack reinforcements at strap junctions
- **Has finish details**: smooth boundary curves (spline), top-stitched
  edges, side seam line, lining hint at binding
- **Material correctness**: fabric continuations show the fabric
  pattern, decorative trim shows the trim color (no longer all white)
- **Archetype-aware**: one-pieces don't get bikini ties; thong bottoms
  don't get visible gussets; halter styles get neck-strap routing,
  shoulder-strap styles get over-shoulder-to-back routing

Remaining gaps (not addressed; would be rounds 37+ if continued):
- Surface-conforming gusset (currently a parametric tube, doesn't trace
  body geometry between legs in the very low-coverage cases)
- True analytic shoulder ridge derivation (currently mesh-tuned offsets)
- Hem ribbing micro-pattern
- Inside lining as a separate fabric layer (currently just a color hint)

## Files

```
tools/output/iter_composite_floral/
  round_17_strap_class/      (R17+R18)
  round_19_strap_suppress/   (R19)
  round_20_gusset_surface/   (R20)
  round_23_topstitch_lining/ (R21-23)
  round_30_final/            (R24-30 final)
  trajectory_17_36.png       (key checkpoints stacked)
  headline_round_30.png      (round 16 vs round 30)
  REPORT_round_17_36.md      (this file)

tools/output/iter_composite_red/round_30_final/   (validation seed 1)
tools/output/iter_swimsuit_2/round_30_final/      (validation seed 2)
tools/output/cross_archetype_gallery_round_30.png (3-seed contact sheet)
```
