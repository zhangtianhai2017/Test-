"""Validation tool for the option-D generator.

Takes a trained checkpoint, generates a set of variants from a brief
pool, renders + judges them, then writes a comparison report:
  - per-variant pass rate, symbolic fitness, J score
  - overview grid (one row per brief)
  - diversity audit across the generated batch

Used after `rl_runner.py` to inspect how the trained generator is
actually behaving.  Also accepts a random-init generator (no
--resume) so you can compare "trained" vs "baseline" outputs.

Usage:
    # validate a trained checkpoint:
    python3 tools/validate_generator.py \
        --resume tools/output/2026-05-18/1418_rl_run/generator_final.pt \
        --n-briefs 8 --judge mock

    # baseline (random init, no resume) for comparison:
    python3 tools/validate_generator.py --n-briefs 8 --judge mock
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch

import iter.capture as cap
cap.VIEWS = [v for v in cap.VIEWS if v.name == "01_front"]

from render3d_uv import load_body_mesh
from output_paths import dated_dir

from design_generator import DesignGenerator, MockTextEncoder
from vision_judge import make_judge
from symbolic_fitness import total_fitness as sym_fitness
from rl_runner import get_id_lists, RenderRunner


VALIDATION_BRIEFS = [
    "classic triangle bikini, vibrant red, beach holiday",
    "elegant bandeau, gold metallic shimmer, mediterranean",
    "sport racerback bralette, deep navy, full coverage",
    "boho macrame asymmetric halter, cream beige",
    "minimalist matte black one-piece, deep V neckline",
    "tropical floral balconette, vivid orange, cheeky bottom",
    "wetsuit neoprene, dark grey, modest cut",
    "sequin gold bandeau, evening party glam",
]


def validate(checkpoint: str | None,
              n_briefs: int = 8,
              judge_backend: str = "mock",
              hidden_dim: int = 256,
              text_dim: int = 384,
              seed: int = 42) -> dict:
    out_root = dated_dir("validate")
    print(f"OUT = {out_root}")
    print(f"checkpoint = {checkpoint or '(random init)'}")
    print(f"judge      = {judge_backend}")

    torch.manual_seed(seed)
    enc = MockTextEncoder(dim=text_dim)
    gen = DesignGenerator(text_dim=text_dim, hidden_dim=hidden_dim)
    gen.eval()

    if checkpoint and os.path.isfile(checkpoint):
        state = torch.load(checkpoint, map_location="cpu")
        if "generator_state" in state:
            gen.load_state_dict(state["generator_state"])
        elif "gen_state" in state:
            gen.load_state_dict(state["gen_state"])
        else:
            gen.load_state_dict(state)
        print(f"resumed from {checkpoint}")
    else:
        print("using random-init generator (baseline)")

    judge = make_judge(judge_backend)
    body  = load_body_mesh()
    id_lists = get_id_lists()
    render_runner = RenderRunner(out_root, id_lists, body)

    briefs = VALIDATION_BRIEFS[:n_briefs]
    print(f"\n=== generating {len(briefs)} variants ===")
    emb = enc.encode(briefs)
    with torch.no_grad():
        config = gen(emb)

    # Argmax sampling for inference (deterministic)
    picks = {}
    for name in gen.discrete_sizes:
        picks[name] = config[f"{name}_logits"].argmax(dim=-1).cpu()

    sym = sym_fitness(config)
    print(f"\nsymbolic fitness per brief:")
    for i, b in enumerate(briefs):
        print(f"  {sym['total'][i].item():.3f}  {b}")
    mean_sym = sym["total"].mean().item()

    # Render
    print(f"\n=== rendering ===")
    t0 = time.time()
    image_paths = render_runner(config, picks)
    print(f"  rendered {sum(1 for p in image_paths if p)}/{len(image_paths)} "
          f"in {time.time()-t0:.1f}s")

    # Judge
    print(f"\n=== {judge_backend} judge ===")
    valid_paths = [p for p in image_paths if p]
    results = judge.judge_batch(valid_paths, verbose=True) if valid_paths else []

    # Summary
    n_pass = sum(1 for r in results if r.is_valid_swimsuit)
    mean_v = (sum(r.validity_score for r in results) / len(results)
              if results else 0)
    mean_a = (sum(r.aesthetic_score for r in results) / len(results)
              if results else 0)
    print(f"\n=== summary ===")
    print(f"symbolic fitness mean : {mean_sym:.3f}")
    print(f"J pass rate           : {n_pass}/{len(results)}")
    print(f"J validity score mean : {mean_v:.2f} / 10")
    print(f"J aesthetic score mean: {mean_a:.2f} / 10")

    # Persist report
    report = {
        "checkpoint": checkpoint,
        "judge_backend": judge_backend,
        "briefs": briefs,
        "n_rendered": sum(1 for p in image_paths if p),
        "symbolic_fitness_mean": mean_sym,
        "symbolic_fitness_per_brief": sym["total"].tolist(),
        "j_pass_rate": n_pass / len(results) if results else 0.0,
        "j_validity_mean": mean_v,
        "j_aesthetic_mean": mean_a,
        "per_variant": [
            {
                "brief": briefs[i],
                "image_path": image_paths[i],
                "symbolic_fitness": float(sym["total"][i].item()),
                "judge": results[i].to_dict() if i < len(results) else None,
            }
            for i in range(len(briefs))
        ],
    }
    report_path = os.path.join(out_root, "validation_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nreport -> {report_path}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", default=None,
                    help="checkpoint .pt (omit for random-init baseline)")
    ap.add_argument("--n-briefs", type=int, default=8)
    ap.add_argument("--judge", choices=["mock", "vllm"], default="mock")
    ap.add_argument("--hidden-dim", type=int, default=256)
    args = ap.parse_args()
    validate(checkpoint=args.resume, n_briefs=args.n_briefs,
              judge_backend=args.judge, hidden_dim=args.hidden_dim)


if __name__ == "__main__":
    main()
