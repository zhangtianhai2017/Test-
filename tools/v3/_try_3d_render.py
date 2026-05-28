"""Try in-process 3D render of trained-ckpt outputs.

Render strategy: load body mesh ONCE, then render multiple designs in
the same process (single OffscreenRenderer instance, scene cleared
between designs). This bypasses both subprocess SIGSEGV and the
'second-render Filament leak' (because we keep one renderer alive).
"""
import os
import sys
import time
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
os.environ.setdefault("OPEN3D_HEADLESS_RENDERING", "true")

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import math
import numpy as np
import torch
import open3d as o3d

from design_generator import SentenceTransformerEncoder
from v3.design_generator_v3 import DesignGeneratorV3
from v3.stroke_renderer import design_to_meshes

DEMO_BRIEFS = [
    "Bayonetta 风, 黑色蕾丝紧身, 戏剧化",
    "cyberpunk neon-trim corset, magenta + chrome",
    "Iris van Herpen sculptural one-piece, orange swooping",
    "classical white triangle bikini, French elegant",
]

CKPT = "tools/output/2026-05-28/p20c_phase_a2_diverse/decoder_pretrained.pt"
OUT_DIR = "tools/output/2026-05-28/p25_3d_render"
W, H = 480, 720


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    torch.manual_seed(2026)

    print("loading sbert + gen...")
    enc = SentenceTransformerEncoder()
    gen = DesignGeneratorV3()
    gen.init_tag_bank(sbert=enc.model)
    ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
    gen.load_state_dict(ckpt["gen_state"])
    gen.eval()

    print("encoding briefs...")
    emb = enc.encode(DEMO_BRIEFS)
    if not isinstance(emb, torch.Tensor):
        emb = torch.tensor(emb)
    with torch.no_grad():
        out = gen(emb.float(), noise_sigma=0.4)
    designs = gen.decode_strokes(out.stroke_tensor)
    for i, strokes in enumerate(designs):
        end_at = next((j + 1 for j, s in enumerate(strokes) if s.is_end),
                      len(strokes))
        designs[i] = strokes[:end_at]
        print(f"  v{i:02d}: {len(designs[i])} strokes  '{DEMO_BRIEFS[i][:50]}'")

    print("\nloading body mesh...")
    from render3d_uv import load_body_mesh
    body = load_body_mesh()

    print("creating OffscreenRenderer (will probably crash if vLLM contested)...")
    R = o3d.visualization.rendering.OffscreenRenderer(W, H)
    R.scene.set_background([0.92, 0.92, 0.94, 1.0])
    R.scene.scene.set_sun_light(
        direction=[-0.4, -0.6, -0.7],
        color=[1.0, 1.0, 1.0], intensity=80_000)
    R.scene.scene.enable_sun_light(True)
    R.scene.scene.enable_indirect_light(True)
    R.scene.scene.set_indirect_light_intensity(28_000)

    mat_body = o3d.visualization.rendering.MaterialRecord()
    mat_body.base_color = [0.90, 0.78, 0.74, 1.0]
    mat_body.shader = "defaultLit"
    mat_stroke = o3d.visualization.rendering.MaterialRecord()
    mat_stroke.base_color = [1.0, 1.0, 1.0, 1.0]
    mat_stroke.shader = "defaultLit"

    V = np.asarray(body.vertices)
    y_lo, y_hi = float(np.percentile(V[:, 1], 2)), float(np.percentile(V[:, 1], 98))
    body_h = y_hi - y_lo
    center = [0.0, y_lo + 0.55 * body_h, 0.0]
    fov = 60.0
    radius = body_h * 0.55 / math.tan(math.radians(fov / 2.0))

    for i, strokes in enumerate(designs):
        print(f"\nrendering v{i:02d} ...", flush=True)
        t0 = time.time()
        # clear scene
        R.scene.clear_geometry()
        R.scene.add_geometry("body", body, mat_body)
        meshes = design_to_meshes(strokes, body)
        for j, m in enumerate(meshes):
            R.scene.add_geometry(f"stroke_{j}", m, mat_stroke)
        R.setup_camera(fov, center, [0, center[1], radius], [0, 1, 0])
        img = R.render_to_image()
        out_path = os.path.join(OUT_DIR, f"v{i:02d}_3d.png")
        o3d.io.write_image(out_path, img, 9)
        print(f"  ✓ v{i:02d}_3d.png ({os.path.getsize(out_path):,} bytes) "
              f"in {time.time()-t0:.1f}s")

    print(f"\ndone, output: {OUT_DIR}")


if __name__ == "__main__":
    main()
