"""Audit pre-RL (p40) vs post-RL (p43) ckpt with vLLM judge.

Same 8 unseen briefs through both. Render PNG, judge each, average.
Shows: did RL actually improve judge score + manuf compliance?
"""
import os
import sys
import time
import torch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")

from design_generator import SentenceTransformerEncoder
from v3.design_generator_v3 import DesignGeneratorV3
from v3.tokens_to_garment import tokens_to_garment
from v3.full_chain_render import render_design_3d
from garment_state import validate_garment
from vision_judge import make_judge
from PIL import Image, ImageDraw, ImageFont

BRIEFS = [
    "Bayonetta gothic black lace asymmetric",
    "Iris van Herpen sculptural orange swooping",
    "cyberpunk magenta + chrome neon cage",
    "Genshin Liyue silk teal sculptural monokini",
    "Maori tribal bone-white + copper wrap",
    "Mugler liquid metal silver chainmail bikini",
    "FFXIV Tibetan dakini ritual armor turquoise",
    "Iridescent holographic Tron cyber teal",
]


def run_ckpt(ckpt_path, label, out_dir, judge):
    print(f"\n========== {label} ==========")
    print(f"ckpt: {ckpt_path}")
    os.makedirs(out_dir, exist_ok=True)

    enc = SentenceTransformerEncoder()
    gen = DesignGeneratorV3()
    gen.init_tag_bank(sbert=enc.model)
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    gen.load_state_dict(ckpt["gen_state"], strict=False)
    gen.eval()

    emb = enc.encode(BRIEFS)
    if not isinstance(emb, torch.Tensor):
        emb = torch.tensor(emb)
    torch.manual_seed(7)
    with torch.no_grad():
        out = gen(emb.float(), noise_sigma=0.3)
    designs = gen.decode_strokes(out.stroke_tensor.cpu(),
                                   length_logits=out.length_logits.cpu())
    for i, ts in enumerate(designs):
        end_at = next((j+1 for j, t in enumerate(ts) if t.is_end), len(ts))
        designs[i] = ts[:end_at]

    scores = []
    manuf = []
    paths = []
    for i, tokens in enumerate(designs):
        png = os.path.join(out_dir, f"v{i:02d}.png")
        render_design_3d(tokens, png, verbose=False)
        # judge
        try:
            jr = judge.judge(png, brief=BRIEFS[i])
            judge_avg = 0.5 * (jr.aesthetic_score + jr.brief_match)
        except Exception as e:
            print(f"  v{i:02d} judge failed: {e}")
            jr = None
            judge_avg = 0.0
        # manuf
        g = tokens_to_garment(tokens)
        n_before = len(g.pieces)
        g2 = validate_garment(g)
        n_after = len(g2.pieces)
        n_dropped = n_before - n_after
        warns = len(g2.metadata.get("validation_warnings", []))
        scores.append(judge_avg)
        manuf.append(n_dropped + 0.5 * warns)
        paths.append(png)
        print(f"  v{i:02d} judge={judge_avg:.2f}/10  "
              f"manuf={n_dropped}drop+{warns}warn  '{BRIEFS[i][:40]}'")

    print(f"\n  avg judge score: {sum(scores)/len(scores):.2f} / 10")
    print(f"  avg manuf cost:  {sum(manuf)/len(manuf):.2f}")
    return scores, manuf, paths


def main():
    judge = make_judge("vllm")
    base = "tools/output/2026-05-28"

    pre_scores, pre_manuf, pre_paths = run_ckpt(
        f"{base}/p40_phase_a2_v2lib/decoder_pretrained.pt",
        "PRE-RL (p40, Phase A2 imitation + length_head)",
        f"{base}/p44_audit/pre_rl", judge)

    post_scores, post_manuf, post_paths = run_ckpt(
        f"{base}/p43_full_rl_30/decoder_rl.pt",
        "POST-RL (p43, +30 iter Phase A3 full RL)",
        f"{base}/p44_audit/post_rl", judge)

    print("\n========== DELTA ==========")
    pre_j = sum(pre_scores) / len(pre_scores)
    post_j = sum(post_scores) / len(post_scores)
    pre_m = sum(pre_manuf) / len(pre_manuf)
    post_m = sum(post_manuf) / len(post_manuf)
    print(f"  judge:  {pre_j:.2f} → {post_j:.2f}  ({'+' if post_j>pre_j else ''}{post_j-pre_j:+.2f})")
    print(f"  manuf cost: {pre_m:.2f} → {post_m:.2f}  ({'+' if post_m<pre_m else ''}{post_m-pre_m:+.2f})")

    # composite grid
    try:
        W, H = 260, 380
        pad = 6
        cw = 2 * (W + pad) + pad
        ch = len(BRIEFS) * (H + 22 + pad) + 30
        canvas = Image.new("RGB", (cw, ch), (245, 245, 247))
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
            font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
        except:
            font = font_s = ImageFont.load_default()
        draw.text((pad + W // 2, 14), f"PRE-RL  judge={pre_j:.1f}/10",
                  font=font, fill=(150, 60, 60), anchor="mm")
        draw.text((pad + W + pad + W // 2, 14), f"POST-RL  judge={post_j:.1f}/10",
                  font=font, fill=(60, 130, 60), anchor="mm")
        for i in range(len(BRIEFS)):
            y = 30 + i * (H + 22 + pad)
            for c, (p, s) in enumerate([(pre_paths[i], pre_scores[i]),
                                          (post_paths[i], post_scores[i])]):
                im = Image.open(p).convert("RGB")
                im.thumbnail((W, H), Image.LANCZOS)
                x = pad + c * (W + pad)
                canvas.paste(im, (x + (W - im.width) // 2, y))
                draw.text((x + W // 2, y + H + 2),
                          f"{BRIEFS[i][:32]}  ({s:.1f}/10)",
                          font=font_s, fill=(40, 40, 40), anchor="mt")
        grid_path = f"{base}/p44_audit/grid_pre_vs_post.png"
        canvas.save(grid_path)
        print(f"\nwrote grid -> {grid_path}")
    except Exception as e:
        print(f"  grid skipped: {e}")


if __name__ == "__main__":
    main()
