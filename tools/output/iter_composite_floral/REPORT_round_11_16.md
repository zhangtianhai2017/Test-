# Rounds 11–16 — Code-level changes (not parameter tuning)

These six rounds modify **algorithm/code**, not just polish parameters,
to address the question: "Is this actually clothing? What's missing?"
The previous 10 rounds (in `REPORT.md`) had hit a parameter-only
plateau — the things still wrong were structural, not numerical.

## What each round changed (one code change per round)

| Round | File | Change | "Not-clothing" symptom it fixed |
|------|------|--------|--------------------------------|
| 11   | `garment_polish.py::project_boundary_to_polygons` | Replaced piecewise-linear polygon projection with **closed cubic B-spline fit** through 400 dense samples + Fourier low-pass on 3D loop (8 harmonics). | Stair-stepped jagged boundaries finally globally smooth, not just locally |
| 12   | `garment_polish.py::cup_dome_replace` (new) | Cup-region vertices **replaced** by a half-ellipsoid surface keyed to Genome `top_half_u/v/inner_u/center_v`, decoupled from breast topology | Cup mirroring breast curvature ("body-coupling") |
| 13   | `render3d_uv.py::build_strap_meshes` (shoulder block) | Shoulder strap routed via 4 control points: front cup top → shoulder ridge apex → mid-back → back-panel top, instead of a stub at the clavicle | Strap going nowhere — fabric had no visible anchor |
| 14   | `render3d_uv.py::build_strap_meshes` (new "underbust_band") | Continuous full-ring elastic ribbon at v = `top_center_v - top_half_v - 0.02` | No mechanical support structure under the cups |
| 15   | `render3d_uv.py::build_strap_meshes` (new "gusset") | Tube along front-to-back inseam path with mid-control dipped under the crotch; radius scales with smaller of `bot_front/back_half_u` | Front and back panels disconnected through legs |
| 16   | `tools/iter/capture.py` (texture overlay) | Bake darker vertical line at u=±0.5 in the albedo to suggest a coverstitched panel seam | No visible panel divisions — looked like a single decal |

## What's already generic vs. still composite_floral-specific

You flagged that these need to generalize across all archetypes
(brazilian / italian_luxe / hunzag_crinkle / etc.). Honest audit:

**Generic now** (drives off Genome fields any genome has):
- Round 11 spline boundary — works on any polygon shape
- Round 12 cup dome — keys to `top_half_u/v/inner_u/center_v`,
  same fields exist in every Genome
- Round 13 shoulder strap routing — gated on `top_shoulder_strap > 0.15`,
  which is a continuous Genome field; strap is skipped for halter-only
  styles
- Round 14 underbust band — gated by cup geometry; degenerates safely
  for bandeau (no cup separation)
- Round 16 side seam line — UV-space overlay, archetype-agnostic

**Still rough / partly tailored to this body mesh**:
- Round 13 shoulder ridge apex offset (4 cm up + 0.4 cm forward) is
  tuned to the NPC mesh's specific shoulder geometry. Real
  generalization: derive it from the mesh's local curvature maximum.
- Round 15 gusset is a straight tube + one dip control point. For
  thongs / Brazilian (where `bot_back_half_u` is small) it should
  shrink to near-invisible; for full-coverage it should widen to a
  real fabric strip. Currently the radius scaling exists but the
  shape doesn't trace the body surface — for v2 sample inseam path
  along body verts.

## Trajectory + Headline

- `trajectory_11_to_16.png` — six 8-view contact sheets stacked, one per round
- `headline_code_changes.png` — round 9 (pure parameter polish) vs round 16
  (after all 6 code changes)
- Per-round `views/`, `params_before.json`, `contact_sheet.png` in
  `round_11_spline/`, `round_12_cupdome/`, `round_13_strap/`,
  `round_14_underbust/`, `round_15_gusset/`, `round_16_seam/`

## Conclusion — does it look like clothing now?

Closer. The structural elements are present that were missing:
- Boundaries are mathematically smooth (round 11)
- Cup is a structured dome, not breast tracing (round 12)
- Straps actually connect to anchor points (round 13)
- Underbust gives mechanical support (round 14)
- Front and back are physically connected (round 15)
- Panel seams suggest construction (round 16)

What still reads as not-quite-clothing:
- Gusset doesn't follow body surface (sticks out)
- No top-stitching at boundary edges (only side seams)
- No hint of inside lining at neckline rim
- No reinforcement geometry at strap junctions (bar tacks / O-rings)

These are the v3 backlog. Each of them is another single code change,
not a parameter tweak.
