"""Global configuration and body measurement constants."""

from dataclasses import dataclass, field
import numpy as np


@dataclass
class BodyConfig:
    """Reference female body measurements (in meters, roughly MetaHuman scale)."""
    height: float = 1.68
    shoulder_width: float = 0.36
    bust_circumference: float = 0.88
    underbust_circumference: float = 0.74
    waist_circumference: float = 0.66
    hip_circumference: float = 0.94
    torso_length: float = 0.42  # shoulder to waist
    breast_radius: float = 0.07
    breast_projection: float = 0.05
    breast_spacing: float = 0.18  # center to center

    # Vertical positions (Y axis, from ground)
    shoulder_height: float = 1.40
    bust_height: float = 1.25
    waist_height: float = 1.05
    hip_height: float = 0.95
    crotch_height: float = 0.78


@dataclass
class PhysicsConfig:
    """Cloth simulation parameters."""
    gravity: float = -9.81
    dt: float = 0.001  # timestep
    num_steps: int = 500  # simulation steps
    cloth_mass_per_vertex: float = 0.002  # kg
    stretch_stiffness: float = 800.0
    shear_stiffness: float = 200.0
    bend_stiffness: float = 50.0
    friction_coefficient: float = 0.6  # cloth-skin friction
    damping: float = 0.995
    collision_margin: float = 0.002  # 2mm
    max_displacement_threshold: float = 0.05  # 5cm - fail if any vertex moves more


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
