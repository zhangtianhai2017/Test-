"""
Tag Embedding Bank — converts the 692-tag pool into a learnable
continuous latent space (per docs/design/2026-05-27_schema_redesign_v3.md §4.2).

Three primary operations:
  1.  init_from_sbert()         — initialize all tag embeddings from sbert(name+def)
  2.  sample_dirichlet_mix(ax)  — sample a soft tag mixture within an axis
                                  (training-time anti "snap-to-nearest-tag" mechanism)
  3.  encode_tag_ids(ids)        — produce a style vector from explicit tag IDs
                                  (inference-time hard-conditioning path)

EMA rollback mechanism (step_ema_rollback) is called after each train step to
softly pull learned embeddings back toward the sbert-init anchor, preventing
semantic drift while still allowing task-specific fine-tuning.
"""
import math
import os
import sys
from typing import Iterable

import torch
import torch.nn as nn
import torch.nn.functional as F

# Make tag_data importable whether run from project root or tools/
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
from tag_data import TAGS, AXES, Tag  # noqa: E402


# Match the model used in design_generator.SentenceTransformerEncoder
# (multilingual so it handles the EN / CN bilingual tag names natively).
SBERT_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
SBERT_DIM = 384


class TagEmbeddingBank(nn.Module):
    """A learnable per-tag embedding bank with sbert init + EMA rollback.

    Args:
        dim: target embedding dimension (default 128, matches style_latent dim)
        ema_alpha: at each step_ema_rollback() call, pull learned embeddings
                   `alpha` of the way back toward the init anchor.
                   0.001 means very slow drift (recommended for stable training).
    """

    def __init__(self, dim: int = 128, ema_alpha: float = 1e-3):
        super().__init__()
        self.dim = dim
        self.ema_alpha = ema_alpha
        self.n_tags = len(TAGS)

        # learned bank
        self.embeddings = nn.Parameter(torch.zeros(self.n_tags, dim))
        # frozen anchor (sbert init) used by EMA pull
        self.register_buffer(
            "init_anchor", torch.zeros(self.n_tags, dim))
        # is bank initialized
        self.register_buffer(
            "is_initialized", torch.tensor(False))

        # axis bookkeeping
        self.id_to_idx = {t.id: i for i, t in enumerate(TAGS)}
        self.axis_indices: dict[str, list[int]] = {
            ax: [i for i, t in enumerate(TAGS) if t.axis == ax]
            for ax in AXES
        }
        # projector sbert(384) -> dim(128). Kept trainable too in case dim < 384.
        self.sbert_proj = nn.Linear(SBERT_DIM, dim, bias=False)

    # ─── init ──────────────────────────────────────────────────────────

    def init_from_sbert(self,
                        sbert=None,
                        include_definition: bool = True,
                        include_examples: bool = False,
                        normalize: bool = True,
                        verbose: bool = True):
        """Initialize all tag embeddings from sbert(text-of-tag).

        text-of-tag = "{en} / {cn}" optionally augmented with definition
        and/or examples for richer semantic grounding.

        sbert: a SentenceTransformer instance, or None to load default.
        """
        from sentence_transformers import SentenceTransformer
        if sbert is None:
            if verbose:
                print(f"[TagEmbeddingBank] loading sbert: {SBERT_MODEL_NAME}")
            sbert = SentenceTransformer(SBERT_MODEL_NAME)

        texts = []
        for t in TAGS:
            parts = [f"{t.en} / {t.cn}"]
            if include_definition and t.definition:
                parts.append(t.definition)
            if include_examples and t.examples:
                parts.append(f"e.g. {t.examples}")
            texts.append(" — ".join(parts))

        if verbose:
            print(f"[TagEmbeddingBank] encoding {len(texts)} tags...")
        with torch.no_grad():
            emb_384 = sbert.encode(texts, convert_to_tensor=True,
                                    show_progress_bar=False)
            emb_384 = emb_384.to(self.sbert_proj.weight.device)
            # project sbert(384) -> bank dim
            x = self.sbert_proj(emb_384)
            if normalize:
                x = F.normalize(x, dim=-1)
            self.embeddings.data.copy_(x)
            self.init_anchor.data.copy_(x)
            self.is_initialized.fill_(True)

        if verbose:
            per_axis = {ax: len(self.axis_indices[ax]) for ax in AXES}
            print(f"[TagEmbeddingBank] initialized — dim={self.dim} "
                  f"axes={per_axis}")

    # ─── training-time hooks ───────────────────────────────────────────

    @torch.no_grad()
    def step_ema_rollback(self):
        """Pull learned embeddings slightly toward init anchor.

        Call after each optimizer step to prevent semantic drift.
        With alpha=1e-3 and 200 steps, the bank retains ~82% of any
        learned displacement while still being firmly anchored.
        """
        if not bool(self.is_initialized):
            return
        a = self.ema_alpha
        self.embeddings.data.mul_(1.0 - a).add_(self.init_anchor, alpha=a)

    # ─── sampling / encoding ───────────────────────────────────────────

    def sample_dirichlet_mix(self,
                              axis: str,
                              alpha: float = 0.5,
                              n_samples: int = 1,
                              device: str | torch.device = None
                              ) -> torch.Tensor:
        """Sample n_samples style vectors as soft Dirichlet mixtures over
        all tags in `axis`. Returns (n_samples, dim).

        alpha < 1 → sparse mixtures (few dominant tags)  ← recommended
        alpha = 1 → uniform over simplex
        alpha > 1 → smooth dense mixtures
        """
        if axis not in self.axis_indices:
            raise KeyError(f"unknown axis: {axis} (valid: {AXES})")
        idx = self.axis_indices[axis]
        n = len(idx)
        if n == 0:
            raise ValueError(f"axis {axis} has 0 tags")
        device = device or self.embeddings.device
        # build mix weights
        mix = torch.distributions.Dirichlet(
            torch.full((n,), float(alpha), device=device)
        ).sample((n_samples,))  # (n_samples, n)
        tag_embs = self.embeddings[idx]  # (n, dim)
        return mix @ tag_embs  # (n_samples, dim)

    def sample_all_axes_mix(self,
                             alpha: float = 0.5,
                             n_samples: int = 1,
                             axis_weights: dict[str, float] | None = None
                             ) -> torch.Tensor:
        """Sample style vectors by mixing across all 6 axes.

        Returns (n_samples, dim) where each is sum of per-axis Dirichlet
        mixtures weighted by axis_weights (default uniform 1/6).
        """
        if axis_weights is None:
            axis_weights = {ax: 1.0 / len(AXES) for ax in AXES}
        out = None
        for ax in AXES:
            w = axis_weights.get(ax, 0.0)
            if w <= 0:
                continue
            sub = self.sample_dirichlet_mix(ax, alpha=alpha, n_samples=n_samples)
            out = sub * w if out is None else out + sub * w
        return out

    def encode_tag_ids(self, tag_ids: Iterable[str]) -> torch.Tensor:
        """Hard-encode a list of tag IDs as their mean embedding (dim,)."""
        idx = [self.id_to_idx[tid] for tid in tag_ids if tid in self.id_to_idx]
        if not idx:
            raise ValueError(f"no matching tags found in pool: {list(tag_ids)}")
        return self.embeddings[idx].mean(dim=0)

    def encode_tag_dict(self, tag_weights: dict[str, float]) -> torch.Tensor:
        """Weighted-mean encoding from {tag_id: weight}."""
        idx, wts = [], []
        for tid, w in tag_weights.items():
            if tid in self.id_to_idx and w > 0:
                idx.append(self.id_to_idx[tid])
                wts.append(w)
        if not idx:
            raise ValueError(
                f"no matching positive-weight tags: {tag_weights}")
        t = torch.tensor(wts, device=self.embeddings.device)
        t = t / t.sum()
        return (t.unsqueeze(1) * self.embeddings[idx]).sum(dim=0)

    # ─── introspection ─────────────────────────────────────────────────

    def summary(self) -> str:
        lines = [f"TagEmbeddingBank dim={self.dim} n_tags={self.n_tags} "
                 f"initialized={bool(self.is_initialized)}"]
        for ax in AXES:
            n = len(self.axis_indices[ax])
            lines.append(f"  {ax:<22} {n}")
        return "\n".join(lines)


# ─── smoke test ────────────────────────────────────────────────────────

def _smoke():
    print("─── TagEmbeddingBank smoke test ───")
    bank = TagEmbeddingBank(dim=128)
    print(bank.summary())

    # Init from sbert
    bank.init_from_sbert(include_definition=True, verbose=True)
    print()
    print(bank.summary())

    # Dirichlet sample on art_style
    z = bank.sample_dirichlet_mix("art_style", alpha=0.5, n_samples=4)
    print(f"\nDirichlet sample (art_style, n=4): shape={tuple(z.shape)}, "
          f"mean_norm={z.norm(dim=-1).mean().item():.4f}")

    # All axes mix
    z2 = bank.sample_all_axes_mix(alpha=0.5, n_samples=4)
    print(f"All-axes mix (n=4): shape={tuple(z2.shape)}, "
          f"mean_norm={z2.norm(dim=-1).mean().item():.4f}")

    # Direct encode known tag IDs
    try:
        v = bank.encode_tag_ids([
            "art_style__cyberpunk",
            "cultural__hanfu_tang",
            "silhouette__sculptural",
        ])
        print(f"Direct encode 3 tags: shape={tuple(v.shape)}, "
              f"norm={v.norm().item():.4f}")
    except KeyError as e:
        print(f"  [skip direct encode test] {e}")

    # EMA rollback
    before = bank.embeddings.data.clone()
    bank.embeddings.data += torch.randn_like(bank.embeddings) * 0.1
    moved = (bank.embeddings.data - before).norm().item()
    bank.step_ema_rollback()
    after_pull = (bank.embeddings.data - before).norm().item()
    print(f"\nEMA rollback (alpha={bank.ema_alpha}): "
          f"perturbed by {moved:.3f}, after one step {after_pull:.3f} "
          f"(expected slightly less, by factor (1-alpha))")

    print("\n✓ smoke test passed")


if __name__ == "__main__":
    _smoke()
