"""DIAGNOSTIC: test the EXPOSURE-BIAS hypothesis for p40's multi-panel
collapse.

p40 trains with teacher forcing (decoder.token_in sees CLEAN encoded
teacher tokens) but at inference feeds back the RAW head-output row
(design_generator_v3.py line 240). Raw rows are off-distribution vs the
clean one-hot/­magnitude-10 tokens token_in saw at train time -> errors
compound across the sequence -> multi-panel designs collapse to degenerate
tiny strips.

This script runs the SAME p40 ckpt two ways at noise_sigma=0.0 (pure
deterministic) on the 8 showcase briefs:

  RAW    : original loop, feed self.token_in(raw_row) back  (= deployed p40)
  CLEAN  : feed self.token_in(encode_token(decode_token(raw_row))) back
           -> re-projects every step onto the training token distribution

If CLEAN renders clean covering bikinis where RAW collapses, the fix is
inference-side (clean-feedback decode) and/or a scheduled-sampling retrain.
If CLEAN is ALSO degenerate, exposure bias is NOT the cause -> look at the
decoder weights / training targets.
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
from v3.token_tensor import decode_token, encode_token
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
CKPT = "tools/output/2026-05-28/p40_phase_a2_v2lib/decoder_pretrained.pt"


@torch.no_grad()
def ar_decode(gen, head_input, anchor_plan, clean_feedback: bool):
    """Replicate StrokeTransformerDecoder autoregressive loop, but optionally
    re-encode each predicted row to a clean training-distribution token before
    feeding it back through token_in."""
    dec = gen.decoder
    B = head_input.shape[0]
    device = head_input.device
    memory = dec.make_memory(head_input, anchor_plan)
    tokens = []
    prev = dec.sos.expand(B, 1, -1)
    for t in range(dec.max_strokes):
        seq = prev + dec.pos_emb[:, :prev.shape[1]]
        T = seq.shape[1]
        causal = torch.triu(torch.ones(T, T, device=device, dtype=torch.bool),
                            diagonal=1)
        out = dec.decoder(tgt=seq, memory=memory, tgt_mask=causal)
        row = dec.head(out[:, -1:])                 # (B, 1, D)
        tokens.append(row)
        if clean_feedback:
            clean_rows = []
            for b in range(B):
                tok = decode_token(row[b, 0].cpu())
                clean_rows.append(encode_token(tok))
            feed = torch.stack(clean_rows, dim=0).unsqueeze(1).to(device)
        else:
            feed = row
        prev = torch.cat([prev, dec.token_in(feed)], dim=1)
    return torch.cat(tokens, dim=1)                  # (B, MAX, D)


def main():
    enc = SentenceTransformerEncoder()
    gen = DesignGeneratorV3()
    gen.init_tag_bank(sbert=enc.model)
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    gen.load_state_dict(ck["gen_state"], strict=False)
    gen.eval()

    emb = enc.encode(BRIEFS)
    if not isinstance(emb, torch.Tensor):
        emb = torch.tensor(emb)
    emb = emb.float()

    out_root = "tools/output/2026-05-30/_diag_p40_cleanfeed"

    for mode, clean in (("raw", False), ("clean", True)):
        d = os.path.join(out_root, mode)
        os.makedirs(d, exist_ok=True)
        torch.manual_seed(7)
        # replicate forward() up to the decoder at noise_sigma=0.0
        with torch.no_grad():
            bias = gen.brief_bias(emb)
            tag_v = gen.tag_summary(emb.shape[0], None, None, device=emb.device)
            enc_in = torch.cat([bias, tag_v], dim=-1)
            mu, logvar = gen.encoder(enc_in)
            z = gen.reparameterize(mu, logvar)
            head_input = gen.inject_noise(z, sigma=0.0)
            anchor_plan = gen.anchor_plan_head(head_input)
            length_logits = gen.length_head(head_input)
            stroke_tensor = ar_decode(gen, head_input, anchor_plan, clean)
        designs = gen.decode_strokes(stroke_tensor.cpu(),
                                     length_logits=length_logits.cpu())
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
                print(f"  [{mode} v{i:02d}] render FAIL: {e}", flush=True)
            print(f"  [{mode:<5} v{i:02d}] {n_p}P/{n_s}S  ok={ok}  {BRIEFS[i][:38]}",
                  flush=True)


if __name__ == "__main__":
    main()
