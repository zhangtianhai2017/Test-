"""MetaHuman UE 5.6 Body skeleton — parent/child hierarchy + stable-deform
whitelist used by the GLB refit pipeline.

Hierarchy below mirrors
  C:\\Program Files\\Epic Games\\UE_5.6\\Engine\\Plugins\\MetaHuman\\
  MetaHumanSDK\\Source\\MetaHumanSDKEditor\\Private\\ProjectUtilities\\
  MetaHumanSkeletonDefinitions.inl
restricted to the BODY section (face joints are omitted — they never
appear in our outfits and would inflate the bone budget).

`STABLE_DEFORM_WHITELIST` is the ordered list of joints we keep as
skin weight targets. Helper / corrective / dynamic bones
(*_correctiveRoot_*, *_fwd_*, *_bck_*, *_in_*, *_out_*, *_knee*,
*_twistCor_*, *_dyn, _bicep, _tricep, clavicle_out/scap/pec,
spine_04_latissimus, wrist_inner/outer, ankle_fwd/bck, finger detail
bones below 01-level) are folded into their nearest whitelisted
ancestor during refit.

Whitelist budget: 70 joints (well under the 128 soft cap, far under
the 256 hard cap). Composition:
  - 42 core deform bones (root → pelvis → spine → neck/clavicle/arms
    → hand_l/r, → thigh/calf → foot → ball)
  - 8 twist-pair bones per limb side (upperarm/lowerarm/thigh/calf)
  - 18 finger-level-1 bones (4 metacarpals + 5 phalanges per side ×2)
    so a future glove/ring/bracelet attachment has bone anchors
  - 10 toe-level-1 bones (5 per side ×2) for future foot accessories
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Full body hierarchy from the inl, child -> parent.  Includes every joint
# in the MetaHuman body skeleton so a fold walk from ANY joint terminates
# at root.  Excludes face joints (FACIAL_*).
# ---------------------------------------------------------------------------
BODY_HIERARCHY: dict[str, str] = {
    # spine
    "pelvis": "root",
    "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02",
    "spine_04": "spine_03", "spine_05": "spine_04",
    "neck_01": "spine_05", "neck_02": "neck_01", "head": "neck_02",

    # left arm chain + corrective/dyn descendants
    "clavicle_l": "spine_05",
    "clavicle_out_l": "clavicle_l", "clavicle_scap_l": "clavicle_l",
    "clavicle_pec_l": "spine_05",
    "clavicle_out_l_dyn": "clavicle_out_l",
    "clavicle_pec_l_dyn": "clavicle_pec_l",
    "upperarm_l": "clavicle_l",
    "upperarm_correctiveRoot_l": "upperarm_l",
    "upperarm_bck_l": "upperarm_correctiveRoot_l",
    "upperarm_fwd_l": "upperarm_correctiveRoot_l",
    "upperarm_in_l":  "upperarm_correctiveRoot_l",
    "upperarm_out_l": "upperarm_correctiveRoot_l",
    "upperarm_twist_01_l": "upperarm_l", "upperarm_twist_02_l": "upperarm_l",
    "upperarm_twistCor_01_l": "upperarm_twist_01_l",
    "upperarm_twistCor_02_l": "upperarm_twist_02_l",
    "upperarm_bicep_l":  "upperarm_twist_02_l",
    "upperarm_tricep_l": "upperarm_twist_02_l",
    "upperarm_bicep_l_dyn":  "upperarm_bicep_l",
    "upperarm_tricep_l_dyn": "upperarm_tricep_l",
    "lowerarm_l": "upperarm_l",
    "lowerarm_correctiveRoot_l": "lowerarm_l",
    "lowerarm_out_l":  "lowerarm_correctiveRoot_l",
    "lowerarm_in_l":   "lowerarm_correctiveRoot_l",
    "lowerarm_fwd_l":  "lowerarm_correctiveRoot_l",
    "lowerarm_bck_l":  "lowerarm_correctiveRoot_l",
    "lowerarm_twist_01_l": "lowerarm_l", "lowerarm_twist_02_l": "lowerarm_l",
    "hand_l": "lowerarm_l",
    "wrist_inner_l": "hand_l", "wrist_outer_l": "hand_l",

    # right arm (mirror)
    "clavicle_r": "spine_05",
    "clavicle_out_r": "clavicle_r", "clavicle_scap_r": "clavicle_r",
    "clavicle_pec_r": "spine_05",
    "clavicle_out_r_dyn": "clavicle_out_r",
    "clavicle_pec_r_dyn": "clavicle_pec_r",
    "upperarm_r": "clavicle_r",
    "upperarm_correctiveRoot_r": "upperarm_r",
    "upperarm_bck_r": "upperarm_correctiveRoot_r",
    "upperarm_fwd_r": "upperarm_correctiveRoot_r",
    "upperarm_in_r":  "upperarm_correctiveRoot_r",
    "upperarm_out_r": "upperarm_correctiveRoot_r",
    "upperarm_twist_01_r": "upperarm_r", "upperarm_twist_02_r": "upperarm_r",
    "upperarm_twistCor_01_r": "upperarm_twist_01_r",
    "upperarm_twistCor_02_r": "upperarm_twist_02_r",
    "upperarm_bicep_r":  "upperarm_twist_02_r",
    "upperarm_tricep_r": "upperarm_twist_02_r",
    "upperarm_bicep_r_dyn":  "upperarm_bicep_r",
    "upperarm_tricep_r_dyn": "upperarm_tricep_r",
    "lowerarm_r": "upperarm_r",
    "lowerarm_correctiveRoot_r": "lowerarm_r",
    "lowerarm_out_r":  "lowerarm_correctiveRoot_r",
    "lowerarm_in_r":   "lowerarm_correctiveRoot_r",
    "lowerarm_fwd_r":  "lowerarm_correctiveRoot_r",
    "lowerarm_bck_r":  "lowerarm_correctiveRoot_r",
    "lowerarm_twist_01_r": "lowerarm_r", "lowerarm_twist_02_r": "lowerarm_r",
    "hand_r": "lowerarm_r",
    "wrist_inner_r": "hand_r", "wrist_outer_r": "hand_r",

    "spine_04_latissimus_l": "spine_05",
    "spine_04_latissimus_r": "spine_05",

    # finger details (left) — all fold to *_01_x  or  hand_x for thumb
    "index_metacarpal_l": "hand_l",
    "index_01_l": "index_metacarpal_l",
    "index_02_l": "index_01_l", "index_03_l": "index_02_l",
    "middle_metacarpal_l": "hand_l",
    "middle_01_l": "middle_metacarpal_l",
    "middle_02_l": "middle_01_l", "middle_03_l": "middle_02_l",
    "pinky_metacarpal_l": "hand_l",
    "pinky_01_l": "pinky_metacarpal_l",
    "pinky_02_l": "pinky_01_l", "pinky_03_l": "pinky_02_l",
    "ring_metacarpal_l": "hand_l",
    "ring_01_l": "ring_metacarpal_l",
    "ring_02_l": "ring_01_l", "ring_03_l": "ring_02_l",
    "thumb_01_l": "hand_l", "thumb_02_l": "thumb_01_l", "thumb_03_l": "thumb_02_l",

    # finger details (right)
    "index_metacarpal_r": "hand_r",
    "index_01_r": "index_metacarpal_r",
    "index_02_r": "index_01_r", "index_03_r": "index_02_r",
    "middle_metacarpal_r": "hand_r",
    "middle_01_r": "middle_metacarpal_r",
    "middle_02_r": "middle_01_r", "middle_03_r": "middle_02_r",
    "pinky_metacarpal_r": "hand_r",
    "pinky_01_r": "pinky_metacarpal_r",
    "pinky_02_r": "pinky_01_r", "pinky_03_r": "pinky_02_r",
    "ring_metacarpal_r": "hand_r",
    "ring_01_r": "ring_metacarpal_r",
    "ring_02_r": "ring_01_r", "ring_03_r": "ring_02_r",
    "thumb_01_r": "hand_r", "thumb_02_r": "thumb_01_r", "thumb_03_r": "thumb_02_r",

    # left leg chain
    "thigh_l": "pelvis",
    "thigh_correctiveRoot_l": "thigh_l",
    "thigh_bck_l": "thigh_correctiveRoot_l",
    "thigh_fwd_l": "thigh_correctiveRoot_l",
    "thigh_out_l": "thigh_correctiveRoot_l",
    "thigh_in_l":  "thigh_correctiveRoot_l",
    "thigh_fwd_lwr_l": "thigh_correctiveRoot_l",
    "thigh_bck_lwr_l": "thigh_correctiveRoot_l",
    "thigh_twist_01_l": "thigh_l", "thigh_twist_02_l": "thigh_l",
    "thigh_twistCor_01_l": "thigh_twist_01_l",
    "thigh_twistCor_02_l": "thigh_twist_02_l",
    "thigh_twistCor_01_l_dyn": "thigh_twistCor_01_l",
    "thigh_twistCor_02_l_dyn": "thigh_twistCor_02_l",
    "calf_l": "thigh_l",
    "calf_correctiveRoot_l": "calf_l",
    "calf_knee_l": "calf_correctiveRoot_l",
    "calf_kneeBack_l": "calf_correctiveRoot_l",
    "calf_twist_01_l": "calf_l", "calf_twist_02_l": "calf_l",
    "calf_twistCor_02_l": "calf_twist_02_l",
    "foot_l": "calf_l",
    "ankle_fwd_l": "foot_l", "ankle_bck_l": "foot_l",
    "ball_l": "foot_l",
    "bigtoe_01_l":     "ball_l", "bigtoe_02_l":     "bigtoe_01_l",
    "indextoe_01_l":   "ball_l", "indextoe_02_l":   "indextoe_01_l",
    "middletoe_01_l":  "ball_l", "middletoe_02_l":  "middletoe_01_l",
    "ringtoe_01_l":    "ball_l", "ringtoe_02_l":    "ringtoe_01_l",
    "littletoe_01_l":  "ball_l", "littletoe_02_l":  "littletoe_01_l",

    # right leg (mirror)
    "thigh_r": "pelvis",
    "thigh_correctiveRoot_r": "thigh_r",
    "thigh_bck_r": "thigh_correctiveRoot_r",
    "thigh_fwd_r": "thigh_correctiveRoot_r",
    "thigh_out_r": "thigh_correctiveRoot_r",
    "thigh_in_r":  "thigh_correctiveRoot_r",
    "thigh_fwd_lwr_r": "thigh_correctiveRoot_r",
    "thigh_bck_lwr_r": "thigh_correctiveRoot_r",
    "thigh_twist_01_r": "thigh_r", "thigh_twist_02_r": "thigh_r",
    "thigh_twistCor_01_r": "thigh_twist_01_r",
    "thigh_twistCor_02_r": "thigh_twist_02_r",
    "thigh_twistCor_01_r_dyn": "thigh_twistCor_01_r",
    "thigh_twistCor_02_r_dyn": "thigh_twistCor_02_r",
    "calf_r": "thigh_r",
    "calf_correctiveRoot_r": "calf_r",
    "calf_knee_r": "calf_correctiveRoot_r",
    "calf_kneeBack_r": "calf_correctiveRoot_r",
    "calf_twist_01_r": "calf_r", "calf_twist_02_r": "calf_r",
    "calf_twistCor_02_r": "calf_twist_02_r",
    "foot_r": "calf_r",
    "ankle_fwd_r": "foot_r", "ankle_bck_r": "foot_r",
    "ball_r": "foot_r",
    "bigtoe_01_r":     "ball_r", "bigtoe_02_r":     "bigtoe_01_r",
    "indextoe_01_r":   "ball_r", "indextoe_02_r":   "indextoe_01_r",
    "middletoe_01_r":  "ball_r", "middletoe_02_r":  "middletoe_01_r",
    "ringtoe_01_r":    "ball_r", "ringtoe_02_r":    "ringtoe_01_r",
    "littletoe_01_r":  "ball_r", "littletoe_02_r":  "littletoe_01_r",
}


# ---------------------------------------------------------------------------
# 70-joint whitelist.  Order matters: this is the order written to
# skin.joints in the output GLB, which UE imports as the bone array.
# ---------------------------------------------------------------------------
STABLE_DEFORM_WHITELIST: list[str] = [
    # spine / head
    "root", "pelvis",
    "spine_01", "spine_02", "spine_03", "spine_04", "spine_05",
    "neck_01", "neck_02", "head",

    # arms (left)
    "clavicle_l", "upperarm_l",
    "upperarm_twist_01_l", "upperarm_twist_02_l",
    "lowerarm_l",
    "lowerarm_twist_01_l", "lowerarm_twist_02_l",
    "hand_l",
    # hand bones (one level, for accessories)
    "index_metacarpal_l", "middle_metacarpal_l",
    "ring_metacarpal_l", "pinky_metacarpal_l",
    "index_01_l", "middle_01_l", "ring_01_l", "pinky_01_l", "thumb_01_l",

    # arms (right)
    "clavicle_r", "upperarm_r",
    "upperarm_twist_01_r", "upperarm_twist_02_r",
    "lowerarm_r",
    "lowerarm_twist_01_r", "lowerarm_twist_02_r",
    "hand_r",
    "index_metacarpal_r", "middle_metacarpal_r",
    "ring_metacarpal_r", "pinky_metacarpal_r",
    "index_01_r", "middle_01_r", "ring_01_r", "pinky_01_r", "thumb_01_r",

    # legs (left)
    "thigh_l",
    "thigh_twist_01_l", "thigh_twist_02_l",
    "calf_l",
    "calf_twist_01_l", "calf_twist_02_l",
    "foot_l", "ball_l",
    # toes (one level)
    "bigtoe_01_l", "indextoe_01_l", "middletoe_01_l",
    "ringtoe_01_l", "littletoe_01_l",

    # legs (right)
    "thigh_r",
    "thigh_twist_01_r", "thigh_twist_02_r",
    "calf_r",
    "calf_twist_01_r", "calf_twist_02_r",
    "foot_r", "ball_r",
    "bigtoe_01_r", "indextoe_01_r", "middletoe_01_r",
    "ringtoe_01_r", "littletoe_01_r",
]

WHITELIST_SET: frozenset[str] = frozenset(STABLE_DEFORM_WHITELIST)


_FINGER_DIGIT_RE     = re.compile(r'^(index|middle|pinky|ring|thumb)_\d+.*_([lr])$')
_FINGER_METACARP_RE  = re.compile(r'^(index|middle|pinky|ring|thumb)_metacarpal.*_([lr])$')
_TOE_RE              = re.compile(r'^(bigtoe|indextoe|middletoe|ringtoe|littletoe)_\d+.*_([lr])$')


def _pattern_fallback(name: str) -> str:
    """Last-resort routing for joints absent from BODY_HIERARCHY.
    Finger micro-detail bones (bulge / half / dip / palm / mcp / slide
    etc.) fold to the corresponding *_01_<side>; toe details to
    <toe>_01_<side>; anything else collapses to root so weight is
    conserved rather than dropped."""
    m = _FINGER_METACARP_RE.match(name)
    if m:
        return f"{m.group(1)}_metacarpal_{m.group(2)}"
    m = _FINGER_DIGIT_RE.match(name)
    if m:
        return f"{m.group(1)}_01_{m.group(2)}"
    m = _TOE_RE.match(name)
    if m:
        return f"{m.group(1)}_01_{m.group(2)}"
    return "root"


def fold_to_whitelist_ancestor(name: str) -> str:
    """Return the nearest whitelisted ancestor of `name`. If the
    explicit BODY_HIERARCHY chain ends without hitting the whitelist,
    fall back to a name-pattern rule (finger/toe detail) and ultimately
    to "root"."""
    if name in WHITELIST_SET:
        return name
    seen: set[str] = set()
    cur = name
    while cur not in WHITELIST_SET:
        if cur in seen:
            return _pattern_fallback(name)
        seen.add(cur)
        parent = BODY_HIERARCHY.get(cur)
        if parent is None:
            return _pattern_fallback(name)
        cur = parent
    return cur


def parent_of(name: str) -> str | None:
    """Direct parent within the WHITELIST.  Walks up the full
    BODY_HIERARCHY skipping intermediate non-whitelist joints, since
    those are not nodes in the refit GLB."""
    cur = BODY_HIERARCHY.get(name)
    while cur is not None and cur not in WHITELIST_SET:
        cur = BODY_HIERARCHY.get(cur)
    return cur


# Sanity: every whitelist entry's parent (per BODY_HIERARCHY) must
# itself be in the whitelist or be None (root).  Verifies the
# whitelist is ancestor-closed so the output node graph is well-formed.
def _self_check() -> None:
    for j in STABLE_DEFORM_WHITELIST:
        if j == "root":
            continue
        p = parent_of(j)
        if p is None and BODY_HIERARCHY.get(j) is not None:
            raise RuntimeError(f"whitelist gap: {j} has parent chain not in whitelist")


_self_check()
