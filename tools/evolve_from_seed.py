"""
Run a GA round seeded from a specific seed library entry.

Pipeline:
  1. Load the chosen seed → becomes Parent A.
  2. Parent B defaults to the existing synthetic Parent B in
     verify_ga_uv.make_parents(), giving a style contrast
     (e.g. brazilian halter + retro_missoni high-waist).
  3. Seed an initial population of POP individuals around both parents,
     evolve for GENS generations with tournament-3 + 2-elitism,
     fitness = overall from tools/fitness.py.
  4. Render the top-8 of the final generation next to the two parents
     and save a fitness trajectory plot.

Usage:
    python3 tools/evolve_from_seed.py swimsuit_2
    python3 tools/evolve_from_seed.py swimsuit_2 --gens 8 --pop 30
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import open3d as o3d

sys.path.insert(0, os.path.dirname(__file__))
from verify_ga_uv import (
    make_parents, crossover, mutate, genome_polygons,
)
from render3d_uv import (
    cylindrical_uvs, torso_anchors, genome_to_texture,
    load_body_mesh, make_renderer, render_mesh,
)
import fitness as fitness_mod
from seed_loader import load_seed, seed_to_genome


OUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def evolve(parent_a, parent_b, pop_size: int, gens: int,
           rng: random.Random):
    """Tournament-3 selection + 2-elitism, fitness = overall score."""
    pop = [parent_a, parent_b] + [
        mutate(crossover(parent_a, parent_b, rng), rng)
        for _ in range(pop_size - 2)
    ]
    mean_traj, max_traj, best_ever = [], [], None

    for gen in range(gens):
        scores = [fitness_mod.evaluate(g)["overall"] for g in pop]
        mean_traj.append(float(np.mean(scores)))
        max_traj.append(float(np.max(scores)))
        i_best = int(np.argmax(scores))
        best_ever = pop[i_best] if best_ever is None or \
            fitness_mod.evaluate(pop[i_best])["overall"] > fitness_mod.evaluate(best_ever)["overall"] \
            else best_ever

        def pick():
            contest = rng.sample(list(zip(pop, scores)), 3)
            return max(contest, key=lambda x: x[1])[0]

        ranked = sorted(zip(pop, scores), key=lambda x: x[1], reverse=True)
        next_pop = [g for g, _ in ranked[:2]]    # elitism
        while len(next_pop) < pop_size:
            a, b = pick(), pick()
            next_pop.append(mutate(crossover(a, b, rng), rng))
        pop = next_pop

    # Final generation
    scores = [fitness_mod.evaluate(g)["overall"] for g in pop]
    mean_traj.append(float(np.mean(scores)))
    max_traj.append(float(np.max(scores)))

    ranked = sorted(zip(pop, scores), key=lambda x: x[1], reverse=True)
    return ranked, mean_traj, max_traj


def render_evolution_grid(seed_name: str, parent_a, parent_b,
                          ranked, mean_traj, max_traj,
                          n_top: int = 8,
                          cell_w: int = 320, cell_h: int = 480,
                          label_b: str = "Parent B (synthetic)"
                          ) -> tuple[str, str]:
    """Save two PNGs: (a) the 2×5 grid parents+top-N, (b) fitness trajectory."""
    mesh = load_body_mesh()
    uvs = cylindrical_uvs(mesh)
    mesh.triangle_uvs = o3d.utility.Vector2dVector(uvs)
    yc, yn = torso_anchors(mesh)
    R = make_renderer(cell_w, cell_h)

    def _render(g):
        return render_mesh(R, mesh, genome_to_texture(g), g, yc, yn,
                           uvs, genome_polygons(g))

    cells = [("Parent A (seed)", parent_a),
             (label_b, parent_b)]
    for i, (g, s) in enumerate(ranked[:n_top]):
        cells.append((f"Top {i+1}  fit={s:.3f}", g))

    cols = 5
    rows = (len(cells) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.0, rows * 4.2),
                             facecolor="white")
    axes = np.array(axes).reshape(-1)
    for ax, (label, g) in zip(axes, cells):
        img = _render(g)
        fit = fitness_mod.evaluate(g)
        ax.imshow(img)
        ax.set_title(
            f"{label}\n{g.style_archetype}  pat={g.pattern}  "
            f"weave={g.fabric_weave}\n"
            f"P={fit['proportion']:.2f} H={fit['harmony']:.2f} "
            f"R={fit['rhythm']:.2f}  overall={fit['overall']:.2f}",
            fontsize=7,
        )
        ax.axis("off")
    for j in range(len(cells), len(axes)):
        axes[j].axis("off")
    fig.suptitle(
        f"GA evolution seeded from '{seed_name}' — "
        f"parents + top {n_top} after {len(mean_traj)-1} generations",
        fontsize=11, y=0.995,
    )
    fig.tight_layout()
    grid_path = os.path.join(OUT_DIR, f"evolve_{seed_name}_grid.png")
    fig.savefig(grid_path, dpi=140, bbox_inches="tight")
    plt.close(fig)

    # Trajectory
    fig, ax = plt.subplots(figsize=(7, 4), facecolor="white")
    ax.plot(mean_traj, marker="o", label="mean")
    ax.plot(max_traj, marker="s", label="max")
    ax.set_xlabel("generation")
    ax.set_ylabel("overall fitness (0..1)")
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_title(f"Fitness trajectory — seed '{seed_name}'")
    ax.set_ylim(min(min(mean_traj), min(max_traj)) - 0.05, 1.0)
    traj_path = os.path.join(OUT_DIR, f"evolve_{seed_name}_traj.png")
    fig.tight_layout()
    fig.savefig(traj_path, dpi=120)
    plt.close(fig)

    return grid_path, traj_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", help="seed name under assets/seeds/")
    ap.add_argument("--seed2", default=None,
                    help="optional second seed for the other parent. "
                         "Omit for single-seed evolution (both parents = seed).")
    ap.add_argument("--pop", type=int, default=30)
    ap.add_argument("--gens", type=int, default=8)
    ap.add_argument("--rng", type=int, default=42)
    args = ap.parse_args()

    seed = load_seed(args.seed)
    parent_a = seed_to_genome(seed)

    if args.seed2:
        parent_b = seed_to_genome(load_seed(args.seed2))
        label_b = f"Parent B (seed '{args.seed2}')"
    else:
        parent_b = parent_a
        label_b = f"Parent B (same seed — mutation-driven)"

    print(f"seeded from '{args.seed}': archetype={parent_a.style_archetype} "
          f"pattern={parent_a.pattern} hue={parent_a.hue:.2f}")
    print(f"{label_b}: archetype={parent_b.style_archetype} "
          f"pattern={parent_b.pattern} hue={parent_b.hue:.2f}")
    print(f"running GA: pop={args.pop}, gens={args.gens}")

    t0 = time.time()
    rng = random.Random(args.rng)
    ranked, mean_t, max_t = evolve(parent_a, parent_b,
                                    args.pop, args.gens, rng)
    print(f"evolved {args.gens} gens in {time.time() - t0:.1f}s")
    print(f"fitness mean: {mean_t[0]:.3f} -> {mean_t[-1]:.3f}")
    print(f"fitness max:  {max_t[0]:.3f} -> {max_t[-1]:.3f}")
    print(f"top individual: overall={ranked[0][1]:.3f}")

    t0 = time.time()
    tag = args.seed if not args.seed2 else f"{args.seed}_x_{args.seed2}"
    grid, traj = render_evolution_grid(
        tag, parent_a, parent_b, ranked, mean_t, max_t,
        label_b=label_b)
    print(f"rendered grid in {time.time() - t0:.1f}s")
    print(f"  {grid}")
    print(f"  {traj}")


if __name__ == "__main__":
    main()
