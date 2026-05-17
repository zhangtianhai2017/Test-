"""Render the 120 outfits produced by the winning self-iterate strategy.

Reads tools/output/_diversity_winner_outfits.json (list of outfit dicts
in the v2 schema), reconstructs Outfit objects, renders front + back,
groups by archetype into 8 contact-sheet "seeds" so the existing
overview / HTML index tools recognise the layout.
"""
from __future__ import annotations

import os, sys, json, time, random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import iter.capture as cap
cap.VIEWS = [v for v in cap.VIEWS if v.name in ("01_front", "04_back")]

from outfit import Outfit, SlotAssignment, outfit_to_genome
from iter.params import IterParams
from render3d_uv import load_body_mesh
from output_paths import dated_dir
import library as lib
import batch_from_diverse_seeds as B


def run() -> None:
    src = os.path.join(ROOT, "tools", "output", "_diversity_winner_outfits.json")
    outfits = json.load(open(src))
    out_root = dated_dir("diverse_winner_full_stack")
    print(f"OUT = {out_root}")
    body = load_body_mesh()

    # Group into "cells" of 15 by archetype + a counter so the contact
    # sheet / overview reads.  Cells named v2_<idx>_<archetype>_<branch>.
    by_arch: dict[str, list] = {}
    for o in outfits:
        by_arch.setdefault(o["archetype"], []).append(o)

    cells: list[tuple[str, list]] = []
    cell_idx = 0
    for arch, lst in by_arch.items():
        per_cell = 15
        for i in range(0, len(lst), per_cell):
            sid = f"v2_{cell_idx:02d}_{arch}_w{i // per_cell}"
            cells.append((sid, lst[i:i + per_cell]))
            cell_idx += 1

    lib.set_bottom_coverage_strict(0.95)
    lib.set_cup_coverage_strict(0.95)

    summary = []
    t_total = time.time()
    for sid, lst in cells:
        seed_dir = os.path.join(out_root, sid)
        os.makedirs(seed_dir, exist_ok=True)
        n_ok = 0
        t0 = time.time()
        for i, od in enumerate(lst):
            sub = os.path.join(seed_dir, f"{i:02d}")
            os.makedirs(sub, exist_ok=True)
            # Persist outfit.json
            with open(os.path.join(sub, "outfit.json"), "w") as f:
                json.dump({**od, "source_seed": sid, "variant_index": i,
                            "modesty": {"bottom_coverage_strict": 0.95,
                                        "cup_coverage_strict": 0.95}}, f, indent=2)
            # Reconstruct Outfit
            o = Outfit(archetype=od["archetype"],
                       slot_assignments=[SlotAssignment(**a) for a in od["slot_assignments"]],
                       global_design=dict(od["global_design"]))
            g = outfit_to_genome(o)
            p = IterParams(); p.outfit = o
            p.bottom_coverage_strict = 0.95
            p.cup_coverage_strict = 0.95
            try:
                cap.render_views(g, p, sub, body_mesh=body)
                n_ok += 1
            except Exception as exc:
                print(f"  [{sid}#{i:02d}] render fail: {exc}")
        B.make_contact_sheet(sid, seed_dir, n=len(lst))
        dt = time.time() - t0
        print(f"[{sid}]  {n_ok}/{len(lst)}  dt={dt:.1f}s")
        summary.append({"seed": sid, "n_rendered": n_ok, "elapsed_s": round(dt, 1)})

    with open(os.path.join(out_root, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"DONE  out={out_root}  total={time.time()-t_total:.1f}s")


if __name__ == "__main__":
    run()
