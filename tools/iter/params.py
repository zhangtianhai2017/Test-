"""
Tunable parameters for the auto-iteration loop.

Everything here is a number we may twist between rounds. Dataclass +
clamp() so deltas can never push us outside safe ranges. Serializable
to JSON for round-by-round audit.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field, fields
import json
import os


# (min, max) bounds for every numeric param. Hard physical / topological
# limits — clamping at apply-time enforces these, so the loop can never
# drive itself into a bad config.
BOUNDS: dict[str, tuple[float, float]] = {
    "smooth_iters":         (0,    40),
    "boundary_snap":        (0.0,  1.0),
    "min_offset_cm":        (0.05, 0.80),
    "cup_extra_cm":         (0.0,  1.20),
    "shell_offset_cm":      (0.10, 0.60),
    "binding_thickness_cm": (0.10, 0.80),
    "binding_offset_cm":    (0.02, 0.20),
    "wrinkle_amp_scale":    (0.0,  3.0),
    "strap_radius_scale":   (0.5,  2.0),
    "weave_intensity":      (0.0,  1.5),
    "cup_dome_depth_cm":    (0.0,  3.0),
    "front_pose_camera":    (0.0,  1.0),
}


@dataclass
class IterParams:
    """Numeric parameters tuned by the loop. Genome overrides go in `genome_patch`.

    Defaults match the post-polish baseline (see garment_polish constants
    + export_garment binding settings).
    """
    smooth_iters: int = 12
    boundary_snap: float = 0.85
    min_offset_cm: float = 0.30
    cup_extra_cm: float = 0.45
    shell_offset_cm: float = 0.30
    binding_thickness_cm: float = 0.40
    binding_offset_cm: float = 0.05
    wrinkle_amp_scale: float = 1.0
    strap_radius_scale: float = 1.0
    weave_intensity: float = 1.0
    cup_dome_depth_cm: float = 0.0
    side_seam_overlay: bool = True
    # Per-Genome overrides applied on top of the seed Genome. Continuous
    # fields are clipped by Genome.clipped(); discrete fields must be
    # valid enum values. We keep this as a flat dict for trivial JSON.
    genome_patch: dict = field(default_factory=dict)

    def clamped(self) -> "IterParams":
        d = asdict(self)
        for k, (lo, hi) in BOUNDS.items():
            if k in d and isinstance(d[k], (int, float)) and not isinstance(d[k], bool):
                v = max(lo, min(hi, d[k]))
                # smooth_iters must stay int
                if k == "smooth_iters":
                    v = int(round(v))
                d[k] = v
        return IterParams(**d)

    def with_delta(self, delta: dict) -> "IterParams":
        """Return a new IterParams with `delta` added (numeric) or merged
        (genome_patch). Always passes through clamped().
        """
        new = asdict(self)
        gp_new = dict(self.genome_patch)
        for k, v in delta.items():
            if k == "genome_patch":
                gp_new.update(v)
                continue
            if k not in new:
                continue
            new[k] = new[k] + v
        new["genome_patch"] = gp_new
        return IterParams(**new).clamped()

    def diff(self, other: "IterParams") -> dict:
        """{ field: (other -> self) numeric deltas + genome diff }."""
        d_self, d_other = asdict(self), asdict(other)
        out = {}
        for k in d_self:
            if k == "genome_patch":
                continue
            if d_self[k] != d_other[k]:
                out[k] = d_self[k] - d_other[k]
        gp_diff = {k: v for k, v in self.genome_patch.items()
                   if other.genome_patch.get(k) != v}
        if gp_diff:
            out["genome_patch"] = gp_diff
        return out

    def to_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "IterParams":
        with open(path) as f:
            data = json.load(f)
        # Drop unknown keys for forward compat.
        valid = {f.name for f in fields(cls)}
        data = {k: v for k, v in data.items() if k in valid}
        return cls(**data)
