"""
Generate 20 outfit variations per iPad-Claude diverse seed.

Inputs : assets/seeds_v2/diverse_samples/*.json  (6 seeds)
Outputs: tools/output/<date>/<time>_seed_batch_20x6/
            <seed_name>/
              _source_seed.json
              00/outfit.json + 01_front.png + 04_back.png
              01/...
              ...
              19/...
              contact.png   (4x5 thumbnail grid, front views)
            summary.json
            INDEX.md

The iPad seeds use a sketch schema (library_ids like
``cup_piece.brazilian_triangle_small`` that do not exist in the
real component library).  We honour only the fields that map cleanly:

  - archetype          -> seeds random_outfit(archetype, ...)
  - global_design.primary_color hex   -> HSL on outfit
  - global_design.secondary_color hex -> secondary HSL
  - global_design.pattern             -> pattern_overlay enum (sanitised)
  - global_design.pattern_scale       -> pattern_scale
  - modesty                           -> library coverage thresholds
                                         (applied BEFORE random_outfit)

Per-seed RNG is derived from ``hash(seed.outfit_id)`` so reruns are
reproducible.
"""
from __future__ import annotations

import os, sys, json, glob, time, random, colorsys, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import iter.capture as cap
# Slim view set: front + back only, plenty for a batch overview.
cap.VIEWS = [v for v in cap.VIEWS if v.name in ("01_front", "04_back")]

from outfit import random_outfit, outfit_to_genome
from iter.params import IterParams
from render3d_uv import load_body_mesh
from output_paths import dated_dir
import library as lib

from PIL import Image, ImageDraw, ImageFont


SEED_DIR = os.path.join(ROOT, "assets", "seeds_v2", "diverse_samples")
N_PER_SEED = 20
GRID_COLS, GRID_ROWS = 5, 4   # 4x5 = 20 thumbnails

_PATTERN_ENUM = {"solid", "stripe", "polka", "floral", "gradient",
                 "color_block", "geometric"}


def hex_to_hsl(h: str | None) -> tuple[float, float, float] | None:
    if not h or not isinstance(h, str):
        return None
    h = h.strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        r, g, b = int(h[:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:], 16) / 255
    except ValueError:
        return None
    H, L, S = colorsys.rgb_to_hls(r, g, b)
    return H, S, L


def make_contact_sheet(seed_name: str, seed_dir: str,
                       n: int = N_PER_SEED) -> str | None:
    """Tile the 01_front.png from each variant into a single PNG."""
    cells = []
    for i in range(n):
        p = os.path.join(seed_dir, f"{i:02d}", "01_front.png")
        if os.path.isfile(p):
            cells.append((i, p))
    if not cells:
        return None
    sample = Image.open(cells[0][1])
    cw, ch = sample.size
    pad = 6
    label_h = 18
    W = GRID_COLS * cw + (GRID_COLS + 1) * pad
    H = GRID_ROWS * (ch + label_h) + (GRID_ROWS + 1) * pad
    sheet = Image.new("RGB", (W, H), (245, 245, 247))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    for k, (i, p) in enumerate(cells):
        col = k % GRID_COLS
        row = k // GRID_COLS
        x = pad + col * (cw + pad)
        y = pad + row * (ch + label_h + pad)
        img = Image.open(p).convert("RGB")
        sheet.paste(img, (x, y))
        draw.text((x + 4, y + ch + 2), f"{seed_name[:14]} #{i:02d}",
                  fill=(40, 40, 40), font=font)
    out = os.path.join(seed_dir, "contact.png")
    sheet.save(out)
    return out


def run() -> None:
    out_root = dated_dir("seed_batch_20x6")
    print(f"OUT = {out_root}")

    body = load_body_mesh()
    summary: list[dict] = []
    paths = sorted(glob.glob(os.path.join(SEED_DIR, "*.json")))
    if not paths:
        raise SystemExit(f"no seeds in {SEED_DIR}")

    t_total = time.time()
    for seed_path in paths:
        seed_name = os.path.basename(seed_path)[:-5]
        seed = json.load(open(seed_path))
        archetype = seed.get("archetype")
        if not archetype:
            print(f"[{seed_name}] skip (no archetype)")
            continue
        outfit_id = seed.get("outfit_id", seed_name)

        gd_src = seed.get("global_design", {}) or {}
        pri = hex_to_hsl(gd_src.get("primary_color"))
        sec = hex_to_hsl(gd_src.get("secondary_color"))
        pattern_raw = gd_src.get("pattern", "solid")
        pattern = pattern_raw if pattern_raw in _PATTERN_ENUM else "solid"
        pattern_scale = float(gd_src.get("pattern_scale", 0.5) or 0.5)

        modesty = seed.get("modesty", {}) or {}
        bcov = float(modesty.get("bottom_coverage_strict", 0.5))
        ccov = float(modesty.get("cup_coverage_strict", 0.5))
        lib.set_bottom_coverage_strict(bcov)
        lib.set_cup_coverage_strict(ccov)

        seed_dir = os.path.join(out_root, seed_name)
        os.makedirs(seed_dir, exist_ok=True)
        with open(os.path.join(seed_dir, "_source_seed.json"), "w") as f:
            json.dump(seed, f, indent=2)

        rng = random.Random(hash(outfit_id) & 0xFFFFFFFF)
        per_seed_t = time.time()
        variants: list[dict] = []
        n_ok = 0
        for i in range(N_PER_SEED):
            try:
                o = random_outfit(archetype, rng)
            except Exception as e:
                print(f"  [{seed_name}#{i:02d}] sample fail: {e}")
                continue
            if pri:
                o.global_design["hue"]        = pri[0]
                o.global_design["saturation"] = pri[1]
                o.global_design["lightness"]  = pri[2]
            if sec:
                o.global_design["secondary_hue"]        = sec[0]
                o.global_design["secondary_saturation"] = sec[1]
                o.global_design["secondary_lightness"]  = sec[2]
            o.global_design["pattern_overlay"] = pattern
            o.global_design["pattern_scale"]   = pattern_scale

            sub = os.path.join(seed_dir, f"{i:02d}")
            os.makedirs(sub, exist_ok=True)
            with open(os.path.join(sub, "outfit.json"), "w") as f:
                json.dump({
                    "archetype": o.archetype,
                    "slot_assignments": [
                        {"slot_name": a.slot_name, "library_id": a.library_id,
                         "local_params": dict(a.local_params)}
                        for a in o.slot_assignments
                    ],
                    "global_design": dict(o.global_design),
                    "source_seed": seed_name,
                    "variant_index": i,
                }, f, indent=2)

            p = IterParams()
            p.outfit = o
            p.bottom_coverage_strict = bcov
            p.cup_coverage_strict = ccov
            g = outfit_to_genome(o)
            try:
                cap.render_views(g, p, sub, body_mesh=body)
                n_ok += 1
            except Exception as e:
                print(f"  [{seed_name}#{i:02d}] render fail: {e}")
                traceback.print_exc()

            variants.append({
                "index": i,
                "slots": [(a.slot_name, a.library_id) for a in o.slot_assignments],
            })

        sheet = make_contact_sheet(seed_name, seed_dir)
        dt = time.time() - per_seed_t
        print(f"[{seed_name}] archetype={archetype}  "
              f"rendered {n_ok}/{N_PER_SEED}  "
              f"dt={dt:.1f}s  sheet={'yes' if sheet else 'no'}")

        summary.append({
            "seed": seed_name,
            "archetype": archetype,
            "modesty": {"bottom": bcov, "cup": ccov},
            "pattern": pattern,
            "primary_hsl": pri,
            "secondary_hsl": sec,
            "n_rendered": n_ok,
            "elapsed_s": round(dt, 1),
            "variants": variants,
        })

    with open(os.path.join(out_root, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    index_lines = [
        f"# Diverse-seed batch — 20 outfits × 6 seeds",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total elapsed: {time.time() - t_total:.1f}s",
        "",
        "## Per-seed",
        "",
        "| seed | archetype | rendered | contact sheet |",
        "|---|---|---|---|",
    ]
    for s in summary:
        index_lines.append(
            f"| `{s['seed']}` | {s['archetype']} | {s['n_rendered']}/{N_PER_SEED} | "
            f"[contact]({s['seed']}/contact.png) |")
    with open(os.path.join(out_root, "INDEX.md"), "w") as f:
        f.write("\n".join(index_lines) + "\n")

    print(f"\nDONE  out={out_root}  total={time.time()-t_total:.1f}s")


if __name__ == "__main__":
    run()
