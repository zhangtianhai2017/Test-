"""v2 outfit_ga demo with new outfit_evaluate fitness.

Runs evolve() per archetype, renders top-3 winners through the v2 pipeline,
writes report.md + overview.png. Uses fixed seeds so results reproducible.
"""
import os, sys, json, random, time
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, "tools")

from output_paths import dated_dir
from outfit import random_outfit
from iter.outfit_ga import evolve
from iter.params import IterParams
from iter.capture import render_views
from outfit_fitness import outfit_evaluate, OUTFIT_SCORE_KEYS
from outfit import outfit_to_genome
from render3d_uv import load_body_mesh
import fitness as fitness_mod

OUT = dated_dir("v2_ga_demo")
print(f"OUT = {OUT}")
os.makedirs(os.path.join(OUT, "renders"), exist_ok=True)

ARCHETYPES = [
    "triangle_string_halter",
    "bandeau_back_band",
    "bralette_shoulder_strap",
    "one_piece_maillot",
]

POP_SIZE = 20
GENS = 12
TOP_K = 3

body = load_body_mesh()
all_results = []
trajectories = {}

for arch in ARCHETYPES:
    rng = random.Random(hash(arch) & 0xFFFF)
    pa = random_outfit(arch, rng)
    pb = random_outfit(arch, rng)
    print(f"\n[{arch}] evolve pop={POP_SIZE} gens={GENS}")
    t0 = time.time()
    ranked, mean_t, max_t = evolve(pa, pb, pop_size=POP_SIZE, gens=GENS,
                                    rng=rng, use_outfit_fitness=True)
    dt = time.time() - t0
    trajectories[arch] = {"mean": mean_t, "max": max_t}
    print(f"  done in {dt:.1f}s  mean {mean_t[0]:.3f}->{mean_t[-1]:.3f}  "
          f"max {max_t[0]:.3f}->{max_t[-1]:.3f}")

    for rank, (o, fit) in enumerate(ranked[:TOP_K]):
        name = f"{arch}__top{rank+1}"
        out_dir = os.path.join(OUT, "renders", name)
        params = IterParams()
        params.outfit = o
        # Render
        g = outfit_to_genome(o)
        t1 = time.time()
        render_views(g, params, out_dir, body_mesh=body)
        dt_r = time.time() - t1
        # Score breakdown
        v1 = fitness_mod.evaluate(g)
        all_results.append({
            "name": name,
            "archetype": arch,
            "rank": rank + 1,
            "overall": round(fit["overall"], 3),
            "overall_outfit": round(fit["overall_outfit"], 3),
            "overall_v1": round(fit["overall_v1"], 3),
            "v1_with_garment": round(v1["overall_with_garment"], 3),
            "axes": {k: round(fit[k], 3) for k in OUTFIT_SCORE_KEYS},
            "slots": [(sa.slot_name, sa.library_id) for sa in o.slot_assignments],
        })
        print(f"  [{name}] composite={fit['overall']:.3f}  "
              f"outfit={fit['overall_outfit']:.3f}  v1={fit['overall_v1']:.3f}  "
              f"render={dt_r:.1f}s")

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
lines = []
lines.append("# v2 outfit_ga demo — outfit-native fitness")
lines.append("")
lines.append("Per archetype, ran `outfit_ga.evolve(pop=20, gens=12)` with the new "
             "`outfit_evaluate` composite (40% aesthetic + 25% manufacturing + "
             "35% outfit-native). Top-3 outfits rendered.")
lines.append("")
lines.append("## Trajectories (mean / max composite per generation)")
lines.append("")
lines.append("| archetype | mean start | mean end | max start | max end | Δ max |")
lines.append("|---|---|---|---|---|---|")
for arch, t in trajectories.items():
    dmax = t["max"][-1] - t["max"][0]
    lines.append(f"| {arch} | {t['mean'][0]:.3f} | {t['mean'][-1]:.3f} | "
                 f"{t['max'][0]:.3f} | {t['max'][-1]:.3f} | {dmax:+.3f} |")
lines.append("")
lines.append("## Top-3 per archetype")
lines.append("")
lines.append("| outfit | composite | outfit | v1 | v1+garment | slot picks |")
lines.append("|---|---|---|---|---|---|")
for r in all_results:
    slots_short = " · ".join(f"{n}={lid}" for n, lid in r["slots"][:5])
    if len(r["slots"]) > 5:
        slots_short += f" · …+{len(r['slots']) - 5}"
    lines.append(f"| `{r['name']}` | {r['overall']:.3f} | "
                 f"{r['overall_outfit']:.3f} | {r['overall_v1']:.3f} | "
                 f"{r['v1_with_garment']:.3f} | {slots_short} |")
lines.append("")
lines.append("## Outfit-native axis breakdown")
lines.append("")
header = "| outfit | " + " | ".join(OUTFIT_SCORE_KEYS) + " |"
sep = "|---|" + "---|" * len(OUTFIT_SCORE_KEYS)
lines.append(header)
lines.append(sep)
for r in all_results:
    row = f"| `{r['name']}` | " + " | ".join(
        f"{r['axes'][k]:.2f}" for k in OUTFIT_SCORE_KEYS) + " |"
    lines.append(row)

with open(os.path.join(OUT, "report.md"), "w") as f:
    f.write("\n".join(lines) + "\n")
with open(os.path.join(OUT, "results.json"), "w") as f:
    json.dump({"trajectories": trajectories, "results": all_results}, f, indent=2)
print(f"\nreport: {OUT}/report.md")

# ---------------------------------------------------------------------------
# Overview contact sheet
# ---------------------------------------------------------------------------
from PIL import Image, ImageDraw, ImageFont
TW, TH = 220, 330
gap = 8
hdr = 80
cols = TOP_K
rows = len(ARCHETYPES)
sw = cols * TW + (cols + 1) * gap
sh = hdr + rows * (TH + 36 + gap) + gap
sheet = Image.new("RGB", (sw, sh), (16, 16, 22))
draw = ImageDraw.Draw(sheet)
try:
    fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
except Exception:
    fb = fs = ImageFont.load_default()
draw.text((20, 18), "v2 outfit_ga demo — top-3 winners per archetype",
          fill=(255, 220, 120), font=fb)
draw.text((20, 44), "outfit_evaluate composite = 0.40 aesthetic + 0.25 manuf + 0.35 outfit-native",
          fill=(180, 200, 220), font=fs)
color_for = {
    "triangle_string_halter":  (240, 140, 180),
    "bandeau_back_band":       (130, 180, 240),
    "bralette_shoulder_strap": (180, 220, 140),
    "one_piece_maillot":       (240, 200, 140),
}
for ri, arch in enumerate(ARCHETYPES):
    archs = [r for r in all_results if r["archetype"] == arch]
    for ci, r in enumerate(archs[:cols]):
        x0 = gap + ci * (TW + gap)
        y0 = hdr + ri * (TH + 36 + gap)
        col = color_for.get(arch, (180, 180, 180))
        draw.rectangle([(x0, y0), (x0 + TW, y0 + 32)],
                        fill=tuple(v // 4 for v in col))
        draw.text((x0 + 4, y0 + 2), f"{arch[:24]}", fill=col, font=fs)
        draw.text((x0 + 4, y0 + 14),
                  f"top{r['rank']} composite={r['overall']:.2f}  "
                  f"o={r['overall_outfit']:.2f}  v1={r['overall_v1']:.2f}",
                  fill=(220, 220, 220), font=fs)
        fp = os.path.join(OUT, "renders", r["name"], "01_front.png")
        if os.path.exists(fp):
            im = Image.open(fp).resize((TW, TH))
            sheet.paste(im, (x0, y0 + 34))
sheet.save(os.path.join(OUT, "overview.png"))
print(f"overview: {OUT}/overview.png")
