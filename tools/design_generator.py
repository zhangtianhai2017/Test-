"""Design Generator — text brief → outfit config tensors.

Per docs/design/2026-05-17_option_D_architecture.md (option D):
- Input: a text brief encoded as a fixed-dim vector
- Network: a learnable MLP (PyTorch) on top of a (frozen) text encoder
- Output: a dict of tensors that
    (a) symbolic_fitness can score directly via autograd
    (b) downstream non-differentiable pipeline can convert into a
        concrete Outfit (sample from logits, plug into the existing
        renderer)

Text-encoder is pluggable. Default = MockTextEncoder (no downloads,
deterministic hash-based), so the generator can be smoke-tested in any
environment. Real choices: SentenceTransformer (multilingual MiniLM) or
CLIP -- loaded lazily so missing deps don't break import.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Text encoders (pluggable)
# ---------------------------------------------------------------------------

class MockTextEncoder:
    """Deterministic hash-derived vector. Same brief -> same vector
    every run. Use this for tests, CI, and bootstrapping; replace with
    a real encoder when training in earnest."""

    def __init__(self, dim: int = 384, seed_salt: int = 0):
        self.dim = dim
        self.seed_salt = seed_salt

    def encode(self, texts: list[str]) -> torch.Tensor:
        out = torch.empty(len(texts), self.dim, dtype=torch.float32)
        for i, t in enumerate(texts):
            h = hashlib.sha256((t + str(self.seed_salt)).encode()).digest()
            rng = np.random.default_rng(int.from_bytes(h[:8], "big"))
            out[i] = torch.from_numpy(
                rng.normal(size=self.dim).astype(np.float32))
        return out


class SentenceTransformerEncoder:
    """Wraps sentence-transformers. Defaults to a multilingual model
    that handles Chinese briefs well. Lazy import so the dep is
    optional."""

    def __init__(self,
                 model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> torch.Tensor:
        with torch.no_grad():
            arr = self.model.encode(texts, convert_to_numpy=True,
                                     normalize_embeddings=True)
        return torch.from_numpy(arr.astype(np.float32))


# ---------------------------------------------------------------------------
# Continuous output spec (name + physical range)
# ---------------------------------------------------------------------------

# Each entry: (name, lo, hi).  Order matters -- it indexes the
# continuous_head output.  Ranges chosen to match what the existing
# pipeline (outfit_to_genome + _enforce_constraints + PRIVACY_SEEDS)
# expects.  Outside these ranges, the symbolic_fitness penalises.
CONTINUOUS_SPECS: list[tuple[str, float, float]] = [
    ("hue",                 0.0,   1.0),
    ("saturation",          0.0,   1.0),
    ("lightness",           0.0,   1.0),
    ("secondary_hue",       0.0,   1.0),
    ("top_center_v",        0.65,  0.85),
    ("top_half_u",          0.05,  0.30),
    ("top_half_v",          0.04,  0.16),
    ("top_inner_u",        -0.05,  0.28),
    ("top_apex_lift",      -0.20,  0.55),
    ("top_underband_dip",  -0.15,  0.20),
    ("bot_front_top_v",     0.20,  0.65),
    ("bot_front_half_u",    0.10,  0.60),
    ("bot_front_leg_curve", 0.10,  0.90),
    ("bot_back_top_v",      0.20,  0.65),
    ("bot_back_half_u",     0.00,  0.50),
    ("asym_amount",         0.0,   1.0),
    ("geom_ratio_pull",     0.0,   1.0),
    ("pattern_scale",       0.0,   1.0),
]


# ---------------------------------------------------------------------------
# Discrete output spec
# ---------------------------------------------------------------------------

# Default sizes match the current library (auto-grow when library changes).
DEFAULT_DISCRETE_SIZES = {
    "archetype": 4,
    "cup":       27,
    "bottom":    10,
    "strap":     16,
    "fabric":    31,
    "accessory": 10,
    "hardware":  10,
    "pattern":   12,    # see verify_ga_uv.PATTERNS
    "weave":     16,    # see render3d_uv._WEAVE_BUILDERS
}


def discrete_sizes_from_library() -> dict[str, int]:
    """Read true sizes from library_data so the generator stays in sync
    when the library grows."""
    try:
        import library_data as ld
        return {
            "archetype": 4,
            "cup":       len(ld.CUP_PIECES),
            "bottom":    len(ld.BOTTOM_PIECES),
            "strap":     len(ld.STRAP_PIECES),
            "fabric":    len(ld.FABRICS),
            "accessory": len(ld.ACCESSORIES),
            "hardware":  len(ld.HARDWARE),
            "pattern":   12,
            "weave":     16,
        }
    except Exception:
        return dict(DEFAULT_DISCRETE_SIZES)


# ---------------------------------------------------------------------------
# Generator NN
# ---------------------------------------------------------------------------

class ResidualMLPBlock(nn.Module):
    """Pre-norm residual MLP block (transformer-style):
       x -> LN -> Linear(h→h) -> GELU -> Linear(h→h) -> Dropout -> +x

    Cheap, stable to deep stacks because of the residual + pre-LN
    structure. Used as the building block for the deep narrow trunk.
    """
    def __init__(self, dim: int, dropout: float = 0.10):
        super().__init__()
        self.ln = nn.LayerNorm(dim)
        self.lin1 = nn.Linear(dim, dim)
        self.lin2 = nn.Linear(dim, dim)
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.drop(self.lin2(F.gelu(self.lin1(self.ln(x)))))


def _multi_layer_head(in_dim: int, out_dim: int, hidden: int = 64,
                       dropout: float = 0.10) -> nn.Module:
    """2-layer MLP head per output target, with LayerNorm + GELU.
    Replaces single-Linear head — gives each output its own small
    'reasoning' net instead of all heads sharing trunk features
    via a single linear projection."""
    return nn.Sequential(
        nn.LayerNorm(in_dim),
        nn.Linear(in_dim, hidden),
        nn.GELU(),
        nn.Dropout(dropout),
        nn.Linear(hidden, out_dim),
    )


class DesignGenerator(nn.Module):
    """Pure-PyTorch generator. text_emb -> outfit-config tensors.

    Architecture (post-2026-05-23 redesign):
      - thin trunk: 8 residual MLP blocks at hidden_dim=128 (16 layers
        total, 2 linears per block) — narrow + deep + residual, the
        ResNet philosophy applied to 1-D inputs. Pre-LN for stable
        deep training.
      - skip connection: concat trunk_out + raw text_emb (kept; this
        was critical for breaking trunk-collapse, see 2026-05-20).
      - each output head: 2-layer MLP with LayerNorm (was 1 linear).
    """

    def __init__(self,
                 text_dim: int = 384,
                 hidden_dim: int = 128,
                 n_hidden_layers: int = 8,    # now = n_residual_blocks
                 discrete_sizes: Optional[dict[str, int]] = None,
                 dropout: float = 0.10,
                 use_skip: bool = True):
        super().__init__()
        self.text_dim = text_dim
        self.hidden_dim = hidden_dim
        self.use_skip = use_skip
        self.discrete_sizes = discrete_sizes or discrete_sizes_from_library()

        # ---- input projection + deep residual trunk ----
        # text_emb (text_dim) -> Linear -> hidden_dim
        # then n_hidden_layers blocks of ResidualMLPBlock(hidden_dim)
        self.input_proj = nn.Linear(text_dim, hidden_dim)
        self.trunk_blocks = nn.ModuleList([
            ResidualMLPBlock(hidden_dim, dropout=dropout)
            for _ in range(n_hidden_layers)
        ])
        # Compatibility: a .trunk attribute that runs the whole stack
        # so existing code (`gen.trunk(emb)` in eval probes) keeps
        # working without modification.
        class _TrunkAdapter(nn.Module):
            def __init__(self, gen):
                super().__init__()
                self.gen = gen
            def forward(self, x):
                h = self.gen.input_proj(x)
                for blk in self.gen.trunk_blocks:
                    h = blk(h)
                return h
        self.trunk = _TrunkAdapter(self)

        # Skip connection: feed text_emb directly into the head layers
        # alongside trunk(h). Without this the trunk can (and empirically
        # does) collapse to ~constant output for all inputs, since RL +
        # symbolic both reward stable "safe" outputs and small weights
        # are the easiest fixed-point (2026-05-20 diagnosis: trunk batch
        # stdev was 0.0012 after 8 iters from sbert input stdev 0.04).
        # The skip path makes the optimum "collapse" require zeroing
        # the head's text_emb columns too — much harder.
        head_in = hidden_dim + (text_dim if use_skip else 0)

        # ---- continuous head (2-layer MLP) ----
        self.continuous_head = _multi_layer_head(
            head_in, len(CONTINUOUS_SPECS), hidden=64, dropout=dropout)
        lo = torch.tensor([s[1] for s in CONTINUOUS_SPECS], dtype=torch.float32)
        hi = torch.tensor([s[2] for s in CONTINUOUS_SPECS], dtype=torch.float32)
        self.register_buffer("cont_lo", lo)
        self.register_buffer("cont_hi", hi)

        # ---- discrete heads (each 2-layer MLP) ----
        self.discrete_heads = nn.ModuleDict({
            name: _multi_layer_head(head_in, n, hidden=64, dropout=dropout)
            for name, n in self.discrete_sizes.items()
        })

    def forward(self, text_emb: torch.Tensor) -> dict[str, torch.Tensor]:
        """text_emb: (B, text_dim)
        Returns dict mapping
          continuous name -> (B,) tensor (in physical range)
          discrete name '<name>_logits' -> (B, n_<name>) tensor
        """
        # Deep narrow trunk: input projection then N residual blocks
        h = self.input_proj(text_emb)
        for blk in self.trunk_blocks:
            h = blk(h)
        h_head = torch.cat([h, text_emb], dim=-1) if self.use_skip else h

        cont_raw = self.continuous_head(h_head)      # (B, n_cont)
        cont = torch.sigmoid(cont_raw) * (self.cont_hi - self.cont_lo) + self.cont_lo
        out: dict[str, torch.Tensor] = {}
        for i, (name, _lo, _hi) in enumerate(CONTINUOUS_SPECS):
            out[name] = cont[..., i]

        for name, head in self.discrete_heads.items():
            out[f"{name}_logits"] = head(h_head)

        return out

    # ---- discrete sampling helpers ----

    @staticmethod
    def gumbel_softmax_sample(logits: torch.Tensor, tau: float = 1.0,
                                hard: bool = False) -> torch.Tensor:
        """Differentiable sample.  If hard=True returns a one-hot but
        with the soft gradient (straight-through estimator)."""
        return torch.nn.functional.gumbel_softmax(logits, tau=tau, hard=hard)

    @staticmethod
    def argmax_sample(logits: torch.Tensor) -> torch.Tensor:
        """Inference-time argmax (no gradient)."""
        return logits.argmax(dim=-1)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def _smoke_test() -> None:
    """Build generator + mock encoder + symbolic fitness, run a
    forward/backward, verify gradients reach EVERY trainable
    parameter."""
    import symbolic_fitness as sf

    torch.manual_seed(0)
    enc = MockTextEncoder(dim=384)
    gen = DesignGenerator(text_dim=384, hidden_dim=128)

    briefs = [
        "summer beach, vibrant pink, classic triangle bikini",
        "elegant bandeau, gold metallic, mediterranean luxury",
        "sport bralette, dark navy, racerback, full coverage",
        "boho macrame, cream, dramatic asymmetry, halter neck",
        "minimalist black one-piece, deep V neckline",
        "tropical floral print, balconette, mid-coverage cheeky",
    ]

    print(f"discrete sizes: {gen.discrete_sizes}")
    print(f"trainable params: "
          f"{sum(p.numel() for p in gen.parameters() if p.requires_grad)}")

    emb = enc.encode(briefs)
    print(f"\ntext embedding shape: {tuple(emb.shape)}")

    config = gen(emb)
    print(f"\noutput keys: {sorted(config.keys())}")
    for k, v in list(config.items())[:5]:
        print(f"  {k:24s} shape={tuple(v.shape)} "
              f"range=[{v.min().item():.3f}, {v.max().item():.3f}]")

    # Score with symbolic fitness
    sym = sf.total_fitness(config)
    print(f"\nfitness per brief: {sym['total'].detach().numpy()}")
    print(f"mean fitness:      {sym['total'].mean().item():.3f}")

    # Verify gradients flow to every parameter
    loss = -sym["total"].mean()
    loss.backward()
    n_grad, n_no_grad = 0, 0
    for name, p in gen.named_parameters():
        if p.grad is None or p.grad.abs().sum().item() == 0:
            n_no_grad += 1
        else:
            n_grad += 1
    print(f"\n[phase 1] params with non-zero grad (continuous-only loss): "
          f"{n_grad} / {n_grad + n_no_grad}")
    print(f"  expected: continuous head + trunk get gradients, discrete "
          f"heads don't (no path through loss)")

    # ---- phase 2: re-forward + add a slot-compat term so discrete heads ---
    gen.zero_grad(set_to_none=True)
    config2 = gen(emb)                         # fresh forward, fresh graph
    cup_logits    = config2["cup_logits"]
    fabric_logits = config2["fabric_logits"]
    compat = torch.ones(cup_logits.shape[-1], fabric_logits.shape[-1])
    sym2 = sf.total_fitness(config2,
                              compat_matrices={"cup_fabric": compat})
    loss2 = -sym2["total"].mean()
    loss2.backward()
    n_grad2 = sum(1 for _, p in gen.named_parameters()
                  if p.grad is not None and p.grad.abs().sum().item() > 0)
    total = sum(1 for _ in gen.parameters())
    print(f"\n[phase 2] with cup_fabric compat term: {n_grad2}/{total} "
          f"params get gradient")
    print(f"  expected: continuous head + trunk + cup_head + fabric_head "
          f"(rest of discrete heads still inactive until their loss is added)")

    # Verify discrete-head sampling helpers work
    cup_logits = config["cup_logits"]
    soft = DesignGenerator.gumbel_softmax_sample(cup_logits)
    hard = DesignGenerator.gumbel_softmax_sample(cup_logits, hard=True)
    am   = DesignGenerator.argmax_sample(cup_logits)
    print(f"\ncup sampling check:")
    print(f"  soft (gumbel) shape={tuple(soft.shape)} sum_per_row="
          f"{soft.sum(dim=-1).detach().numpy()}")
    print(f"  hard (gumbel ST) shape={tuple(hard.shape)} sum_per_row="
          f"{hard.sum(dim=-1).detach().numpy()}")
    print(f"  argmax (inference) shape={tuple(am.shape)} values="
          f"{am.detach().numpy()}")


if __name__ == "__main__":
    _smoke_test()
