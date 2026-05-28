"""
DesignGeneratorV3 — game-character-first stroke-sequence generator.

Per docs/design/2026-05-27_schema_redesign_v3.md §3+§4.

Architecture:

    brief (text)
       │
       ▼ sbert (frozen, 384-d)
    [brief_emb]
       │
       ▼ Linear(384 → 128) + LN
    [brief_bias] (128-d, "user intent")
       │
       │   ┌─ Optional tag conditioning ─────┐
       │   │  Dirichlet mix over tags        │
       │   │  per axis → 128-d style vector  │
       │   └────────────┬────────────────────┘
       │                │
       ▼                ▼
       ┌── concat (256) ──┐
                │
                ▼
    Encoder MLP (256 → 256 → 2×128)
    splits to (μ, log_σ²) for VAE posterior
                │
                ▼ reparameterize: z = μ + σ⊙ε
    [style_latent] (128-d)
                │
                ▼  noise channel mix
    head_input = √0.9 · style + √0.1 · noise   (∈ ℝ^128, total var ≈ 1)
                │
                ▼
    Anchor-Plan MLP (128 → 10-way activation mask, σ-gate per anchor)
    [anchor_plan_logits] (10) → which anchors are "active" for this design
                │
                ▼
    Transformer Stroke Decoder (autoregressive)
       inputs:
         - previous decoded stroke tokens (positionally embedded)
         - cross-attention key/value = [head_input | anchor_plan]
       outputs per step:
         - stroke_tensor_row (STROKE_TENSOR_DIM = 669)
       stops at <is_end> token or MAX_STROKES.

Public API:
    gen = DesignGeneratorV3(...)
    gen.init_tag_bank()            # one-shot: sbert init the bank
    out = gen(brief_texts, tag_axis_weights=None, sigma=1.0)
        → {style_latent, anchor_plan, stroke_tensor (B, T, D), strokes_decoded}
    gen.train_step_loss(briefs, target_strokes) → loss (for Phase A2 imitation)

Three sampling modes:
    1. "tag-free":  encoder sees only brief — natural generation
    2. "tag-soft":  encoder sees brief + Dirichlet-mixed tag axis cocktail
    3. "tag-hard":  caller supplies explicit tag_ids → encoder bypasses brief

This file is dependency-light: only torch + project tag_embeddings.
The actual rendering happens elsewhere (v3/stroke_renderer.py).
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from typing import Iterable

import torch
import torch.nn as nn
import torch.nn.functional as F

# allow `python -m tools.v3.design_generator_v3` and direct invocation
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from tag_embeddings import TagEmbeddingBank, SBERT_DIM            # noqa: E402
from tag_data import AXES                                          # noqa: E402
from v3.stroke_schema import (                                     # noqa: E402
    Anchor, N_ANCHORS, MAX_STROKES,
    N_ANCHOR_LOGITS, N_PALETTE, N_MATERIAL_VFX_TAGS, WIDTH_SEGMENTS,
    PANEL_BOUNDARY_POINTS,
    TOKEN_TYPE_PANEL, TOKEN_TYPE_STROKE,
)
# v3.1: use the unified Panel+Stroke token tensor
from v3.token_tensor import (                                      # noqa: E402
    TOKEN_TENSOR_DIM, encode_design, decode_batch, offsets,
    N_FABRICS, N_LAYER_ROLES, N_TOKEN_TYPES,
)
# Backward-compat alias
STROKE_TENSOR_DIM = TOKEN_TENSOR_DIM
_OFFSETS = offsets()


# ─── small modules ─────────────────────────────────────────────────────

class BriefBias(nn.Module):
    """sbert(brief) -> 128-d brief intent vector."""
    def __init__(self, sbert_dim: int = SBERT_DIM, out_dim: int = 128):
        super().__init__()
        self.proj = nn.Linear(sbert_dim, out_dim)
        self.norm = nn.LayerNorm(out_dim)

    def forward(self, brief_emb: torch.Tensor) -> torch.Tensor:
        return self.norm(self.proj(brief_emb))


class VAEEncoder(nn.Module):
    """[brief_bias | tag_summary] -> posterior (mu, logvar) over style latent."""
    def __init__(self, in_dim: int, latent_dim: int = 128, hidden: int = 256):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
            nn.GELU(),
        )
        self.mu = nn.Linear(hidden, latent_dim)
        self.logvar = nn.Linear(hidden, latent_dim)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(x)
        return self.mu(h), self.logvar(h).clamp(-8, 4)


class AnchorPlan(nn.Module):
    """style_latent -> per-anchor activation gate (10 anchors)."""
    def __init__(self, latent_dim: int = 128, n_anchors: int = N_ANCHORS):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, 64),
            nn.GELU(),
            nn.Linear(64, n_anchors),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.net(z)   # logits, shape (B, N_ANCHORS)


class StrokeTransformerDecoder(nn.Module):
    """Autoregressive transformer producing stroke token sequence.

    cross-attention key/value = [head_input || anchor_plan_logits]
        (single condensed token broadcast to all positions)
    self-attention: causal over stroke positions

    output: per-position vector of size STROKE_TENSOR_DIM (669)
    """
    def __init__(self,
                 d_model: int = 192,
                 n_heads: int = 4,
                 n_layers: int = 4,
                 ff_dim: int = 384,
                 latent_dim: int = 128,
                 n_anchors: int = N_ANCHORS,
                 max_strokes: int = MAX_STROKES,
                 dropout: float = 0.1):
        super().__init__()
        self.d_model = d_model
        self.max_strokes = max_strokes

        # cross-attention memory comes from style_latent + anchor_plan
        # condensed to a single d_model token.
        self.memory_proj = nn.Linear(latent_dim + n_anchors, d_model)

        # input projection: a stroke "token" entering the decoder.
        # At training (teacher-forcing): the previous (encoded) stroke row.
        # At inference: same, computed step-by-step.
        self.token_in = nn.Linear(STROKE_TENSOR_DIM, d_model)

        # learned start-of-sequence token
        self.sos = nn.Parameter(torch.zeros(1, 1, d_model))
        nn.init.normal_(self.sos, std=0.02)

        # position embeddings
        self.pos_emb = nn.Parameter(torch.zeros(1, max_strokes + 1, d_model))
        nn.init.normal_(self.pos_emb, std=0.02)

        # transformer decoder
        dec_layer = nn.TransformerDecoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=ff_dim,
            dropout=dropout, batch_first=True, activation="gelu",
            norm_first=True)
        self.decoder = nn.TransformerDecoder(dec_layer, num_layers=n_layers)

        # output projection: d_model -> STROKE_TENSOR_DIM (669)
        self.head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, ff_dim),
            nn.GELU(),
            nn.Linear(ff_dim, STROKE_TENSOR_DIM),
        )

    def make_memory(self, head_input: torch.Tensor,
                    anchor_plan: torch.Tensor) -> torch.Tensor:
        """style_latent (B, latent) + anchor_plan (B, N_ANCHORS) -> (B, 1, d_model)."""
        x = torch.cat([head_input, anchor_plan], dim=-1)
        return self.memory_proj(x).unsqueeze(1)  # (B, 1, d_model)

    def forward(self,
                head_input: torch.Tensor,
                anchor_plan: torch.Tensor,
                teacher_tokens: torch.Tensor | None = None
                ) -> torch.Tensor:
        """If teacher_tokens given (B, T, STROKE_TENSOR_DIM), train via
        teacher forcing — predict the t-th stroke from previous strokes.
        Otherwise inference: autoregressive sampling (slower)."""
        B = head_input.shape[0]
        device = head_input.device
        memory = self.make_memory(head_input, anchor_plan)  # (B, 1, d_model)

        if teacher_tokens is not None:
            T = teacher_tokens.shape[1]
            # Build input sequence: [SOS, tok[0], tok[1], ..., tok[T-1]]
            tok_emb = self.token_in(teacher_tokens)         # (B, T, d_model)
            sos = self.sos.expand(B, 1, -1)                 # (B, 1, d_model)
            seq = torch.cat([sos, tok_emb], dim=1)          # (B, T+1, d_model)
            seq = seq[:, :T] + self.pos_emb[:, :T]          # use first T positions
            causal = torch.triu(torch.ones(T, T, device=device, dtype=torch.bool),
                                  diagonal=1)
            out = self.decoder(tgt=seq, memory=memory, tgt_mask=causal)
            return self.head(out)                            # (B, T, STROKE_TENSOR_DIM)
        else:
            # Autoregressive (B, MAX_STROKES, STROKE_TENSOR_DIM)
            tokens = []
            prev = self.sos.expand(B, 1, -1)
            for t in range(self.max_strokes):
                seq = prev + self.pos_emb[:, :prev.shape[1]]
                T = seq.shape[1]
                causal = torch.triu(torch.ones(T, T, device=device, dtype=torch.bool),
                                      diagonal=1)
                out = self.decoder(tgt=seq, memory=memory, tgt_mask=causal)
                row = self.head(out[:, -1:])                # (B, 1, STROKE_TENSOR_DIM)
                tokens.append(row)
                # feed the predicted row back as the next input
                prev = torch.cat([prev, self.token_in(row)], dim=1)
                # early-exit not possible per-batch (different lengths) — caller
                # truncates at is_end downstream
            return torch.cat(tokens, dim=1)  # (B, MAX_STROKES, STROKE_TENSOR_DIM)


# ─── main module ───────────────────────────────────────────────────────

@dataclass
class V3Output:
    style_mu:        torch.Tensor      # (B, latent_dim)
    style_logvar:    torch.Tensor      # (B, latent_dim)
    style_latent:    torch.Tensor      # (B, latent_dim) sampled
    anchor_plan:     torch.Tensor      # (B, N_ANCHORS)
    stroke_tensor:   torch.Tensor      # (B, T, STROKE_TENSOR_DIM)
    head_input:      torch.Tensor      # (B, latent_dim) after noise mix


class DesignGeneratorV3(nn.Module):
    """Top-level v3 design generator."""
    def __init__(self,
                 sbert_dim: int = SBERT_DIM,
                 latent_dim: int = 128,
                 tag_bank: TagEmbeddingBank | None = None,
                 transformer_layers: int = 4,
                 transformer_heads: int = 4,
                 transformer_d_model: int = 192,
                 max_strokes: int = MAX_STROKES,
                 noise_energy: float = 0.10):
        super().__init__()
        self.latent_dim = latent_dim
        self.max_strokes = max_strokes
        self.noise_energy = noise_energy
        self.noise_scale = math.sqrt(noise_energy)
        self.style_scale = math.sqrt(1 - noise_energy)

        # text->intent
        self.brief_bias = BriefBias(sbert_dim, latent_dim)

        # tag bank (shared; can be None at init, set later)
        self.tag_bank = tag_bank if tag_bank is not None else \
            TagEmbeddingBank(dim=latent_dim)

        # encoder: input dim depends on whether we concat tag summary
        # we ALWAYS allocate space for the tag summary (zeros if absent)
        # → keeps the architecture single-shape and inference-friendly
        self.encoder = VAEEncoder(in_dim=2 * latent_dim,
                                   latent_dim=latent_dim,
                                   hidden=2 * latent_dim)

        # anchor plan head
        self.anchor_plan_head = AnchorPlan(latent_dim, N_ANCHORS)

        # stroke decoder
        self.decoder = StrokeTransformerDecoder(
            d_model=transformer_d_model,
            n_heads=transformer_heads,
            n_layers=transformer_layers,
            ff_dim=transformer_d_model * 2,
            latent_dim=latent_dim,
            n_anchors=N_ANCHORS,
            max_strokes=max_strokes,
        )

    # ─── tag bank ops ─────────────────────────────────────────────────

    def init_tag_bank(self, sbert=None):
        """One-shot sbert init of the embedded tag bank.
        Call once after construction; persists across saves."""
        self.tag_bank.init_from_sbert(sbert=sbert)

    # ─── summarize tag mixture as a vector ────────────────────────────

    def tag_summary(self,
                    B: int,
                    axis_weights: dict[str, float] | None = None,
                    explicit_tag_ids: list[str] | None = None,
                    dirichlet_alpha: float = 0.5,
                    device: torch.device = None) -> torch.Tensor:
        """Build a (B, latent_dim) tag summary vector.

        - If explicit_tag_ids: hard-encode those tags (same for all B).
        - Elif axis_weights: Dirichlet-mix from each axis weighted.
        - Else: zero vector (brief-only conditioning).
        """
        device = device or self.brief_bias.proj.weight.device
        if explicit_tag_ids:
            v = self.tag_bank.encode_tag_ids(explicit_tag_ids).to(device)
            return v.unsqueeze(0).expand(B, -1)
        if axis_weights:
            return self.tag_bank.sample_all_axes_mix(
                alpha=dirichlet_alpha, n_samples=B,
                axis_weights=axis_weights).to(device)
        return torch.zeros(B, self.latent_dim, device=device)

    # ─── reparam + noise mix ─────────────────────────────────────────

    def reparameterize(self, mu: torch.Tensor,
                        logvar: torch.Tensor) -> torch.Tensor:
        std = (0.5 * logvar).exp()
        return mu + std * torch.randn_like(std)

    def inject_noise(self, style_latent: torch.Tensor,
                     sigma: float = 1.0) -> torch.Tensor:
        """Mix in 10% energy of pure noise (per design doc §4.3)."""
        noise = torch.randn_like(style_latent) * sigma
        return self.style_scale * style_latent + self.noise_scale * noise

    # ─── forward ──────────────────────────────────────────────────────

    def forward(self,
                brief_emb: torch.Tensor,
                axis_weights: dict[str, float] | None = None,
                explicit_tag_ids: list[str] | None = None,
                noise_sigma: float = 1.0,
                teacher_tokens: torch.Tensor | None = None,
                ) -> V3Output:
        """brief_emb: (B, sbert_dim) precomputed sbert embeddings.
        Optional axis_weights / explicit_tag_ids for tag conditioning.
        teacher_tokens: (B, T, STROKE_TENSOR_DIM) for training; None for inference."""
        B = brief_emb.shape[0]
        device = brief_emb.device

        bias = self.brief_bias(brief_emb)                              # (B, L)
        tag_v = self.tag_summary(B, axis_weights, explicit_tag_ids,
                                  device=device)                        # (B, L)
        enc_in = torch.cat([bias, tag_v], dim=-1)                       # (B, 2L)

        mu, logvar = self.encoder(enc_in)                               # (B, L), (B, L)
        z = self.reparameterize(mu, logvar)                              # (B, L)
        head_input = self.inject_noise(z, sigma=noise_sigma)             # (B, L)

        anchor_plan = self.anchor_plan_head(head_input)                  # (B, N_ANCHORS)

        stroke_tensor = self.decoder(head_input, anchor_plan,
                                       teacher_tokens=teacher_tokens)
        return V3Output(
            style_mu=mu, style_logvar=logvar, style_latent=z,
            anchor_plan=anchor_plan, stroke_tensor=stroke_tensor,
            head_input=head_input,
        )

    # ─── losses ───────────────────────────────────────────────────────

    def imitation_loss(self,
                        pred_tensor: torch.Tensor,
                        target_tensor: torch.Tensor,
                        target_mask: torch.Tensor,
                        ) -> dict[str, torch.Tensor]:
        """v3.1 imitation loss with type-masked Panel + Stroke heads.

        pred_tensor:   (B, T, TOKEN_TENSOR_DIM=709)
        target_tensor: (B, T, TOKEN_TENSOR_DIM=709)
        target_mask:   (B, T) — 1 for real tokens, 0 for padding

        Loss structure:
          - shared heads (color/material/decoration/is_end/type)  → always
          - stroke heads → masked: only contribute where target type=stroke
          - panel heads  → masked: only contribute where target type=panel
        """
        B, T, D = pred_tensor.shape
        o = _OFFSETS
        m = target_mask  # (B, T)
        m_pos = m.sum().clamp(min=1)

        # --- determine target token type per position from one-hot at offset 0
        type_logits_target = target_tensor[:, :, o["type"]:o["type"] + N_TOKEN_TYPES]
        target_type = type_logits_target.argmax(dim=-1)   # (B, T) ∈ {0=panel, 1=stroke}
        is_target_panel = (target_type == TOKEN_TYPE_PANEL).float() * m
        is_target_stroke = (target_type == TOKEN_TYPE_STROKE).float() * m
        m_panel = is_target_panel.sum().clamp(min=1)
        m_stroke = is_target_stroke.sum().clamp(min=1)

        # --- helpers
        def ce_at(offset, n_classes, mask=m, denom=None):
            """Cross-entropy at offset, masked by `mask` (B,T). denom defaults to mask.sum()."""
            denom = denom if denom is not None else mask.sum().clamp(min=1)
            pl = pred_tensor[:, :, offset:offset + n_classes]
            tl = target_tensor[:, :, offset:offset + n_classes]
            tgt = tl.argmax(dim=-1)                                # (B, T)
            ce = F.cross_entropy(pl.reshape(-1, n_classes),
                                  tgt.reshape(-1), reduction="none")
            ce = ce.view(B, T)
            return (ce * mask).sum() / denom

        def mse_at(offset, span, mask=m, denom=None):
            denom = (denom if denom is not None else mask.sum().clamp(min=1)) * span
            p = pred_tensor[:, :, offset:offset + span]
            t = target_tensor[:, :, offset:offset + span]
            return ((p - t).pow(2) * mask.unsqueeze(-1)).sum() / denom.clamp(min=1)

        def kl_at(offset, span, mask=m, denom=None):
            denom = denom if denom is not None else mask.sum().clamp(min=1)
            pl = pred_tensor[:, :, offset:offset + span]
            tl = target_tensor[:, :, offset:offset + span]
            t_prob = F.softmax(tl + 1e-6, dim=-1)
            log_p = F.log_softmax(pl, dim=-1)
            kl = (t_prob * (t_prob.clamp_min(1e-8).log() - log_p)).sum(dim=-1)
            return (kl * mask).sum() / denom

        def bce_at(offset, mask=m, denom=None, pos_weight_factor=5.0):
            denom = denom if denom is not None else mask.sum().clamp(min=1)
            pe = pred_tensor[:, :, offset]
            te = target_tensor[:, :, offset]
            tgt = torch.sigmoid(te)
            pw = 1.0 + (pos_weight_factor - 1.0) * tgt
            bce = F.binary_cross_entropy_with_logits(
                pe, tgt, reduction="none") * pw
            return (bce * mask).sum() / denom

        # ====== SHARED heads (all tokens) ======
        loss_type = ce_at(o["type"], N_TOKEN_TYPES)
        loss_color = ce_at(o["color"], N_PALETTE)
        loss_material = kl_at(o["material"], N_MATERIAL_VFX_TAGS)
        loss_decoration = kl_at(o["decoration"], N_MATERIAL_VFX_TAGS)
        loss_is_end = bce_at(o["is_end"], pos_weight_factor=5.0)
        # extra termination penalty: at true_end_pos, prob_end should be ~1
        prob_end = torch.sigmoid(pred_tensor[:, :, o["is_end"]])
        true_end_pos = m.sum(dim=-1).long() - 1
        idx = torch.arange(B, device=pred_tensor.device)
        prob_at_end = prob_end[idx, true_end_pos.clamp(min=0)]
        loss_is_end = loss_is_end + 0.5 * -torch.log(prob_at_end.clamp(min=1e-6)).mean()

        # ====== STROKE heads (only on stroke tokens) ======
        loss_s_start = ce_at(o["s_start_log"], N_ANCHOR_LOGITS,
                              mask=is_target_stroke, denom=m_stroke)
        loss_s_end = ce_at(o["s_end_log"], N_ANCHOR_LOGITS,
                            mask=is_target_stroke, denom=m_stroke)
        loss_s_bezier = mse_at(o["s_bezier"], 4,
                                mask=is_target_stroke, denom=m_stroke)
        loss_s_width = mse_at(o["s_width"], WIDTH_SEGMENTS,
                               mask=is_target_stroke, denom=m_stroke)
        loss_s_tension = mse_at(o["s_tension"], 1,
                                 mask=is_target_stroke, denom=m_stroke)
        loss_s_uv_free = (
            mse_at(o["s_start_uv"], 2, mask=is_target_stroke, denom=m_stroke) +
            mse_at(o["s_end_uv"], 2, mask=is_target_stroke, denom=m_stroke)
        ) * 0.5

        # ====== PANEL heads (only on panel tokens) ======
        loss_p_boundary = mse_at(o["p_boundary"], 2 * PANEL_BOUNDARY_POINTS,
                                  mask=is_target_panel, denom=m_panel)
        # anchor_active: sigmoid per anchor
        anc_pred = pred_tensor[:, :, o["p_anchors"]:o["p_anchors"] + N_ANCHORS]
        anc_target = torch.sigmoid(target_tensor[:, :, o["p_anchors"]:o["p_anchors"] + N_ANCHORS])
        bce_anc = F.binary_cross_entropy_with_logits(
            anc_pred, anc_target, reduction="none").mean(dim=-1)  # (B, T)
        loss_p_anchors = (bce_anc * is_target_panel).sum() / m_panel
        loss_p_fabric = ce_at(o["p_fabric"], N_FABRICS,
                               mask=is_target_panel, denom=m_panel)
        loss_p_layer = ce_at(o["p_layer"], N_LAYER_ROLES,
                              mask=is_target_panel, denom=m_panel)

        # ====== total ======
        total = (loss_type + loss_color
                 + loss_material + loss_decoration + loss_is_end
                 + loss_s_start + loss_s_end + loss_s_bezier
                 + loss_s_width + loss_s_tension + loss_s_uv_free
                 + loss_p_boundary + loss_p_anchors + loss_p_fabric + loss_p_layer)
        return {
            "total": total,
            "type": loss_type, "color": loss_color,
            "material": loss_material, "decoration": loss_decoration,
            "is_end": loss_is_end,
            "s_start": loss_s_start, "s_end": loss_s_end,
            "s_bezier": loss_s_bezier, "s_width": loss_s_width,
            "s_tension": loss_s_tension, "s_uv_free": loss_s_uv_free,
            "p_boundary": loss_p_boundary, "p_anchors": loss_p_anchors,
            "p_fabric": loss_p_fabric, "p_layer": loss_p_layer,
        }

    def kl_loss(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        """Standard VAE KL divergence to N(0, I)."""
        return -0.5 * (1 + logvar - mu.pow(2) - logvar.exp()).sum(dim=-1).mean()

    # ─── decode helpers ───────────────────────────────────────────────

    def decode_strokes(self, stroke_tensor: torch.Tensor,
                        enforce_anchored: bool = True):
        """(B, T, D) tensor -> batch of stroke lists."""
        return decode_batch(stroke_tensor, enforce_anchored=enforce_anchored)


# ─── smoke test ────────────────────────────────────────────────────────

def _smoke():
    print("─── DesignGeneratorV3 smoke ───")
    torch.manual_seed(0)
    gen = DesignGeneratorV3()
    n_params = sum(p.numel() for p in gen.parameters())
    print(f"total parameters: {n_params:,} (~{n_params / 1e6:.2f} M)")
    print(f"  tag_bank:  {sum(p.numel() for p in gen.tag_bank.parameters()):,}")
    print(f"  decoder:   {sum(p.numel() for p in gen.decoder.parameters()):,}")

    # Random fake brief embeddings (B=2)
    brief_emb = torch.randn(2, SBERT_DIM)
    out = gen(brief_emb, noise_sigma=1.0)
    print(f"\noutput shapes:")
    print(f"  style_mu      = {tuple(out.style_mu.shape)}")
    print(f"  style_latent  = {tuple(out.style_latent.shape)}")
    print(f"  anchor_plan   = {tuple(out.anchor_plan.shape)}")
    print(f"  stroke_tensor = {tuple(out.stroke_tensor.shape)}")
    print(f"  head_input.var ≈ {out.head_input.var().item():.3f} (target ~1.0)")

    # Teacher-forced inference
    from v3.stroke_schema import example_avant_garde_harness
    teacher = example_avant_garde_harness()
    enc, mask = encode_design(teacher)
    teacher_batch = enc.unsqueeze(0).expand(2, -1, -1).clone()
    mask_batch = mask.unsqueeze(0).expand(2, -1).clone()
    out2 = gen(brief_emb, teacher_tokens=teacher_batch)
    losses = gen.imitation_loss(out2.stroke_tensor, teacher_batch, mask_batch)
    print(f"\nteacher-forced imitation losses (random-init, untrained):")
    for k, v in losses.items():
        print(f"  {k:<10} = {v.item():.3f}")
    kl = gen.kl_loss(out2.style_mu, out2.style_logvar)
    print(f"  kl         = {kl.item():.3f}")

    # Decode autoregressive output
    decoded = gen.decode_strokes(out.stroke_tensor)
    print(f"\nautoregressive decoded:")
    for b, strokes in enumerate(decoded):
        # find first is_end if any
        end_at = next((i for i, s in enumerate(strokes) if s.is_end), len(strokes))
        print(f"  batch[{b}]: {len(strokes)} strokes, "
              f"first_is_end={end_at if end_at < len(strokes) else 'none'}")

    # Backward pass (sanity)
    losses["total"].backward()
    grad_norm = sum(p.grad.norm().item() ** 2 for p in gen.parameters()
                    if p.grad is not None) ** 0.5
    print(f"\nbackward OK, grad-norm = {grad_norm:.3f}")
    print("\n✓ smoke test passed")


if __name__ == "__main__":
    _smoke()
