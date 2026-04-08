"""AI-powered texture and design generation.

Uses DeepSeek API for creative design suggestions.
Includes mock mode for development without API access.
"""

import json
import numpy as np
from ..config import AI


# --- Mock AI responses for development ---

MOCK_DESIGNS = [
    {
        "cup_style": "triangle",
        "connector_style": "ring",
        "strap_style": "halter",
        "front_style": "high_cut",
        "back_style": "brazilian",
        "bottom_strap_style": "side_tie",
        "texture_description": "Iridescent holographic fabric with shifting purple-to-teal gradient",
        "pattern": "gradient",
        "material_effect": "sheen",
        "palette_hint": "midnight",
    },
    {
        "cup_style": "bandeau",
        "connector_style": "band",
        "strap_style": "strapless",
        "front_style": "classic",
        "back_style": "full",
        "bottom_strap_style": "waistband",
        "texture_description": "Tropical botanical print with large monstera leaves",
        "pattern": "floral",
        "material_effect": "satin",
        "palette_hint": "tropical",
    },
    {
        "cup_style": "scallop",
        "connector_style": "string",
        "strap_style": "cross_back",
        "front_style": "v_shape",
        "back_style": "thong",
        "bottom_strap_style": "chain",
        "texture_description": "Black lace with gold chain accents, Gothic inspired",
        "pattern": "dots",
        "material_effect": "lace",
        "palette_hint": "black_gold",
    },
    {
        "cup_style": "cone",
        "connector_style": "cross",
        "strap_style": "multi_web",
        "front_style": "ruched",
        "back_style": "classic",
        "bottom_strap_style": "multi_strap",
        "texture_description": "Futuristic neon grid pattern on matte black base",
        "pattern": "geometric",
        "material_effect": "none",
        "palette_hint": "neon",
    },
    {
        "cup_style": "round",
        "connector_style": "none",
        "strap_style": "over_shoulder",
        "front_style": "skirt",
        "back_style": "full",
        "bottom_strap_style": "waistband",
        "texture_description": "Sunset-colored tie-dye with organic flowing patterns",
        "pattern": "noise",
        "material_effect": "velvet",
        "palette_hint": "sunset",
    },
    {
        "cup_style": "triangle",
        "connector_style": "string",
        "strap_style": "halter",
        "front_style": "high_cut",
        "back_style": "thong",
        "bottom_strap_style": "side_tie",
        "texture_description": "Leopard print with rose gold metallic accents",
        "pattern": "animal_print",
        "material_effect": "sheen",
        "palette_hint": "earth",
    },
    {
        "cup_style": "scallop",
        "connector_style": "band",
        "strap_style": "over_shoulder",
        "front_style": "classic",
        "back_style": "brazilian",
        "bottom_strap_style": "side_tie",
        "texture_description": "Ocean wave pattern with pearl white and deep aqua stripes",
        "pattern": "chevron",
        "material_effect": "satin",
        "palette_hint": "ocean",
    },
    {
        "cup_style": "round",
        "connector_style": "ring",
        "strap_style": "cross_back",
        "front_style": "v_shape",
        "back_style": "classic",
        "bottom_strap_style": "chain",
        "texture_description": "Celestial theme with constellation dots on dark navy",
        "pattern": "dots",
        "material_effect": "embossed",
        "palette_hint": "midnight",
    },
]

MOCK_TEXTURE_PROMPTS = [
    "seamless fabric texture, tropical floral pattern, vibrant colors, 512x512",
    "metallic gold thread weave on black silk, luxury fashion, seamless",
    "holographic iridescent fabric, pink and blue shift, seamless texture",
    "hand-painted watercolor flowers on white cotton, feminine, seamless",
    "geometric Art Deco pattern, gold and emerald, seamless fashion textile",
    "tie-dye swirl pattern, sunset orange and purple, boho style, seamless",
    "delicate lace pattern, ivory white, intricate floral, seamless",
    "snake skin texture, metallic teal and black, exotic fashion, seamless",
]


def get_design_suggestion(
    prompt: str = "Generate a creative bikini design",
    seed: int | None = None,
) -> dict:
    """Get a design suggestion from AI (or mock).

    Returns a dict with style parameters that can feed into the randomizer.
    """
    if AI.mock_mode:
        return _mock_design_suggestion(seed)

    return _call_deepseek_design(prompt)


def get_texture_prompt(
    design_description: str = "",
    seed: int | None = None,
) -> str:
    """Get a texture generation prompt from AI (or mock)."""
    if AI.mock_mode:
        rng = np.random.default_rng(seed)
        return rng.choice(MOCK_TEXTURE_PROMPTS)

    return _call_deepseek_texture(design_description)


def _mock_design_suggestion(seed: int | None = None) -> dict:
    """Return a mock design suggestion."""
    rng = np.random.default_rng(seed)
    idx = int(rng.integers(0, len(MOCK_DESIGNS)))
    design = MOCK_DESIGNS[idx].copy()

    # Add some randomization to the mock
    if rng.random() < 0.3:
        design["asymmetric"] = True

    return design


def _call_deepseek_design(prompt: str) -> dict:
    """Call DeepSeek API for design suggestion."""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=AI.api_key,
            base_url=AI.base_url,
        )

        system_prompt = """You are a creative fashion designer specializing in swimwear.
Generate a unique bikini design as a JSON object with these fields:
- cup_style: one of [triangle, round, bandeau, scallop, cone]
- connector_style: one of [string, band, ring, cross, none]
- strap_style: one of [over_shoulder, halter, cross_back, multi_web, strapless]
- front_style: one of [classic, v_shape, high_cut, ruched, skirt]
- back_style: one of [classic, thong, brazilian, full]
- bottom_strap_style: one of [side_tie, waistband, chain, multi_strap]
- texture_description: creative description of the fabric/pattern
- pattern: one of [noise, stripes, dots, chevron, animal_print, floral, geometric, gradient]
- material_effect: one of [none, sheen, lace, velvet, satin, embossed]
- palette_hint: one of [tropical, ocean, sunset, midnight, coral, black_gold] or "random"

Be creative and imaginative! Think of unusual combinations.
Return ONLY valid JSON, no markdown."""

        response = client.chat.completions.create(
            model=AI.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_tokens=500,
        )

        text = response.choices[0].message.content.strip()
        # Try to parse JSON
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)

    except Exception as e:
        print(f"DeepSeek API error: {e}, falling back to mock")
        return _mock_design_suggestion()


def _call_deepseek_texture(description: str) -> str:
    """Call DeepSeek API for texture prompt."""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=AI.api_key,
            base_url=AI.base_url,
        )

        response = client.chat.completions.create(
            model=AI.model,
            messages=[
                {
                    "role": "system",
                    "content": "Generate a short, descriptive prompt for a seamless fabric texture. Keep it under 50 words.",
                },
                {
                    "role": "user",
                    "content": f"Design: {description}. Generate a texture prompt.",
                },
            ],
            temperature=0.8,
            max_tokens=100,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"DeepSeek API error: {e}, falling back to mock")
        rng = np.random.default_rng()
        return rng.choice(MOCK_TEXTURE_PROMPTS)
