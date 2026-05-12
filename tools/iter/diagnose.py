"""
Stage 3 — translate critique JSON into a numeric param delta.

Pure function. The mapping table below is the single source of truth
for "fix_hint -> what number changes by how much". Allowed fix_hints
are a closed set; anything else falls into 'other' which produces no
change but gets logged as an unresolved issue.
"""
from __future__ import annotations
from dataclasses import asdict
from collections import defaultdict


# severity -> step magnitude
_SEV = {"low": 1.0, "med": 2.0, "high": 3.0}


def _scaled(base: float, sev: str) -> float:
    return base * _SEV.get(sev, 1.0)


# fix_hint -> callable(severity) -> partial delta dict
_TABLE: dict[str, callable] = {
    # ----- cup / nipple area -----
    "increase_cup_dome":   lambda s: {"cup_extra_cm":   _scaled(+0.10, s)},
    "decrease_cup_dome":   lambda s: {"cup_extra_cm":   _scaled(-0.08, s)},
    "increase_min_offset": lambda s: {"min_offset_cm":  _scaled(+0.05, s)},
    "decrease_min_offset": lambda s: {"min_offset_cm":  _scaled(-0.04, s)},

    # ----- edge / boundary -----
    "increase_boundary_snap": lambda s: {"boundary_snap": _scaled(+0.05, s)},
    "more_smooth_iters":      lambda s: {"smooth_iters":  _scaled(+3,    s)},
    "less_smooth_iters":      lambda s: {"smooth_iters":  _scaled(-2,    s)},

    # ----- binding (FOE) -----
    "thicken_binding": lambda s: {"binding_thickness_cm": _scaled(+0.05, s)},
    "thinner_binding": lambda s: {"binding_thickness_cm": _scaled(-0.04, s)},
    "raise_binding":   lambda s: {"binding_offset_cm":    _scaled(+0.02, s)},

    # ----- straps -----
    "thicken_strap": lambda s: {"strap_radius_scale": _scaled(+0.10, s)},
    "thinner_strap": lambda s: {"strap_radius_scale": _scaled(-0.08, s)},
    "remove_neck_strap":  lambda s: {"genome_patch": {"top_neck_strap": 0.0}},
    "add_neck_strap":     lambda s: {"genome_patch": {"top_neck_strap": 0.85}},
    "remove_shoulder_strap": lambda s: {"genome_patch": {"top_shoulder_strap": 0.0}},
    "add_shoulder_strap":    lambda s: {"genome_patch": {"top_shoulder_strap": 0.95}},

    # ----- coverage / Genome shape -----
    "widen_back_coverage": lambda s: {"genome_patch": {"top_back_coverage": _scaled(+0.05, s)}},
    "narrow_back_coverage": lambda s: {"genome_patch": {"top_back_coverage": _scaled(-0.05, s)}},
    "raise_front_panel":   lambda s: {"genome_patch": {"bot_front_top_v":  _scaled(+0.03, s)}},
    "lower_front_panel":   lambda s: {"genome_patch": {"bot_front_top_v":  _scaled(-0.03, s)}},
    "widen_front_panel":   lambda s: {"genome_patch": {"bot_front_half_u": _scaled(+0.02, s)}},
    "narrow_front_panel":  lambda s: {"genome_patch": {"bot_front_half_u": _scaled(-0.02, s)}},
    "widen_top_cup":   lambda s: {"genome_patch": {"top_half_u": _scaled(+0.02, s)}},
    "taller_top_cup":  lambda s: {"genome_patch": {"top_half_v": _scaled(+0.02, s)}},
    "raise_top_band":  lambda s: {"genome_patch": {"top_center_v": _scaled(+0.02, s)}},
    "lower_top_band":  lambda s: {"genome_patch": {"top_center_v": _scaled(-0.02, s)}},

    # ----- pattern / texture -----
    "scale_pattern_up":   lambda s: {"genome_patch": {"pattern_scale": _scaled(+0.10, s)}},
    "scale_pattern_down": lambda s: {"genome_patch": {"pattern_scale": _scaled(-0.10, s)}},

    # ----- fabric -----
    "more_wrinkles": lambda s: {"wrinkle_amp_scale": _scaled(+0.30, s)},
    "less_wrinkles": lambda s: {"wrinkle_amp_scale": _scaled(-0.20, s)},

    # ----- shell positioning -----
    "increase_shell_offset": lambda s: {"shell_offset_cm": _scaled(+0.05, s)},
    "decrease_shell_offset": lambda s: {"shell_offset_cm": _scaled(-0.04, s)},

    # ----- weave / fabric grain -----
    "less_weave_grain": lambda s: {"weave_intensity": _scaled(-0.20, s)},
    "more_weave_grain": lambda s: {"weave_intensity": _scaled(+0.15, s)},

    # ----- catch-all -----
    "other": lambda s: {},
}

KNOWN_FIX_HINTS = sorted(_TABLE.keys())


def diagnose(critique: dict) -> tuple[dict, list[dict]]:
    """critique JSON -> (delta dict, unresolved list).

    Aggregates all issues' deltas into a single dict. If the same
    parameter is touched by multiple issues, sum the deltas.
    """
    delta: dict[str, float] = defaultdict(float)
    gp_delta: dict[str, float] = defaultdict(float)
    unresolved: list[dict] = []

    for issue in critique.get("issues", []):
        hint = issue.get("fix_hint", "other")
        sev = issue.get("severity", "low")
        fn = _TABLE.get(hint)
        if fn is None or hint == "other":
            unresolved.append(issue)
            continue
        d = fn(sev)
        for k, v in d.items():
            if k == "genome_patch":
                for gk, gv in v.items():
                    gp_delta[gk] += gv
            else:
                delta[k] += v

    out = dict(delta)
    if gp_delta:
        out["genome_patch"] = dict(gp_delta)
    return out, unresolved
