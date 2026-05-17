"""Render one bikini per weave family so the new fabric library can be
inspected side-by-side.  Picks a representative fabric per weave from
library_data.FABRICS, forces it onto a triangle_string_halter outfit's
primary_fabric slot, renders front view, tiles the lot into a grid.
"""
from __future__ import annotations

import os, sys, time, random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import iter.capture as cap
cap.VIEWS = [v for v in cap.VIEWS if v.name == "01_front"]

from PIL import Image, ImageDraw, ImageFont
from outfit import random_outfit, SlotAssignment, outfit_to_genome
from iter.params import IterParams
from render3d_uv import load_body_mesh
from output_paths import dated_dir
import library as lib
import library_data as ld


# Pick one representative fabric per weave family.  Prefer the entry
# whose tags include the weave name (so e.g. mesh -> F_MESH_OUTER not
# F_POWERMESH_LINING).
def pick_one_per_weave() -> dict[str, str]:
    out: dict[str, str] = {}
    for fab_id, e in ld.FABRICS.items():
        w = e.weave
        if w in out:
            existing = ld.FABRICS[out[w]]
            # prefer the entry whose tags mention the weave name
            if w in e.tags and w not in existing.tags:
                out[w] = fab_id
            continue
        out[w] = fab_id
    return out


def run() -> None:
    out_root = dated_dir("fabric_weave_showcase")
    print(f"OUT = {out_root}")
    body = load_body_mesh()
    lib.set_bottom_coverage_strict(0.6)
    lib.set_cup_coverage_strict(0.6)

    weave_to_fab = pick_one_per_weave()
    weave_order = sorted(weave_to_fab.keys())
    print(f"weaves: {weave_order}")

    samples = []
    for weave in weave_order:
        fab_id = weave_to_fab[weave]
        # Sample a fresh outfit per weave so non-fabric slots vary
        # naturally; use the weave name as RNG seed for reproducibility.
        rng = random.Random(hash(("weave_showcase", weave)) & 0xFFFFFFFF)
        o = random_outfit("triangle_string_halter", rng)
        # Force the primary_fabric slot
        for sa in o.slot_assignments:
            if sa.slot_name == "primary_fabric":
                sa.library_id = fab_id
                sa.local_params = {}
                break
        # Constant neutral colour so the weave does the talking
        o.global_design["hue"] = 0.05
        o.global_design["saturation"] = 0.10
        o.global_design["lightness"] = 0.55
        o.global_design["pattern_overlay"] = "solid"

        sub = os.path.join(out_root, weave)
        os.makedirs(sub, exist_ok=True)
        p = IterParams(); p.outfit = o
        g = outfit_to_genome(o)
        t0 = time.time()
        try:
            cap.render_views(g, p, sub, body_mesh=body)
            print(f"  {weave:12s} {fab_id:30s}  {time.time()-t0:.1f}s")
        except Exception as exc:
            print(f"  {weave:12s} FAIL: {exc}")
            continue
        samples.append((weave, fab_id, os.path.join(sub, "01_front.png")))

    # Tile into a 4x4 grid with labels
    if not samples:
        return
    sample = Image.open(samples[0][2])
    cw, ch = sample.size
    cols = 4
    rows = (len(samples) + cols - 1) // cols
    label_h = 32
    pad = 8
    W = cols * (cw + pad) + pad
    H = rows * (ch + label_h + pad) + pad
    canvas = Image.new("RGB", (W, H), (245, 245, 247))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        font_s = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except Exception:
        font = font_s = ImageFont.load_default()
    for idx, (weave, fab_id, png) in enumerate(samples):
        col = idx % cols
        row = idx // cols
        x = pad + col * (cw + pad)
        y = pad + row * (ch + label_h + pad)
        img = Image.open(png).convert("RGB")
        canvas.paste(img, (x, y))
        draw.text((x + 6, y + ch + 4),  weave, fill=(20, 20, 30),  font=font)
        draw.text((x + 6, y + ch + 20), fab_id, fill=(110, 110, 120), font=font_s)

    out_grid = os.path.join(out_root, "fabric_showcase.png")
    canvas.save(out_grid, optimize=True)
    print(f"\ngrid -> {out_grid}  ({os.path.getsize(out_grid)//1024} KiB)")


if __name__ == "__main__":
    run()
