"""Global configuration and body measurement constants."""

from dataclasses import dataclass, field
import numpy as np


@dataclass
class BodyConfig:
    """Reference female body measurements (meters), extracted from ZBrush base_body.obj."""
    height: float = 1.729
    shoulder_width: float = 0.317  # left_shoulder to right_shoulder X distance
    bust_circumference: float = 0.88
    underbust_circumference: float = 0.74
    waist_circumference: float = 0.66
    hip_circumference: float = 0.94
    torso_length: float = 0.39  # shoulder to waist
    breast_radius: float = 0.043  # apex to outer edge distance
    breast_projection: float = 0.015  # apex Z beyond sternum Z
    breast_spacing: float = 0.144  # center to center (apex X distance)

    # Vertical positions (Y axis, from ground) — from real mesh
    shoulder_height: float = 1.422
    bust_height: float = 1.298
    waist_height: float = 1.032
    hip_height: float = 0.976
    crotch_height: float = 0.781

    # Path to the real body mesh (OBJ)
    mesh_path: str = "assets/base_body.obj"
    mesh_scale: float = 0.01  # ZBrush cm -> meters


@dataclass
class PhysicsConfig:
    """Cloth simulation parameters."""
    gravity: float = -9.81
    dt: float = 0.001  # timestep per step
    num_steps: int = 200  # simulation steps (settle time ~0.2s)
    num_substeps: int = 15  # PBD constraint iterations per step
    cloth_mass_per_vertex: float = 0.001  # kg
    stretch_stiffness: float = 10000.0  # very stiff — tight-fitting garment
    shear_stiffness: float = 500.0
    bend_stiffness: float = 100.0
    friction_coefficient: float = 0.8  # cloth-skin friction
    damping: float = 0.90  # very strong damping — fast settling, models air resistance
    collision_margin: float = 0.004  # 4mm
    max_displacement_threshold: float = 0.10  # 10cm (straps legitimately span distances)


@dataclass
class GenerationConfig:
    """Parameters controlling the generation pipeline."""
    texture_resolution: int = 1024
    mesh_resolution_u: int = 32  # UV subdivision for garment patches
    mesh_resolution_v: int = 32
    max_physics_retries: int = 5
    body_mesh_resolution_low: int = 16  # for limbs/torso
    body_mesh_resolution_high: int = 48  # for chest/butt/crotch
    output_dir: str = "web/generated"


@dataclass
class AIConfig:
    """AI texture/design generation config."""
    enabled: bool = False
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    mock_mode: bool = True  # Use mock responses until real API is connected


# Singleton defaults
BODY = BodyConfig()
PHYSICS = PhysicsConfig()
GENERATION = GenerationConfig()
AI = AIConfig()
