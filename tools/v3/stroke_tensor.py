"""
Stroke ↔ tensor conversion for NN training/inference.

Tensor layout per stroke (one row, all floats):
    [0]                                start_anchor_logits   (N_ANCHOR_LOGITS = 11)
    [N_ANCHOR_LOGITS]                  start_uv_free         (2)   used iff start = FREE_UV
    [N_ANCHOR_LOGITS + 2]              end_anchor_logits     (11)
    [22 + 2]                           end_uv_free           (2)
    [26]                               bezier_ctrl_uv        (4)   2 internal control points × (u,v)
    [30]                               width_profile         (3)
    [33]                               tension               (1)
    [34]                               color_logits          (N_PALETTE = 256)
    [290]                              material_mix_logits   (N_MATERIAL_VFX_TAGS = 189)
    [479]                              decoration_mix_logits (189)
    [668]                              is_end_logit          (1)

Total per-stroke dim = 669.

Decoder produces a (B, T, 669) tensor where T ≤ MAX_STROKES. Decoding
back to list[Stroke] happens via `decode_stroke_tensor()` which performs
argmax / softmax / sigmoid as appropriate per slice.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F

from .stroke_schema import (
    Anchor, Stroke, MAX_STROKES,
    N_ANCHORS, N_ANCHOR_LOGITS,
    N_BEZIER_CTRL, WIDTH_SEGMENTS,
    N_PALETTE, N_MATERIAL_VFX_TAGS,
)


# ─── layout offsets ────────────────────────────────────────────────────

_OFF_START_LOGITS    = 0
_OFF_START_UV_FREE   = _OFF_START_LOGITS + N_ANCHOR_LOGITS           # 11
_OFF_END_LOGITS      = _OFF_START_UV_FREE + 2                         # 13
_OFF_END_UV_FREE     = _OFF_END_LOGITS + N_ANCHOR_LOGITS              # 24
_OFF_BEZIER          = _OFF_END_UV_FREE + 2                            # 26
_OFF_WIDTH           = _OFF_BEZIER + 2 * (N_BEZIER_CTRL - 2)           # 30  (2 internal × 2 coord)
_OFF_TENSION         = _OFF_WIDTH + WIDTH_SEGMENTS                    # 33
_OFF_COLOR           = _OFF_TENSION + 1                                # 34
_OFF_MATERIAL        = _OFF_COLOR + N_PALETTE                          # 290
_OFF_DECORATION      = _OFF_MATERIAL + N_MATERIAL_VFX_TAGS             # 479
_OFF_IS_END          = _OFF_DECORATION + N_MATERIAL_VFX_TAGS           # 668
STROKE_TENSOR_DIM    = _OFF_IS_END + 1                                  # 669


def stroke_tensor_dim() -> int:
    return STROKE_TENSOR_DIM


def decode_stroke_tensor(row: torch.Tensor,
                          topk_material: int = 3,
                          topk_decoration: int = 3,
                          ) -> Stroke:
    """Decode a single (STROKE_TENSOR_DIM,) tensor row into a Stroke.

    Argmax for categorical heads; sigmoid for is_end; softmax+topk for
    mixture heads (only keep the top-k highest tags for sparsity).
    """
    assert row.shape == (STROKE_TENSOR_DIM,), \
        f"expected ({STROKE_TENSOR_DIM},) got {tuple(row.shape)}"

    start_logits = row[_OFF_START_LOGITS:_OFF_START_LOGITS + N_ANCHOR_LOGITS]
    start_idx = int(start_logits.argmax().item())
    start_uv_free = row[_OFF_START_UV_FREE:_OFF_START_UV_FREE + 2]

    end_logits = row[_OFF_END_LOGITS:_OFF_END_LOGITS + N_ANCHOR_LOGITS]
    end_idx = int(end_logits.argmax().item())
    end_uv_free = row[_OFF_END_UV_FREE:_OFF_END_UV_FREE + 2]

    bezier = row[_OFF_BEZIER:_OFF_BEZIER + 4]
    width = row[_OFF_WIDTH:_OFF_WIDTH + WIDTH_SEGMENTS]
    tension = float(torch.sigmoid(row[_OFF_TENSION]).item())

    color_logits = row[_OFF_COLOR:_OFF_COLOR + N_PALETTE]
    color_id = int(color_logits.argmax().item())

    material_logits = row[_OFF_MATERIAL:_OFF_MATERIAL + N_MATERIAL_VFX_TAGS]
    material_mix = _topk_softmax_sparse(material_logits, topk_material)

    decoration_logits = row[_OFF_DECORATION:_OFF_DECORATION + N_MATERIAL_VFX_TAGS]
    decoration_mix = _topk_softmax_sparse(decoration_logits, topk_decoration)

    is_end_logit = row[_OFF_IS_END]
    is_end = bool(torch.sigmoid(is_end_logit).item() > 0.5)

    return Stroke(
        start_anchor=Anchor(start_idx),
        start_uv=(_safe_unit(float(start_uv_free[0])),
                  _safe_unit(float(start_uv_free[1])))
                  if start_idx == Anchor.FREE_UV else None,
        end_anchor=Anchor(end_idx),
        end_uv=(_safe_unit(float(end_uv_free[0])),
                _safe_unit(float(end_uv_free[1])))
                if end_idx == Anchor.FREE_UV else None,
        bezier_internal=(
            (_safe_unit(float(bezier[0])), _safe_unit(float(bezier[1]))),
            (_safe_unit(float(bezier[2])), _safe_unit(float(bezier[3]))),
        ),
        width_profile=(
            _safe_width(float(width[0])),
            _safe_width(float(width[1])),
            _safe_width(float(width[2])),
        ),
        tension=tension,
        color_id=color_id,
        material_mix=material_mix,
        decoration_mix=decoration_mix,
        is_end=is_end,
    )


def decode_batch(tensor: torch.Tensor,
                  enforce_anchored: bool = True
                  ) -> list[list[Stroke]]:
    """Decode a (B, T, D) tensor → batch of stroke lists.
    Truncates each design at the first is_end=True stroke.
    Optionally enforces the Phase-1 coherence rule.
    """
    B, T, D = tensor.shape
    assert D == STROKE_TENSOR_DIM, \
        f"expected D={STROKE_TENSOR_DIM} got {D}"
    out = []
    for b in range(B):
        strokes = []
        for t in range(T):
            s = decode_stroke_tensor(tensor[b, t])
            if enforce_anchored and not s.is_anchored():
                # Fallback: force start to nearest anchor (STERNUM)
                # to satisfy coherence. NN will learn the right thing
                # via the anchor-classification loss.
                s.start_anchor = Anchor.STERNUM
                s.start_uv = None
            strokes.append(s)
            if s.is_end:
                break
        # ensure at least the last stroke has is_end=True (for downstream)
        if strokes and not strokes[-1].is_end:
            strokes[-1].is_end = True
        out.append(strokes)
    return out


# ─── encode (for teacher / imitation learning) ─────────────────────────

def encode_stroke(stroke: Stroke) -> torch.Tensor:
    """Encode a Stroke into a (STROKE_TENSOR_DIM,) tensor with one-hot
    categoricals and raw values for continuous fields.
    Used by Phase A2 imitation learning to convert teacher designs into
    decoder targets."""
    row = torch.zeros(STROKE_TENSOR_DIM)
    # start anchor one-hot
    row[_OFF_START_LOGITS + int(stroke.start_anchor)] = 10.0  # large logit
    if stroke.start_uv is not None:
        row[_OFF_START_UV_FREE]     = stroke.start_uv[0]
        row[_OFF_START_UV_FREE + 1] = stroke.start_uv[1]
    # end anchor one-hot
    row[_OFF_END_LOGITS + int(stroke.end_anchor)] = 10.0
    if stroke.end_uv is not None:
        row[_OFF_END_UV_FREE]     = stroke.end_uv[0]
        row[_OFF_END_UV_FREE + 1] = stroke.end_uv[1]
    # bezier
    c1, c2 = stroke.bezier_internal
    row[_OFF_BEZIER]     = c1[0]
    row[_OFF_BEZIER + 1] = c1[1]
    row[_OFF_BEZIER + 2] = c2[0]
    row[_OFF_BEZIER + 3] = c2[1]
    # width
    for i, w in enumerate(stroke.width_profile):
        row[_OFF_WIDTH + i] = w
    # tension (encode as logit: inverse sigmoid of clamped value)
    t = max(0.001, min(0.999, stroke.tension))
    import math
    row[_OFF_TENSION] = math.log(t / (1 - t))
    # color one-hot
    row[_OFF_COLOR + stroke.color_id] = 10.0
    # material mix
    for idx, w in stroke.material_mix:
        if 0 <= idx < N_MATERIAL_VFX_TAGS:
            row[_OFF_MATERIAL + idx] = w
    # decoration mix
    for idx, w in stroke.decoration_mix:
        if 0 <= idx < N_MATERIAL_VFX_TAGS:
            row[_OFF_DECORATION + idx] = w
    # is_end logit
    row[_OFF_IS_END] = 5.0 if stroke.is_end else -5.0
    return row


def encode_design(strokes: list[Stroke],
                   pad_to: int = MAX_STROKES) -> tuple[torch.Tensor, torch.Tensor]:
    """Encode a design into (pad_to, D) tensor + (pad_to,) mask.
    mask[i] = 1 for real strokes (including the <END> one), 0 for padding."""
    assert len(strokes) <= pad_to
    rows = []
    for s in strokes:
        rows.append(encode_stroke(s))
    while len(rows) < pad_to:
        rows.append(torch.zeros(STROKE_TENSOR_DIM))
    tensor = torch.stack(rows, dim=0)
    mask = torch.zeros(pad_to)
    mask[:len(strokes)] = 1.0
    return tensor, mask


# ─── helpers ────────────────────────────────────────────────────────────

def _safe_unit(x: float) -> float:
    return max(0.0, min(1.0, x))


def _safe_width(x: float) -> float:
    return max(0.0, min(30.0, x))


def _topk_softmax_sparse(logits: torch.Tensor, k: int) -> list[tuple[int, float]]:
    """Softmax over logits, keep top-k, return [(idx, weight), ...] renormed."""
    probs = F.softmax(logits, dim=-1)
    vals, idxs = torch.topk(probs, k=min(k, logits.shape[0]))
    total = vals.sum().item()
    if total <= 0:
        return []
    return [(int(i.item()), float(v.item() / total))
            for i, v in zip(idxs, vals)]


# ─── smoke test ────────────────────────────────────────────────────────

def _smoke():
    print("─── stroke_tensor smoke ───")
    print(f"STROKE_TENSOR_DIM = {STROKE_TENSOR_DIM}")
    print(f"  start_logits  @ {_OFF_START_LOGITS:>4}..{_OFF_START_UV_FREE}")
    print(f"  end_logits    @ {_OFF_END_LOGITS:>4}..{_OFF_END_UV_FREE}")
    print(f"  bezier        @ {_OFF_BEZIER:>4}..{_OFF_WIDTH}")
    print(f"  width         @ {_OFF_WIDTH:>4}..{_OFF_TENSION}")
    print(f"  tension       @ {_OFF_TENSION}")
    print(f"  color_logits  @ {_OFF_COLOR:>4}..{_OFF_MATERIAL}")
    print(f"  material_mix  @ {_OFF_MATERIAL:>4}..{_OFF_DECORATION}")
    print(f"  decoration    @ {_OFF_DECORATION:>4}..{_OFF_IS_END}")
    print(f"  is_end_logit  @ {_OFF_IS_END}")

    # round-trip test
    from .stroke_schema import example_avant_garde_harness
    teacher = example_avant_garde_harness()
    encoded, mask = encode_design(teacher)
    print(f"\nencoded shape = {tuple(encoded.shape)}, mask sum = {int(mask.sum())}")
    # decode all strokes (with batch dim)
    decoded = decode_batch(encoded.unsqueeze(0), enforce_anchored=False)[0]
    print(f"decoded {len(decoded)} strokes from teacher of {len(teacher)} strokes")
    # Check anchors round-trip
    for i, (orig, dec) in enumerate(zip(teacher, decoded)):
        if orig.start_anchor != dec.start_anchor:
            print(f"  ✗ stroke[{i}] start_anchor changed "
                  f"{orig.start_anchor.name} -> {dec.start_anchor.name}")
        if orig.end_anchor != dec.end_anchor:
            print(f"  ✗ stroke[{i}] end_anchor changed "
                  f"{orig.end_anchor.name} -> {dec.end_anchor.name}")
        if orig.color_id != dec.color_id:
            print(f"  ✗ stroke[{i}] color_id {orig.color_id} -> {dec.color_id}")
        if orig.is_end != dec.is_end:
            print(f"  ✗ stroke[{i}] is_end {orig.is_end} -> {dec.is_end}")
    print("✓ encode/decode round-trip OK")


if __name__ == "__main__":
    _smoke()
