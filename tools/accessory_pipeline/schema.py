"""Accessory entry schema — the catalog/library type for the accessory
sub-project. Mirrors LibraryEntry conventions from tools/library.py but
adds 3D-relevant fields the outfit library doesn't carry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Family = Literal[
    "ring",            # parametric torus: O-ring, D-ring, square ring
    "slider",          # ladder / figure-8 slider
    "buckle",          # adjustable square buckle
    "clasp",           # hook-and-eye, lobster clasp
    "charm_pendant",   # shell, drop, coin — small 3D charm on a loop
    "chain",           # link chain along an anchor path (catenary or fixed)
    "fringe_curtain",  # array of strands hanging from a top rail
    "fabric_knot",     # bow / knot / tassel — fabric-like, sewn or tied
]


SwingMode = Literal[
    "rigid",     # attached to bone, no secondary animation
    "loose",    # short pendulum, simple constraint
    "floating", # catenary / chain, multi-segment
]


Mount = Literal[
    "loop",         # threaded through a fabric loop
    "chain_link",   # part of a longer chain
    "sewn",         # stitched flat to fabric
    "glued",        # decorative adherent
    "earring_post", # earring stud through earlobe
]


@dataclass(frozen=True)
class AccessoryEntry:
    # ---- identity ----
    id: str                       # canonical id, eg. ACX_OR_12MM_GOLD
    family: Family                # see Family literal
    name: str                     # display
    tags: tuple[str, ...] = ()

    # ---- geometry params (family-specific) ----
    geom: dict = field(default_factory=dict)
    # examples:
    #   ring:   {outer_diameter_mm, ring_thickness_mm, profile: round|square|d}
    #   chain:  {link_outer_mm, link_thickness_mm, links_per_cm}
    #   charm:  {height_mm, width_mm, depth_mm, geometry_id}

    # ---- material ----
    metal: str = ""               # gold | silver | rosegold | nickel | matte_black | brushed_steel
    metallic: float = 0.0         # PBR
    roughness: float = 0.5        # PBR
    base_color_hex: str = ""      # eg. "#d4af37" for gold

    # ---- attachment ----
    mount: Mount = "loop"
    anchor_anatomy: tuple[str, ...] = ()
    # eg. ("sternum_mid",) for an O-ring centred between cups
    # or  ("hip_left", "hip_right") for a waist body chain

    # ---- physical / behavioural ----
    bbox_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    weight_g: float = 0.0
    swing_mode: SwingMode = "rigid"

    # ---- compatibility hints (mirrors outfit library_compat ideas) ----
    compatible_archetypes: tuple[str, ...] = ()  # empty = any
