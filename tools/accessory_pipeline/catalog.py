"""Hand-authored accessory catalogue. Mirrors library_data.HARDWARE /
ACCESSORIES / BODY_JEWELRY conventions but every entry here has the
geometric + PBR metadata needed for the 3D builder."""
from __future__ import annotations

from .schema import AccessoryEntry


# Standard finish swatches — keep colours in one place
_GOLD       = "#d4af37"
_ROSE_GOLD  = "#c98a8a"
_SILVER     = "#c0c0c0"
_NICKEL     = "#a8a8a8"
_BRUSHED    = "#9a9a9a"
_BLACK      = "#1a1a1a"


# ---------------------------------------------------------------------------
# RING family — parametric tori; first family to land an actual GLB.
# ---------------------------------------------------------------------------

RINGS: dict[str, AccessoryEntry] = {
    "ACX_OR_8MM_GOLD": AccessoryEntry(
        id="ACX_OR_8MM_GOLD", family="ring",
        name="O-ring 8 mm gold",
        tags=("o_ring", "small", "gold"),
        geom={"outer_diameter_mm": 8.0, "ring_thickness_mm": 1.4, "profile": "round"},
        metal="gold", metallic=1.0, roughness=0.22, base_color_hex=_GOLD,
        mount="loop", anchor_anatomy=("sternum_mid",),
        bbox_mm=(8.0, 8.0, 1.4), weight_g=0.4, swing_mode="rigid",
    ),
    "ACX_OR_12MM_GOLD": AccessoryEntry(
        id="ACX_OR_12MM_GOLD", family="ring",
        name="O-ring 12 mm gold",
        tags=("o_ring", "gold"),
        geom={"outer_diameter_mm": 12.0, "ring_thickness_mm": 2.0, "profile": "round"},
        metal="gold", metallic=1.0, roughness=0.22, base_color_hex=_GOLD,
        mount="loop", anchor_anatomy=("sternum_mid",),
        bbox_mm=(12.0, 12.0, 2.0), weight_g=0.9, swing_mode="rigid",
    ),
    "ACX_OR_18MM_SILVER": AccessoryEntry(
        id="ACX_OR_18MM_SILVER", family="ring",
        name="O-ring 18 mm silver",
        tags=("o_ring", "large", "silver"),
        geom={"outer_diameter_mm": 18.0, "ring_thickness_mm": 2.8, "profile": "round"},
        metal="silver", metallic=1.0, roughness=0.18, base_color_hex=_SILVER,
        mount="loop", anchor_anatomy=("waist_left_side",),
        bbox_mm=(18.0, 18.0, 2.8), weight_g=2.4, swing_mode="rigid",
    ),
    "ACX_OR_12MM_ROSEGOLD": AccessoryEntry(
        id="ACX_OR_12MM_ROSEGOLD", family="ring",
        name="O-ring 12 mm rose gold",
        tags=("o_ring", "rose_gold"),
        geom={"outer_diameter_mm": 12.0, "ring_thickness_mm": 2.0, "profile": "round"},
        metal="rosegold", metallic=1.0, roughness=0.25, base_color_hex=_ROSE_GOLD,
        mount="loop", anchor_anatomy=("sternum_mid",),
        bbox_mm=(12.0, 12.0, 2.0), weight_g=0.9, swing_mode="rigid",
    ),
    "ACX_DR_15MM_SILVER": AccessoryEntry(
        id="ACX_DR_15MM_SILVER", family="ring",
        name="D-ring 15 mm silver",
        tags=("d_ring", "silver"),
        geom={"outer_diameter_mm": 15.0, "ring_thickness_mm": 2.4, "profile": "d"},
        metal="silver", metallic=1.0, roughness=0.20, base_color_hex=_SILVER,
        mount="loop", anchor_anatomy=("sternum_mid",),
        bbox_mm=(15.0, 15.0, 2.4), weight_g=1.6, swing_mode="rigid",
    ),
    "ACX_SR_20MM_BLACK": AccessoryEntry(
        id="ACX_SR_20MM_BLACK", family="ring",
        name="Square ring 20 mm matte black",
        tags=("square_ring", "matte_black", "modern"),
        geom={"outer_diameter_mm": 20.0, "ring_thickness_mm": 2.6, "profile": "square"},
        metal="matte_black", metallic=0.85, roughness=0.55, base_color_hex=_BLACK,
        mount="loop", anchor_anatomy=("hip_left",),
        bbox_mm=(20.0, 20.0, 2.6), weight_g=2.0, swing_mode="rigid",
    ),
}


# Combined catalogue — additional family dicts (CHAINS, BUCKLES, etc.)
# get merged here in later commits.
ACCESSORY_CATALOG: dict[str, AccessoryEntry] = {**RINGS}


def entries_by_family(family: str) -> list[AccessoryEntry]:
    return [e for e in ACCESSORY_CATALOG.values() if e.family == family]
