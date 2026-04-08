"""API routes for bikini generation."""

import os
import json
import time
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

GENERATED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")


class GenerateRequest(BaseModel):
    seed: int | None = None
    use_ai: bool = True
    skip_physics: bool = False
    texture_resolution: int = 512


class GenerateResponse(BaseModel):
    success: bool
    model_id: str
    obj_url: str = ""
    mtl_url: str = ""
    texture_url: str = ""
    body_url: str = ""
    description: str = ""
    generation_time: float = 0.0
    retries: int = 0
    message: str = ""
    metadata: dict = {}


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """Generate a new random bikini model."""
    from bikini_generator.pipeline import generate_bikini

    result = generate_bikini(
        seed=req.seed,
        use_ai=req.use_ai,
        skip_physics=req.skip_physics,
        output_dir=os.path.join(GENERATED_DIR, "latest"),
        texture_resolution=req.texture_resolution,
    )

    # Build URLs relative to /generated/
    base_url = "/generated/latest"
    obj_url = ""
    mtl_url = ""
    tex_url = ""
    body_url = ""

    if result.files.get("obj"):
        obj_url = f"{base_url}/{os.path.basename(result.files['obj'])}"
    if result.files.get("mtl"):
        mtl_url = f"{base_url}/{os.path.basename(result.files['mtl'])}"
    if result.files.get("texture"):
        tex_url = f"{base_url}/{os.path.basename(result.files['texture'])}"
    if result.files.get("body"):
        body_url = f"{base_url}/{os.path.basename(result.files['body'])}"

    return GenerateResponse(
        success=result.success,
        model_id=result.model_id,
        obj_url=obj_url,
        mtl_url=mtl_url,
        texture_url=tex_url,
        body_url=body_url,
        description=result.design.to_text() if result.design else "",
        generation_time=result.generation_time,
        retries=result.retries,
        message=result.message,
        metadata=result.texture_metadata,
    )


@router.get("/gallery")
async def gallery():
    """List all generated models."""
    models = []
    if os.path.exists(GENERATED_DIR):
        for entry in sorted(os.listdir(GENERATED_DIR)):
            model_dir = os.path.join(GENERATED_DIR, entry)
            if os.path.isdir(model_dir):
                obj_files = [f for f in os.listdir(model_dir) if f.endswith(".obj") and f != "mannequin.obj"]
                if obj_files:
                    models.append({
                        "id": entry,
                        "obj_url": f"/generated/{entry}/{obj_files[0]}",
                        "has_texture": any(f.endswith(".png") for f in os.listdir(model_dir)),
                    })
    return {"models": models}


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}
