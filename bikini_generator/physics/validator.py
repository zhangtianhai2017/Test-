"""Physics validation orchestrator.

Runs cloth simulation, checks displacement and coverage.
If validation fails, suggests parameter adjustments for retry.
"""

import numpy as np
from dataclasses import dataclass
from .coverage_check import check_coverage, all_covered
from ..garment.assembly import GarmentAssembly
from ..body.mannequin import get_body_collision_primitives
from ..config import PHYSICS


@dataclass
class ValidationResult:
    """Result of physics validation."""
    passed: bool
    max_displacement: float
    coverage_results: dict[str, bool]
    final_vertices: np.ndarray | None = None
    message: str = ""


def validate_garment(
    assembly: GarmentAssembly,
    config: object | None = None,
) -> ValidationResult:
    """Run physics simulation and validate garment stability + coverage.

    Args:
        assembly: the garment to validate
        config: physics config override

    Returns:
        ValidationResult with pass/fail and diagnostics
    """
    cfg = config or PHYSICS

    # Merge all patches into single mesh
    vertices, faces, uvs = assembly.merge_to_single_mesh()
    anchor_ids, anchor_positions = assembly.get_all_anchors()

    if len(vertices) == 0:
        return ValidationResult(
            passed=False,
            max_displacement=0,
            coverage_results={},
            message="Empty garment — no vertices",
        )

    # Get body collision primitives
    collision_prims = get_body_collision_primitives()

    # Lazy import Taichi and cloth sim (heavy deps)
    import taichi as ti
    from .cloth_sim import ClothSimulator

    # Initialize Taichi (idempotent)
    try:
        ti.init(arch=ti.gpu, default_fp=ti.f32)
    except Exception:
        ti.init(arch=ti.cpu, default_fp=ti.f32)

    # Run simulation
    sim = ClothSimulator(
        vertices=vertices,
        faces=faces,
        anchor_ids=anchor_ids,
        anchor_positions=anchor_positions,
        collision_primitives=collision_prims,
        config=cfg,
    )

    final_positions = sim.simulate()
    max_disp = sim.get_max_displacement()

    # Check displacement
    disp_ok = max_disp < cfg.max_displacement_threshold

    # Check coverage on the deformed mesh
    coverage_results = check_coverage(final_positions, faces)
    cov_ok = all_covered(coverage_results)

    passed = disp_ok and cov_ok

    # Build message
    msgs = []
    if not disp_ok:
        msgs.append(
            f"Displacement too large: {max_disp:.4f}m > {cfg.max_displacement_threshold}m"
        )
    if not cov_ok:
        uncovered = [k for k, v in coverage_results.items() if not v]
        msgs.append(f"Uncovered zones: {', '.join(uncovered)}")
    if passed:
        msgs.append("PASSED — garment is stable and covers all zones")

    return ValidationResult(
        passed=passed,
        max_displacement=max_disp,
        coverage_results=coverage_results,
        final_vertices=final_positions,
        message=" | ".join(msgs),
    )


def suggest_adjustments(result: ValidationResult) -> dict:
    """Suggest parameter adjustments when validation fails.

    Returns dict of parameter hints for the randomizer retry.
    """
    adjustments = {}

    if result.max_displacement > PHYSICS.max_displacement_threshold:
        # Garment is falling — need more/stronger anchors or wider straps
        adjustments["increase_strap_width"] = True
        adjustments["prefer_band_style"] = "back_band"
        adjustments["min_coverage"] = 0.5

    uncovered = [k for k, v in result.coverage_results.items() if not v]
    if "left_breast" in uncovered or "right_breast" in uncovered:
        adjustments["min_cup_coverage"] = 0.6
    if "crotch_front" in uncovered:
        adjustments["min_front_coverage"] = 0.5
    if "crotch_back" in uncovered:
        adjustments["prefer_back_style"] = "classic"

    return adjustments
