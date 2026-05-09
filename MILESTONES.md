# Milestones

Project milestones recorded in repo content (in addition to git tags
that are accepted by upstream — this file ensures the marker survives
even if local proxies reject tag pushes).

---

## milestone-1 — v2 cascaded latent stack with realistic bikini geometry

**Tag:** `milestone-1`
**Commit:** `2a817c4` (2026-05-09)
**Branch:** `claude/bikini-variation-algorithm-Dv5q5`

### State at this milestone

**Component Library v2** — 86+ hand-authored entries across 8 kinds:
`cup_piece` / `bottom_piece` / `strap_piece` / `hardware` / `accessory` /
`fabric` / `body_jewelry` / `seam_type`. Each entry has its own
`local_params_schema` describing variations that preserve real-world
identity (a Brazilian triangle never smoothly morphs into a balconette;
cross-category jumps require explicit `library_id` swaps).

**Outfit chromosome layer** — `archetype + slot_assignments +
global_design`. 4 archetypes (`triangle_string_halter` /
`bandeau_back_band` / `bralette_shoulder_strap` / `one_piece_maillot`),
each with a `SlotSpec` template the outfit fills. Slots can be required
or optional; `allowed_tags` and `excluded_tags` filter library entries.

**Outfit-level GA** — BLX-α crossover + tournament-3 + 2-elitism on
Outfits, not on the lossy 44-dim Genome. `outfit_evaluate` composite
(40% aesthetic / 25% manufacturing / 35% library-driven) drives
monotonic gains across all 4 archetypes.

**Modesty hyperparameters** — `bottom_coverage_strict` and
`cup_coverage_strict`, range 0..1 (0 = unconstrained, 1 = fullest
coverage tier the archetype's slot tags allow). Honored at sampling,
v1 → v2 migration, and GA mutation. `local_params` pinned to schema
extremes at `strict >= 0.66`.

**Optional `hip_strap` library element + O7 wearability rule** — Cup
floats off body without an anchor → `validate_outfit` catches it via
the new O7 rule. `hip_strap` is intentionally optional; C-style
bottoms held by polygon continuity remain valid.

**Renderer correctness fixes**:
- `bottom_piece` polygon `front_half_u` widened to actually cover the
  body's hip surface in cylindrical UV space (root cause of long-running
  "下身没衣服" complaints — polygons were falling in empty UV space)
- Fringe and gusset rendering bugs squashed
- Hardware (rings, sliders, buckles) gain `anatomy_hints` so they
  survive `deploy_to_body` accountability filtering

**Backward compatibility** — 37 v1 seeds at `assets/seeds/*.json`
migrate cleanly to `assets/seeds_v2/*.json` via `seed_to_outfit.py`.

**Pure-RNG generation works** — `random_outfit(archetype, rng)` with
no v1 seed prior produces coherent, validated, visually-recognizable
bikini outfits. Confirms the v2 library + slot template are
self-sufficient.

### Demo galleries

- `tools/output/2026-05-09/0104_v2_modest_series/` — strict=1+1, all
  16 outfits show real visible bottom panels (real triangle look,
  briefs/highwaist coverage)
- `tools/output/2026-05-08/1238_v2_tieside_series/` — 12 tie-side
  bikinis with visible side ribbons / cords / dangles
- `tools/output/2026-05-08/1135_v2_strict_both_max/` — strict=1+1
  baseline gallery
- `tools/output/2026-05-08/1021_v2_pure_random/` — 16 outfits from
  pure RNG, no seed prior

### Key documentation

- `docs/component-library-v2.md` — full architecture
- `docs/stage-report-2026-04-29.md` — earlier stage report

### Significant commits leading to this milestone

| commit | summary |
|---|---|
| `427b360` | v2 Phase A: library schema + 86 entries + polygon recipes |
| `9d180a6` | v2 Phase B: Outfit chromosome + GA operators |
| `2d0d1fe` | v2 Step 6: anatomy anchors + body_jewelry render |
| `da789cb` | v2 Step 7: capture.py outfit cascade + v1→v2 migration + docs |
| `72a7f3e` | v2 Step 8: outfit-native fitness + GA demo with monotonic gains |
| `8284018` | v2 audit fixes: 7 critical bugs + 4 medium + dead code cleanup |
| `cc22801` | cup_coverage_strict hyperparameter (mirrors bottom_coverage_strict) |
| `c853b22` | hip_strap as first-class library element + O7 wearability rule |
| `2a817c4` | bottom_piece front_half_u schema fix (the root-cause render bug) |
