"""Profile one outfit through render_views and report time per stage."""
import os, sys, time
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, "tools")

import numpy as np, open3d as o3d, random
from outfit import random_outfit, outfit_to_genome
from iter.params import IterParams
from render3d_uv import (load_body_mesh, cylindrical_uvs, torso_anchors,
                          genome_to_texture, make_renderer, render_mesh,
                          build_fabric_shell, build_binding_mesh,
                          build_strap_meshes, apply_wrinkles)
from garment_polish import polish_shell
from verify_ga_uv import genome_polygons
import library as lib

# warm-up
body = load_body_mesh()
lib.set_bottom_coverage_strict(0.95); lib.set_cup_coverage_strict(0.95)

ARCHETYPES = ["triangle_string_halter", "bandeau_back_band",
              "bralette_shoulder_strap", "one_piece_maillot"]

def profile_one(arch: str, seed: int) -> dict:
    rng = random.Random(seed)
    o = random_outfit(arch, rng)
    g = outfit_to_genome(o)
    timings: dict[str, float] = {}

    t = time.time()
    body_uvs = cylindrical_uvs(body)
    body.triangle_uvs = o3d.utility.Vector2dVector(body_uvs)
    yc, yn = torso_anchors(body)
    timings["body_uv+anchors"] = time.time() - t

    t = time.time()
    polys_uv = genome_polygons(g)
    timings["genome_polygons"] = time.time() - t

    t = time.time()
    shell = build_fabric_shell(body, body_uvs, polys_uv, offset=0.3)
    timings["build_fabric_shell"] = time.time() - t

    t = time.time()
    if len(np.asarray(shell.triangles)) > 0:
        shell = polish_shell(shell, body, polys_uv, yc, yn)
    timings["polish_shell"] = time.time() - t

    t = time.time()
    binding = (build_binding_mesh(shell, offset=0.05, thickness=0.40)
               if len(shell.vertices) > 0 else o3d.geometry.TriangleMesh())
    timings["build_binding"] = time.time() - t

    t = time.time()
    straps = build_strap_meshes(body, g, yc, yn)
    timings["build_strap_meshes"] = time.time() - t

    t = time.time()
    tex = genome_to_texture(g)
    timings["genome_to_texture"] = time.time() - t

    t = time.time()
    R = make_renderer(480, 720)
    timings["make_renderer"] = time.time() - t

    # Actual 3D render: front view
    t = time.time()
    img_front = render_mesh(R, body, tex, body_uvs=body_uvs, polys_uv=polys_uv)
    timings["render_mesh_view_1"] = time.time() - t

    # Second view of same scene -- renderer scene is cached, only camera moves
    t = time.time()
    img_back = render_mesh(R, body, tex, body_uvs=body_uvs, polys_uv=polys_uv)
    timings["render_mesh_view_2"] = time.time() - t

    timings["TOTAL"] = sum(v for k, v in timings.items() if k != "TOTAL")
    return timings


results = []
for arch in ARCHETYPES:
    rows = []
    for seed in (0, 1, 2):
        rows.append(profile_one(arch, seed))
    results.append((arch, rows))

# Aggregate
print(f"{'stage':28s}  {'min':>7s}  {'median':>7s}  {'max':>7s}  {'mean':>7s}")
all_keys = list(results[0][1][0].keys())
for k in all_keys:
    vals = [r[k] for _, rows in results for r in rows]
    vals.sort()
    n = len(vals)
    med = vals[n // 2]
    print(f"{k:28s}  {min(vals):6.3f}s  {med:6.3f}s  {max(vals):6.3f}s  {sum(vals)/n:6.3f}s")

# Render-only summary
render_only = []
for _, rows in results:
    for r in rows:
        render_only.append(r["render_mesh_view_1"] + r["render_mesh_view_2"])
print(f"\nPure 3D render call (2 views): avg {sum(render_only)/len(render_only):.2f}s, max {max(render_only):.2f}s")

setup_keys = [k for k in all_keys
               if k not in ("render_mesh_view_1","render_mesh_view_2","TOTAL")]
setup_total = [sum(r[k] for k in setup_keys) for _, rows in results for r in rows]
print(f"Everything BEFORE the 3D render: avg {sum(setup_total)/len(setup_total):.2f}s")

totals = [r["TOTAL"] for _, rows in results for r in rows]
print(f"End-to-end one outfit (2 views): avg {sum(totals)/len(totals):.2f}s")
