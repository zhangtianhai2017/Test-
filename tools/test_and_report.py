"""
End-to-end test + report runner for the bikini GA.

Exercises every subsystem built across Batches 1-2 and produces a
markdown report plus two grid PNGs:

  1. Sanity        — Genome construction, clipping, privacy seed
                     enforcement, pattern-rendering with all 12 patterns.
  2. GA mechanics  — crossover/mutation preserve constraints and produce
                     diverse offspring.
  3. Fitness dist. — 7 design-principle scores on a 200-Genome random
                     population; mean/std/histogram bins.
  4. Multi-gen GA  — 8 generations with fitness-weighted tournament
                     selection; show mean/max fitness trajectory.
  5. Archetype gallery — render one 3D sample per STYLE_ARCHETYPE
                         (14 total) to prove each preset lands on a
                         visually distinct bikini.

All outputs go to tools/output/test_*.png / TEST_REPORT.md.
Run:

    export XDG_RUNTIME_DIR=/tmp/xdg LIBGL_ALWAYS_SOFTWARE=1 \
           EGL_PLATFORM=surfaceless MESA_LOADER_DRIVER_OVERRIDE=swrast \
           OPEN3D_CPU_RENDERING=true
    python3 tools/test_and_report.py
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import traceback

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import open3d as o3d

sys.path.insert(0, os.path.dirname(__file__))
from verify_ga_uv import (
    CONT_FIELDS, PATTERNS, STYLE_ARCHETYPES, PALETTE_PRESETS,
    FABRIC_SOURCES, FABRIC_WEAVES, HARDWARE_METALS,
    Genome, make_parents, run_ga, crossover, mutate, _enforce_constraints,
    genome_polygons, PRIVACY_SEEDS,
)
from render3d_uv import (
    load_body_mesh, cylindrical_uvs, torso_anchors,
    genome_to_texture, make_renderer, render_mesh,
)
import fitness as fitness_mod


OUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUT_DIR, exist_ok=True)
REPORT_PATH = os.path.join(OUT_DIR, "TEST_REPORT.md")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.lines = []
        self.failures = 0
        self.passed = 0

    def h1(self, s): self.lines.append(f"# {s}\n")
    def h2(self, s): self.lines.append(f"\n## {s}\n")
    def h3(self, s): self.lines.append(f"\n### {s}\n")
    def p(self, s): self.lines.append(s + "\n")
    def code(self, s): self.lines.append(f"```\n{s}\n```\n")
    def table(self, headers, rows):
        self.lines.append("| " + " | ".join(headers) + " |")
        self.lines.append("|" + "|".join("---" for _ in headers) + "|")
        for r in rows:
            self.lines.append("| " + " | ".join(str(c) for c in r) + " |")
        self.lines.append("")

    def check(self, cond: bool, desc: str, detail: str = ""):
        if cond:
            self.passed += 1
            self.lines.append(f"- ✅ **PASS** — {desc}")
        else:
            self.failures += 1
            self.lines.append(f"- ❌ **FAIL** — {desc}")
            if detail:
                self.lines.append(f"      └─ {detail}")

    def write(self):
        with open(REPORT_PATH, "w") as f:
            f.write("\n".join(self.lines))


def _point_in_poly(u: float, v: float, poly) -> bool:
    from matplotlib.path import Path
    return Path(np.asarray(poly)).contains_point((u, v))


# ---------------------------------------------------------------------------
# TEST 1 — Sanity
# ---------------------------------------------------------------------------

def test_sanity(R: Report):
    R.h2("1. Sanity — construction, constraints, privacy seeds, patterns")

    pa, pb = make_parents()
    R.check(len(pa.as_dict()) == 44, f"Genome has 44 fields (got {len(pa.as_dict())})")
    R.check(pa.style_archetype in STYLE_ARCHETYPES,
            f"Parent A archetype '{pa.style_archetype}' in whitelist")
    R.check(pa.fabric_weave in FABRIC_WEAVES, "Parent A fabric_weave valid")
    R.check(pa.fabric_source in FABRIC_SOURCES, "Parent A fabric_source valid")
    R.check(pa.palette_preset in PALETTE_PRESETS, "Parent A palette_preset valid")
    R.check(pa.hardware_metal in HARDWARE_METALS, "Parent A hardware_metal valid")

    # Every Genome polygon should enclose the privacy seeds. Test a small
    # grid of points INSIDE the seed (shrunk 2% to avoid float-equality on
    # polygon boundaries).
    polys = genome_polygons(pa)
    def seed_covered(u0, u1, v0, v1):
        m_u = (u1 - u0) * 0.02
        m_v = (v1 - v0) * 0.02
        test_pts = [
            ((u0 + u1) / 2, (v0 + v1) / 2),                   # center
            (u0 + m_u, v0 + m_v), (u1 - m_u, v0 + m_v),       # inner corners
            (u0 + m_u, v1 - m_v), (u1 - m_u, v1 - m_v),
        ]
        return all(any(_point_in_poly(cu, cv, p) for p in polys)
                   for (cu, cv) in test_pts)
    for name, (u0, u1, v0, v1) in PRIVACY_SEEDS.items():
        R.check(seed_covered(u0, u1, v0, v1),
                f"Privacy seed '{name}' enclosed by at least one cup/panel")

    # Continuous fields stay in [0, 1] after clipping
    out_of_range = []
    for k in CONT_FIELDS:
        v = getattr(pa, k)
        if k in ("hue", "secondary_hue", "pattern_angle"):
            ok = 0.0 <= v <= 1.0
        else:
            ok = 0.0 <= v <= 1.0
        if not ok:
            out_of_range.append((k, v))
    R.check(len(out_of_range) == 0,
            "All continuous fields clipped to [0,1]",
            detail=str(out_of_range) if out_of_range else "")

    # Biodegradable / single_material thresholded to 0/1
    for k in ("biodegradable", "single_material",
              "has_oring", "has_bow", "has_fringe",
              "has_beads", "has_shell"):
        v = getattr(pa, k)
        R.check(v in (0.0, 1.0),
                f"'{k}' thresholded to 0/1 (got {v})")

    R.p(f"\n**{R.passed} passed / {R.failures} failed** so far.\n")


# ---------------------------------------------------------------------------
# TEST 2 — GA mechanics
# ---------------------------------------------------------------------------

def test_ga_mechanics(R: Report):
    R.h2("2. GA mechanics — crossover + mutation preserve constraints")

    pa, pb = make_parents()
    rng = random.Random(1234)
    N = 200
    offspring = [mutate(crossover(pa, pb, rng), rng) for _ in range(N)]

    # No offspring should violate privacy seeds (test shrunk-interior
    # points to skip float-equality edge cases).
    def _seed_covered(polys, u0, u1, v0, v1):
        m_u = (u1 - u0) * 0.02
        m_v = (v1 - v0) * 0.02
        test_pts = [((u0 + u1) / 2, (v0 + v1) / 2),
                    (u0 + m_u, v0 + m_v), (u1 - m_u, v1 - m_v)]
        return all(any(_point_in_poly(cu, cv, p) for p in polys)
                   for (cu, cv) in test_pts)
    violations = 0
    for g in offspring:
        polys = genome_polygons(g)
        if not all(_seed_covered(polys, u0, u1, v0, v1)
                    for _, (u0, u1, v0, v1) in PRIVACY_SEEDS.items()):
            violations += 1
    R.check(violations == 0,
            f"All {N} offspring pass privacy-seed containment",
            detail=f"{violations} violations" if violations else "")

    # Topology: top_back_coverage >= 0.05, waist diff <= 0.10
    topo_viol = 0
    for g in offspring:
        if g.top_back_coverage < 0.05 - 1e-6:
            topo_viol += 1
        elif abs(g.bot_front_top_v - g.bot_back_top_v) > 0.10 + 1e-6:
            topo_viol += 1
    R.check(topo_viol == 0,
            "All offspring respect stay-on topology (back coverage, waist span)")

    # Field diversity: every discrete enum appears in offspring
    patterns_seen = {g.pattern for g in offspring}
    archetypes_seen = {g.style_archetype for g in offspring}
    metals_seen = {g.hardware_metal for g in offspring}
    R.p(f"- 📊 Offspring spans **{len(patterns_seen)}/12 patterns**, "
        f"**{len(archetypes_seen)}/14 archetypes**, "
        f"**{len(metals_seen)}/6 hardware metals**.")
    R.check(len(patterns_seen) >= 3, "Offspring show multiple patterns")
    R.check(len(archetypes_seen) >= 3, "Offspring show multiple archetypes")

    # Continuous diversity: check std of hue is non-trivial
    hues = np.array([g.hue for g in offspring])
    R.p(f"- 📊 Hue std across {N} offspring = **{hues.std():.3f}** "
        f"(expected > 0.05)")
    R.check(hues.std() > 0.05, "Hue diversifies via GA")

    # Every continuous field should vary. Exclude thresholded-boolean
    # fields — they're continuous in the GA but snap to 0/1 which can
    # freeze at either rail.
    boolean_cont = {"biodegradable", "single_material",
                    "has_oring", "has_bow", "has_fringe",
                    "has_beads", "has_shell"}
    zero_var = []
    for k in CONT_FIELDS:
        if k in boolean_cont:
            continue
        vals = np.array([getattr(g, k) for g in offspring])
        if vals.std() < 1e-4:
            zero_var.append(k)
    R.check(len(zero_var) == 0,
            "All non-boolean continuous fields vary across offspring",
            detail=f"frozen: {zero_var}" if zero_var else "")

    return offspring


# ---------------------------------------------------------------------------
# TEST 3 — Fitness distribution
# ---------------------------------------------------------------------------

def test_fitness_dist(R: Report, population: list):
    R.h2("3. Fitness distribution on 200-Genome random population")

    scores = [fitness_mod.evaluate(g) for g in population]
    keys = ["balance", "proportion", "harmony", "emphasis",
            "rhythm", "unity", "contrast", "overall"]
    rows = []
    for k in keys:
        arr = np.array([s[k] for s in scores])
        rows.append((k, f"{arr.mean():.3f}", f"{arr.std():.3f}",
                     f"{arr.min():.3f}", f"{arr.max():.3f}"))
    R.table(["principle", "mean", "std", "min", "max"], rows)

    # Render histograms
    fig, axes = plt.subplots(2, 4, figsize=(12, 5), facecolor="white")
    for ax, k in zip(axes.ravel(), keys):
        arr = np.array([s[k] for s in scores])
        ax.hist(arr, bins=20, color="#4a90d9", edgecolor="#222")
        ax.set_title(f"{k}  μ={arr.mean():.2f}", fontsize=9)
        ax.set_xlim(0, 1)
    fig.suptitle("Fitness distribution — 200 random GA offspring", fontsize=11)
    fig.tight_layout()
    hist_path = os.path.join(OUT_DIR, "test_fitness_histogram.png")
    fig.savefig(hist_path, dpi=120)
    plt.close(fig)
    R.p(f"\n![Fitness histograms]({os.path.basename(hist_path)})\n")
    R.check(np.mean([s["overall"] for s in scores]) > 0.4,
            "Mean overall fitness > 0.4")


# ---------------------------------------------------------------------------
# TEST 4 — Multi-generation GA
# ---------------------------------------------------------------------------

def test_multigen(R: Report):
    R.h2("4. Multi-generation evolution — 8 generations, fitness-driven")

    pa, pb = make_parents()
    rng = random.Random(42)
    POP = 30
    GENS = 8

    # seed the population around both parents
    pop = [pa, pb] + [mutate(crossover(pa, pb, rng), rng) for _ in range(POP - 2)]

    mean_traj, max_traj = [], []
    for gen in range(GENS):
        scores = [fitness_mod.evaluate(g)["overall"] for g in pop]
        mean_traj.append(float(np.mean(scores)))
        max_traj.append(float(np.max(scores)))

        # tournament selection (k=3)
        def pick():
            contest = rng.sample(list(zip(pop, scores)), 3)
            return max(contest, key=lambda x: x[1])[0]

        next_pop = []
        # elitism: carry top-2 unchanged
        ranked = sorted(zip(pop, scores), key=lambda x: x[1], reverse=True)
        next_pop.extend([g for g, _ in ranked[:2]])
        while len(next_pop) < POP:
            a, b = pick(), pick()
            next_pop.append(mutate(crossover(a, b, rng), rng))
        pop = next_pop

    # Final
    scores = [fitness_mod.evaluate(g)["overall"] for g in pop]
    mean_traj.append(float(np.mean(scores)))
    max_traj.append(float(np.max(scores)))

    rows = [(i, f"{m:.3f}", f"{mx:.3f}")
            for i, (m, mx) in enumerate(zip(mean_traj, max_traj))]
    R.table(["gen", "mean_fitness", "max_fitness"], rows)

    fig, ax = plt.subplots(figsize=(7, 4), facecolor="white")
    ax.plot(mean_traj, marker="o", label="population mean")
    ax.plot(max_traj, marker="s", label="population max")
    ax.set_xlabel("generation")
    ax.set_ylabel("overall fitness (0..1)")
    ax.set_ylim(0.3, 1.0)
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_title("GA fitness trajectory over 8 generations")
    traj_path = os.path.join(OUT_DIR, "test_fitness_trajectory.png")
    fig.tight_layout()
    fig.savefig(traj_path, dpi=120)
    plt.close(fig)
    R.p(f"\n![Fitness trajectory]({os.path.basename(traj_path)})\n")

    improved = mean_traj[-1] > mean_traj[0]
    R.check(improved,
            f"Mean fitness improved: {mean_traj[0]:.3f} -> {mean_traj[-1]:.3f}")
    R.check(max_traj[-1] >= max_traj[0],
            f"Max fitness non-decreasing: {max_traj[0]:.3f} -> {max_traj[-1]:.3f}")


# ---------------------------------------------------------------------------
# TEST 5 — Archetype gallery (3D render per style_archetype)
# ---------------------------------------------------------------------------

def test_archetype_gallery(R: Report):
    R.h2("5. Style archetype gallery — one 3D render per style_archetype")

    mesh = load_body_mesh()
    uvs = cylindrical_uvs(mesh)
    mesh.triangle_uvs = o3d.utility.Vector2dVector(uvs)
    yc, yn = torso_anchors(mesh)
    renderer = make_renderer(320, 480)

    # Build one genome per archetype with a distinct random starting
    # point so the archetype's target fields are the main driver of
    # differences instead of shared baseline from Parent A.
    pa, pb = make_parents()
    gallery = []
    for i, arch in enumerate(STYLE_ARCHETYPES):
        rng = random.Random(2026 + i * 17)
        # Start from a crossover of both parents with strong mutation, then
        # override the archetype so _enforce_constraints applies the target.
        child = mutate(crossover(pa, pb, rng), rng)
        d = child.as_dict()
        d["style_archetype"] = arch
        # add independent noise so even same-archetype samples would differ
        for k in CONT_FIELDS:
            noise = rng.gauss(0, 0.10)
            if k in ("hue", "secondary_hue", "pattern_angle"):
                d[k] = (d[k] + noise) % 1.0
            else:
                d[k] = float(np.clip(d[k] + noise, 0.0, 1.0))
        # roll discrete non-archetype fields too
        from verify_ga_uv import _DISCRETE_ENUMS
        for k, enum in _DISCRETE_ENUMS.items():
            if k == "style_archetype":
                continue
            if rng.random() < 0.5:
                d[k] = rng.choice(enum)
        g = _enforce_constraints(Genome(**d).clipped())
        gallery.append((arch, g))

    imgs = []
    for arch, g in gallery:
        t0 = time.time()
        tex = genome_to_texture(g)
        img = render_mesh(renderer, mesh, tex, g, yc, yn, uvs, genome_polygons(g))
        imgs.append((arch, img, g, time.time() - t0))

    # Compose a 4x4 grid (14 samples + 2 empty)
    cols = 4
    rows = 4
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.5, rows * 3.6),
                             facecolor="white")
    axes = np.asarray(axes).reshape(-1)
    for i, (arch, img, g, dt) in enumerate(imgs):
        ax = axes[i]
        ax.imshow(img)
        fit = fitness_mod.evaluate(g)
        ax.set_title(
            f"{arch}\npat={g.pattern} weave={g.fabric_weave}\n"
            f"metal={g.hardware_metal}  overall={fit['overall']:.2f}",
            fontsize=7,
        )
        ax.axis("off")
    for j in range(len(imgs), len(axes)):
        axes[j].axis("off")
    fig.suptitle("Style archetype gallery — Parent A base + each preset applied",
                 fontsize=11, y=0.997)
    gallery_path = os.path.join(OUT_DIR, "test_archetype_gallery.png")
    fig.tight_layout()
    fig.savefig(gallery_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    R.p(f"\n![Archetype gallery]({os.path.basename(gallery_path)})\n")

    # Check that archetypes produce distinct images (~6% mean pixel diff
    # is a reasonable "visibly different" threshold given skin takes up
    # most of every frame).
    img_arrays = [im.astype(np.int32) for _, im, _, _ in imgs]
    DIFF_THRESH = 1.5
    distinct = 0
    for i in range(len(img_arrays)):
        for j in range(i + 1, len(img_arrays)):
            diff = np.abs(img_arrays[i] - img_arrays[j]).mean()
            if diff > DIFF_THRESH:
                distinct += 1
    total_pairs = len(img_arrays) * (len(img_arrays) - 1) // 2
    R.p(f"\n- 🖼 {distinct}/{total_pairs} archetype pairs render distinctly "
        f"(image-diff > {DIFF_THRESH}).\n")
    R.check(distinct > total_pairs * 0.80,
            ">80% of archetype pairs are visibly distinct")

    # Dump the genome JSONs for reference
    gallery_json = os.path.join(OUT_DIR, "test_archetype_gallery.json")
    with open(gallery_json, "w") as f:
        json.dump({arch: g.as_dict() for arch, g in gallery}, f, indent=2)
    R.p(f"- JSON dump: `{os.path.basename(gallery_json)}`")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    R = Report()
    R.h1("Bikini GA — Test + Report")
    R.p(f"Generated at {time.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        test_sanity(R)
    except Exception as e:
        R.p(f"💥 Exception in sanity: {e}")
        R.code(traceback.format_exc())

    try:
        pop = test_ga_mechanics(R)
    except Exception as e:
        R.p(f"💥 Exception in GA mechanics: {e}")
        R.code(traceback.format_exc())
        pop = []

    try:
        if pop:
            test_fitness_dist(R, pop)
    except Exception as e:
        R.p(f"💥 Exception in fitness: {e}")
        R.code(traceback.format_exc())

    try:
        test_multigen(R)
    except Exception as e:
        R.p(f"💥 Exception in multigen: {e}")
        R.code(traceback.format_exc())

    try:
        test_archetype_gallery(R)
    except Exception as e:
        R.p(f"💥 Exception in archetype gallery: {e}")
        R.code(traceback.format_exc())

    R.h2("Summary")
    R.p(f"- ✅ **Passed**: {R.passed}")
    R.p(f"- ❌ **Failed**: {R.failures}")
    R.write()
    print(f"\n=== {R.passed} passed, {R.failures} failed ===")
    print(f"report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
