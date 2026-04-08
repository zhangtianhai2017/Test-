"""Anatomical landmark positions extracted from the real ZBrush body mesh.

All coordinates in meters (original mesh was in cm, scaled by 0.01).
Y is up, Z is forward (facing direction).
"""

import numpy as np


def get_landmarks() -> dict[str, np.ndarray]:
    """Return dictionary of named anatomical landmark 3D positions.

    These coordinates were extracted from assets/base_body.obj by analyzing
    vertex positions in each anatomical region.
    """
    return {
        # --- Shoulder / Neck ---
        "neck_front": np.array([0.0, 1.567, 0.092]),
        "neck_back": np.array([0.0, 1.580, -0.097]),
        "left_shoulder": np.array([-0.155, 1.424, -0.037]),
        "right_shoulder": np.array([0.162, 1.421, -0.045]),

        # --- Chest / Bust ---
        "sternum_top": np.array([0.0, 1.350, 0.095]),
        "sternum_center": np.array([-0.020, 1.287, 0.103]),
        "left_breast_apex": np.array([-0.073, 1.298, 0.118]),
        "right_breast_apex": np.array([0.072, 1.297, 0.118]),
        "left_breast_outer": np.array([-0.116, 1.283, 0.082]),
        "right_breast_outer": np.array([0.116, 1.283, 0.082]),
        "left_breast_inner": np.array([-0.030, 1.290, 0.108]),
        "right_breast_inner": np.array([0.030, 1.290, 0.108]),
        "left_underbust": np.array([-0.050, 1.270, 0.114]),
        "right_underbust": np.array([0.048, 1.268, 0.113]),

        # --- Torso / Back ---
        "spine_upper": np.array([-0.032, 1.355, -0.102]),
        "spine_mid": np.array([0.022, 1.192, -0.080]),
        "left_ribcage": np.array([-0.265, 1.253, -0.048]),
        "right_ribcage": np.array([0.264, 1.253, -0.043]),

        # --- Waist ---
        "waist_front": np.array([-0.013, 1.034, 0.088]),
        "waist_back": np.array([0.033, 1.031, -0.098]),
        "waist_left": np.array([-0.428, 1.030, 0.146]),
        "waist_right": np.array([0.429, 1.030, 0.146]),

        # --- Hip ---
        "hip_front": np.array([-0.007, 0.996, 0.086]),
        "hip_back": np.array([0.032, 0.926, -0.136]),
        "hip_left": np.array([-0.452, 0.976, 0.185]),
        "hip_right": np.array([0.451, 0.975, 0.185]),

        # --- Buttocks ---
        "left_buttock_apex": np.array([-0.062, 0.926, -0.140]),
        "right_buttock_apex": np.array([0.061, 0.929, -0.140]),
        "buttock_crease_left": np.array([-0.058, 0.871, -0.129]),
        "buttock_crease_right": np.array([0.057, 0.874, -0.129]),

        # --- Crotch / Pubic ---
        "crotch_center": np.array([0.0, 0.781, -0.007]),
        "pubic_top": np.array([0.048, 0.865, 0.051]),
        "crotch_front": np.array([0.041, 0.846, 0.043]),
        "crotch_back": np.array([-0.047, 0.849, -0.108]),
        "inner_thigh_left": np.array([-0.022, 0.766, -0.010]),
        "inner_thigh_right": np.array([0.021, 0.782, 0.010]),
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
