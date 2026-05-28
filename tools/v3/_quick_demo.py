"""Quick demo render — 8 brand-new briefs through the trained ckpt."""
import os
import sys
import torch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from design_generator import SentenceTransformerEncoder
from v3.design_generator_v3 import DesignGeneratorV3
from v3.stroke_renderer import render_uv_sketch
from PIL import Image, ImageDraw, ImageFont

DEMO_BRIEFS = [
    "Honkai Star Rail Robin idol stage outfit, golden + white feathers",
    "暗黑哥特 Bayonetta 风, 黑色蕾丝紧身, 戏剧化",
    "FFXIV summoner ceremonial robe, sapphire + gold runes",
    "cyberpunk neon-trim corset bodysuit, magenta + chrome",
    "Tibetan dakini ritual armor, turquoise + bronze, mystical",
    "原神璃月仙气飘带泳装, 翡翠绿丝绸",
    "Mugler 1995 mecha cyborg one-piece, liquid metal",
    "tropical Maori-Polynesian body chain, palm-green + bone-white",
]

CKPT = "tools/output/2026-05-28/p20c_phase_a2_diverse/decoder_pretrained.pt"
OUT_DIR = "tools/output/2026-05-28/p24_quick_demo"


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

    print(f"encoding {len(DEMO_BRIEFS)} briefs...")
    emb = enc.encode(DEMO_BRIEFS)
    if not isinstance(emb, torch.Tensor):
        emb = torch.tensor(emb)
    emb = emb.float()

    print("generating with tag-mix + noise...")
    with torch.no_grad():
        out = gen(emb,
                  axis_weights={"art_style": 0.30, "cultural": 0.20,
                                 "costume_convention": 0.20, "material_vfx": 0.15,
                                 "silhouette": 0.10, "archetype": 0.05},
                  noise_sigma=0.6)
    designs = gen.decode_strokes(out.stroke_tensor)
    for i, strokes in enumerate(designs):
        end_at = next((j + 1 for j, s in enumerate(strokes) if s.is_end),
                      len(strokes))
        designs[i] = strokes[:end_at]

    print("rendering...")
    paths = []
    for i, (brief, strokes) in enumerate(zip(DEMO_BRIEFS, designs)):
        p = os.path.join(OUT_DIR, f"v{i:02d}.png")
        render_uv_sketch(strokes, p,
                          title=f"v{i:02d} ({len(strokes)} strokes): {brief[:55]}")
        paths.append(p)
        print(f"  v{i:02d}: {len(strokes)} strokes  '{brief[:50]}'")

    # composite 2x4 grid
    sample = Image.open(paths[0])
    W, H = sample.size
    W_thumb, H_thumb = 360, 540
    pad = 8
    cw = 4 * (W_thumb + pad) + pad
    ch = 2 * (H_thumb + pad) + pad + 30
    canvas = Image.new("RGB", (cw, ch), (245, 245, 247))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    draw.text((cw // 2, 12),
              "v3 trained — 8 new briefs (Phase A2 7-teacher ckpt)",
              font=font, fill=(40, 40, 40), anchor="mm")
    for i, p in enumerate(paths):
        r, c = i // 4, i % 4
        im = Image.open(p).convert("RGB")
        im.thumbnail((W_thumb, H_thumb), Image.LANCZOS)
        x = pad + c * (W_thumb + pad)
        y = 30 + pad + r * (H_thumb + pad)
        ox = x + (W_thumb - im.width) // 2
        oy = y + (H_thumb - im.height) // 2
        canvas.paste(im, (ox, oy))
    grid_path = os.path.join(OUT_DIR, "demo_grid.png")
    canvas.save(grid_path)
    print(f"\nwrote grid -> {grid_path}")


if __name__ == "__main__":
    main()
