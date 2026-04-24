# run_2composite — GA round 2, larger populations

Everything in this folder is generated **from the single source image you uploaded**:

    assets/2-swimsuits-2row.png   (2 rows × 3 views)

The top row (red Brazilian halter) and the bottom row (white + green monstera
one-piece) are the two real swimwear references. Each became a hand-authored
44-field genome seed in `assets/seeds/`:

| Seed | Derived from | Archetype | Pattern |
|------|--------------|-----------|---------|
| `composite_red`    | top row of the composite    | brazilian      | solid  |
| `composite_floral` | bottom row of the composite | boho_cultgaia  | floral |

## GA settings (all three runs)

- population = 60
- generations = 12
- selection = tournament-3 + 2-elitism
- crossover = single-point discrete fields, BLX-α on continuous (α=0.25)
- mutation = gaussian σ=0.08 on continuous, p=0.08 discrete resample
- fitness  = `tools/fitness.py` overall (7 design principles averaged)

## Files in this folder

| File | What it is |
|------|-----------|
| `00_overview.png` | Source composite + all three grids stacked for at-a-glance review |
| `evolve_composite_red_grid.png` | **Run A** — parents + top-18 offspring, single-parent GA from `composite_red` |
| `evolve_composite_red_traj.png` | Run A fitness mean/max per generation |
| `evolve_composite_floral_grid.png` | **Run B** — parents + top-18 offspring, single-parent GA from `composite_floral` |
| `evolve_composite_floral_traj.png` | Run B fitness trajectory |
| `evolve_composite_red_x_composite_floral_grid.png` | **Run C** — parents + top-18 offspring, double-parent crossover of both seeds |
| `evolve_composite_red_x_composite_floral_traj.png` | Run C fitness trajectory |

Parent A of every grid is directly one of the two seeds above, i.e. the
algorithm is definitely seeded from the swimwear you gave us (not synthetic).
