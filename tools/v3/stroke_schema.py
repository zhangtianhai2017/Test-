"""
v3 Stroke Schema — the variable-length fabric-stroke output format that
replaces v2's rigid cup/bottom/strap categorical heads.

Per docs/design/2026-05-27_schema_redesign_v3.md §4.4.

Each design = sequence of N strokes (N ≤ MAX_STROKES, terminated by <END>).
Each stroke = a single piece of fabric ribbon described by:
  - start anchor   (one of 10 body anchors, OR free UV point)
  - end anchor     (one of 10 body anchors, OR free UV point)
  - 4 Bezier control points (in body-cylindrical UV)
  - width profile (3 segments: start / mid / end widths in cm)
  - tension       (0 = full drape, 1 = body-hugging)
  - color_id      (one of 256 palette entries)
  - material_mix  (soft distribution over 189 material_vfx tags)
  - decoration_mix (soft distribution over 189 material_vfx tags)
  - is_end token  (terminates the sequence)

Coherence rule (Phase-1 fix):
  at least one of {start_anchor, end_anchor} MUST be a body anchor (not free UV).
  This is what prevents Phase-1's "fabric floating in space" failure.

This module is dependency-free (no torch). The decoder produces tensors of
the layouts defined here; conversion to/from tensors lives in
v3/stroke_tensor.py to keep this file pure-Python data definition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Sequence

import math


# ─── Anchor system ──────────────────────────────────────────────────────

class Anchor(IntEnum):
    """10 named body anchors.

    The first 8 are the v2-era anatomy anchors (sternum / underbust /
    waist L/R / hip L/R / shoulder L/R). collarbone and neck_back are
    new in v3 to support halter / choker / ribbon-trailing designs.

    UV coordinates are in body-cylindrical UV space:
      u ∈ [0,1] runs anti-clockwise around the body
        (u=0   = back center,
         u=0.25 = right side,
         u=0.5 = front center,
         u=0.75 = left side)
      v ∈ [0,1] runs bottom-to-top
        (v=0 ≈ ankles, v=1 ≈ top of head)
    """
    SHOULDER_L      = 0
    SHOULDER_R      = 1
    COLLARBONE      = 2
    NECK_BACK       = 3
    STERNUM         = 4
    UNDERBUST       = 5
    WAIST_L         = 6
    WAIST_R         = 7
    HIP_L           = 8
    HIP_R           = 9

    # used by the head as the "free UV" option (no anchor)
    FREE_UV         = 10


N_ANCHORS = 10
N_ANCHOR_LOGITS = N_ANCHORS + 1   # +1 for FREE_UV


# Default UV coordinates for each anchor.
# These are *fallback* coordinates used when the body mesh anatomy
# landmarks haven't been resolved yet (e.g. NN training, where the
# decoder works in pure UV space without knowing the specific body).
# At render time, ANCHOR_UV is overridden by the body-mesh-derived
# anchor positions from v3/anchor_resolver.py.
#
# (u, v) — see Anchor docstring for axis convention.
DEFAULT_ANCHOR_UV: dict[Anchor, tuple[float, float]] = {
    Anchor.SHOULDER_L:  (0.75, 0.83),
    Anchor.SHOULDER_R:  (0.25, 0.83),
    Anchor.COLLARBONE:  (0.50, 0.80),
    Anchor.NECK_BACK:   (0.00, 0.82),
    Anchor.STERNUM:     (0.50, 0.74),
    Anchor.UNDERBUST:   (0.50, 0.68),
    Anchor.WAIST_L:     (0.70, 0.58),
    Anchor.WAIST_R:     (0.30, 0.58),
    Anchor.HIP_L:       (0.70, 0.48),
    Anchor.HIP_R:       (0.30, 0.48),
}


# ─── Stroke data ────────────────────────────────────────────────────────

MAX_STROKES = 16                  # per docs/design/v3 §9 D5
N_BEZIER_CTRL = 4                 # 4 control points (2 endpoints + 2 mid)
WIDTH_SEGMENTS = 3                # start / mid / end widths
N_PALETTE = 256                   # color palette size (per discussion D8 palette)
N_MATERIAL_VFX_TAGS = 189         # from tag_data.py axis "material_vfx"


@dataclass
class Stroke:
    """A single fabric-ribbon stroke. UV in body-cylindrical space."""

    # Endpoint specification — exactly one of (anchor, free_uv) per end.
    start_anchor: Anchor                              # Anchor or FREE_UV
    start_uv:     tuple[float, float] | None = None   # used iff start_anchor == FREE_UV
    end_anchor:   Anchor = Anchor.FREE_UV
    end_uv:       tuple[float, float] | None = None

    # Path shape — 2 internal Bezier control points (in UV)
    bezier_internal: tuple[tuple[float, float],
                           tuple[float, float]] = ((0.5, 0.5), (0.5, 0.5))

    # Width along stroke (cm). 0 width means stroke vanishes at that point.
    width_profile: tuple[float, float, float] = (3.0, 3.0, 3.0)  # start / mid / end

    # 0 = pure gravity drape, 1 = tight body-hug. Renderer uses this to
    # interpolate between body-surface ribbon (1) and floating ribbon (0).
    tension: float = 1.0

    # Color: one of N_PALETTE palette entries. Palette table is owned by
    # v3/palette.py (not yet built — placeholder for now).
    color_id: int = 0

    # Soft distributions over material_vfx tags (n=189).
    # Stored as (tag_indices, weights) for sparsity. Empty = silent.
    material_mix: list[tuple[int, float]] = field(default_factory=list)
    decoration_mix: list[tuple[int, float]] = field(default_factory=list)

    # Sequence terminator. The decoder sets this on the last stroke.
    # In a stroke list, all strokes before <END> have is_end=False.
    is_end: bool = False

    def is_anchored(self) -> bool:
        """Phase-1 coherence rule: at least one end must be a body anchor."""
        return (self.start_anchor != Anchor.FREE_UV) or \
               (self.end_anchor != Anchor.FREE_UV)

    def resolve_endpoints_uv(self,
                              anchor_uv: dict[Anchor, tuple[float, float]]
                              = None) -> tuple[tuple[float, float],
                                                tuple[float, float]]:
        """Compute concrete (start_uv, end_uv) using the given anchor map
        (defaults to DEFAULT_ANCHOR_UV)."""
        if anchor_uv is None:
            anchor_uv = DEFAULT_ANCHOR_UV
        s = (self.start_uv if self.start_anchor == Anchor.FREE_UV
             else anchor_uv[self.start_anchor])
        e = (self.end_uv if self.end_anchor == Anchor.FREE_UV
             else anchor_uv[self.end_anchor])
        if s is None:
            raise ValueError("start_anchor=FREE_UV but start_uv is None")
        if e is None:
            raise ValueError("end_anchor=FREE_UV but end_uv is None")
        return s, e

    def bezier_points_uv(self,
                          anchor_uv: dict[Anchor, tuple[float, float]]
                          = None) -> list[tuple[float, float]]:
        """Return the 4 Bezier control points in UV.
        [start, ctrl1, ctrl2, end] — what _arc_tube / equivalent expects."""
        s, e = self.resolve_endpoints_uv(anchor_uv)
        c1, c2 = self.bezier_internal
        return [s, c1, c2, e]

    def sample_path(self,
                     n_samples: int = 32,
                     anchor_uv: dict[Anchor, tuple[float, float]] = None
                     ) -> list[tuple[float, float]]:
        """Sample the Bezier path at n_samples points (uniform t).
        Returns list of (u, v)."""
        p0, p1, p2, p3 = self.bezier_points_uv(anchor_uv)

        def bez(t):
            mt = 1 - t
            u = (mt**3 * p0[0] + 3 * mt**2 * t * p1[0]
                 + 3 * mt * t**2 * p2[0] + t**3 * p3[0])
            v = (mt**3 * p0[1] + 3 * mt**2 * t * p1[1]
                 + 3 * mt * t**2 * p2[1] + t**3 * p3[1])
            return (u, v)
        return [bez(i / (n_samples - 1)) for i in range(n_samples)]

    def width_at(self, t: float) -> float:
        """Interpolated width (cm) at param t ∈ [0, 1] along the stroke."""
        w0, w1, w2 = self.width_profile
        if t <= 0.5:
            tt = t * 2
            return (1 - tt) * w0 + tt * w1
        else:
            tt = (t - 0.5) * 2
            return (1 - tt) * w1 + tt * w2


# ─── Validation ────────────────────────────────────────────────────────

def stroke_to_dict(s: Stroke) -> dict:
    """Serialize a Stroke to a JSON-safe dict."""
    return {
        "start_anchor": int(s.start_anchor),
        "start_uv": list(s.start_uv) if s.start_uv is not None else None,
        "end_anchor": int(s.end_anchor),
        "end_uv": list(s.end_uv) if s.end_uv is not None else None,
        "bezier_internal": [list(s.bezier_internal[0]),
                             list(s.bezier_internal[1])],
        "width_profile": list(s.width_profile),
        "tension": float(s.tension),
        "color_id": int(s.color_id),
        "material_mix": [[int(i), float(w)] for i, w in s.material_mix],
        "decoration_mix": [[int(i), float(w)] for i, w in s.decoration_mix],
        "is_end": bool(s.is_end),
    }


def stroke_from_dict(d: dict) -> Stroke:
    """Deserialize a Stroke from a JSON dict."""
    return Stroke(
        start_anchor=Anchor(d["start_anchor"]),
        start_uv=tuple(d["start_uv"]) if d["start_uv"] is not None else None,
        end_anchor=Anchor(d["end_anchor"]),
        end_uv=tuple(d["end_uv"]) if d["end_uv"] is not None else None,
        bezier_internal=(tuple(d["bezier_internal"][0]),
                          tuple(d["bezier_internal"][1])),
        width_profile=tuple(d["width_profile"]),
        tension=float(d["tension"]),
        color_id=int(d["color_id"]),
        material_mix=[(int(i), float(w)) for i, w in d.get("material_mix", [])],
        decoration_mix=[(int(i), float(w)) for i, w in d.get("decoration_mix", [])],
        is_end=bool(d.get("is_end", False)),
    )


def validate_stroke(stroke: Stroke) -> list[str]:
    """Return list of error messages (empty list = valid)."""
    errs = []
    if not stroke.is_anchored():
        errs.append("coherence: both ends are FREE_UV (no body anchor)")
    if not (0 <= stroke.color_id < N_PALETTE):
        errs.append(f"color_id {stroke.color_id} not in [0, {N_PALETTE})")
    for label, w in zip(["start", "mid", "end"], stroke.width_profile):
        if not (0 <= w <= 30):  # 30 cm = full hip wrap-around segment
            errs.append(f"width_{label}={w} out of [0, 30]")
    if not (0 <= stroke.tension <= 1):
        errs.append(f"tension={stroke.tension} out of [0, 1]")
    # bezier in [0,1] (allow slight overshoot for drape)
    s, e = stroke.resolve_endpoints_uv()
    for label, (u, v) in [("start", s), ("end", e),
                           ("ctrl1", stroke.bezier_internal[0]),
                           ("ctrl2", stroke.bezier_internal[1])]:
        if not (-0.1 <= u <= 1.1):
            errs.append(f"{label} u={u} out of [-0.1, 1.1]")
        if not (-0.1 <= v <= 1.1):
            errs.append(f"{label} v={v} out of [-0.1, 1.1]")
    return errs


def validate_design(strokes: Sequence[Stroke]) -> list[str]:
    """Validate a full design (list of strokes). Returns all errors."""
    errs = []
    if len(strokes) == 0:
        errs.append("design has 0 strokes")
        return errs
    if len(strokes) > MAX_STROKES:
        errs.append(f"design has {len(strokes)} > MAX_STROKES={MAX_STROKES}")
    if not strokes[-1].is_end:
        errs.append("last stroke should have is_end=True")
    for i, s in enumerate(strokes[:-1]):
        if s.is_end:
            errs.append(f"stroke[{i}] has is_end=True but is not the last stroke")
    for i, s in enumerate(strokes):
        for e in validate_stroke(s):
            errs.append(f"stroke[{i}]: {e}")
    return errs


# ─── Hand-crafted reference designs (for smoke tests) ─────────────────

def example_classical_bikini() -> list[Stroke]:
    """A reference 'classical triangle bikini' as 4 strokes — proves the
    new schema can still express the old vocabulary."""
    return [
        # Left cup
        Stroke(
            start_anchor=Anchor.SHOULDER_L, end_anchor=Anchor.STERNUM,
            bezier_internal=((0.65, 0.78), (0.55, 0.74)),
            width_profile=(0.5, 8.0, 0.5),
            tension=0.9, color_id=0,
        ),
        # Right cup
        Stroke(
            start_anchor=Anchor.SHOULDER_R, end_anchor=Anchor.STERNUM,
            bezier_internal=((0.35, 0.78), (0.45, 0.74)),
            width_profile=(0.5, 8.0, 0.5),
            tension=0.9, color_id=0,
        ),
        # Bottom front
        Stroke(
            start_anchor=Anchor.HIP_L, end_anchor=Anchor.HIP_R,
            bezier_internal=((0.6, 0.45), (0.4, 0.45)),
            width_profile=(1.0, 9.0, 1.0),
            tension=0.95, color_id=0,
        ),
        # Bottom back
        Stroke(
            start_anchor=Anchor.HIP_L, end_anchor=Anchor.HIP_R,
            bezier_internal=((0.85, 0.48), (0.15, 0.48)),
            width_profile=(1.0, 6.0, 1.0),
            tension=0.95, color_id=0, is_end=True,
        ),
    ]


def example_avant_garde_harness() -> list[Stroke]:
    """A 'cross-body harness' — only expressible in v3, not v2."""
    return [
        # Diagonal strap: left shoulder → right hip
        Stroke(
            start_anchor=Anchor.SHOULDER_L, end_anchor=Anchor.HIP_R,
            bezier_internal=((0.55, 0.70), (0.45, 0.55)),
            width_profile=(2.0, 1.5, 2.0),
            tension=0.95, color_id=1,
        ),
        # Diagonal strap: right shoulder → left hip
        Stroke(
            start_anchor=Anchor.SHOULDER_R, end_anchor=Anchor.HIP_L,
            bezier_internal=((0.45, 0.70), (0.55, 0.55)),
            width_profile=(2.0, 1.5, 2.0),
            tension=0.95, color_id=1,
        ),
        # Underbust band
        Stroke(
            start_anchor=Anchor.WAIST_L, end_anchor=Anchor.WAIST_R,
            bezier_internal=((0.55, 0.66), (0.45, 0.66)),
            width_profile=(3.0, 3.0, 3.0),
            tension=1.0, color_id=1,
        ),
        # Hip wrap
        Stroke(
            start_anchor=Anchor.HIP_L, end_anchor=Anchor.HIP_R,
            bezier_internal=((0.6, 0.46), (0.4, 0.46)),
            width_profile=(2.0, 5.0, 2.0),
            tension=0.95, color_id=1, is_end=True,
        ),
    ]


# ─── Smoke test ────────────────────────────────────────────────────────

def _smoke():
    print("─── stroke_schema smoke ───")
    for name, fn in [
        ("classical_bikini", example_classical_bikini),
        ("avant_garde_harness", example_avant_garde_harness),
    ]:
        strokes = fn()
        errs = validate_design(strokes)
        path = strokes[0].sample_path(n_samples=8)
        print(f"\n{name}:")
        print(f"  n_strokes = {len(strokes)}")
        print(f"  valid = {len(errs) == 0}")
        if errs:
            for e in errs:
                print(f"    ! {e}")
        print(f"  stroke[0].sampled_path[:3] = {[f'({u:.2f}, {v:.2f})' for u, v in path[:3]]}")
        for i, s in enumerate(strokes):
            sp, ep = s.resolve_endpoints_uv()
            print(f"  stroke[{i}]: {s.start_anchor.name} -> {s.end_anchor.name}  "
                  f"({sp[0]:.2f},{sp[1]:.2f}) → ({ep[0]:.2f},{ep[1]:.2f})  "
                  f"w=({s.width_profile[0]:.1f},{s.width_profile[1]:.1f},{s.width_profile[2]:.1f})"
                  f"  end={s.is_end}")


if __name__ == "__main__":
    _smoke()
