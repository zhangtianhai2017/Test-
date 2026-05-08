"""
Hand-authored component library — ~80 entries across 7 kinds.

Companion to tools/library.py (the schema). Every dict here is a
{id: LibraryEntry} catalog. Combined into LIBRARY at the bottom for
single-import convenience.

Authoring conventions:
- Each entry is a real-world component (real fabric SKU, real industry
  hardware size, real swimwear cut). Citations follow earlier docs
  (Cloth Habit, Yarnspirations, Brother USA, Janome, Marvelous Designer
  Manual, Spandex By Yard).
- local_params_schema declares the entry's internal latent space — only
  variations that keep the entry "still itself" (size grading, color,
  small dimensional tweaks). Cross-component morphing is NOT in this
  space; it's a discrete library_id swap.
- compatible_with is best-effort: empty tuple = pairs with anything;
  non-empty = explicitly required partner ids.
- anatomy_hints supply default Attachment.anatomy_anchor names so the
  Outfit -> Garment cascade can wire up a default deployment without
  per-archetype guessing.
"""
from __future__ import annotations

from library import LibraryEntry


# ---------------------------------------------------------------------------
# CUP_PIECES — 15 entries (5 geometry × 3 size class)
# ---------------------------------------------------------------------------

# Geometry kind notes:
#   triangle           — string-bikini classic, soft fabric, no foam
#   brazilian          — like triangle but smaller, cheekier coverage
#   balconette         — wide horizontal cut, lifts and frames, soft
#   bandeau_unified    — single horizontal strip across both breasts
#   molded_foam        — structured foam dome for shape independent of breast
#   softcup_squareneck — low square front, soft unstructured cup

CUP_PIECES: dict[str, LibraryEntry] = {}

for size_class, scale in (("S", 0.85), ("M", 1.00), ("L", 1.18)):
    CUP_PIECES[f"CUP_TRIANGLE_{size_class}"] = LibraryEntry(
        id=f"CUP_TRIANGLE_{size_class}", kind="cup_piece",
        name=f"Triangle string cup {size_class}",
        tags=("triangle", "brazilian", "soft", "string"),
        compatible_with=(),  # works with any halter or shoulder strap
        anatomy_hints=("front_chest",),
        geometry_kind="triangle", base_polygon_recipe="cup_triangle",
        cup_size_class=size_class,
        local_params_schema={
            "half_u":      (0.10 * scale, 0.20 * scale, 0.16 * scale),
            "half_v":      (0.05 * scale, 0.10 * scale, 0.07 * scale),
            "inner_u":     (0.05, 0.16, 0.12),
            "apex_lift":   (0.0, 0.30, 0.15),
            "underband_dip": (0.0, 0.10, 0.05),
        },
        notes="Brazilian halter classic; soft, no foam.",
    )
    CUP_PIECES[f"CUP_BRAZILIAN_{size_class}"] = LibraryEntry(
        id=f"CUP_BRAZILIAN_{size_class}", kind="cup_piece",
        name=f"Brazilian small triangle {size_class}",
        tags=("brazilian", "triangle", "soft", "small"),
        anatomy_hints=("front_chest",),
        geometry_kind="triangle", base_polygon_recipe="cup_triangle",
        cup_size_class=size_class,
        local_params_schema={
            "half_u":      (0.08 * scale, 0.16 * scale, 0.12 * scale),
            "half_v":      (0.04 * scale, 0.08 * scale, 0.06 * scale),
            "inner_u":     (0.06, 0.12, 0.10),
            "apex_lift":   (0.10, 0.30, 0.20),
            "underband_dip": (0.0, 0.08, 0.04),
        },
        notes="Tighter cheeky Brazilian cut.",
    )
    CUP_PIECES[f"CUP_BALCONETTE_{size_class}"] = LibraryEntry(
        id=f"CUP_BALCONETTE_{size_class}", kind="cup_piece",
        name=f"Balconette wide cup {size_class}",
        tags=("balconette", "wide", "lifted"),
        anatomy_hints=("front_chest",),
        geometry_kind="balconette", base_polygon_recipe="cup_balconette",
        cup_size_class=size_class,
        local_params_schema={
            "half_u":      (0.16 * scale, 0.24 * scale, 0.20 * scale),
            "half_v":      (0.06 * scale, 0.10 * scale, 0.08 * scale),
            "inner_u":     (0.04, 0.10, 0.07),
            "apex_lift":   (-0.05, 0.10, 0.0),
            "underband_dip": (-0.05, 0.05, 0.0),
        },
        notes="Wide horizontal cut for lift and framing.",
    )
    CUP_PIECES[f"CUP_BANDEAU_{size_class}"] = LibraryEntry(
        id=f"CUP_BANDEAU_{size_class}", kind="cup_piece",
        name=f"Bandeau unified {size_class}",
        tags=("bandeau", "unified", "strapless"),
        anatomy_hints=("front_chest", "back_chest"),
        geometry_kind="bandeau_unified", base_polygon_recipe="cup_bandeau",
        cup_size_class=size_class,
        local_params_schema={
            "half_u":      (0.20 * scale, 0.26 * scale, 0.22 * scale),
            "half_v":      (0.08 * scale, 0.12 * scale, 0.10 * scale),
            "inner_u":     (0.0, 0.04, 0.0),
            "apex_lift":   (-0.10, 0.05, -0.05),
            "underband_dip": (-0.10, 0.05, -0.05),
        },
        notes="Single horizontal strip; strapless support relies on band.",
    )
    CUP_PIECES[f"CUP_FOAM_MOLDED_{size_class}"] = LibraryEntry(
        id=f"CUP_FOAM_MOLDED_{size_class}", kind="cup_piece",
        name=f"Molded foam cup {size_class}",
        tags=("molded_foam", "structured", "balconette"),
        compatible_with=("F_FOAM_CUP_3MM",),  # requires foam fabric
        anatomy_hints=("front_chest",),
        geometry_kind="molded_foam", base_polygon_recipe="cup_balconette",
        cup_size_class=size_class, foam_thickness_mm=3.0,
        local_params_schema={
            "half_u":      (0.16 * scale, 0.22 * scale, 0.18 * scale),
            "half_v":      (0.08 * scale, 0.12 * scale, 0.10 * scale),
            "inner_u":     (0.04, 0.10, 0.07),
            "apex_lift":   (0.0, 0.08, 0.04),
            "underband_dip": (0.0, 0.05, 0.02),
            "dome_depth_cm": (1.0, 2.0, 1.5),  # foam dome depth
        },
        notes="3mm EVA foam dome that bridges over breast topology.",
    )

# 15 cups total across 5 geometries × 3 size classes


# ---------------------------------------------------------------------------
# BOTTOM_PIECES — 10 entries (5 geometry × 2 size class)
# ---------------------------------------------------------------------------

# Geometry notes:
#   thong         — minimal back, single string
#   brazilian     — cheeky, partial back coverage
#   cheeky        — moderate, exposes some glute
#   brief         — full bottom coverage classic
#   high_waisted  — rises above natural waist

BOTTOM_PIECES: dict[str, LibraryEntry] = {}
for cov_class, scale in (("S", 0.85), ("M", 1.00)):
    BOTTOM_PIECES[f"BOT_THONG_{cov_class}"] = LibraryEntry(
        id=f"BOT_THONG_{cov_class}", kind="bottom_piece",
        name=f"Thong bottom {cov_class}",
        tags=("thong", "minimal"),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="thong", base_polygon_recipe="bottom_thong",
        coverage_class="minimal",
        local_params_schema={
            "front_top_v":   (0.20, 0.32, 0.25),
            "front_half_u":  (0.12 * scale, 0.20 * scale, 0.15 * scale),
            "front_leg_curve": (0.50, 0.80, 0.65),
            "back_top_v":    (0.20, 0.30, 0.25),
            "back_half_u":   (0.04, 0.10, 0.06),
        },
    )
    BOTTOM_PIECES[f"BOT_BRAZILIAN_{cov_class}"] = LibraryEntry(
        id=f"BOT_BRAZILIAN_{cov_class}", kind="bottom_piece",
        name=f"Brazilian cheeky {cov_class}",
        tags=("brazilian", "cheeky", "tie-side"),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="brazilian", base_polygon_recipe="bottom_thong",
        coverage_class="minimal",
        local_params_schema={
            "front_top_v":   (0.22, 0.30, 0.25),
            "front_half_u":  (0.16 * scale, 0.22 * scale, 0.18 * scale),
            "front_leg_curve": (0.55, 0.80, 0.70),
            "back_top_v":    (0.22, 0.28, 0.25),
            "back_half_u":   (0.08, 0.12, 0.10),
        },
    )
    BOTTOM_PIECES[f"BOT_CHEEKY_{cov_class}"] = LibraryEntry(
        id=f"BOT_CHEEKY_{cov_class}", kind="bottom_piece",
        name=f"Cheeky bottom {cov_class}",
        tags=("cheeky",),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="cheeky", base_polygon_recipe="bottom_brief",
        coverage_class="medium",
        local_params_schema={
            "front_top_v":   (0.24, 0.34, 0.28),
            "front_half_u":  (0.18 * scale, 0.22 * scale, 0.20 * scale),
            "front_leg_curve": (0.50, 0.75, 0.60),
            "back_top_v":    (0.24, 0.32, 0.28),
            "back_half_u":   (0.12, 0.16, 0.14),
        },
    )
    BOTTOM_PIECES[f"BOT_BRIEF_{cov_class}"] = LibraryEntry(
        id=f"BOT_BRIEF_{cov_class}", kind="bottom_piece",
        name=f"Classic brief {cov_class}",
        tags=("brief", "full_coverage"),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="brief", base_polygon_recipe="bottom_brief",
        coverage_class="full",
        local_params_schema={
            "front_top_v":   (0.30, 0.40, 0.34),
            "front_half_u":  (0.20 * scale, 0.26 * scale, 0.22 * scale),
            "front_leg_curve": (0.30, 0.55, 0.45),
            "back_top_v":    (0.30, 0.38, 0.34),
            "back_half_u":   (0.18, 0.24, 0.20),
        },
    )
    BOTTOM_PIECES[f"BOT_HIGHWAIST_{cov_class}"] = LibraryEntry(
        id=f"BOT_HIGHWAIST_{cov_class}", kind="bottom_piece",
        name=f"High-waisted {cov_class}",
        tags=("high_waisted", "retro", "full_coverage"),
        anatomy_hints=("front_pelvis", "back_pelvis"),
        geometry_kind="high_waisted", base_polygon_recipe="bottom_brief",
        coverage_class="full",
        local_params_schema={
            "front_top_v":   (0.40, 0.55, 0.48),
            "front_half_u":  (0.20 * scale, 0.26 * scale, 0.22 * scale),
            "front_leg_curve": (0.30, 0.50, 0.40),
            "back_top_v":    (0.40, 0.55, 0.48),
            "back_half_u":   (0.20, 0.26, 0.22),
        },
    )


# ---------------------------------------------------------------------------
# STRAP_PIECES — 12 entries
# ---------------------------------------------------------------------------

STRAP_PIECES: dict[str, LibraryEntry] = {
    # Halter cords — string going around behind the neck
    "STR_HALTER_3MM": LibraryEntry(
        id="STR_HALTER_3MM", kind="strap_piece",
        name="Halter cord 3 mm round polyester",
        tags=("halter", "cord", "thin"),
        anatomy_hints=("neck_base_back",),
        width_cm=0.3, length_cm=0.0, elastic=False,
        local_params_schema={"length_cm": (40.0, 70.0, 55.0)},
    ),
    "STR_HALTER_5MM": LibraryEntry(
        id="STR_HALTER_5MM", kind="strap_piece",
        name="Halter cord 5 mm round polyester",
        tags=("halter", "cord"),
        anatomy_hints=("neck_base_back",),
        width_cm=0.5, length_cm=0.0, elastic=False,
        local_params_schema={"length_cm": (40.0, 70.0, 55.0)},
    ),
    # Shoulder straps
    "STR_SHOULDER_WOVEN_10MM": LibraryEntry(
        id="STR_SHOULDER_WOVEN_10MM", kind="strap_piece",
        name="Shoulder strap woven 10 mm",
        tags=("shoulder", "woven", "thin"),
        anatomy_hints=("front_clavicle_R", "back_scapula_R"),
        width_cm=1.0, length_cm=0.0, elastic=True,
        local_params_schema={"length_cm": (24.0, 36.0, 30.0)},
    ),
    "STR_SHOULDER_WOVEN_15MM": LibraryEntry(
        id="STR_SHOULDER_WOVEN_15MM", kind="strap_piece",
        name="Shoulder strap woven 15 mm",
        tags=("shoulder", "woven"),
        anatomy_hints=("front_clavicle_R", "back_scapula_R"),
        width_cm=1.5, length_cm=0.0, elastic=True,
        local_params_schema={"length_cm": (24.0, 36.0, 30.0)},
    ),
    "STR_SHOULDER_PADDED_20MM": LibraryEntry(
        id="STR_SHOULDER_PADDED_20MM", kind="strap_piece",
        name="Shoulder strap padded 20 mm",
        tags=("shoulder", "padded", "wide"),
        anatomy_hints=("front_clavicle_R", "back_scapula_R"),
        width_cm=2.0, length_cm=0.0, elastic=True,
        local_params_schema={"length_cm": (24.0, 38.0, 32.0)},
    ),
    # Side ties
    "STR_TIE_CORD_3MM": LibraryEntry(
        id="STR_TIE_CORD_3MM", kind="strap_piece",
        name="Side tie cord 3 mm",
        tags=("tie", "side_tie", "cord", "thin"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=0.3,
        local_params_schema={"length_cm": (15.0, 30.0, 22.0)},
    ),
    "STR_TIE_CORD_5MM": LibraryEntry(
        id="STR_TIE_CORD_5MM", kind="strap_piece",
        name="Side tie cord 5 mm",
        tags=("tie", "side_tie", "cord"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=0.5,
        local_params_schema={"length_cm": (15.0, 30.0, 22.0)},
    ),
    "STR_TIE_RIBBON_15MM": LibraryEntry(
        id="STR_TIE_RIBBON_15MM", kind="strap_piece",
        name="Side tie ribbon 15 mm",
        tags=("tie", "side_tie", "ribbon", "wide"),
        anatomy_hints=("hip_R", "hip_L"),
        width_cm=1.5,
        local_params_schema={"length_cm": (20.0, 35.0, 28.0)},
    ),
    # FOE elastic — fold-over edge finish, also used as underbust band
    "STR_FOE_10MM": LibraryEntry(
        id="STR_FOE_10MM", kind="strap_piece",
        name="3/8\" fold-over elastic 10 mm",
        tags=("FOE", "underbust", "elastic", "edge"),
        anatomy_hints=("sternum",),
        width_cm=1.0, elastic=True,
    ),
    "STR_FOE_15MM": LibraryEntry(
        id="STR_FOE_15MM", kind="strap_piece",
        name="5/8\" fold-over elastic 15 mm",
        tags=("FOE", "underbust", "elastic", "edge"),
        anatomy_hints=("sternum",),
        width_cm=1.5, elastic=True,
    ),
    "STR_FOE_25MM": LibraryEntry(
        id="STR_FOE_25MM", kind="strap_piece",
        name="1\" fold-over elastic 25 mm",
        tags=("FOE", "underbust", "elastic", "edge", "wide"),
        anatomy_hints=("sternum",),
        width_cm=2.5, elastic=True,
    ),
    # Back band (bandeau-style continuous fabric)
    "STR_BACKBAND_RIBBED": LibraryEntry(
        id="STR_BACKBAND_RIBBED", kind="strap_piece",
        name="Back band ribbed wide",
        tags=("back_band", "wide", "structured"),
        anatomy_hints=("back_scapula_R", "back_scapula_L"),
        width_cm=4.0,
        local_params_schema={"height_cm": (3.5, 6.0, 4.5)},
    ),
    "STR_BACKBAND_PLAIN": LibraryEntry(
        id="STR_BACKBAND_PLAIN", kind="strap_piece",
        name="Back band plain",
        tags=("back_band",),
        anatomy_hints=("back_scapula_R", "back_scapula_L"),
        width_cm=3.0,
        local_params_schema={"height_cm": (2.5, 5.0, 3.5)},
    ),
}


# ---------------------------------------------------------------------------
# HARDWARE — 10 entries (rings + sliders + buckles)
# ---------------------------------------------------------------------------

HARDWARE: dict[str, LibraryEntry] = {
    "HW_OR_8MM_GOLD": LibraryEntry(
        id="HW_OR_8MM_GOLD", kind="hardware",
        name="O-ring 8 mm gold",
        tags=("o_ring", "small", "gold"),
        diameter_cm=0.8, metal_finish="gold",
    ),
    "HW_OR_12MM_GOLD": LibraryEntry(
        id="HW_OR_12MM_GOLD", kind="hardware",
        name="O-ring 12 mm gold",
        tags=("o_ring", "gold"),
        diameter_cm=1.2, metal_finish="gold",
    ),
    "HW_OR_18MM_SILVER": LibraryEntry(
        id="HW_OR_18MM_SILVER", kind="hardware",
        name="O-ring 18 mm silver",
        tags=("o_ring", "large", "silver"),
        diameter_cm=1.8, metal_finish="silver",
    ),
    "HW_OR_12MM_ROSEGOLD": LibraryEntry(
        id="HW_OR_12MM_ROSEGOLD", kind="hardware",
        name="O-ring 12 mm rose gold",
        tags=("o_ring", "rose_gold"),
        diameter_cm=1.2, metal_finish="rose_gold",
    ),
    "HW_DR_15MM_SILVER": LibraryEntry(
        id="HW_DR_15MM_SILVER", kind="hardware",
        name="D-ring 15 mm silver",
        tags=("d_ring", "silver"),
        diameter_cm=1.5, metal_finish="silver",
    ),
    "HW_SLIDER_10MM_NICKEL": LibraryEntry(
        id="HW_SLIDER_10MM_NICKEL", kind="hardware",
        name="Strap slider 10 mm nickel",
        tags=("slider",), width_cm=1.0, metal_finish="silver",
    ),
    "HW_SLIDER_15MM_NICKEL": LibraryEntry(
        id="HW_SLIDER_15MM_NICKEL", kind="hardware",
        name="Strap slider 15 mm nickel",
        tags=("slider",), width_cm=1.5, metal_finish="silver",
    ),
    "HW_SLIDER_20MM_GOLD": LibraryEntry(
        id="HW_SLIDER_20MM_GOLD", kind="hardware",
        name="Strap slider 20 mm gold",
        tags=("slider", "gold"), width_cm=2.0, metal_finish="gold",
    ),
    "HW_BUCKLE_15MM_GOLD": LibraryEntry(
        id="HW_BUCKLE_15MM_GOLD", kind="hardware",
        name="Side buckle 15 mm gold",
        tags=("buckle", "gold"), width_cm=1.5, metal_finish="gold",
    ),
    "HW_HOOKEYE_BLACK": LibraryEntry(
        id="HW_HOOKEYE_BLACK", kind="hardware",
        name="Hook & eye pair black",
        tags=("hook_eye", "closure"),
        width_cm=0.8, metal_finish="none",
    ),
}


# ---------------------------------------------------------------------------
# ACCESSORIES — 10 entries
# ---------------------------------------------------------------------------

ACCESSORIES: dict[str, LibraryEntry] = {
    "ACC_BOW_CHIFFON_30MM": LibraryEntry(
        id="ACC_BOW_CHIFFON_30MM", kind="accessory",
        name="Chiffon bow 30 mm",
        tags=("bow", "chiffon"),
        anatomy_hints=("sternum",),
        local_params_schema={"size_cm": (2.0, 5.0, 3.0)},
    ),
    "ACC_BOW_SATIN_40MM": LibraryEntry(
        id="ACC_BOW_SATIN_40MM", kind="accessory",
        name="Satin bow 40 mm",
        tags=("bow", "satin"),
        anatomy_hints=("sternum",),
        local_params_schema={"size_cm": (3.0, 6.0, 4.0)},
    ),
    "ACC_SHELL_TROCHUS_25MM": LibraryEntry(
        id="ACC_SHELL_TROCHUS_25MM", kind="accessory",
        name="Trochus shell charm 25 mm",
        tags=("shell_charm", "shell", "boho", "natural"),
        anatomy_hints=("sternum",),
        local_params_schema={"size_cm": (1.5, 3.0, 2.5)},
    ),
    "ACC_SHELL_COWRIE_20MM": LibraryEntry(
        id="ACC_SHELL_COWRIE_20MM", kind="accessory",
        name="Cowrie shell 20 mm",
        tags=("shell_charm", "shell", "boho"),
        anatomy_hints=("sternum",),
        local_params_schema={"size_cm": (1.2, 2.5, 2.0)},
    ),
    "ACC_PENDANT_DROP_15MM_GOLD": LibraryEntry(
        id="ACC_PENDANT_DROP_15MM_GOLD", kind="accessory",
        name="Drop pendant 15 mm gold",
        tags=("pendant", "drop", "gold"),
        anatomy_hints=("sternum",),
        metal_finish="gold",
        local_params_schema={"size_cm": (1.0, 2.5, 1.5)},
    ),
    "ACC_FRINGE_BEADED_80MM": LibraryEntry(
        id="ACC_FRINGE_BEADED_80MM", kind="accessory",
        name="Beaded fringe 80 mm",
        tags=("fringe", "beaded", "boho"),
        anatomy_hints=("hip_R", "hip_L"),
        local_params_schema={"length_cm": (5.0, 12.0, 8.0)},
    ),
    "ACC_FRINGE_RAW_60MM": LibraryEntry(
        id="ACC_FRINGE_RAW_60MM", kind="accessory",
        name="Raw fabric fringe 60 mm",
        tags=("fringe", "raw"),
        anatomy_hints=("hip_R", "hip_L"),
        local_params_schema={"length_cm": (4.0, 10.0, 6.0)},
    ),
    "ACC_BEADS_SMALL_4MM": LibraryEntry(
        id="ACC_BEADS_SMALL_4MM", kind="accessory",
        name="Small round beads 4 mm",
        tags=("beads",),
        anatomy_hints=("neck_base_front",),
        local_params_schema={"count": (8, 30, 12)},
    ),
    "ACC_BEADS_OVAL_8MM": LibraryEntry(
        id="ACC_BEADS_OVAL_8MM", kind="accessory",
        name="Oval ceramic beads 8 mm",
        tags=("beads", "ceramic"),
        anatomy_hints=("neck_base_front",),
        local_params_schema={"count": (5, 15, 8)},
    ),
    "ACC_TASSEL_SILK_50MM": LibraryEntry(
        id="ACC_TASSEL_SILK_50MM", kind="accessory",
        name="Silk tassel 50 mm",
        tags=("tassel", "silk"),
        anatomy_hints=("hip_R", "hip_L", "sternum"),
        local_params_schema={"length_cm": (3.0, 8.0, 5.0)},
    ),
}


# ---------------------------------------------------------------------------
# FABRICS — 12 entries (carried over from catalogs.py + cleanup)
# ---------------------------------------------------------------------------

FABRICS: dict[str, LibraryEntry] = {
    "F_ECONYL_PLAIN_LIGHT": LibraryEntry(
        id="F_ECONYL_PLAIN_LIGHT", kind="fabric",
        name="Econyl 4-way light", tags=("plain", "swim", "eco"),
        weave="plain", composition="78% recycled nylon / 22% spandex",
        weight_gsm=190, stretch_warp_pct=180, stretch_weft_pct=160,
        opacity=0.92, sheen=0.35, fabric_source="econyl",
    ),
    "F_ECONYL_PLAIN_HEAVY": LibraryEntry(
        id="F_ECONYL_PLAIN_HEAVY", kind="fabric",
        name="Econyl 4-way heavy", tags=("plain", "swim", "eco", "heavy"),
        weave="plain", composition="80% recycled nylon / 20% spandex",
        weight_gsm=230, stretch_warp_pct=140, stretch_weft_pct=120,
        opacity=1.0, sheen=0.45, fabric_source="econyl",
    ),
    "F_QNOVA_RIBBED": LibraryEntry(
        id="F_QNOVA_RIBBED", kind="fabric",
        name="Q-NOVA ribbed", tags=("ribbed", "swim", "eco"),
        weave="ribbed", composition="80% Q-NOVA nylon / 20% spandex",
        weight_gsm=210, stretch_warp_pct=150, stretch_weft_pct=130,
        opacity=1.0, sheen=0.40, fabric_source="qnova",
    ),
    "F_VIRGIN_VELVET": LibraryEntry(
        id="F_VIRGIN_VELVET", kind="fabric",
        name="Velvet swim", tags=("velvet", "luxe", "shiny"),
        weave="velvet", composition="82% nylon / 18% spandex",
        weight_gsm=240, stretch_warp_pct=130, stretch_weft_pct=130,
        opacity=1.0, sheen=0.65, fabric_source="virgin",
    ),
    "F_HUNZA_CRINKLE": LibraryEntry(
        id="F_HUNZA_CRINKLE", kind="fabric",
        name="Crinkle (Hunza-G style)", tags=("crinkle", "textured"),
        weave="crinkle", composition="78% nylon / 22% spandex",
        weight_gsm=205, stretch_warp_pct=170, stretch_weft_pct=150,
        opacity=0.95, sheen=0.30, fabric_source="virgin",
    ),
    "F_MISSONI_SHINY_KNIT": LibraryEntry(
        id="F_MISSONI_SHINY_KNIT", kind="fabric",
        name="Shiny knit", tags=("shiny_knit", "luxe", "metallic"),
        weave="shiny_knit", composition="80% nylon / 20% spandex",
        weight_gsm=200, stretch_warp_pct=160, stretch_weft_pct=140,
        opacity=1.0, sheen=0.85, metallic=0.15, fabric_source="virgin",
    ),
    "F_MESH_OUTER": LibraryEntry(
        id="F_MESH_OUTER", kind="fabric",
        name="Mesh outer layer", tags=("mesh", "sheer"),
        weave="mesh", composition="85% nylon / 15% spandex",
        weight_gsm=120, stretch_warp_pct=200, stretch_weft_pct=200,
        opacity=0.40, sheen=0.20, fabric_source="virgin",
    ),
    "F_POWERMESH_LINING": LibraryEntry(
        id="F_POWERMESH_LINING", kind="fabric",
        name="Powermesh lining", tags=("powermesh", "lining", "smoothing"),
        weave="mesh", composition="75% nylon / 25% spandex",
        weight_gsm=150, stretch_warp_pct=200, stretch_weft_pct=180,
        opacity=0.55, sheen=0.10, fabric_source="virgin",
    ),
    "F_FOAM_CUP_3MM": LibraryEntry(
        id="F_FOAM_CUP_3MM", kind="fabric",
        name="Molded EVA foam cup 3 mm", tags=("foam", "padding", "structured"),
        weave="plain", composition="EVA foam laminated tricot",
        weight_gsm=380, stretch_warp_pct=20, stretch_weft_pct=20,
        opacity=1.0, sheen=0.10, fabric_source="virgin",
    ),
    "F_CROCHET_COTTON": LibraryEntry(
        id="F_CROCHET_COTTON", kind="fabric",
        name="Crochet cotton", tags=("crochet", "cotton", "boho"),
        weave="crochet", composition="100% organic cotton",
        weight_gsm=170, stretch_warp_pct=30, stretch_weft_pct=30,
        opacity=0.65, sheen=0.05, fabric_source="cotton_blend",
        biodegradable=True,
    ),
    "F_BIOPOLYMER_PLAIN": LibraryEntry(
        id="F_BIOPOLYMER_PLAIN", kind="fabric",
        name="Bio-polyamide plain", tags=("plain", "bio", "eco"),
        weave="plain", composition="82% bio-polyamide / 18% spandex",
        weight_gsm=195, stretch_warp_pct=170, stretch_weft_pct=150,
        opacity=0.95, sheen=0.30, fabric_source="biopolymer",
        biodegradable=True,
    ),
    "F_AMNI_SOUL_RIBBED": LibraryEntry(
        id="F_AMNI_SOUL_RIBBED", kind="fabric",
        name="Amni Soul Eco ribbed", tags=("ribbed", "bio", "eco"),
        weave="ribbed", composition="80% Amni Soul Eco / 20% spandex",
        weight_gsm=215, stretch_warp_pct=140, stretch_weft_pct=120,
        opacity=1.0, sheen=0.30, fabric_source="amni_soul",
        biodegradable=True,
    ),
}


# ---------------------------------------------------------------------------
# BODY_JEWELRY — 10 entries (NEW v2 — independent body-worn accessories)
# ---------------------------------------------------------------------------

BODY_JEWELRY: dict[str, LibraryEntry] = {
    "BJ_BRACELET_CHAIN_GOLD": LibraryEntry(
        id="BJ_BRACELET_CHAIN_GOLD", kind="body_jewelry",
        name="Wrist chain bracelet gold",
        tags=("bracelet", "chain", "gold"),
        anatomy_hints=("wrist_R",), jewelry_form="bracelet_chain",
        metal_finish="gold",
        local_params_schema={"diameter_cm": (5.5, 7.5, 6.5)},
    ),
    "BJ_BRACELET_BEADED": LibraryEntry(
        id="BJ_BRACELET_BEADED", kind="body_jewelry",
        name="Beaded wrist bracelet",
        tags=("bracelet", "beaded", "boho"),
        anatomy_hints=("wrist_R",), jewelry_form="bracelet_beaded",
        local_params_schema={"diameter_cm": (5.5, 7.5, 6.5)},
    ),
    "BJ_NECKLACE_CHOKER_GOLD": LibraryEntry(
        id="BJ_NECKLACE_CHOKER_GOLD", kind="body_jewelry",
        name="Gold choker necklace",
        tags=("necklace", "choker", "gold"),
        anatomy_hints=("neck_front",), jewelry_form="necklace_choker",
        metal_finish="gold",
        local_params_schema={"width_cm": (0.3, 1.5, 0.6)},
    ),
    "BJ_NECKLACE_PENDANT_SHELL": LibraryEntry(
        id="BJ_NECKLACE_PENDANT_SHELL", kind="body_jewelry",
        name="Shell pendant necklace",
        tags=("necklace", "pendant", "shell", "boho"),
        anatomy_hints=("neck_front",), jewelry_form="necklace_pendant",
        local_params_schema={"chain_length_cm": (40.0, 55.0, 45.0)},
    ),
    "BJ_EARRING_DROP_GOLD": LibraryEntry(
        id="BJ_EARRING_DROP_GOLD", kind="body_jewelry",
        name="Gold drop earring",
        tags=("earring", "drop", "gold"),
        anatomy_hints=("earlobe_R", "earlobe_L"), jewelry_form="earring_drop",
        metal_finish="gold",
        local_params_schema={"length_cm": (1.5, 4.0, 2.5)},
    ),
    "BJ_EARRING_STUD_PEARL": LibraryEntry(
        id="BJ_EARRING_STUD_PEARL", kind="body_jewelry",
        name="Pearl stud earring",
        tags=("earring", "stud", "pearl"),
        anatomy_hints=("earlobe_R", "earlobe_L"), jewelry_form="earring_stud",
        metal_finish="pearl",
        local_params_schema={"size_cm": (0.4, 1.0, 0.6)},
    ),
    "BJ_BODY_CHAIN_WAIST": LibraryEntry(
        id="BJ_BODY_CHAIN_WAIST", kind="body_jewelry",
        name="Body chain waist gold",
        tags=("body_chain", "waist", "gold"),
        anatomy_hints=("belly_button",), jewelry_form="body_chain_waist",
        metal_finish="gold",
        local_params_schema={"length_cm": (60.0, 90.0, 75.0)},
    ),
    "BJ_BODY_CHAIN_BELLY": LibraryEntry(
        id="BJ_BODY_CHAIN_BELLY", kind="body_jewelry",
        name="Belly chain layered",
        tags=("body_chain", "belly", "layered"),
        anatomy_hints=("belly_button",), jewelry_form="body_chain_belly",
        metal_finish="silver",
        local_params_schema={"length_cm": (55.0, 85.0, 68.0)},
    ),
    "BJ_ANKLET_CHAIN": LibraryEntry(
        id="BJ_ANKLET_CHAIN", kind="body_jewelry",
        name="Anklet chain silver",
        tags=("anklet", "chain", "silver"),
        anatomy_hints=("ankle_R",), jewelry_form="anklet_chain",
        metal_finish="silver",
        local_params_schema={"diameter_cm": (7.0, 10.0, 8.5)},
    ),
    "BJ_ANKLET_CHARM_BEACH": LibraryEntry(
        id="BJ_ANKLET_CHARM_BEACH", kind="body_jewelry",
        name="Beach charm anklet",
        tags=("anklet", "charm", "beach", "boho"),
        anatomy_hints=("ankle_R",), jewelry_form="anklet_charm",
        local_params_schema={"diameter_cm": (7.0, 10.0, 8.5)},
    ),
}


# ---------------------------------------------------------------------------
# SEAM_TYPES — 6 entries
# ---------------------------------------------------------------------------

SEAM_TYPES: dict[str, LibraryEntry] = {
    "S_OVERLOCK_4THREAD": LibraryEntry(
        id="S_OVERLOCK_4THREAD", kind="seam_type",
        name="4-thread overlock", tags=("structural", "overlock"),
        machine="overlock", threads=4, spi=12, structural=True,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle"),
    ),
    "S_COVERSTITCH_3NEEDLE": LibraryEntry(
        id="S_COVERSTITCH_3NEEDLE", kind="seam_type",
        name="3-needle coverstitch", tags=("decorative", "coverstitch"),
        machine="coverstitch", threads=5, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle"),
    ),
    "S_FOE_BIND_25MM": LibraryEntry(
        id="S_FOE_BIND_25MM", kind="seam_type",
        name="1\" FOE binding seam", tags=("FOE", "edge", "wide"),
        machine="coverstitch", threads=3, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit", "velvet"),
    ),
    "S_FOE_BIND_15MM": LibraryEntry(
        id="S_FOE_BIND_15MM", kind="seam_type",
        name="5/8\" FOE binding seam", tags=("FOE", "edge"),
        machine="coverstitch", threads=3, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle"),
    ),
    "S_BARTACK": LibraryEntry(
        id="S_BARTACK", kind="seam_type",
        name="Bartack reinforcement", tags=("bartack", "reinforce"),
        machine="bartack", threads=2, spi=20, structural=False,
        fabric_compat=("plain", "ribbed", "mesh", "shiny_knit",
                         "velvet", "crinkle", "crochet"),
    ),
    "S_FLATLOCK": LibraryEntry(
        id="S_FLATLOCK", kind="seam_type",
        name="Flatlock decorative seam", tags=("decorative", "flatlock"),
        machine="overlock", threads=4, spi=10, structural=False,
        fabric_compat=("plain", "ribbed", "shiny_knit"),
    ),
}


# ---------------------------------------------------------------------------
# Combined library — merge all kind dicts into one id-keyed lookup
# ---------------------------------------------------------------------------

LIBRARY: dict[str, LibraryEntry] = {}
for d in (CUP_PIECES, BOTTOM_PIECES, STRAP_PIECES, HARDWARE,
            ACCESSORIES, FABRICS, BODY_JEWELRY, SEAM_TYPES):
    LIBRARY.update(d)


def entries_by_kind(kind: str) -> list[LibraryEntry]:
    return [e for e in LIBRARY.values() if e.kind == kind]


def entries_matching_slot(slot, library: dict = None) -> list[LibraryEntry]:
    """Return all library entries that satisfy a SlotSpec."""
    library = library or LIBRARY
    return [e for e in library.values() if slot.matches(e)]


# Sanity: every SlotSpec.allowed_tags has at least 2 matching entries
def _sanity_slot_coverage():
    from library import ARCHETYPE_SLOTS
    issues = []
    for arch, slots in ARCHETYPE_SLOTS.items():
        for s in slots:
            matches = entries_matching_slot(s)
            if s.required and len(matches) < 1:
                issues.append(f"  {arch}.{s.name}: 0 matches "
                              f"(required, kind={s.kind} tags={s.allowed_tags})")
            elif len(matches) < 2:
                issues.append(f"  {arch}.{s.name}: {len(matches)} matches "
                              f"(below diversity floor of 2)")
    return issues


if __name__ == "__main__":
    print(f"library size: {len(LIBRARY)} entries")
    by_kind = {}
    for e in LIBRARY.values():
        by_kind.setdefault(e.kind, []).append(e.id)
    for k in sorted(by_kind):
        print(f"  {k:14s} {len(by_kind[k]):3d}")
    issues = _sanity_slot_coverage()
    if issues:
        print(f"\n{len(issues)} slot coverage issue(s):")
        for i in issues:
            print(i)
    else:
        print("\nall slots have >=2 matching entries")
