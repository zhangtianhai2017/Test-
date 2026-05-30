"""EVAL: p48 (scheduled-sampling retrain) vs p40 (pure teacher forcing),
both through the SAME clean-feedback autoregressive inference path at
noise_sigma=0.0 on the 8 showcase briefs.

Hypothesis: p40 trained with pure teacher forcing -> even with clean
feedback its per-step boundaries drift (diagonal one-breast sash). p48
trained with scheduled sampling on its own clean-feedback outputs ->
boundaries should hold -> symmetric covering bikinis.
"""
import os
import sys
import torch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from design_generator import SentenceTransformerEncoder
from v3.design_generator_v3 import DesignGeneratorV3
from v3.full_chain_render import render_design_3d

BRIEFS = [
    "cyberpunk magenta + chrome neon cage bikini",
    "Iris van Herpen sculptural translucent shards, pearl white",
    "Genshin Liyue silk teal sculptural monokini with peibo",
    "Mugler liquid metal silver chainmail bikini",
    "Maori tribal bone-white + copper wrap harness",
    "Bayonetta gothic black lace asymmetric",
    "tropical sunset coral + gold high-cut",
    "iridescent holographic Tron cyber teal",
]
CKPTS = [
    ("p40", "tools/output/2026-05-28/p40_phase_a2_v2lib/decoder_pretrained.pt"),
    ("p48", "tools/output/2026-05-30/p48_phase_a2_ss/decoder_pretrained.pt"),
]


def main():
    enc = SentenceTransformerEncoder()
    emb = enc.encode(BRIEFS)
    if not isinstance(emb, torch.Tensor):
        emb = torch.tensor(emb)
    emb = emb.float()

    out_root = "tools/output/2026-05-30/_eval_p48_vs_p40"

    for tag, ckpt in CKPTS:
        gen = DesignGeneratorV3()
        gen.init_tag_bank(sbert=enc.model)
        ck = torch.load(ckpt, map_location="cpu", weights_only=False)
        gen.load_state_dict(ck["gen_state"], strict=False)
        gen.eval()

        d = os.path.join(out_root, tag)
        os.makedirs(d, exist_ok=True)
        torch.manual_seed(7)
        with torch.no_grad():
            out = gen(emb, noise_sigma=0.0)   # clean_feedback=True default
        designs = gen.decode_strokes(out.stroke_tensor.cpu(),
                                     length_logits=out.length_logits.cpu())
        for i, tokens in enumerate(designs):
            end_at = next((j + 1 for j, s in enumerate(tokens) if s.is_end),
                          len(tokens))
            tk = tokens[:end_at]
            n_p = sum(1 for t in tk if type(t).__name__ == "Panel")
            n_s = sum(1 for t in tk if type(t).__name__ == "Stroke")
            png = os.path.join(d, f"v{i:02d}.png")
            try:
                render_design_3d(tk, png, verbose=False)
                ok = os.path.exists(png) and os.path.getsize(png) > 1000
            except Exception as e:
                ok = False
                print(f"  [{tag} v{i:02d}] render FAIL: {e}", flush=True)
            print(f"  [{tag} v{i:02d}] {n_p}P/{n_s}S  ok={ok}  {BRIEFS[i][:38]}",
                  flush=True)


if __name__ == "__main__":
    main()
