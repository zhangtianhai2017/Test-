"""
Outfit — chromosome layer of the v2 cascaded stack.

    Component Library  →  [Outfit]  →  Garment  →  BodyDeployment  →  mesh

Outfit is the GA-friendly representation: an archetype + a list of
slot assignments (library_id + local_params per slot) + a small bag
of global_design fields (color/pattern/palette that don't belong to
any one component).

Pipeline functions
------------------
- random_outfit(archetype, rng) — sample a legal Outfit from scratch
  by picking one matching library entry per slot.
- outfit_to_garment(outfit) — concretize Outfit into the
  existing Garment dataclass that downstream code already consumes
  (validate_garment, deploy_to_body, build_strap_meshes, etc.).
- outfit_to_genome(outfit) — lossy projection back to the legacy 44-dim
  Genome so existing fitness functions still work unchanged.
- genome_to_outfit(genome) — for migration: snap an existing Genome's
  abstract floats to the nearest library entries and harvest local_params.

Convention: outfit_to_garment is the SOURCE OF TRUTH; outfit_to_genome
is just a dumb projection for backward compatibility with fitness.py
and the v1 GA. Future fitness can read Outfit directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
import random

from library import (LibraryEntry, SlotSpec, ARCHETYPE_SLOTS,
                       validate_outfit)
from library_data import (LIBRARY, entries_matching_slot,
                            CUP_PIECES, BOTTOM_PIECES, STRAP_PIECES,
                            HARDWARE, ACCESSORIES, FABRICS, BODY_JEWELRY,
                            SEAM_TYPES)
import polygon_recipes
from garment_state import (
    Garment, PatternPiece, FabricRef, ConnectorRef, AccessoryRef,
    Seam, EdgeRef, Attachment, GENERATOR_VERSION,
)


# ---------------------------------------------------------------------------
# Outfit dataclass
# ---------------------------------------------------------------------------

@dataclass
class SlotAssignment:
    slot_name: str
    library_id: str
    local_params: dict = field(default_factory=dict)


@dataclass
class Outfit:
    archetype: str
    slot_assignments: list[SlotAssignment] = field(default_factory=list)
    global_design: dict = field(default_factory=dict)
    # global_design recognized keys:
    #   hue, saturation, lightness  — primary HSL color (overrides
    #     fabric's stored color when set)
    #   secondary_hue, secondary_saturation, secondary_lightness
    #   pattern_overlay   — "solid" / "stripe" / "polka" / "floral" / etc.
    #   pattern_scale     — 0..1
    #   pattern_angle     — 0..1
    #   palette_preset    — name of a WGSN palette preset

    def get_assignments(self, slot_name: str) -> list[SlotAssignment]:
        return [a for a in self.slot_assignments if a.slot_name == slot_name]

    def first_assignment(self, slot_name: str) -> Optional[SlotAssignment]:
        for a in self.slot_assignments:
            if a.slot_name == slot_name:
                return a
        return None


# ---------------------------------------------------------------------------
# Random sampling — pick one legal entry per required slot
# ---------------------------------------------------------------------------

def _pin_to_max_coverage(entry: LibraryEntry, lp: dict) -> dict:
    """At bottom strict=1, force front_top_v / front_half_u / back_top_v
    / back_half_u to schema MAX (most coverage)."""
    schema = entry.local_params_schema or {}
    out = dict(lp)
    for k in ("front_top_v", "front_half_u", "back_top_v", "back_half_u"):
        if k in schema:
            _, hi, _ = schema[k]
            out[k] = float(hi)
    return out


def _pin_to_max_cup_coverage(entry: LibraryEntry, lp: dict) -> dict:
    """At cup strict=1, pin half_u / half_v to schema MAX (wider, taller
    cup) and inner_u to schema MIN (cups close in toward sternum, less
    cleavage gap). Lift / underband_dip stay at their sampled values."""
    schema = entry.local_params_schema or {}
    out = dict(lp)
    for k in ("half_u", "half_v"):
        if k in schema:
            _, hi, _ = schema[k]
            out[k] = float(hi)
    if "inner_u" in schema:
        lo, _, _ = schema["inner_u"]
        out["inner_u"] = float(lo)
    return out


def random_outfit(archetype: str, rng: Optional[random.Random] = None,
                   bottom_coverage_strict: Optional[float] = None,
                   cup_coverage_strict: Optional[float] = None) -> Outfit:
    """Sample an Outfit by picking one library entry per slot. Required
    slots get filled; optional slots get filled with probability 0.5
    (or 0.3 for body_jewelry / accessory).

    bottom_coverage_strict / cup_coverage_strict: 0..1 each (None = use
    the corresponding library.* module global).
    """
    if archetype not in ARCHETYPE_SLOTS:
        raise ValueError(f"unknown archetype '{archetype}'")
    rng = rng or random.Random()
    import library
    bottom_strict = library.BOTTOM_COVERAGE_STRICT if bottom_coverage_strict is None \
        else float(bottom_coverage_strict)
    cup_strict = library.CUP_COVERAGE_STRICT if cup_coverage_strict is None \
        else float(cup_coverage_strict)

    assignments: list[SlotAssignment] = []
    for spec in ARCHETYPE_SLOTS[archetype]:
        candidates = entries_matching_slot(spec)
        if spec.kind == "bottom_piece":
            candidates = library.filter_bottoms_by_coverage(candidates, bottom_strict)
        elif spec.kind == "cup_piece":
            candidates = library.filter_cups_by_coverage(candidates, cup_strict)
        if not candidates:
            if spec.required:
                raise RuntimeError(
                    f"required slot '{spec.name}' has no library entries")
            continue
        if not spec.required:
            p_include = 0.3 if spec.kind in ("accessory", "body_jewelry") else 0.5
            if rng.random() > p_include:
                continue
        n = 1
        if spec.max_count > 1:
            n = rng.randint(1, min(spec.max_count, len(candidates)))
        chosen = rng.sample(candidates, n)
        for entry in chosen:
            lp = entry.sample_local_params(rng)
            if spec.kind == "bottom_piece" and bottom_strict >= 0.66:
                lp = _pin_to_max_coverage(entry, lp)
            elif spec.kind == "cup_piece" and cup_strict >= 0.66:
                lp = _pin_to_max_cup_coverage(entry, lp)
            assignments.append(SlotAssignment(
                slot_name=spec.name,
                library_id=entry.id,
                local_params=lp,
            ))

    # Resolve compatible_with constraints. Default policy: drop the
    # offending entry and resample from candidates whose compatible_with
    # is already satisfied (avoids foam laminate in primary_fabric).
    # When cup_strict >= 0.66 the user explicitly chose a structured cup
    # (molded foam needs foam laminate), so we respect that and override
    # primary_fabric instead of swapping the cup back to a softer geom.
    archetype_slots = {s.name: s for s in ARCHETYPE_SLOTS[archetype]}
    selected_ids = {a.library_id for a in assignments}
    for a in list(assignments):
        entry = LIBRARY.get(a.library_id)
        if not entry or not entry.compatible_with:
            continue
        if set(entry.compatible_with) & selected_ids:
            continue
        spec = archetype_slots.get(a.slot_name)
        force_keep = (spec is not None and spec.kind == "cup_piece"
                       and cup_strict >= 0.66)
        if spec is not None and not force_keep:
            same_slot = entries_matching_slot(spec)
            if spec.kind == "cup_piece":
                same_slot = library.filter_cups_by_coverage(same_slot, cup_strict)
            elif spec.kind == "bottom_piece":
                same_slot = library.filter_bottoms_by_coverage(same_slot, bottom_strict)
            alts = [c for c in same_slot
                    if c.id != entry.id and (
                        not c.compatible_with
                        or set(c.compatible_with) & selected_ids)]
            if alts:
                replacement = rng.choice(alts)
                a.library_id = replacement.id
                a.local_params = replacement.sample_local_params(rng)
                selected_ids.discard(entry.id)
                selected_ids.add(replacement.id)
                continue
        # No clean alternate (or strict cup forced us to keep): inject
        # the partner. Fabric partners go to a real lining_fabric slot
        # if the archetype has one; else under strict cup we override
        # primary_fabric (foam laminate IS the right material for a
        # molded cup), else fall back to 'auxiliary_<kind>' which the
        # validator surfaces as an O4 conflict.
        req_id = entry.compatible_with[0]
        req_entry = LIBRARY.get(req_id)
        if req_entry is None:
            continue
        if "lining_fabric" in archetype_slots and req_entry.kind == "fabric":
            existing = next((sa for sa in assignments
                              if sa.slot_name == "lining_fabric"), None)
            if existing is not None:
                existing.library_id = req_id
                existing.local_params = req_entry.sample_local_params(rng)
            else:
                assignments.append(SlotAssignment(
                    slot_name="lining_fabric", library_id=req_id,
                    local_params=req_entry.sample_local_params(rng)))
        elif force_keep and req_entry.kind == "fabric":
            for sa in assignments:
                if sa.slot_name == "primary_fabric":
                    sa.library_id = req_id
                    sa.local_params = {}
                    break
        else:
            assignments.append(SlotAssignment(
                slot_name=f"auxiliary_{req_entry.kind}",
                library_id=req_id,
                local_params=req_entry.sample_local_params(rng)))
        selected_ids.add(req_id)

    # Random global_design
    # symmetry: binary — 70% perfect mirror, 30% dramatic asymmetric.
    # No middle ground (a small skew reads as a construction defect).
    if rng.random() < 0.30:
        symmetry_mode, asym_amount = "dramatic_asym", 0.5 + 0.5 * rng.random()
    else:
        symmetry_mode, asym_amount = "mirror", 0.0
    # geom_aesthetic: free / thirds / golden.  When chosen, pulls cup
    # hu/hv ratio toward 1.5 (thirds) or 1.618 (phi).
    geom_choice = rng.choices(
        ["free", "thirds", "golden"], weights=[0.55, 0.20, 0.25])[0]
    geom_pull = {"free": 0.0, "thirds": 0.45, "golden": 0.85}[geom_choice]

    global_design = {
        "hue": rng.uniform(0.0, 1.0),
        "saturation": rng.uniform(0.3, 0.85),
        "lightness": rng.uniform(0.3, 0.8),
        "pattern_overlay": rng.choice(
            ["solid", "stripe", "polka", "gingham", "chevron",
             "floral", "tropical", "leopard", "tie_dye", "ombre",
             "checker", "herringbone"]),
        "pattern_scale": rng.uniform(0.2, 0.9),
        "palette_preset": "free",
        # Batch-3 structural / aesthetic axes (see verify_ga_uv constraints).
        "symmetry_mode":  symmetry_mode,
        "asym_amount":    asym_amount,
        "geom_aesthetic": geom_choice,
        "geom_ratio_pull": geom_pull,
    }
    return Outfit(archetype=archetype, slot_assignments=assignments,
                    global_design=global_design)


# ---------------------------------------------------------------------------
# outfit_to_garment — the central translation
# ---------------------------------------------------------------------------

def _entry(library_id: str) -> LibraryEntry:
    e = LIBRARY.get(library_id)
    if e is None:
        raise KeyError(f"library_id '{library_id}' not in LIBRARY")
    return e


def _build_fabric_ref(entry: LibraryEntry) -> FabricRef:
    return FabricRef(
        id=entry.id, name=entry.name, weave=entry.weave,
        composition=entry.composition, weight_gsm=entry.weight_gsm,
        stretch_warp_pct=entry.stretch_warp_pct,
        stretch_weft_pct=entry.stretch_weft_pct,
        opacity=entry.opacity, sheen=entry.sheen, metallic=entry.metallic,
        source=entry.fabric_source, biodegradable=entry.biodegradable,
    )


def _build_connector_ref(entry: LibraryEntry) -> ConnectorRef:
    # Map library_entry to the legacy ConnectorRef shape. Kind is
    # derived from the library entry's kind + tag set.
    if entry.kind == "strap_piece":
        if "halter" in entry.tags:
            kind = "halter_strap"
        elif "shoulder" in entry.tags:
            kind = "shoulder_strap"
        elif "tie" in entry.tags or "side_tie" in entry.tags:
            kind = "tie_string"
        elif "hip_side" in entry.tags:
            kind = "hip_strap"
        elif "underbust" in entry.tags or "FOE" in entry.tags:
            kind = "underbust_elastic"
        elif "back_band" in entry.tags:
            kind = "elastic_band"
        else:
            kind = "elastic_band"
    elif entry.kind == "hardware":
        if "o_ring" in entry.tags:
            kind = "o_ring"
        elif "d_ring" in entry.tags:
            kind = "d_ring"
        elif "slider" in entry.tags:
            kind = "slider"
        elif "buckle" in entry.tags:
            kind = "buckle"
        else:
            kind = entry.kind
    else:
        kind = entry.kind
    return ConnectorRef(
        id=entry.id, name=entry.name, kind=kind,
        diameter_cm=entry.diameter_cm, width_cm=entry.width_cm,
        length_cm=entry.length_cm, material="",
        metal_finish=entry.metal_finish,
        elastic=entry.elastic,
    )


def _build_accessory_ref(entry: LibraryEntry) -> AccessoryRef:
    # Derive accessory.kind from tags
    for tag in ("bow", "shell_charm", "pendant", "fringe",
                  "beads", "tassel", "ring_charm"):
        if tag in entry.tags:
            kind = tag
            break
    else:
        kind = "pendant"
    size = entry.local_params_schema.get("size_cm", (1.0, 5.0, 2.5))[2]
    return AccessoryRef(
        id=entry.id, name=entry.name, kind=kind,
        size_cm=float(size), material="", metal_finish=entry.metal_finish,
        count=1,
    )


def _make_pattern_piece_from_cup(cup_entry: LibraryEntry,
                                    local_params: dict,
                                    fabric_id: str) -> PatternPiece:
    """One PatternPiece with count=2 mirror_axis=u for the cup."""
    poly = polygon_recipes.call_recipe(
        cup_entry.base_polygon_recipe, local_params, side=1)
    edge_names = ["cup_outer", "armhole", "underbust", "cup_inner"][:len(poly) - 1]
    return PatternPiece(
        id="cup", role="cup", polygon_uv=list(poly),
        count=2, mirror_axis="u", fabric_id=fabric_id,
        layer_role="shell", edge_names=edge_names,
        notes=f"library: {cup_entry.id}",
    )


def _make_bottom_pieces(bottom_entry: LibraryEntry,
                          local_params: dict, fabric_id: str
                          ) -> list[PatternPiece]:
    """Build front bottom + back bottom strips from a bottom_piece entry."""
    pieces: list[PatternPiece] = []
    front_poly = polygon_recipes.call_recipe(
        bottom_entry.base_polygon_recipe, local_params)
    en_front = ["waistband", "leg_opening", "inseam",
                "leg_opening", "side_seam", "leg_opening"]
    pieces.append(PatternPiece(
        id="bottom_front", role="front_bottom",
        polygon_uv=list(front_poly), count=1,
        fabric_id=fabric_id, layer_role="shell",
        edge_names=en_front[: len(front_poly) - 1],
        notes=f"library: {bottom_entry.id}",
    ))
    back_strips = polygon_recipes.back_bottom_strips(local_params)
    for i, p in enumerate(back_strips):
        side = "R" if i == 0 else "L"
        en = ["waistband", "leg_opening", "inseam", "back_seam"]
        pieces.append(PatternPiece(
            id=f"bottom_back_{side}", role="back_bottom",
            polygon_uv=list(p), count=1, fabric_id=fabric_id,
            layer_role="shell", edge_names=en[: len(p) - 1],
            notes=f"library: {bottom_entry.id} (back strip)",
        ))
    return pieces


def outfit_to_garment(outfit: Outfit) -> Garment:
    """Concretize an Outfit into a Garment. Pattern-piece slots produce
    PatternPieces; connector slots produce ConnectorRefs; accessory
    slots produce AccessoryRefs; each connector/accessory gets default
    Attachments derived from its library entry's anatomy_hints."""
    if outfit.archetype not in ARCHETYPE_SLOTS:
        raise ValueError(f"unknown archetype '{outfit.archetype}'")

    primary_fabric_assn = outfit.first_assignment("primary_fabric")
    if primary_fabric_assn is None:
        raise ValueError("outfit missing required 'primary_fabric' slot")
    primary_fabric_entry = _entry(primary_fabric_assn.library_id)
    primary_fabric_id = primary_fabric_entry.id

    pieces: list[PatternPiece] = []
    fabrics: list[FabricRef] = [_build_fabric_ref(primary_fabric_entry)]
    connectors: list[ConnectorRef] = []
    accessories: list[AccessoryRef] = []
    seams: list[Seam] = []
    attachments: list[Attachment] = []
    fabric_seen = {primary_fabric_id}

    # ---- Cup ----
    cup_assn = outfit.first_assignment("cup")
    if cup_assn is None:
        raise ValueError("outfit missing required 'cup' slot")
    cup_entry = _entry(cup_assn.library_id)
    cup_params = cup_entry.clamp_local_params(cup_assn.local_params)
    pieces.append(_make_pattern_piece_from_cup(
        cup_entry, cup_params, primary_fabric_id))
    # foam padding for molded cups
    if cup_entry.foam_thickness_mm > 0.01:
        foam_poly = polygon_recipes.call_recipe(
            cup_entry.base_polygon_recipe, cup_params, side=1)
        foam_id = "F_FOAM_CUP_3MM"
        if foam_id not in fabric_seen:
            fabrics.append(_build_fabric_ref(LIBRARY[foam_id]))
            fabric_seen.add(foam_id)
        pieces.append(PatternPiece(
            id="cup_foam", role="cup", polygon_uv=list(foam_poly),
            count=2, mirror_axis="u", fabric_id=foam_id,
            layer_role="padding", parent_id="cup",
            edge_names=["cup_outer"] * (len(foam_poly) - 1),
        ))
    # FOE binding seam on the cup armhole (auto-derived)
    seams.append(Seam(
        id="seam_cup_armhole",
        edge_a=EdgeRef(piece_id="cup", edge_index=1,
                         edge_name="armhole", side="R"),
        edge_b=None, seam_type_id="S_FOE_BIND_15MM",
        elastic_id="STR_FOE_15MM", finish="FOE", visible=True,
    ))

    # ---- Optional center gore (auto-emit when cups don't touch) ----
    if cup_params.get("inner_u", 0) > 0.01:
        gore = polygon_recipes.center_gore({
            "center_v": cup_params.get("center_v", 0.74),
            "half_v": cup_params.get("half_v", 0.07),
            "inner_u": cup_params.get("inner_u", 0.10),
            "underband_dip": cup_params.get("underband_dip", 0.05),
            "apex_lift": cup_params.get("apex_lift", 0.15),
        })
        if gore is not None:
            pieces.append(PatternPiece(
                id="center_gore", role="center_gore",
                polygon_uv=list(gore), count=1, fabric_id=primary_fabric_id,
                layer_role="shell", edge_names=["center_front"] * 4,
            ))

    # ---- Bottom front (use either bottom_front or bottom_back slot) ----
    bot_front_assn = (outfit.first_assignment("bottom_front")
                      or outfit.first_assignment("bottom_back"))
    if bot_front_assn is not None:
        bot_entry = _entry(bot_front_assn.library_id)
        bot_params = bot_entry.clamp_local_params(bot_front_assn.local_params)
        pieces.extend(_make_bottom_pieces(
            bot_entry, bot_params, primary_fabric_id))
        # Inseam join
        if any(p.id == "bottom_front" for p in pieces) and \
           any(p.id.startswith("bottom_back_") for p in pieces):
            seams.append(Seam(
                id="seam_inseam_R",
                edge_a=EdgeRef("bottom_front", 2, "inseam", "R"),
                edge_b=EdgeRef("bottom_back_R", 2, "inseam", "R"),
                seam_type_id="S_OVERLOCK_4THREAD", finish="topstitch",
            ))

    # ---- Back top band (bandeau / bralette / one-piece — strap_piece slot) ----
    band_assn = (outfit.first_assignment("back_band")
                  or outfit.first_assignment("underbust"))
    if band_assn is not None and outfit.archetype != "triangle_string_halter":
        band_entry = _entry(band_assn.library_id)
        # Top back band polygons (fabric-continuous)
        if "back_band" in band_entry.tags:
            band_polys = polygon_recipes.back_top_band({
                "center_v": cup_params.get("center_v", 0.74),
                "coverage": 0.55,
            })
            for i, p in enumerate(band_polys):
                side = "R" if i == 0 else "L"
                pieces.append(PatternPiece(
                    id=f"back_band_{side}", role="back_band_panel",
                    polygon_uv=list(p), count=1, fabric_id=primary_fabric_id,
                    layer_role="shell",
                    edge_names=["waistband"] * (len(p) - 1),
                ))

    # ---- Side ties (only for triangle archetype with side_tie slot) ----
    side_tie_assn = outfit.first_assignment("side_tie")
    if side_tie_assn is not None and bot_front_assn is not None:
        st_polys = polygon_recipes.side_tie({
            "front_top_v": bot_params.get("front_top_v", 0.25),
            "back_top_v": bot_params.get("back_top_v", 0.25),
        })
        for i, p in enumerate(st_polys):
            side = "R" if i == 0 else "L"
            pieces.append(PatternPiece(
                id=f"side_tie_panel_{side}", role="side_tie_panel",
                polygon_uv=list(p), count=1, fabric_id=primary_fabric_id,
                layer_role="shell",
                edge_names=["side_seam"] * (len(p) - 1),
                notes=f"side={side}",
            ))

    # ---- Connectors: walk every strap_piece + hardware slot ----
    for assn in outfit.slot_assignments:
        entry = _entry(assn.library_id)
        if entry.kind not in ("strap_piece", "hardware"):
            continue
        # Skip any strap_piece already converted to PatternPiece (back_band)
        # — actually we keep both: it's a panel AND a connector. But to
        # avoid double-counting in attachments, only emit connector for
        # non-fabric-panel slots:
        if assn.slot_name in ("back_band",):
            continue
        cref = _build_connector_ref(entry)
        connectors.append(cref)
        # Emit one Attachment per anatomy_hint in the library entry.
        for anchor in entry.anatomy_hints:
            attachments.append(Attachment(
                id=f"att_{assn.slot_name}_{anchor}",
                component_kind="connector",
                component_id=entry.id,
                target_kind="anatomy_anchor",
                anatomy_anchor=anchor,
            ))

    # ---- Accessories ----
    for assn in outfit.slot_assignments:
        entry = _entry(assn.library_id)
        if entry.kind != "accessory":
            continue
        aref = _build_accessory_ref(entry)
        accessories.append(aref)
        for anchor in entry.anatomy_hints:
            attachments.append(Attachment(
                id=f"att_acc_{entry.id}_{anchor}",
                component_kind="accessory",
                component_id=entry.id,
                target_kind="anatomy_anchor",
                anatomy_anchor=anchor,
            ))

    # ---- Body jewelry (NEW v2) ----
    for assn in outfit.slot_assignments:
        entry = _entry(assn.library_id)
        if entry.kind != "body_jewelry":
            continue
        # Reuse AccessoryRef shape but mark kind explicitly
        aref = AccessoryRef(
            id=entry.id, name=entry.name, kind=entry.jewelry_form,
            size_cm=float(entry.local_params_schema.get(
                "diameter_cm", entry.local_params_schema.get(
                    "length_cm", entry.local_params_schema.get(
                        "size_cm", (1.0, 5.0, 2.5))))[2]),
            material="", metal_finish=entry.metal_finish,
        )
        accessories.append(aref)
        for anchor in entry.anatomy_hints:
            attachments.append(Attachment(
                id=f"att_jewelry_{entry.id}_{anchor}",
                component_kind="accessory",
                component_id=entry.id,
                target_kind="anatomy_anchor",
                anatomy_anchor=anchor,
            ))

    return Garment(
        archetype=outfit.archetype,
        pieces=pieces, fabrics=fabrics,
        connectors=connectors, accessories=accessories,
        seams=seams, attachments=attachments,
        metadata={
            "generator_version": GENERATOR_VERSION + " + outfit_to_garment v1",
            "primary_fabric_id": primary_fabric_id,
            "outfit_summary": _outfit_summary(outfit),
            "validation_warnings": [],
        },
    )


def _outfit_summary(outfit: Outfit) -> dict:
    return {
        "archetype": outfit.archetype,
        "slots": [
            {"name": a.slot_name, "library_id": a.library_id}
            for a in outfit.slot_assignments
        ],
        "global_design": dict(outfit.global_design),
    }


# ---------------------------------------------------------------------------
# Bidirectional projection — Outfit ↔ Genome (for v1 backward compat)
# ---------------------------------------------------------------------------

# v2 archetype → closest v1 STYLE_ARCHETYPES enum. v1 only had "free" plus
# culture/brand styles, so v2 archetype maps to a representative v1 style
# rather than a structural one. Triangle ↔ brazilian (both string-tied),
# bandeau ↔ hunzag_crinkle (both unstrap top), bralette ↔ sporty_chromat
# (both shoulder-strapped), one_piece ↔ eres_architect (molded silhouette).
_V2_TO_V1_STYLE = {
    "triangle_string_halter":  "brazilian",
    "bandeau_back_band":       "hunzag_crinkle",
    "bralette_shoulder_strap": "sporty_chromat",
    "one_piece_maillot":       "eres_architect",
}


def _v1_style_for(outfit: Outfit) -> str:
    return _V2_TO_V1_STYLE.get(outfit.archetype, "free")


def outfit_to_genome(outfit: Outfit):
    """Lossy projection: extract enough Genome fields for legacy
    fitness.py to score the outfit. Continuous fields come from cup/
    bottom local_params + global_design; discrete fields snap to closest
    legacy enum values."""
    from verify_ga_uv import Genome, _enforce_constraints

    cup_assn = outfit.first_assignment("cup")
    bot_assn = outfit.first_assignment("bottom_front") or \
                outfit.first_assignment("bottom_back")
    fab_assn = outfit.first_assignment("primary_fabric")

    cup_p = cup_assn.local_params if cup_assn else {}
    bot_p = bot_assn.local_params if bot_assn else {}
    fab_entry = LIBRARY.get(fab_assn.library_id) if fab_assn else None
    cup_entry = LIBRARY.get(cup_assn.library_id) if cup_assn else None

    has_neck = (outfit.first_assignment("halter_strap") is not None)
    has_shoulder = (outfit.first_assignment("shoulder_strap") is not None)
    has_oring = (outfit.first_assignment("oring") is not None)
    has_bow = any(LIBRARY.get(a.library_id, None) and
                    "bow" in LIBRARY[a.library_id].tags
                    for a in outfit.slot_assignments)
    has_fringe = any(LIBRARY.get(a.library_id, None) and
                       "fringe" in LIBRARY[a.library_id].tags
                       for a in outfit.slot_assignments)
    has_beads = any(LIBRARY.get(a.library_id, None) and
                      "beads" in LIBRARY[a.library_id].tags
                      for a in outfit.slot_assignments)
    has_shell = any(LIBRARY.get(a.library_id, None) and
                      "shell_charm" in LIBRARY[a.library_id].tags
                      for a in outfit.slot_assignments)

    g = Genome(
        pattern=outfit.global_design.get("pattern_overlay", "solid"),
        top_center_v=cup_p.get("center_v", 0.74),
        top_half_v=cup_p.get("half_v", 0.07),
        top_half_u=cup_p.get("half_u", 0.16),
        top_inner_u=cup_p.get("inner_u", 0.10),
        top_apex_lift=cup_p.get("apex_lift", 0.15),
        top_underband_dip=cup_p.get("underband_dip", 0.05),
        top_back_coverage=(0.55 if outfit.archetype in
                                ("bandeau_back_band", "bralette_shoulder_strap",
                                  "one_piece_maillot")
                            else 0.05),
        top_neck_strap=(0.85 if has_neck else 0.0),
        top_shoulder_strap=(0.85 if has_shoulder else 0.0),
        bot_front_top_v=bot_p.get("front_top_v", 0.25),
        bot_front_half_u=bot_p.get("front_half_u", 0.18),
        bot_front_leg_curve=bot_p.get("front_leg_curve", 0.65),
        bot_back_top_v=bot_p.get("back_top_v", 0.25),
        bot_back_half_u=bot_p.get("back_half_u", 0.10),
        bot_tie_dangle=0.40 if outfit.first_assignment("side_tie") else 0.0,
        hue=outfit.global_design.get("hue", 0.5),
        saturation=outfit.global_design.get("saturation", 0.6),
        lightness=outfit.global_design.get("lightness", 0.5),
        secondary_hue=outfit.global_design.get("secondary_hue", 0.5),
        secondary_saturation=outfit.global_design.get("secondary_saturation", 0.4),
        secondary_lightness=outfit.global_design.get("secondary_lightness", 0.4),
        pattern_scale=outfit.global_design.get("pattern_scale", 0.5),
        pattern_angle=outfit.global_design.get("pattern_angle", 0.0),
        trim_color_mode=0.3,
        fabric_sheen=(fab_entry.sheen if fab_entry else 0.4),
        fabric_metallic=(fab_entry.metallic if fab_entry else 0.0),
        fabric_opacity=(fab_entry.opacity if fab_entry else 1.0),
        fabric_weight=min(1.0, max(0.0,
                            (fab_entry.weight_gsm - 150) / 250.0
                            if fab_entry else 0.5)),
        fabric_weave=(fab_entry.weave if fab_entry else "plain"),
        palette_preset=outfit.global_design.get("palette_preset", "free"),
        fabric_source=(fab_entry.fabric_source if fab_entry else "econyl"),
        biodegradable=1.0 if (fab_entry and fab_entry.biodegradable) else 0.0,
        single_material=1.0,
        has_oring=1.0 if has_oring else 0.0,
        oring_size=0.5,
        has_bow=1.0 if has_bow else 0.0,
        bow_size=0.4,
        has_fringe=1.0 if has_fringe else 0.0,
        fringe_length=0.4,
        has_beads=1.0 if has_beads else 0.0,
        has_shell=1.0 if has_shell else 0.0,
        style_archetype=_v1_style_for(outfit),
        hardware_metal="gold",
        asym_amount=float(outfit.global_design.get("asym_amount", 0.0)),
        geom_ratio_pull=float(outfit.global_design.get("geom_ratio_pull", 0.0)),
    ).clipped()
    return _enforce_constraints(g)


def genome_to_outfit(genome,
                       bottom_coverage_strict: Optional[float] = None,
                       cup_coverage_strict: Optional[float] = None) -> Outfit:
    """Snap a legacy Genome to the closest library entries per slot.
    Used for v1 → v2 seed migration. Picks archetype via the same
    dispatch rule as garment_state._detect_archetype.

    bottom_coverage_strict / cup_coverage_strict (None = use the
    corresponding library.* module global) force full-coverage choices
    regardless of what the source genome's coverage looked like."""
    import library
    strict = library.BOTTOM_COVERAGE_STRICT if bottom_coverage_strict is None \
        else float(bottom_coverage_strict)
    cup_strict = library.CUP_COVERAGE_STRICT if cup_coverage_strict is None \
        else float(cup_coverage_strict)
    cup_bottom = genome.top_center_v - genome.top_half_v
    if genome.top_back_coverage > 0.7 and genome.bot_front_top_v > cup_bottom - 0.15:
        archetype = "one_piece_maillot"
    elif genome.top_shoulder_strap > 0.5:
        archetype = "bralette_shoulder_strap"
    elif genome.top_neck_strap > 0.4 and genome.top_inner_u > 0.05:
        archetype = "triangle_string_halter"
    else:
        archetype = "bandeau_back_band"

    assignments: list[SlotAssignment] = []
    slots = ARCHETYPE_SLOTS[archetype]

    # Cup: pick by half_u → size_class proxy, geometry by archetype
    cup_geo = {
        "triangle_string_halter": "triangle",
        "bralette_shoulder_strap": "balconette",
        "bandeau_back_band": "bandeau",
        "one_piece_maillot": "balconette",
    }[archetype]
    if genome.top_half_u < 0.13:
        sz = "S"
    elif genome.top_half_u > 0.18:
        sz = "L"
    else:
        sz = "M"
    cup_id_map = {
        ("triangle", "S"): "CUP_TRIANGLE_S",
        ("triangle", "M"): "CUP_TRIANGLE_M",
        ("triangle", "L"): "CUP_TRIANGLE_L",
        ("balconette", "S"): "CUP_BALCONETTE_S",
        ("balconette", "M"): "CUP_BALCONETTE_M",
        ("balconette", "L"): "CUP_BALCONETTE_L",
        ("bandeau", "S"): "CUP_BANDEAU_S",
        ("bandeau", "M"): "CUP_BANDEAU_M",
        ("bandeau", "L"): "CUP_BANDEAU_L",
    }
    # Cup modesty override: if cup_strict pushes toward higher coverage,
    # pick a sturdier geometry the archetype's slot tags still allow.
    cup_slot_spec = next(s for s in slots if s.name == "cup")
    cup_allowed = cup_slot_spec.allowed_tags or ()
    if cup_strict >= 0.66 and (not cup_allowed or "molded_foam" in cup_allowed):
        cup_id = f"CUP_FOAM_MOLDED_{sz}"
    elif cup_strict >= 0.33 and (not cup_allowed or "balconette" in cup_allowed):
        cup_id = f"CUP_BALCONETTE_{sz}"
    elif cup_strict >= 0.33 and (not cup_allowed or "bandeau" in cup_allowed):
        cup_id = f"CUP_BANDEAU_{sz}"
    else:
        cup_id = cup_id_map.get((cup_geo, sz), "CUP_TRIANGLE_M")
    cup_lp = {
        "half_u": genome.top_half_u,
        "half_v": genome.top_half_v,
        "inner_u": genome.top_inner_u,
        "apex_lift": genome.top_apex_lift,
        "underband_dip": genome.top_underband_dip,
        "center_v": genome.top_center_v,
    }
    if cup_strict >= 0.66 and cup_id in LIBRARY:
        cup_lp = _pin_to_max_cup_coverage(LIBRARY[cup_id], cup_lp)
    assignments.append(SlotAssignment(
        slot_name="cup", library_id=cup_id, local_params=cup_lp))

    # Bottom: pick by coverage — but obey archetype's allowed_tags so a
    # triangle_string_halter never gets a high_waisted bottom.
    bottom_slot_spec = next(s for s in slots if s.name == "bottom_front")
    allowed = bottom_slot_spec.allowed_tags or ()
    if strict >= 0.66 and (not allowed or "high_waisted" in allowed):
        bot_id = "BOT_HIGHWAIST_M"
    elif strict >= 0.66 and (not allowed or "brief" in allowed):
        bot_id = "BOT_BRIEF_M"
    elif strict >= 0.33 and (not allowed or "cheeky" in allowed):
        bot_id = "BOT_CHEEKY_M"
    elif genome.bot_back_half_u < 0.08 and (not allowed or "thong" in allowed):
        bot_id = "BOT_THONG_M"
    elif genome.bot_back_half_u < 0.12 and (not allowed or "brazilian" in allowed):
        bot_id = "BOT_BRAZILIAN_M"
    elif genome.bot_back_half_u < 0.16 and (not allowed or "cheeky" in allowed):
        bot_id = "BOT_CHEEKY_M"
    elif genome.bot_front_top_v < 0.40 and (not allowed or "brief" in allowed):
        bot_id = "BOT_BRIEF_M"
    elif not allowed or "high_waisted" in allowed:
        bot_id = "BOT_HIGHWAIST_M"
    else:
        candidates = entries_matching_slot(bottom_slot_spec)
        bot_id = candidates[0].id if candidates else "BOT_BRAZILIAN_M"
    bot_lp = {
        "front_top_v": genome.bot_front_top_v,
        "front_half_u": genome.bot_front_half_u,
        "front_leg_curve": genome.bot_front_leg_curve,
        "back_top_v": genome.bot_back_top_v,
        "back_half_u": genome.bot_back_half_u,
    }
    if strict >= 0.66:
        bot_lp = _pin_to_max_coverage(LIBRARY[bot_id], bot_lp)
    assignments.append(SlotAssignment(
        slot_name="bottom_front", library_id=bot_id, local_params=bot_lp))

    # Halter / shoulder strap
    if archetype == "triangle_string_halter":
        halter_id = "STR_HALTER_5MM" if genome.top_neck_strap > 0.6 else "STR_HALTER_3MM"
        assignments.append(SlotAssignment(
            slot_name="halter_strap", library_id=halter_id,
            local_params={"length_cm": 55.0}))
        # Side tie
        tie_id = ("STR_TIE_RIBBON_15MM" if genome.bot_tie_dangle > 0.6
                  else "STR_TIE_CORD_5MM" if genome.bot_tie_dangle > 0.3
                  else "STR_TIE_CORD_3MM")
        assignments.append(SlotAssignment(
            slot_name="side_tie", library_id=tie_id,
            local_params={"length_cm": 22.0}))
    elif archetype == "bralette_shoulder_strap":
        sw = 1.0 + 1.0 * float(genome.top_shoulder_strap)
        if sw < 1.2:
            sid = "STR_SHOULDER_WOVEN_10MM"
        elif sw < 1.7:
            sid = "STR_SHOULDER_WOVEN_15MM"
        else:
            sid = "STR_SHOULDER_PADDED_20MM"
        assignments.append(SlotAssignment(
            slot_name="shoulder_strap", library_id=sid,
            local_params={"length_cm": 30.0}))
    elif archetype == "bandeau_back_band":
        bb_id = "STR_BACKBAND_RIBBED" if genome.fabric_weave == "ribbed" else "STR_BACKBAND_PLAIN"
        assignments.append(SlotAssignment(
            slot_name="back_band", library_id=bb_id,
            local_params={}))
    elif archetype == "one_piece_maillot":
        # one_piece's anchor straps are all optional in the schema, but
        # the cup needs *some* anchor (O7 wearability rule). If the
        # genome's shoulder_strap signal is high enough, use shoulder;
        # otherwise add an underbust elastic so the cup stays on.
        if genome.top_shoulder_strap > 0.15:
            assignments.append(SlotAssignment(
                slot_name="shoulder_strap",
                library_id="STR_SHOULDER_PADDED_20MM",
                local_params={"length_cm": 32.0}))
        else:
            assignments.append(SlotAssignment(
                slot_name="underbust",
                library_id="STR_FOE_15MM",
                local_params={}))

    # Optional O-ring
    if genome.has_oring > 0.5:
        size = 0.8 + 1.6 * genome.oring_size
        if size < 1.0:
            ring = "HW_OR_8MM_GOLD"
        elif size < 1.5:
            ring = "HW_OR_12MM_GOLD"
        else:
            ring = "HW_OR_18MM_SILVER"
        assignments.append(SlotAssignment(
            slot_name="oring", library_id=ring, local_params={}))

    # Primary fabric — snap by (weave, source, weight), filtered to
    # entries the slot's SlotSpec.matches accepts (e.g. excluded_tags
    # keeps foam / powermesh / lining out of primary_fabric).
    primary_spec = next(s for s in slots if s.name == "primary_fabric")
    target_gsm = int(150 + 100 * genome.fabric_weight)
    legal = [(k, v) for k, v in FABRICS.items() if primary_spec.matches(v)]
    fab_candidates = [(k, v) for k, v in legal
                      if v.weave == genome.fabric_weave] or legal
    same_src = [(k, v) for k, v in fab_candidates
                if v.fabric_source == genome.fabric_source]
    if same_src:
        fab_candidates = same_src
    fab_id = min(fab_candidates,
                 key=lambda kv: abs(kv[1].weight_gsm - target_gsm))[0]
    assignments.append(SlotAssignment(
        slot_name="primary_fabric", library_id=fab_id, local_params={}))

    # seam_type — pick a structural option compatible with the fabric
    seam_id = "S_OVERLOCK_4THREAD"
    assignments.append(SlotAssignment(
        slot_name="seam_type", library_id=seam_id, local_params={}))

    # Optional accessories from has_* — cap to slot max_count (=2 for v1)
    optional_accessories: list[tuple[str, dict]] = []
    if genome.has_bow > 0.5:
        optional_accessories.append(("ACC_BOW_CHIFFON_30MM",
                                       {"size_cm": 1.0 + 4.0 * genome.bow_size}))
    if genome.has_shell > 0.5:
        optional_accessories.append(("ACC_SHELL_TROCHUS_25MM",
                                       {"size_cm": 2.5}))
    if genome.has_beads > 0.5:
        optional_accessories.append(("ACC_BEADS_OVAL_8MM", {"count": 12}))
    if genome.has_fringe > 0.5:
        optional_accessories.append(("ACC_FRINGE_BEADED_80MM",
                                       {"length_cm": 1.0 + 9.0 * genome.fringe_length}))
    # Cap at SlotSpec.max_count (= 2 in current v1)
    accessory_max = 2
    for spec in slots:
        if spec.name == "accessory":
            accessory_max = spec.max_count
            break
    for acc_id, lp in optional_accessories[:accessory_max]:
        assignments.append(SlotAssignment(
            slot_name="accessory", library_id=acc_id,
            local_params=lp))

    global_design = {
        "hue": genome.hue, "saturation": genome.saturation,
        "lightness": genome.lightness,
        "secondary_hue": genome.secondary_hue,
        "secondary_saturation": genome.secondary_saturation,
        "secondary_lightness": genome.secondary_lightness,
        "pattern_overlay": genome.pattern,
        "pattern_scale": genome.pattern_scale,
        "pattern_angle": genome.pattern_angle,
        "palette_preset": genome.palette_preset,
    }
    # Snap raw genome floats to each entry's local_params schema bounds.
    # Without this a v1 seed with bot_front_half_u=0.05 would silently
    # propagate to a BOT_THONG_M whose schema floor is 0.12.
    for sa in assignments:
        entry = LIBRARY.get(sa.library_id)
        if entry and entry.local_params_schema:
            sa.local_params = entry.clamp_local_params(sa.local_params)
    return Outfit(archetype=archetype,
                    slot_assignments=assignments,
                    global_design=global_design)
