"""
Seed-library loader + renderer.

A "seed" is a hand-crafted or VLM-annotated Genome + provenance metadata,
stored as JSON under assets/seeds/*.json with the schema:

    {
      "meta": {
        "name":              str,
        "source_views":      {"front": path, "back": path, "left": path, ...},
        "analysis_notes":    str,
        "confidence":        {"shape": 0..1, "color": 0..1, ...},
        "tags":              [str, ...]            # optional
      },
      "genome": { ... 44 Genome fields ... }
    }

This module:
  - loads seed JSONs
  - applies _enforce_constraints (so older seeds stay valid)
  - renders them on the body mesh
  - builds a comparison grid vs. source view images

Usage:
    # list everything in the library
    python3 tools/seed_loader.py list

    # render one seed next to its source views
    python3 tools/seed_loader.py render swimsuit_2

    # render all seeds in a gallery PNG
    python3 tools/seed_loader.py gallery
"""

from __future__ import annotations

import glob
import json
import os
import sys

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import open3d as o3d

sys.path.insert(0, os.path.dirname(__file__))
from verify_ga_uv import Genome, _enforce_constraints, genome_polygons
from render3d_uv import (
    cylindrical_uvs, torso_anchors, genome_to_texture,
    load_body_mesh, make_renderer, render_mesh,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS_DIR = os.path.join(ROOT, "assets", "seeds")
OUT_DIR = os.path.join(ROOT, "tools", "output")


def load_seed(name_or_path: str) -> dict:
    """Load a seed by short name (looks in assets/seeds) or by path."""
    if os.path.isfile(name_or_path):
        path = name_or_path
    else:
        path = os.path.join(SEEDS_DIR, f"{name_or_path}.json")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"no seed '{name_or_path}' in {SEEDS_DIR}")
    with open(path) as f:
        return json.load(f)


def seed_to_genome(seed: dict) -> Genome:
    """Apply the same constraint pipeline to a seed so it stays valid as the
    Genome schema evolves — newer fields with missing values fall back to
    defaults via the constraint clamps."""
    return _enforce_constraints(Genome(**seed["genome"]).clipped())


def list_seeds() -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(SEEDS_DIR, "*.json"))):
        with open(path) as f:
            s = json.load(f)
        out.append({
            "name": s["meta"]["name"],
            "path": path,
            "tags": s["meta"].get("tags", []),
            "archetype": s["genome"].get("style_archetype", "?"),
            "pattern": s["genome"].get("pattern", "?"),
            "notes": s["meta"].get("analysis_notes", "")[:80],
        })
    return out


def _render_seed(R, mesh, uvs, yc, yn, genome: Genome) -> np.ndarray:
    return render_mesh(R, mesh, genome_to_texture(genome), genome,
                       yc, yn, uvs, genome_polygons(genome))


def render_seed_comparison(name: str, width: int = 500, height: int = 750) -> str:
    """Render a single seed and build a comparison PNG:
        [front view, back view, left view, our genome render]
    Returns the output path."""
    seed = load_seed(name)
    g = seed_to_genome(seed)

    mesh = load_body_mesh()
    uvs = cylindrical_uvs(mesh)
    mesh.triangle_uvs = o3d.utility.Vector2dVector(uvs)
    yc, yn = torso_anchors(mesh)
    R = make_renderer(width, height)
    our_img = _render_seed(R, mesh, uvs, yc, yn, g)

    # panels: one for each source view + our render
    views = seed["meta"].get("source_views", {})
    panel_paths = []
    for label in ("front", "back", "left", "right", "side"):
        if label in views:
            abs_path = os.path.join(ROOT, views[label])
            if os.path.isfile(abs_path):
                panel_paths.append((f"source: {label}", abs_path))

    n = len(panel_paths) + 1
    fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 5.0), facecolor="white")
    if n == 1:
        axes = [axes]
    for ax, (title, path) in zip(axes[:-1], panel_paths):
        ax.imshow(Image.open(path))
        ax.set_title(title, fontsize=9)
        ax.axis("off")
    axes[-1].imshow(our_img)
    axes[-1].set_title(f"our Genome render\n({g.style_archetype})", fontsize=9)
    axes[-1].axis("off")

    fig.suptitle(f"Seed '{name}' — source views vs. rendered Genome",
                 fontsize=11, y=0.995)
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, f"seed_compare_{name}.png")
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_gallery(width: int = 320, height: int = 480) -> str:
    """Render all seeds in a grid."""
    seeds = list_seeds()
    if not seeds:
        raise SystemExit("no seeds found under assets/seeds/*.json")
    mesh = load_body_mesh()
    uvs = cylindrical_uvs(mesh)
    mesh.triangle_uvs = o3d.utility.Vector2dVector(uvs)
    yc, yn = torso_anchors(mesh)
    R = make_renderer(width, height)

    imgs = []
    for s in seeds:
        with open(s["path"]) as f:
            seed = json.load(f)
        g = seed_to_genome(seed)
        img = _render_seed(R, mesh, uvs, yc, yn, g)
        imgs.append((s, g, img))

    cols = min(4, len(imgs))
    rows = (len(imgs) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.0, rows * 4.2),
                             facecolor="white")
    axes = np.array(axes).reshape(-1)
    for i, (meta, g, img) in enumerate(imgs):
        ax = axes[i]
        ax.imshow(img)
        ax.set_title(f"{meta['name']}\n{g.style_archetype}  pat={g.pattern}",
                     fontsize=8)
        ax.axis("off")
    for j in range(len(imgs), len(axes)):
        axes[j].axis("off")
    fig.suptitle("Seed library gallery", fontsize=11)
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, "seed_gallery.png")
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main():
    args = sys.argv[1:]
    if not args or args[0] == "list":
        for s in list_seeds():
            print(f"  {s['name']:25s}  archetype={s['archetype']:20s}  "
                  f"pattern={s['pattern']:10s}  — {s['notes']}")
        return
    if args[0] == "render":
        if len(args) < 2:
            raise SystemExit("usage: seed_loader.py render <seed_name>")
        print(render_seed_comparison(args[1]))
        return
    if args[0] == "gallery":
        print(render_gallery())
        return
    raise SystemExit(f"unknown command: {args[0]}")


if __name__ == "__main__":
    main()
