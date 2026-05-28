"""Verify the manufacturability loss actually improved H1 compliance.

Run BOTH ckpts (p35 without manuf loss, p37 with) on 24 random briefs
and count validate_garment H1/H2 violations on the decoded outputs.
"""
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
from v3.tokens_to_garment import tokens_to_garment
from garment_state import validate_garment

BRIEFS = [
    "cyberpunk neon-trim crop top, magenta + black",
    "Iris van Herpen sculptural one-piece, translucent shards",
    "Genshin Liyue silk drape with 披帛, pearl + jade",
    "K/DA-style idol stage micro-bikini, neon teal + silver",
    "Maori-inspired body harness with bone pendants, ochre",
    "Bayonetta hair-as-catsuit, deep violet, beauty mark",
    "Dune Fremen stillsuit-bikini hybrid, desert sand + bone",
    "FFXIV summoner glamour with floating glyphs, gold + sapphire",
    "Honkai Star Rail Robin idol stage, golden + feathers",
    "暗黑哥特 Bayonetta 黑色蕾丝", "vaporwave Y2K iridescent",
    "Tibetan dakini turquoise bronze", "Mugler 1995 silver cyborg",
    "原神璃月仙气飘带翡翠绿", "tropical Maori palm-green bone",
    "Wakanda afrofuturism gold body chain", "Heian junihitoe pastel layers",
    "Aztec quetzal feather warrior",
    "Stellar Blade nano-suit chrome", "NieR 2B lace blindfold",
    "Frost Druid bark organic", "Solarpunk plant-fiber",
    "Slavic kokoshnik red-white", "Akira Neo-Tokyo bike-suit",
]


def run_ckpt(ckpt_path, label):
    print(f"\n========== {label} ==========")
    print(f"ckpt: {ckpt_path}")
    enc = SentenceTransformerEncoder()
    gen = DesignGeneratorV3()
    gen.init_tag_bank(sbert=enc.model)
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    # length_head may not exist in older ckpts; handle missing key
    try:
        gen.load_state_dict(ckpt["gen_state"])
    except RuntimeError as e:
        print(f"  (load with strict=False due to: {str(e)[:80]})")
        gen.load_state_dict(ckpt["gen_state"], strict=False)
    gen.eval()

    emb = enc.encode(BRIEFS)
    if not isinstance(emb, torch.Tensor):
        emb = torch.tensor(emb)
    with torch.no_grad():
        out = gen(emb.float(), noise_sigma=0.2)
    if out.length_logits is not None:
        designs = gen.decode_strokes(
            out.stroke_tensor.cpu(),
            length_logits=out.length_logits.cpu())
    else:
        designs = gen.decode_strokes(out.stroke_tensor.cpu())

    total_pieces = 0
    total_dropped = 0
    total_h1 = 0
    total_h2 = 0
    total_warnings = 0
    for tokens in designs:
        end_at = next((i + 1 for i, t in enumerate(tokens) if t.is_end), len(tokens))
        tokens = tokens[:end_at]
        garment = tokens_to_garment(tokens)
        n_before = len(garment.pieces)
        total_pieces += n_before
        garment2 = validate_garment(garment)
        n_after = len(garment2.pieces)
        warnings = garment2.metadata.get("validation_warnings", [])
        total_dropped += (n_before - n_after)
        total_warnings += len(warnings)
        for w in warnings:
            if "H1" in w:
                total_h1 += 1
            if "H2" in w:
                total_h2 += 1

    print(f"  {len(BRIEFS)} designs, {total_pieces} total pieces")
    print(f"  pieces dropped by validate_garment: {total_dropped} ({100*total_dropped/max(1,total_pieces):.1f}%)")
    print(f"  H1 (area<8cm²) violations: {total_h1}")
    print(f"  H2 (self-intersect) violations: {total_h2}")
    print(f"  total warnings: {total_warnings}")
    return total_h1, total_h2, total_dropped, total_pieces


if __name__ == "__main__":
    base = "tools/output/2026-05-28"
    h1_a, h2_a, drop_a, total_a = run_ckpt(f"{base}/p35_length_head/decoder_pretrained.pt",
                                            "p35 baseline (length_head only)")
    h1_b, h2_b, drop_b, total_b = run_ckpt(f"{base}/p39_manuf_rl/decoder_rl.pt",
                                            "p39 + REINFORCE on validate_garment")
    print("\n========== DELTA ==========")
    print(f"  H1 violations: {h1_a} → {h1_b}  ({'IMPROVED' if h1_b < h1_a else 'WORSE' if h1_b > h1_a else 'SAME'})")
    print(f"  H2 violations: {h2_a} → {h2_b}  ({'IMPROVED' if h2_b < h2_a else 'WORSE' if h2_b > h2_a else 'SAME'})")
    print(f"  drop rate:     {100*drop_a/max(1,total_a):.1f}% → {100*drop_b/max(1,total_b):.1f}%")
