"""Anatomical landmark positions on the reference body.

All coordinates in meters. Y is up, Z is forward (facing direction).
Origin at center of body at ground level.
"""

import numpy as np
from ..config import BODY


def get_landmarks() -> dict[str, np.ndarray]:
    """Return dictionary of named anatomical landmark 3D positions."""
    b = BODY
    half_spacing = b.breast_spacing / 2

    return {
        # --- Shoulder / Neck ---
        "neck_front": np.array([0.0, b.shoulder_height + 0.04, 0.06]),
        "neck_back": np.array([0.0, b.shoulder_height + 0.04, -0.06]),
        "left_shoulder": np.array([-b.shoulder_width / 2, b.shoulder_height, 0.0]),
        "right_shoulder": np.array([b.shoulder_width / 2, b.shoulder_height, 0.0]),

        # --- Chest / Bust ---
        "sternum_top": np.array([0.0, b.bust_height + 0.06, 0.08]),
        "sternum_center": np.array([0.0, b.bust_height, 0.10]),
        "left_breast_apex": np.array(
            [-half_spacing, b.bust_height, 0.10 + b.breast_projection]
        ),
        "right_breast_apex": np.array(
            [half_spacing, b.bust_height, 0.10 + b.breast_projection]
        ),
        "left_breast_outer": np.array(
            [-half_spacing - b.breast_radius, b.bust_height, 0.08]
        ),
        "right_breast_outer": np.array(
            [half_spacing + b.breast_radius, b.bust_height, 0.08]
        ),
        "left_breast_inner": np.array(
            [-half_spacing + b.breast_radius * 0.6, b.bust_height, 0.09]
        ),
        "right_breast_inner": np.array(
            [half_spacing - b.breast_radius * 0.6, b.bust_height, 0.09]
        ),
        "left_underbust": np.array([-half_spacing, b.bust_height - 0.06, 0.08]),
        "right_underbust": np.array([half_spacing, b.bust_height - 0.06, 0.08]),

        # --- Torso / Back ---
        "spine_upper": np.array([0.0, b.bust_height, -0.10]),
        "spine_mid": np.array([0.0, b.waist_height + 0.05, -0.09]),
        "left_ribcage": np.array([-0.14, b.bust_height - 0.04, -0.02]),
        "right_ribcage": np.array([0.14, b.bust_height - 0.04, -0.02]),

        # --- Waist ---
        "waist_front": np.array([0.0, b.waist_height, 0.09]),
        "waist_back": np.array([0.0, b.waist_height, -0.09]),
        "waist_left": np.array([-0.14, b.waist_height, 0.0]),
        "waist_right": np.array([0.14, b.waist_height, 0.0]),

        # --- Hip ---
        "hip_front": np.array([0.0, b.hip_height, 0.10]),
        "hip_back": np.array([0.0, b.hip_height, -0.12]),
        "hip_left": np.array([-0.17, b.hip_height, 0.0]),
        "hip_right": np.array([0.17, b.hip_height, 0.0]),

        # --- Buttocks ---
        "left_buttock_apex": np.array([-0.08, b.hip_height - 0.04, -0.13]),
        "right_buttock_apex": np.array([0.08, b.hip_height - 0.04, -0.13]),
        "buttock_crease_left": np.array([-0.07, b.crotch_height + 0.02, -0.10]),
        "buttock_crease_right": np.array([0.07, b.crotch_height + 0.02, -0.10]),

        # --- Crotch / Pubic ---
        "crotch_center": np.array([0.0, b.crotch_height, 0.04]),
        "pubic_top": np.array([0.0, b.crotch_height + 0.06, 0.09]),
        "crotch_back": np.array([0.0, b.crotch_height, -0.04]),
        "inner_thigh_left": np.array([-0.06, b.crotch_height, 0.0]),
        "inner_thigh_right": np.array([0.06, b.crotch_height, 0.0]),
    }


# Coverage zones: groups of landmarks that MUST be covered
COVERAGE_ZONES = {
    "left_breast": [
        "left_breast_apex",
    ],
    "right_breast": [
        "right_breast_apex",
    ],
    "crotch_front": [
        "pubic_top",
        "crotch_center",
    ],
    "crotch_back": [
        "crotch_back",
    ],
}


def get_coverage_points() -> dict[str, list[np.ndarray]]:
    """Return coverage zone name -> list of 3D points that must be covered."""
    landmarks = get_landmarks()
    result = {}
    for zone_name, landmark_names in COVERAGE_ZONES.items():
        result[zone_name] = [landmarks[n] for n in landmark_names]
    return result


# Attachment anchor groups: where garment straps/bands can anchor to the body
ANCHOR_GROUPS = {
    "shoulders": ["left_shoulder", "right_shoulder"],
    "neck": ["neck_front", "neck_back"],
    "underbust_band": ["left_underbust", "right_underbust", "left_ribcage", "right_ribcage"],
    "waist_band": ["waist_left", "waist_right", "waist_front", "waist_back"],
    "hip_band": ["hip_left", "hip_right", "hip_front", "hip_back"],
}
