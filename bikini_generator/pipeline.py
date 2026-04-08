"""End-to-end generation pipeline.

Orchestrates: AI design → geometry generation → physics validation
→ texture generation → OBJ export.
"""

import os
import time
import uuid
import numpy as np
from dataclasses import dataclass, field

from .config import GENERATION, PHYSICS, AI
from .garment.randomizer import generate_random_bikini, DesignDescription
from .physics.validator import validate_garment, suggest_adjustments, ValidationResult
from .texture.compositing import generate_texture, random_texture
from .texture.palette import random_palette, PRESET_PALETTES
from .texture.ai_texture import get_design_suggestion
from .export.obj_writer import export_obj, export_body_obj
from .body.mannequin import generate_full_body


@dataclass
class GenerationResult:
    """Result from the full generation pipeline."""
    success: bool
    model_id: str
    files: dict[str, str] = field(default_factory=dict)
    design: DesignDescription | None = None
    validation: ValidationResult | None = None
    texture_metadata: dict = field(default_factory=dict)
    generation_time: float = 0.0
    retries: int = 0
    message: str = ""


def generate_bikini(
    seed: int | None = None,
    use_ai: bool = False,
    skip_physics: bool = False,
    output_dir: str | None = None,
    texture_resolution: int | None = None,
) -> GenerationResult:
    """Run the full bikini generation pipeline.

    Args:
        seed: random seed for reproducibility
        use_ai: whether to use AI for design suggestions
        skip_physics: skip physics validation (faster, for testing)
        output_dir: override output directory
        texture_resolution: override texture resolution

    Returns:
        GenerationResult with file paths and metadata
    """
    start_time = time.time()
    model_id = str(uuid.uuid4())[:8]
    out_dir = output_dir or os.path.join(GENERATION.output_dir, model_id)
    tex_res = texture_resolution or GENERATION.texture_resolution

    rng = np.random.default_rng(seed)
    actual_seed = int(rng.integers(0, 2**31))

    result = GenerationResult(success=False, model_id=model_id)

    # --- Step 1: Get design parameters ---
    ai_params = None
    if use_ai or AI.mock_mode:
        ai_params = get_design_suggestion(seed=actual_seed)

    # --- Step 2: Generate geometry with physics retry loop ---
    max_retries = GENERATION.max_physics_retries
    assembly = None
    design = None
    validation = None

    for attempt in range(max_retries):
        attempt_seed = actual_seed + attempt * 1000
        assembly, design = generate_random_bikini(
            seed=attempt_seed, ai_params=ai_params,
        )

        if skip_physics:
            break

        # Validate
        try:
            validation = validate_garment(assembly)
        except Exception as e:
            validation = ValidationResult(
                passed=False,
                max_displacement=999,
                coverage_results={},
                message=f"Physics error: {e}",
            )

        if validation.passed:
            result.retries = attempt
            break

        # Adjust parameters for retry
        if attempt < max_retries - 1:
            adjustments = suggest_adjustments(validation)
            if ai_params:
                ai_params.update(adjustments)
            else:
                ai_params = adjustments

    if assembly is None:
        result.message = "Failed to generate garment"
        result.generation_time = time.time() - start_time
        return result

    result.design = design
    result.validation = validation

    # --- Step 3: Generate texture ---
    try:
        palette_hint = None
        if ai_params and "palette_hint" in ai_params:
            hint = ai_params["palette_hint"]
            if hint in PRESET_PALETTES:
                palette_hint = PRESET_PALETTES[hint]

        pattern_name = "noise"
        material_effect = "none"
        if ai_params:
            pattern_name = ai_params.get("pattern", "noise")
            material_effect = ai_params.get("material_effect", "none")

        texture_img = generate_texture(
            width=tex_res,
            height=tex_res,
            pattern_name=pattern_name,
            palette=palette_hint or random_palette(actual_seed),
            material_effect=material_effect,
            seed=actual_seed,
        )
        result.texture_metadata = {
            "pattern": pattern_name,
            "effect": material_effect,
            "resolution": tex_res,
        }
    except Exception as e:
        # Fallback: plain color texture
        from PIL import Image
        texture_img = Image.new("RGB", (tex_res, tex_res), (200, 100, 100))
        result.texture_metadata = {"error": str(e), "fallback": True}

    # --- Step 4: Export ---
    try:
        deformed_verts = None
        if validation and validation.final_vertices is not None:
            deformed_verts = validation.final_vertices

        files = export_obj(
            assembly=assembly,
            output_dir=out_dir,
            name=f"bikini_{model_id}",
            texture_image=texture_img,
            deformed_vertices=deformed_verts,
        )

        # Also export mannequin body for reference
        body_verts, body_faces = generate_full_body()
        body_path = export_body_obj(body_verts, body_faces, out_dir, "mannequin")
        files["body"] = body_path

        result.files = files
        result.success = True
        result.message = f"Generated successfully: {design.to_text()}"

    except Exception as e:
        result.message = f"Export error: {e}"

    result.generation_time = time.time() - start_time
    return result


def generate_batch(
    count: int = 10,
    base_seed: int | None = None,
    use_ai: bool = False,
    skip_physics: bool = False,
    output_dir: str | None = None,
) -> list[GenerationResult]:
    """Generate multiple bikinis."""
    rng = np.random.default_rng(base_seed)
    results = []
    for i in range(count):
        seed = int(rng.integers(0, 2**31))
        result = generate_bikini(
            seed=seed,
            use_ai=use_ai,
            skip_physics=skip_physics,
            output_dir=os.path.join(output_dir or GENERATION.output_dir, f"batch_{i:04d}") if output_dir else None,
        )
        results.append(result)
    return results
