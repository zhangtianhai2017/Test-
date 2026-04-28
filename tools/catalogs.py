"""
Discrete catalogs for the Manufacturing Latent State layer.

Every Genome materialization picks SKUs from these dicts. Snapping is
deterministic (argmin distance, no RNG) — same Genome always picks the
same SKU. Hand-authored with citations to industry sources; sized to
v1 scope (bikini-style two-piece swimwear).

Catalog sizes (per the approved plan):
    FABRICS      12
    CONNECTORS   18
    ACCESSORIES   8
    SEAM_TYPES    6

Citations
---------
Industry references for fabric / hardware / construction SKUs follow
the same sources already cited in docs/bikini-game-export-pipeline.md
(Cloth Habit, Yarnspirations, Brother USA, Janome, Marvelous Designer
Manual, Spandex By Yard).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Fabric — 12 SKUs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FabricSKU:
    id: str
    name: str
    weave: str           # mirrors Genome.fabric_weave possible values
    composition: str
    weight_gsm: int      # grams per square meter
    stretch_warp_pct: int
    stretch_weft_pct: int
    opacity: float       # 0..1
    sheen: float         # 0..1, 0 matte / 1 satin
    metallic: float      # 0..1
    source: str          # mirrors Genome.fabric_source
    biodegradable: bool


# Real-world swim fabrics. Stretch percentages and weights from
# Spandex By Yard / Discovery Fabrics buyer guides (industry-standard
# 4-way stretch swimwear lycra: weight 180-220 gsm, stretch 50-200%).
FABRICS: dict[str, FabricSKU] = {
    "F_ECONYL_PLAIN_LIGHT": FabricSKU(
        id="F_ECONYL_PLAIN_LIGHT", name="Econyl 4-way light",
        weave="plain", composition="78% recycled nylon / 22% spandex",
        weight_gsm=190, stretch_warp_pct=180, stretch_weft_pct=160,
        opacity=0.92, sheen=0.35, metallic=0.0,
        source="econyl", biodegradable=False,
    ),
    "F_ECONYL_PLAIN_HEAVY": FabricSKU(
        id="F_ECONYL_PLAIN_HEAVY", name="Econyl 4-way heavy",
        weave="plain", composition="80% recycled nylon / 20% spandex",
        weight_gsm=230, stretch_warp_pct=140, stretch_weft_pct=120,
        opacity=1.0, sheen=0.45, metallic=0.0,
        source="econyl", biodegradable=False,
    ),
    "F_QNOVA_RIBBED": FabricSKU(
        id="F_QNOVA_RIBBED", name="Q-NOVA recycled ribbed",
        weave="ribbed", composition="80% Q-NOVA nylon / 20% spandex",
        weight_gsm=210, stretch_warp_pct=150, stretch_weft_pct=130,
        opacity=1.0, sheen=0.40, metallic=0.0,
        source="qnova", biodegradable=False,
    ),
    "F_VIRGIN_VELVET": FabricSKU(
        id="F_VIRGIN_VELVET", name="Velvet swim",
        weave="velvet", composition="82% nylon / 18% spandex",
        weight_gsm=240, stretch_warp_pct=130, stretch_weft_pct=130,
        opacity=1.0, sheen=0.65, metallic=0.0,
        source="virgin", biodegradable=False,
    ),
    "F_HUNZA_CRINKLE": FabricSKU(
        id="F_HUNZA_CRINKLE", name="Crinkle (Hunza-G style)",
        weave="crinkle", composition="78% nylon / 22% spandex",
        weight_gsm=205, stretch_warp_pct=170, stretch_weft_pct=150,
        opacity=0.95, sheen=0.30, metallic=0.0,
        source="virgin", biodegradable=False,
    ),
    "F_MISSONI_SHINY_KNIT": FabricSKU(
        id="F_MISSONI_SHINY_KNIT", name="Shiny knit (Missoni style)",
        weave="shiny_knit", composition="80% nylon / 20% spandex",
        weight_gsm=200, stretch_warp_pct=160, stretch_weft_pct=140,
        opacity=1.0, sheen=0.85, metallic=0.15,
        source="virgin", biodegradable=False,
    ),
    "F_MESH_LINING": FabricSKU(
        id="F_MESH_LINING", name="Mesh outer",
        weave="mesh", composition="85% nylon / 15% spandex",
        weight_gsm=120, stretch_warp_pct=200, stretch_weft_pct=200,
        opacity=0.40, sheen=0.20, metallic=0.0,
        source="virgin", biodegradable=False,
    ),
    "F_POWERMESH_LINING": FabricSKU(
        id="F_POWERMESH_LINING", name="Powermesh inner lining",
        weave="mesh", composition="75% nylon / 25% spandex",
        weight_gsm=150, stretch_warp_pct=200, stretch_weft_pct=180,
        opacity=0.55, sheen=0.10, metallic=0.0,
        source="virgin", biodegradable=False,
    ),
    "F_FOAM_CUP_3MM": FabricSKU(
        id="F_FOAM_CUP_3MM", name="Molded EVA foam cup, 3 mm",
        weave="plain", composition="EVA foam laminated tricot",
        weight_gsm=380, stretch_warp_pct=20, stretch_weft_pct=20,
        opacity=1.0, sheen=0.10, metallic=0.0,
        source="virgin", biodegradable=False,
    ),
    "F_CROCHET_COTTON": FabricSKU(
        id="F_CROCHET_COTTON", name="Hand crochet cotton",
        weave="crochet", composition="100% organic cotton",
        weight_gsm=170, stretch_warp_pct=30, stretch_weft_pct=30,
        opacity=0.65, sheen=0.05, metallic=0.0,
        source="cotton_blend", biodegradable=True,
    ),
    "F_BIOPOLYMER_PLAIN": FabricSKU(
        id="F_BIOPOLYMER_PLAIN", name="Bio-polyamide plain",
        weave="plain", composition="82% bio-polyamide / 18% spandex",
        weight_gsm=195, stretch_warp_pct=170, stretch_weft_pct=150,
        opacity=0.95, sheen=0.30, metallic=0.0,
        source="biopolymer", biodegradable=True,
    ),
    "F_AMNI_SOUL_RIBBED": FabricSKU(
        id="F_AMNI_SOUL_RIBBED", name="Amni Soul Eco ribbed",
        weave="ribbed", composition="80% Amni Soul Eco / 20% spandex",
        weight_gsm=215, stretch_warp_pct=140, stretch_weft_pct=120,
        opacity=1.0, sheen=0.30, metallic=0.0,
        source="amni_soul", biodegradable=True,
    ),
}


# ---------------------------------------------------------------------------
# Connectors — 18 SKUs (rings, sliders, elastics, ties, straps, specialty)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConnectorSKU:
    id: str
    name: str
    kind: str            # o_ring / d_ring / slider / buckle / tie_string /
                          # elastic_band / halter_strap / shoulder_strap /
                          # side_tie / underbust_elastic / waist_elastic
    diameter_cm: float = 0.0    # rings / sliders
    width_cm: float = 0.0       # straps / elastics
    length_cm: float = 0.0      # ties (0 = derive from anatomy at runtime)
    material: str = ""
    metal_finish: str = "none"  # mirrors Genome.hardware_metal
    path_policy: str = "free_anchored"
    elastic: bool = False
    breaking_strength_n: int = 0


# Sizes from typical garment-industry hardware catalogs (Strapworks /
# Bra-Makers Supply). Common O-rings: 0.8 / 1.2 / 1.8 cm. Common FOE
# widths: 1 cm / 1.5 cm / 2 cm. Tie-string cord: 3-5 mm round / 1.5 cm flat.
CONNECTORS: dict[str, ConnectorSKU] = {
    # rings
    "OR_8MM_GOLD": ConnectorSKU(
        id="OR_8MM_GOLD", name="8 mm O-ring brass gold-plated",
        kind="o_ring", diameter_cm=0.8, material="brass",
        metal_finish="gold", path_policy="free_anchored",
        breaking_strength_n=120),
    "OR_12MM_GOLD": ConnectorSKU(
        id="OR_12MM_GOLD", name="12 mm O-ring brass gold-plated",
        kind="o_ring", diameter_cm=1.2, material="brass",
        metal_finish="gold", path_policy="free_anchored",
        breaking_strength_n=180),
    "OR_18MM_SILVER": ConnectorSKU(
        id="OR_18MM_SILVER", name="18 mm O-ring stainless silver",
        kind="o_ring", diameter_cm=1.8, material="stainless_steel",
        metal_finish="silver", path_policy="free_anchored",
        breaking_strength_n=240),
    # sliders / buckles
    "SLI_10MM_NICKEL": ConnectorSKU(
        id="SLI_10MM_NICKEL", name="10 mm strap slider nickel",
        kind="slider", diameter_cm=1.0, width_cm=1.0, material="nickel",
        metal_finish="silver", path_policy="free_anchored"),
    "SLI_15MM_NICKEL": ConnectorSKU(
        id="SLI_15MM_NICKEL", name="15 mm strap slider nickel",
        kind="slider", diameter_cm=1.5, width_cm=1.5, material="nickel",
        metal_finish="silver", path_policy="free_anchored"),
    "BCK_15MM_GOLD": ConnectorSKU(
        id="BCK_15MM_GOLD", name="15 mm side buckle gold",
        kind="buckle", diameter_cm=1.5, width_cm=1.5, material="zinc_alloy",
        metal_finish="gold", path_policy="free_anchored"),
    # FOE elastics (industry standard widths from Brother USA / Janome FOE
    # technique guides — 5/8" and 1" are the two most common; we add 3/8")
    "FOE_10MM": ConnectorSKU(
        id="FOE_10MM", name="3/8\" fold-over elastic 10 mm",
        kind="elastic_band", width_cm=1.0, material="elastic_woven",
        elastic=True, path_policy="free_anchored"),
    "FOE_15MM": ConnectorSKU(
        id="FOE_15MM", name="5/8\" fold-over elastic 15 mm",
        kind="elastic_band", width_cm=1.5, material="elastic_woven",
        elastic=True, path_policy="free_anchored"),
    "FOE_25MM": ConnectorSKU(
        id="FOE_25MM", name="1\" fold-over elastic 25 mm",
        kind="elastic_band", width_cm=2.5, material="elastic_woven",
        elastic=True, path_policy="free_anchored"),
    # tie strings
    "TIE_CORD_3MM": ConnectorSKU(
        id="TIE_CORD_3MM", name="3 mm round polyester cord",
        kind="tie_string", width_cm=0.3, material="cord_polyester",
        path_policy="side_tie_hip_vertical"),
    "TIE_CORD_5MM": ConnectorSKU(
        id="TIE_CORD_5MM", name="5 mm round polyester cord",
        kind="tie_string", width_cm=0.5, material="cord_polyester",
        path_policy="side_tie_hip_vertical"),
    "TIE_RIBBON_15MM": ConnectorSKU(
        id="TIE_RIBBON_15MM", name="15 mm fabric ribbon tie",
        kind="tie_string", width_cm=1.5, material="woven_satin",
        path_policy="side_tie_hip_vertical"),
    # straps
    "STR_WOVEN_10MM": ConnectorSKU(
        id="STR_WOVEN_10MM", name="10 mm woven strap",
        kind="shoulder_strap", width_cm=1.0, material="elastic_woven",
        elastic=True, path_policy="shoulder_acromion_scapula"),
    "STR_WOVEN_15MM": ConnectorSKU(
        id="STR_WOVEN_15MM", name="15 mm woven strap",
        kind="shoulder_strap", width_cm=1.5, material="elastic_woven",
        elastic=True, path_policy="shoulder_acromion_scapula"),
    "STR_PADDED_20MM": ConnectorSKU(
        id="STR_PADDED_20MM", name="20 mm padded strap",
        kind="shoulder_strap", width_cm=2.0, material="elastic_padded",
        elastic=True, path_policy="shoulder_acromion_scapula"),
    # specialty
    "STR_HALTER_CORD": ConnectorSKU(
        id="STR_HALTER_CORD", name="Halter neck cord 5 mm",
        kind="halter_strap", width_cm=0.5, material="cord_polyester",
        path_policy="halter_behind_neck"),
    "ELS_UNDERBUST_15MM": ConnectorSKU(
        id="ELS_UNDERBUST_15MM", name="Underbust elastic 15 mm",
        kind="underbust_elastic", width_cm=1.5, material="elastic_woven",
        elastic=True, path_policy="underbust_horizontal"),
    "ELS_WAIST_15MM": ConnectorSKU(
        id="ELS_WAIST_15MM", name="Waist elastic 15 mm",
        kind="waist_elastic", width_cm=1.5, material="elastic_woven",
        elastic=True, path_policy="waist_band_horizontal"),
}


# ---------------------------------------------------------------------------
# Accessories — 8 SKUs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AccessorySKU:
    id: str
    name: str
    kind: str            # bow / shell_charm / pendant / fringe / beads /
                          # tassel / ring_charm
    size_cm: float       # nominal characteristic size
    material: str = ""
    metal_finish: str = "none"


ACCESSORIES: dict[str, AccessorySKU] = {
    "BOW_CHIFFON_30MM": AccessorySKU(
        id="BOW_CHIFFON_30MM", name="Chiffon bow 30 mm",
        kind="bow", size_cm=3.0, material="chiffon"),
    "SHL_TROCHUS_25MM": AccessorySKU(
        id="SHL_TROCHUS_25MM", name="Trochus shell charm",
        kind="shell_charm", size_cm=2.5, material="natural_shell"),
    "PND_DROP_15MM": AccessorySKU(
        id="PND_DROP_15MM", name="Drop pendant 15 mm",
        kind="pendant", size_cm=1.5, material="brass",
        metal_finish="gold"),
    "FRG_BEADED_80MM": AccessorySKU(
        id="FRG_BEADED_80MM", name="Beaded fringe 80 mm",
        kind="fringe", size_cm=8.0, material="seed_beads"),
    "BD_ROUND_4MM": AccessorySKU(
        id="BD_ROUND_4MM", name="Small round bead 4 mm",
        kind="beads", size_cm=0.4, material="glass"),
    "BD_OVAL_8MM": AccessorySKU(
        id="BD_OVAL_8MM", name="Oval bead 8 mm",
        kind="beads", size_cm=0.8, material="ceramic"),
    "TSL_SILK_50MM": AccessorySKU(
        id="TSL_SILK_50MM", name="Silk tassel 50 mm",
        kind="tassel", size_cm=5.0, material="silk"),
    "RNG_CHARM_15MM": AccessorySKU(
        id="RNG_CHARM_15MM", name="Ring charm 15 mm",
        kind="ring_charm", size_cm=1.5, material="brass",
        metal_finish="gold"),
}


# ---------------------------------------------------------------------------
# Seam types — 6 SKUs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeamTypeSKU:
    id: str
    name: str
    machine: str         # overlock / coverstitch / lockstitch / bartack
    threads: int
    spi: int             # stitches per inch (industry typical 8-14)
    structural: bool     # true = panel-to-panel join; false = decorative
    fabric_compat: tuple[str, ...]   # weave families it's good for


SEAM_TYPES: dict[str, SeamTypeSKU] = {
    "S_OVERLOCK_4THREAD": SeamTypeSKU(
        id="S_OVERLOCK_4THREAD", name="4-thread overlock",
        machine="overlock", threads=4, spi=12, structural=True,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle")),
    "S_COVERSTITCH_3NEEDLE": SeamTypeSKU(
        id="S_COVERSTITCH_3NEEDLE", name="3-needle coverstitch",
        machine="coverstitch", threads=5, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle")),
    "S_FOE_BIND_25MM": SeamTypeSKU(
        id="S_FOE_BIND_25MM", name="1\" FOE binding seam",
        machine="coverstitch", threads=3, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit", "velvet")),
    "S_FOE_BIND_15MM": SeamTypeSKU(
        id="S_FOE_BIND_15MM", name="5/8\" FOE binding seam",
        machine="coverstitch", threads=3, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit", "velvet",
                         "crinkle")),
    "S_BARTACK": SeamTypeSKU(
        id="S_BARTACK", name="Bartack reinforcement",
        machine="bartack", threads=2, spi=20, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit", "velvet",
                         "crinkle", "crochet")),
    "S_FLATLOCK": SeamTypeSKU(
        id="S_FLATLOCK", name="Flatlock decorative seam",
        machine="overlock", threads=4, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "shiny_knit")),
}


# ---------------------------------------------------------------------------
# Discrete snapping helpers — argmin distance, deterministic.
# ---------------------------------------------------------------------------

def snap_oring(diameter_cm: float, metal: str = "gold") -> str:
    """Snap a continuous diameter to the nearest O-ring SKU. Metal filter
    is best-effort; falls back to any metal if exact match misses."""
    rings = [(k, v) for k, v in CONNECTORS.items() if v.kind == "o_ring"]
    if metal != "any":
        match = [(k, v) for k, v in rings if v.metal_finish == metal]
        if match:
            rings = match
    return min(rings, key=lambda kv: abs(kv[1].diameter_cm - diameter_cm))[0]


def snap_strap(width_cm: float, padded: bool = False) -> str:
    """Snap to nearest shoulder/halter strap SKU."""
    candidates = [(k, v) for k, v in CONNECTORS.items()
                  if v.kind == "shoulder_strap"]
    if padded:
        match = [(k, v) for k, v in candidates if "padded" in v.material]
        if match:
            candidates = match
    return min(candidates,
                key=lambda kv: abs(kv[1].width_cm - width_cm))[0]


def snap_elastic(width_cm: float,
                 kind: str = "elastic_band") -> str:
    """Snap to nearest elastic SKU (FOE / underbust / waist)."""
    candidates = [(k, v) for k, v in CONNECTORS.items()
                  if v.kind == kind]
    if not candidates:
        candidates = [(k, v) for k, v in CONNECTORS.items() if v.elastic]
    return min(candidates,
                key=lambda kv: abs(kv[1].width_cm - width_cm))[0]


def snap_fabric(weave: str, source: str,
                 weight_gsm_target: int = 200) -> str:
    """Snap to nearest fabric SKU by (weave, source, weight)."""
    candidates = [(k, v) for k, v in FABRICS.items() if v.weave == weave]
    if not candidates:
        candidates = list(FABRICS.items())
    same_source = [(k, v) for k, v in candidates if v.source == source]
    if same_source:
        candidates = same_source
    return min(candidates,
                key=lambda kv: abs(kv[1].weight_gsm - weight_gsm_target))[0]


def snap_seam_for_fabric(fabric_id: str,
                          structural: bool = True) -> str:
    """Pick a seam type compatible with the given fabric."""
    fab = FABRICS.get(fabric_id)
    weave = fab.weave if fab is not None else "plain"
    candidates = [(k, v) for k, v in SEAM_TYPES.items()
                  if v.structural == structural and weave in v.fabric_compat]
    if not candidates:
        candidates = [(k, v) for k, v in SEAM_TYPES.items()
                      if v.structural == structural]
    return candidates[0][0]


def snap_accessory(kind: str, size_cm: float = 3.0) -> Optional[str]:
    """Snap to nearest accessory SKU of the given kind."""
    candidates = [(k, v) for k, v in ACCESSORIES.items() if v.kind == kind]
    if not candidates:
        return None
    return min(candidates,
                key=lambda kv: abs(kv[1].size_cm - size_cm))[0]


# Sanity assertions — keep dict sizes pinned to the plan.
assert len(FABRICS) == 12, f"FABRICS has {len(FABRICS)} entries, expected 12"
assert len(CONNECTORS) == 18, f"CONNECTORS has {len(CONNECTORS)}, expected 18"
assert len(ACCESSORIES) == 8, f"ACCESSORIES has {len(ACCESSORIES)}, expected 8"
assert len(SEAM_TYPES) == 6, f"SEAM_TYPES has {len(SEAM_TYPES)}, expected 6"
