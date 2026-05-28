"""Render v3.1-trained NN outputs through full v2 chain.

8 fresh briefs, trained ckpt = p30_phase_a2_v31."""
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
from v3.full_chain_render import render_design_3d
from PIL import Image, ImageDraw, ImageFont

CKPT = "tools/output/2026-05-28/p32_phase_a2_v31_wider/decoder_pretrained.pt"
OUT_DIR = "tools/output/2026-05-28/p33_v31_wider_trained_3d"

DEMO_BRIEFS = [
    "Bayonetta gothic black lace asymmetric",
    "Iris van Herpen sculptural orange swooping",
    "cyberpunk magenta + chrome neon cage",
    "Genshin Liyue silk teal sculptural monokini",
    "Maori tribal bone-white + copper wrap",
    "Mugler liquid metal silver chainmail bikini",
    "FFXIV Tibetan dakini ritual armor turquoise",
    "Iridescent holographic Tron cyber teal",
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    torch.manual_seed(7)

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
    with torch.no_grad():
        out = gen(emb.float(), noise_sigma=0.3)
    designs = gen.decode_strokes(out.stroke_tensor.cpu())
    for i, tokens in enumerate(designs):
        end_at = next((j + 1 for j, s in enumerate(tokens) if s.is_end),
                      len(tokens))
        designs[i] = tokens[:end_at]
        n_p = sum(1 for t in designs[i] if type(t).__name__ == "Panel")
        n_s = sum(1 for t in designs[i] if type(t).__name__ == "Stroke")
        print(f"  v{i:02d}: {len(designs[i])} tokens ({n_p}P/{n_s}S)  "
              f"'{DEMO_BRIEFS[i][:50]}'")

    paths = []
    for i, tokens in enumerate(designs):
        p = os.path.join(OUT_DIR, f"v{i:02d}.png")
        print(f"rendering v{i:02d}...", flush=True)
        render_design_3d(tokens, p, verbose=True)
        paths.append(p)

    # grid
    W, H = 260, 380
    pad = 6
    cols = 4
    rows = 2
    cw = cols * (W + pad) + pad
    ch = rows * (H + 22 + pad) + pad + 30
    canvas = Image.new("RGB", (cw, ch), (245, 245, 247))
    draw = ImageDraw.Draw(canvas)
    try:
        font_t = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        font_t = font = ImageFont.load_default()
    draw.text((cw // 2, 12),
              "v3.1 NN-trained (9 stylized teachers × 4 paraphrases, 3000 iter GPU)",
              font=font_t, fill=(40, 40, 40), anchor="mm")
    for i, p in enumerate(paths):
        r, c = i // cols, i % cols
        im = Image.open(p).convert("RGB")
        im.thumbnail((W, H), Image.LANCZOS)
        x = pad + c * (W + pad)
        y = 30 + pad + r * (H + 22 + pad)
        canvas.paste(im, (x + (W - im.width) // 2, y))
        draw.text((x + W // 2, y + H + 2),
                  DEMO_BRIEFS[i][:35], font=font, fill=(40, 40, 40), anchor="mt")
    out = os.path.join(OUT_DIR, "grid.png")
    canvas.save(out)
    print(f"\nwrote grid -> {out}")


if __name__ == "__main__":
    main()
