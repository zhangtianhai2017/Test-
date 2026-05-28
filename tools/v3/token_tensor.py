"""
Token tensor layout (v3.1) — replaces v3 stroke_tensor.

A Token can be either a Panel or a Stroke. NN output per step is a
single dense vector of TOKEN_TENSOR_DIM = 709 floats:

  [shared block]
    type_logits          (2)     0..2     panel=0, stroke=1
    color_logits         (256)   2..258   one of 256 palette
    material_mix_logits  (189)   258..447 soft mix over material_vfx
    decoration_mix_logits(189)   447..636 soft mix over material_vfx
    is_end_logit         (1)     636..637 sigmoid

  [stroke block — used only when type=stroke]
    start_anchor_logits  (11)    637..648
    start_uv_free        (2)     648..650
    end_anchor_logits    (11)    650..661
    end_uv_free          (2)     661..663
    bezier_internal      (4)     663..667
    width_profile        (3)     667..670
    tension_logit        (1)     670..671

  [panel block — used only when type=panel]
    boundary_uv          (12)    671..683   6 (u,v) points
    anchor_active_logits (10)    683..693   sigmoid per anchor
    fabric_id_logits     (12)    693..705   one of 12 fabrics
    layer_role_logits    (4)     705..709   shell/lining/padding/trim

Design principle: panel and stroke share color/material/decoration/is_end.
Type decides which type-specific block matters. Loss masks the inactive
block to zero contribution.
"""
from __future__ import annotations

import math
import torch
import torch.nn.functional as F

from .stroke_schema import (
    Anchor, Stroke, Panel, MAX_STROKES,
    N_ANCHORS, N_ANCHOR_LOGITS, WIDTH_SEGMENTS,
    N_PALETTE, N_MATERIAL_VFX_TAGS, PANEL_BOUNDARY_POINTS,
    TOKEN_TYPE_PANEL, TOKEN_TYPE_STROKE,
)

# fabric / layer_role catalogs (12 fabrics, 4 layer roles)
FABRIC_IDS = [
    "F_ECONYL_PLAIN_LIGHT", "F_ECONYL_PLAIN_HEAVY", "F_QNOVA_RIBBED",
    "F_VIRGIN_VELVET", "F_HUNZA_CRINKLE", "F_MISSONI_SHINY_KNIT",
    "F_MESH_LINING", "F_POWERMESH_LINING", "F_FOAM_CUP_3MM",
    "F_CROCHET_COTTON", "F_BIOPOLYMER_PLAIN", "F_AMNI_SOUL_RIBBED",
]
N_FABRICS = len(FABRIC_IDS)
LAYER_ROLES = ["shell", "lining", "padding", "trim"]
N_LAYER_ROLES = len(LAYER_ROLES)
N_TOKEN_TYPES = 2


# ─── layout offsets ───────────────────────────────────────────────────

# Shared block
_OFF_TYPE         = 0
_OFF_COLOR        = _OFF_TYPE + N_TOKEN_TYPES                 # 2
_OFF_MATERIAL     = _OFF_COLOR + N_PALETTE                    # 258
_OFF_DECORATION   = _OFF_MATERIAL + N_MATERIAL_VFX_TAGS       # 447
_OFF_IS_END       = _OFF_DECORATION + N_MATERIAL_VFX_TAGS     # 636
_END_SHARED       = _OFF_IS_END + 1                           # 637

# Stroke block
_OFF_S_START_LOG  = _END_SHARED                                # 637
_OFF_S_START_UV   = _OFF_S_START_LOG + N_ANCHOR_LOGITS         # 648
_OFF_S_END_LOG    = _OFF_S_START_UV + 2                        # 650
_OFF_S_END_UV     = _OFF_S_END_LOG + N_ANCHOR_LOGITS           # 661
_OFF_S_BEZIER     = _OFF_S_END_UV + 2                          # 663
_OFF_S_WIDTH      = _OFF_S_BEZIER + 4                          # 667
_OFF_S_TENSION    = _OFF_S_WIDTH + WIDTH_SEGMENTS              # 670
_END_STROKE       = _OFF_S_TENSION + 1                         # 671

# Panel block
_OFF_P_BOUNDARY   = _END_STROKE                                # 671
_OFF_P_ANCHORS    = _OFF_P_BOUNDARY + 2 * PANEL_BOUNDARY_POINTS  # 683
_OFF_P_FABRIC     = _OFF_P_ANCHORS + N_ANCHORS                 # 693
_OFF_P_LAYER      = _OFF_P_FABRIC + N_FABRICS                  # 705
_END_PANEL        = _OFF_P_LAYER + N_LAYER_ROLES               # 709

TOKEN_TENSOR_DIM = _END_PANEL  # 709


def token_tensor_dim() -> int:
    return TOKEN_TENSOR_DIM


# ─── encode ────────────────────────────────────────────────────────────

def _set_one_hot(row: torch.Tensor, offset: int, idx: int, n: int,
                 magnitude: float = 10.0):
    """Place a high logit at offset+idx to encode a categorical target."""
    if 0 <= idx < n:
        row[offset + idx] = magnitude


def encode_token(tok) -> torch.Tensor:
    """Encode a single Panel or Stroke into a (TOKEN_TENSOR_DIM,) tensor."""
    row = torch.zeros(TOKEN_TENSOR_DIM)
    if isinstance(tok, Panel):
        _set_one_hot(row, _OFF_TYPE, TOKEN_TYPE_PANEL, N_TOKEN_TYPES)
        _set_one_hot(row, _OFF_COLOR, tok.color_id, N_PALETTE)
        for idx, w in tok.material_mix:
            if 0 <= idx < N_MATERIAL_VFX_TAGS:
                row[_OFF_MATERIAL + idx] = w
        for idx, w in tok.decoration_mix:
            if 0 <= idx < N_MATERIAL_VFX_TAGS:
                row[_OFF_DECORATION + idx] = w
        row[_OFF_IS_END] = 5.0 if tok.is_end else -5.0
        # panel block
        for i, (u, v) in enumerate(tok.boundary_uv[:PANEL_BOUNDARY_POINTS]):
            row[_OFF_P_BOUNDARY + 2 * i]     = u
            row[_OFF_P_BOUNDARY + 2 * i + 1] = v
        active_anchors = set(tok.anchors)
        for a in active_anchors:
            if 0 <= int(a) < N_ANCHORS:
                row[_OFF_P_ANCHORS + int(a)] = 5.0
        if tok.fabric_id in FABRIC_IDS:
            _set_one_hot(row, _OFF_P_FABRIC,
                         FABRIC_IDS.index(tok.fabric_id), N_FABRICS)
        else:
            _set_one_hot(row, _OFF_P_FABRIC, 0, N_FABRICS)   # default
        if tok.layer_role in LAYER_ROLES:
            _set_one_hot(row, _OFF_P_LAYER,
                         LAYER_ROLES.index(tok.layer_role), N_LAYER_ROLES)
        else:
            _set_one_hot(row, _OFF_P_LAYER, 0, N_LAYER_ROLES)  # "shell"
        return row

    if isinstance(tok, Stroke):
        _set_one_hot(row, _OFF_TYPE, TOKEN_TYPE_STROKE, N_TOKEN_TYPES)
        _set_one_hot(row, _OFF_COLOR, tok.color_id, N_PALETTE)
        for idx, w in tok.material_mix:
            if 0 <= idx < N_MATERIAL_VFX_TAGS:
                row[_OFF_MATERIAL + idx] = w
        for idx, w in tok.decoration_mix:
            if 0 <= idx < N_MATERIAL_VFX_TAGS:
                row[_OFF_DECORATION + idx] = w
        row[_OFF_IS_END] = 5.0 if tok.is_end else -5.0
        # stroke block
        _set_one_hot(row, _OFF_S_START_LOG, int(tok.start_anchor), N_ANCHOR_LOGITS)
        if tok.start_uv is not None:
            row[_OFF_S_START_UV]     = tok.start_uv[0]
            row[_OFF_S_START_UV + 1] = tok.start_uv[1]
        _set_one_hot(row, _OFF_S_END_LOG, int(tok.end_anchor), N_ANCHOR_LOGITS)
        if tok.end_uv is not None:
            row[_OFF_S_END_UV]     = tok.end_uv[0]
            row[_OFF_S_END_UV + 1] = tok.end_uv[1]
        c1, c2 = tok.bezier_internal
        row[_OFF_S_BEZIER]     = c1[0]
        row[_OFF_S_BEZIER + 1] = c1[1]
        row[_OFF_S_BEZIER + 2] = c2[0]
        row[_OFF_S_BEZIER + 3] = c2[1]
        for i, w in enumerate(tok.width_profile):
            row[_OFF_S_WIDTH + i] = w
        t = max(0.001, min(0.999, tok.tension))
        row[_OFF_S_TENSION] = math.log(t / (1 - t))
        return row

    raise TypeError(f"unknown token type: {type(tok)}")


def encode_design(tokens, pad_to: int = MAX_STROKES
                   ) -> tuple[torch.Tensor, torch.Tensor]:
    """Encode list[Token] → (pad_to, TOKEN_TENSOR_DIM) tensor + (pad_to,) mask."""
    assert len(tokens) <= pad_to
    rows = [encode_token(t) for t in tokens]
    while len(rows) < pad_to:
        rows.append(torch.zeros(TOKEN_TENSOR_DIM))
    tensor = torch.stack(rows, dim=0)
    mask = torch.zeros(pad_to)
    mask[:len(tokens)] = 1.0
    return tensor, mask


# ─── decode ────────────────────────────────────────────────────────────

def _safe_unit(x: float) -> float:
    return max(0.0, min(1.0, x))


def _safe_width(x: float) -> float:
    return max(0.0, min(30.0, x))


def _topk_softmax_sparse(logits: torch.Tensor, k: int) -> list[tuple[int, float]]:
    probs = F.softmax(logits, dim=-1)
    vals, idxs = torch.topk(probs, k=min(k, logits.shape[0]))
    total = vals.sum().item()
    if total <= 0:
        return []
    return [(int(i.item()), float(v.item() / total))
            for i, v in zip(idxs, vals)]


def decode_token(row: torch.Tensor):
    """Decode a single (TOKEN_TENSOR_DIM,) tensor row.
    Returns Panel or Stroke based on argmax(type)."""
    assert row.shape == (TOKEN_TENSOR_DIM,), \
        f"expected ({TOKEN_TENSOR_DIM},) got {tuple(row.shape)}"

    # Shared decode
    type_logits = row[_OFF_TYPE:_OFF_TYPE + N_TOKEN_TYPES]
    tok_type = int(type_logits.argmax().item())

    color_id = int(row[_OFF_COLOR:_OFF_COLOR + N_PALETTE].argmax().item())
    material_mix = _topk_softmax_sparse(
        row[_OFF_MATERIAL:_OFF_MATERIAL + N_MATERIAL_VFX_TAGS], 3)
    decoration_mix = _topk_softmax_sparse(
        row[_OFF_DECORATION:_OFF_DECORATION + N_MATERIAL_VFX_TAGS], 3)
    is_end = bool(torch.sigmoid(row[_OFF_IS_END]).item() > 0.5)

    if tok_type == TOKEN_TYPE_PANEL:
        # decode panel block
        boundary = []
        for i in range(PANEL_BOUNDARY_POINTS):
            u = _safe_unit(float(row[_OFF_P_BOUNDARY + 2 * i].item()))
            v = _safe_unit(float(row[_OFF_P_BOUNDARY + 2 * i + 1].item()))
            boundary.append((u, v))
        anchor_logits = row[_OFF_P_ANCHORS:_OFF_P_ANCHORS + N_ANCHORS]
        anchor_probs = torch.sigmoid(anchor_logits)
        anchors = [Anchor(i) for i, p in enumerate(anchor_probs)
                   if float(p.item()) > 0.5]
        fabric_idx = int(row[_OFF_P_FABRIC:_OFF_P_FABRIC + N_FABRICS]
                         .argmax().item())
        layer_idx = int(row[_OFF_P_LAYER:_OFF_P_LAYER + N_LAYER_ROLES]
                        .argmax().item())
        return Panel(
            boundary_uv=boundary,
            anchors=anchors,
            color_id=color_id,
            material_mix=material_mix,
            decoration_mix=decoration_mix,
            fabric_id=FABRIC_IDS[fabric_idx],
            layer_role=LAYER_ROLES[layer_idx],
            is_end=is_end,
        )

    # Stroke decode
    start_logits = row[_OFF_S_START_LOG:_OFF_S_START_LOG + N_ANCHOR_LOGITS]
    start_idx = int(start_logits.argmax().item())
    end_logits = row[_OFF_S_END_LOG:_OFF_S_END_LOG + N_ANCHOR_LOGITS]
    end_idx = int(end_logits.argmax().item())
    bezier = row[_OFF_S_BEZIER:_OFF_S_BEZIER + 4]
    width = row[_OFF_S_WIDTH:_OFF_S_WIDTH + WIDTH_SEGMENTS]
    tension = float(torch.sigmoid(row[_OFF_S_TENSION]).item())
    start_uv = row[_OFF_S_START_UV:_OFF_S_START_UV + 2]
    end_uv = row[_OFF_S_END_UV:_OFF_S_END_UV + 2]

    return Stroke(
        start_anchor=Anchor(start_idx),
        start_uv=(_safe_unit(float(start_uv[0])),
                  _safe_unit(float(start_uv[1])))
                  if start_idx == Anchor.FREE_UV else None,
        end_anchor=Anchor(end_idx),
        end_uv=(_safe_unit(float(end_uv[0])),
                _safe_unit(float(end_uv[1])))
                if end_idx == Anchor.FREE_UV else None,
        bezier_internal=(
            (_safe_unit(float(bezier[0])), _safe_unit(float(bezier[1]))),
            (_safe_unit(float(bezier[2])), _safe_unit(float(bezier[3]))),
        ),
        width_profile=(_safe_width(float(width[0])),
                       _safe_width(float(width[1])),
                       _safe_width(float(width[2]))),
        tension=tension,
        color_id=color_id,
        material_mix=material_mix,
        decoration_mix=decoration_mix,
        is_end=is_end,
    )


def decode_batch(tensor: torch.Tensor, enforce_anchored: bool = True) -> list[list]:
    """(B, T, TOKEN_TENSOR_DIM) → batch of token lists."""
    B, T, D = tensor.shape
    assert D == TOKEN_TENSOR_DIM, \
        f"expected D={TOKEN_TENSOR_DIM} got {D}"
    out = []
    for b in range(B):
        tokens = []
        for t in range(T):
            tok = decode_token(tensor[b, t])
            # Phase-1 coherence rule applies only to strokes
            if enforce_anchored and isinstance(tok, Stroke) and not tok.is_anchored():
                tok.start_anchor = Anchor.STERNUM
                tok.start_uv = None
            tokens.append(tok)
            if tok.is_end:
                break
        # ensure terminator
        if tokens and not tokens[-1].is_end:
            tokens[-1].is_end = True
        out.append(tokens)
    return out


# ─── offset accessors (for the loss decomposition) ───────────────────

def offsets():
    """Return all offset constants as a dict (for design_generator_v3 loss)."""
    return {
        "type": _OFF_TYPE, "color": _OFF_COLOR,
        "material": _OFF_MATERIAL, "decoration": _OFF_DECORATION,
        "is_end": _OFF_IS_END,
        "s_start_log": _OFF_S_START_LOG, "s_start_uv": _OFF_S_START_UV,
        "s_end_log": _OFF_S_END_LOG, "s_end_uv": _OFF_S_END_UV,
        "s_bezier": _OFF_S_BEZIER, "s_width": _OFF_S_WIDTH,
        "s_tension": _OFF_S_TENSION,
        "p_boundary": _OFF_P_BOUNDARY, "p_anchors": _OFF_P_ANCHORS,
        "p_fabric": _OFF_P_FABRIC, "p_layer": _OFF_P_LAYER,
    }


# ─── smoke ────────────────────────────────────────────────────────────

def _smoke():
    print("─── token_tensor smoke ───")
    print(f"TOKEN_TENSOR_DIM = {TOKEN_TENSOR_DIM}")
    print("layout:")
    print(f"  shared    : type@{_OFF_TYPE}..{_OFF_COLOR}, color@{_OFF_COLOR}..{_OFF_MATERIAL}, "
          f"material@{_OFF_MATERIAL}..{_OFF_DECORATION}, "
          f"decoration@{_OFF_DECORATION}..{_OFF_IS_END}, is_end@{_OFF_IS_END}")
    print(f"  stroke    : {_END_SHARED}..{_END_STROKE}  (33 floats)")
    print(f"  panel     : {_END_STROKE}..{_END_PANEL}  (38 floats)")
    # Round-trip test on the 9 references
    from .stroke_schema import all_reference_designs_v31
    refs = all_reference_designs_v31()
    print(f"\nround-trip test on {len(refs)} v3.1 refs:")
    for name, tokens in refs.items():
        t, m = encode_design(tokens)
        decoded = decode_batch(t.unsqueeze(0), enforce_anchored=False)[0]
        # cut to true end
        end_at = next((i + 1 for i, x in enumerate(decoded) if x.is_end),
                      len(decoded))
        decoded = decoded[:end_at]
        n_match_type = sum(1 for a, b in zip(tokens, decoded)
                           if type(a) is type(b))
        print(f"  {name:<22} {len(tokens)}→{len(decoded)} tokens, "
              f"type-match {n_match_type}/{len(tokens)}")
    print("\n✓ token_tensor smoke OK")


if __name__ == "__main__":
    _smoke()
