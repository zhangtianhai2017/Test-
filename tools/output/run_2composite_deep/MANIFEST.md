# run_2composite_deep — GA round 3, deeper evolution

Same source and same two seeds as `run_2composite/`, just **evolved further**.

Source image (single file you uploaded):

    assets/2-swimsuits-2row.png   (2 rows x 3 views)

Two seeds derived from it:

| Seed | From | Archetype | Pattern |
|------|------|-----------|---------|
| `composite_red`    | top row    | brazilian      | solid  |
| `composite_floral` | bottom row | boho_cultgaia  | floral |

## GA settings

- population = 60
- generations = **30**  (was 12 in `run_2composite/`, 8 in the original run)
- selection / crossover / mutation = same as before
- rng seed = 42 (so the first 12 gens reproduce the previous run)

## Final fitness after 30 generations

| Run | Pairing | gen 0 max | **gen 30 max** | gen 0 mean | gen 30 mean |
|-----|---------|-----------|----------------|------------|-------------|
| A | single-parent `composite_red`    | 0.853 | **0.983** | 0.717 | 0.878 |
| B | single-parent `composite_floral` | 0.960 | **0.985** | 0.799 | 0.900 |
| C | double-parent `red x floral`     | 0.918 | **0.981** | 0.803 | 0.871 |

The max-fitness curve is roughly flat after generation 15 — the population has
converged to its local optimum. What you see in this round is more refined
versions of the same families that were emerging in the 12-gen run.

## Files

| File | What it is |
|------|-----------|
| `00_overview.png` | Source composite + the three grids stacked |
| `evolve_composite_red_grid.png` | Run A — parents + top-18 after 30 gens |
| `evolve_composite_red_traj.png` | Run A fitness trajectory across all 30 gens |
| `evolve_composite_floral_grid.png` | Run B — parents + top-18 after 30 gens |
| `evolve_composite_floral_traj.png` | Run B fitness trajectory |
| `evolve_composite_red_x_composite_floral_grid.png` | Run C — parents + top-18 |
| `evolve_composite_red_x_composite_floral_traj.png` | Run C fitness trajectory |

Every offspring still descends from the two real swimwear references in
`assets/2-swimsuits-2row.png` — Parent A in the grids is one of those seeds
unchanged.
