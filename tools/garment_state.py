"""
Manufacturing Latent State for swimwear.

Sits between Genome (44 abstract design dims) and the renderer:

    Genome -> [genome_to_garment] -> Garment -> [validate_garment] ->
              -> renderer consumes Garment.connectors / .accessories / .pieces
              -> .glb output (extras carries Garment SKU JSON for inspection)

Why this layer exists: realism comes from the implicit constraint
"could this actually be cut, sewn, and held on the body?". Encoding
that constraint as latent state gives the renderer a single source of
truth for seam placement, hardware location, accessory anchors, and
fabric properties — instead of scattering Genome.has_oring / has_bow
checks across build_strap_meshes.

v1 scope: bikini-style two-piece swimwear only. Three archetypes:
    triangle_string_halter  — Brazilian / halter triangle string
    bandeau_back_band       — strapless bandeau with back band
    bralette_shoulder_strap — sporty bralette with shoulder straps

One-piece / monokini (top_back_coverage > 0.7 AND
bot_front_top_v overlapping the cup band) raises
UnsupportedArchetypeV1 — deferred to v2.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from catalogs import (
    FABRICS, CONNECTORS, ACCESSORIES, SEAM_TYPES,
    snap_oring, snap_strap, snap_elastic, snap_fabric,
    snap_seam_for_fabric, snap_accessory,
)


GENERATOR_VERSION = "garment_state v1.0"


class UnsupportedArchetypeV1(Exception):
    """Raised when a Genome describes a garment shape outside v1 scope."""


# ---------------------------------------------------------------------------
# Edge / Piece / Component dataclasses
# ---------------------------------------------------------------------------

# Closed-set semantic edge labels for catalog matching and validators.
# Each PatternPiece declares one edge_name per polygon edge in traversal
# order, matched by edge_index.
EDGE_NAMES = (
    "neckline", "armhole", "underbust",
    "side_seam", "leg_opening", "waistband",
    "inseam", "center_front", "back_seam",
    "cup_inner", "cup_outer",
)

LAYER_ROLES = ("shell", "lining", "padding", "trim")

PATH_POLICIES = (
    "halter_behind_neck",
    "shoulder_acromion_scapula",
    "side_tie_hip_vertical",
    "back_band_horizontal",
    "underbust_horizontal",
    "waist_band_horizontal",
    "center_gore_static",
    "free_anchored",
)

ATTACHMENT_TARGETS = ("seam_at_param", "anatomy_anchor", "piece_centroid")

ANATOMY_ANCHORS = (
    "front_clavicle_R", "front_clavicle_L",
    "back_scapula_R",  "back_scapula_L",
    "neck_base_front", "neck_base_back",
    "sternum",         "navel",
    "hip_R",           "hip_L",
    "crotch_front",    "crotch_back",
)


@dataclass(frozen=True)
class EdgeRef:
    """Reference to one edge of one PatternPiece. Edge index follows the
    polygon traversal order (polygon_uv[i] -> polygon_uv[i+1]).

    Convention for cup polygons (from genome_polygons in verify_ga_uv.py):
      0: inner_top -> outer_top  (cup_inner / armhole-ish)
      1: outer_top -> outer_bot
      2: outer_bot -> inner_bot
      3: inner_bot -> inner_top
    """
    piece_id: str
    edge_index: int
    edge_name: str   # one of EDGE_NAMES
    side: str = "C"  # "L" / "R" / "C"


@dataclass
class PatternPiece:
    """A 2D pattern piece in body-cylinder UV space [-1,1] x [0,1].

    For v1 we keep the polygon in UV space (matches existing
    genome_polygons output). True 2D flat-pattern unwrap is v2 work.
    """
    id: str
    role: str   # cup / back_band_panel / front_bottom / back_bottom /
                # side_tie_panel / center_gore / underband / gusset /
                # halter_strap_panel / shoulder_strap_panel
    polygon_uv: list[tuple[float, float]]
    count: int = 1
    mirror_axis: Optional[str] = "none"   # "u" or "none"
    fabric_id: str = ""
    layer_role: str = "shell"             # one of LAYER_ROLES
    parent_id: Optional[str] = None       # for layered (lining/padding)
    grain_dir_deg: float = 0.0            # 0 = stretchy axis along u
    seam_allowance_cm: float = 0.64       # 1/4" industry standard
    edge_names: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class FabricRef:
    """Resolved fabric spec — value-copied from FABRICS[id] for self-contained Garment."""
    id: str
    name: str
    weave: str
    composition: str
    weight_gsm: int
    stretch_warp_pct: int
    stretch_weft_pct: int
    opacity: float
    sheen: float
    metallic: float
    source: str
    biodegradable: bool


@dataclass
class ConnectorRef:
    id: str
    name: str
    kind: str
    diameter_cm: float = 0.0
    width_cm: float = 0.0
    length_cm: float = 0.0
    material: str = ""
    metal_finish: str = "none"
    path_policy: str = "free_anchored"
    elastic: bool = False
    breaking_strength_n: int = 0


@dataclass
class AccessoryRef:
    id: str
    name: str
    kind: str
    size_cm: float
    material: str = ""
    metal_finish: str = "none"
    count: int = 1


@dataclass
class Seam:
    """Joins two PatternPiece edges (or, when edge_b is None, finishes
    a free edge with an elastic / FOE binding).
    """
    id: str
    edge_a: EdgeRef
    edge_b: Optional[EdgeRef] = None
    seam_type_id: str = ""           # SKU into SEAM_TYPES
    elastic_id: Optional[str] = None # SKU into CONNECTORS (if FOE etc.)
    finish: str = "FOE"              # raw / FOE / binding / topstitch / bartack
    visible: bool = True


@dataclass
class Attachment:
    """Pins a Connector or Accessory to a seam parameter point or to a
    named anatomy anchor.
    """
    id: str
    component_kind: str              # "connector" / "accessory"
    component_id: str
    target_kind: str                 # one of ATTACHMENT_TARGETS
    seam_id: Optional[str] = None
    seam_param_t: Optional[float] = None
    piece_id: Optional[str] = None
    anatomy_anchor: Optional[str] = None
    offset_cm: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class Garment:
    archetype: str                   # one of {"triangle_string_halter",
                                      #         "bandeau_back_band",
                                      #         "bralette_shoulder_strap"}
    pieces: list[PatternPiece] = field(default_factory=list)
    fabrics: list[FabricRef] = field(default_factory=list)
    connectors: list[ConnectorRef] = field(default_factory=list)
    accessories: list[AccessoryRef] = field(default_factory=list)
    seams: list[Seam] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # ---- Back-compat helpers --------------------------------------------------

    def flatten_polygons(self) -> list[list[tuple[float, float]]]:
        """Return polys in the format build_fabric_shell / polish_shell want.
        Includes mirrored shell pieces explicitly. Skips lining/padding/trim.
        """
        out: list[list[tuple[float, float]]] = []
        for p in self.pieces:
            if p.layer_role != "shell":
                continue
            out.append(list(p.polygon_uv))
            if p.count == 2 and p.mirror_axis == "u":
                out.append([(-u, v) for (u, v) in p.polygon_uv])
        return out

    def sku_summary(self) -> dict:
        """Compact SKU-only summary for embedding in glTF extras (avoids
        the 64 KB practical limit some importers have)."""
        return {
            "archetype": self.archetype,
            "pieces": [
                {"id": p.id, "role": p.role, "fabric_id": p.fabric_id,
                 "count": p.count, "layer_role": p.layer_role,
                 "parent_id": p.parent_id}
                for p in self.pieces
            ],
            "fabrics":     [f.id for f in self.fabrics],
            "connectors":  [c.id for c in self.connectors],
            "accessories": [a.id for a in self.accessories],
            "seams": [
                {"id": s.id, "type": s.seam_type_id, "elastic": s.elastic_id,
                 "finish": s.finish}
                for s in self.seams
            ],
            "attachments": [
                {"id": a.id, "component": a.component_id,
                 "target": a.target_kind, "anchor": a.anatomy_anchor,
                 "seam": a.seam_id}
                for a in self.attachments
            ],
            "warnings": list(self.metadata.get("validation_warnings", [])),
            "generator_version": self.metadata.get("generator_version",
                                                     GENERATOR_VERSION),
        }


# ---------------------------------------------------------------------------
# Catalog -> Ref helpers (lookup + value-copy)
# ---------------------------------------------------------------------------

def _fabric_ref(fid: str) -> FabricRef:
    f = FABRICS[fid]
    return FabricRef(
        id=f.id, name=f.name, weave=f.weave, composition=f.composition,
        weight_gsm=f.weight_gsm, stretch_warp_pct=f.stretch_warp_pct,
        stretch_weft_pct=f.stretch_weft_pct, opacity=f.opacity,
        sheen=f.sheen, metallic=f.metallic, source=f.source,
        biodegradable=f.biodegradable,
    )


def _connector_ref(cid: str) -> ConnectorRef:
    c = CONNECTORS[cid]
    return ConnectorRef(
        id=c.id, name=c.name, kind=c.kind, diameter_cm=c.diameter_cm,
        width_cm=c.width_cm, length_cm=c.length_cm, material=c.material,
        metal_finish=c.metal_finish, path_policy=c.path_policy,
        elastic=c.elastic, breaking_strength_n=c.breaking_strength_n,
    )


def _accessory_ref(aid: str, count: int = 1) -> AccessoryRef:
    a = ACCESSORIES[aid]
    return AccessoryRef(
        id=a.id, name=a.name, kind=a.kind, size_cm=a.size_cm,
        material=a.material, metal_finish=a.metal_finish, count=count,
    )


def _dedup_fabrics(refs: list[FabricRef]) -> list[FabricRef]:
    seen, out = set(), []
    for r in refs:
        if r.id in seen:
            continue
        seen.add(r.id)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Step 3 — genome_to_garment
# ---------------------------------------------------------------------------

# Polygon-builder helpers from verify_ga_uv. The leading underscore is
# convention only; importing is fine. Promoting them to public was
# considered but would touch verify_ga_uv.py; this is equivalent and
# narrower.
from verify_ga_uv import (
    _cup_polygon, _back_top_polygons, _bottom_front_polygon,
    _bottom_back_polygons, _side_tie_polygons, _center_gore_polygon,
)


def _detect_archetype(g) -> str:
    """v1 dispatch including the v2-promoted one_piece_maillot.

    Priority:
      1. one_piece_maillot — full-coverage continuous garment
      2. bralette_shoulder_strap — sporty bralette with shoulder straps
      3. triangle_string_halter — Brazilian halter triangle
      4. bandeau_back_band — strapless bandeau (catch-all)
    """
    cup_bottom = g.top_center_v - g.top_half_v
    if g.top_back_coverage > 0.7 and g.bot_front_top_v > cup_bottom - 0.15:
        return "one_piece_maillot"
    if g.top_shoulder_strap > 0.5:
        return "bralette_shoulder_strap"
    if g.top_neck_strap > 0.4 and g.top_inner_u > 0.05:
        return "triangle_string_halter"
    return "bandeau_back_band"


def _shell_fabric_for_genome(g) -> str:
    """Pick primary shell fabric SKU from Genome.fabric_weave + fabric_source.
    fabric_weight gene drives target gsm (lighter genes -> ~190, heavier -> ~230)."""
    target_gsm = int(190 + 50 * float(g.fabric_weight))
    return snap_fabric(g.fabric_weave, g.fabric_source,
                        weight_gsm_target=target_gsm)


def _bow_size_to_cm(g) -> float:
    return 1.0 + 4.0 * float(g.bow_size)   # 1..5 cm


def _fringe_length_to_cm(g) -> float:
    return 1.0 + 9.0 * float(g.fringe_length)   # 1..10 cm


def _make_cup_pieces(g, primary_fid: str
                     ) -> tuple[list[PatternPiece], list[Seam]]:
    """One PatternPiece with count=2 mirror_axis=u for the cup, plus
    optional foam-cup padding piece if structural archetype calls for it.
    Returns (pieces, seams_internal).
    """
    poly = _cup_polygon(g, +1)   # right cup; mirror via count=2
    # Cup edge naming following _cup_polygon traversal:
    #   0: inner_top -> outer_top  (cup_outer)
    #   1: outer_top -> outer_bot  (armhole)
    #   2: outer_bot -> inner_bot  (underbust)
    #   3: inner_bot -> inner_top  (cup_inner)
    # _cup_polygon also has a top_apex_lift midpoint creating a 5-vertex
    # polygon on the top edge, so edges 0 and 1 might both be cup_outer.
    edge_names: list[str] = []
    for i in range(len(poly) - 1):
        if i == 0:
            edge_names.append("cup_outer")
        elif i == 1:
            edge_names.append("armhole")
        elif i == 2:
            edge_names.append("underbust")
        elif i == 3:
            edge_names.append("cup_inner")
        else:
            edge_names.append("cup_outer")

    cup = PatternPiece(
        id="cup", role="cup", polygon_uv=list(poly),
        count=2, mirror_axis="u", fabric_id=primary_fid,
        layer_role="shell", grain_dir_deg=0.0,
        edge_names=edge_names,
    )
    pieces = [cup]
    seams: list[Seam] = []

    # Foam-cup padding stack on the same UV region. Triggered when
    # archetype implies structured cups (bralette / bandeau lean
    # structured; halter triangles are typically unstructured).
    # Genome doesn't have an explicit "padded" field; we use
    # fabric_weight > 0.6 as proxy for structured cup desire.
    if float(g.fabric_weight) > 0.6:
        pieces.append(PatternPiece(
            id="cup_foam", role="cup", polygon_uv=list(poly),
            count=2, mirror_axis="u", fabric_id="F_FOAM_CUP_3MM",
            layer_role="padding", parent_id="cup",
            edge_names=edge_names,
        ))

    # Internal cup-edge bind seam (FOE around armhole + cup_outer).
    foe_id = "FOE_15MM"
    seam_type = snap_seam_for_fabric(primary_fid, structural=False)
    seams.append(Seam(
        id="seam_cup_armhole",
        edge_a=EdgeRef(piece_id="cup", edge_index=1, edge_name="armhole",
                         side="R"),
        edge_b=None, seam_type_id="S_FOE_BIND_15MM",
        elastic_id=foe_id, finish="FOE", visible=True,
    ))
    return pieces, seams


def _make_bottom_pieces(g, primary_fid: str
                        ) -> tuple[list[PatternPiece], list[Seam]]:
    poly_front = _bottom_front_polygon(g)
    pieces: list[PatternPiece] = []
    seams: list[Seam] = []
    if poly_front and len(poly_front) >= 4:
        # Polygon edges (5 verts: top-left, top-right, leg-cut-right,
        # crotch, leg-cut-left), reasonable semantic labels:
        edge_names_front = ["waistband", "leg_opening", "inseam",
                              "leg_opening", "side_seam"]
        # If poly has different vertex count, pad/truncate the names
        en = (edge_names_front[: len(poly_front) - 1]
              if len(poly_front) - 1 <= len(edge_names_front)
              else edge_names_front + ["side_seam"] * (len(poly_front) - 1 - len(edge_names_front)))
        pieces.append(PatternPiece(
            id="bottom_front", role="front_bottom", polygon_uv=list(poly_front),
            count=1, fabric_id=primary_fid, layer_role="shell",
            edge_names=en,
        ))
        seams.append(Seam(
            id="seam_bottom_front_legs",
            edge_a=EdgeRef("bottom_front", 1, "leg_opening", "R"),
            edge_b=None, seam_type_id="S_FOE_BIND_15MM",
            elastic_id="FOE_15MM", finish="FOE",
        ))
    polys_back = _bottom_back_polygons(g)
    for i, p in enumerate(polys_back):
        if len(p) < 4:
            continue
        side = "R" if i == 0 else "L"
        en = ["waistband", "leg_opening", "side_seam", "back_seam"]
        en = en[: len(p) - 1]
        if len(en) < len(p) - 1:
            en += ["back_seam"] * (len(p) - 1 - len(en))
        pieces.append(PatternPiece(
            id=f"bottom_back_{side}",
            role="back_bottom", polygon_uv=list(p),
            count=1, fabric_id=primary_fid, layer_role="shell",
            edge_names=en, notes=f"side={side}",
        ))
    return pieces, seams


def _make_back_band_pieces(g, primary_fid: str) -> list[PatternPiece]:
    polys = _back_top_polygons(g)
    out = []
    for i, p in enumerate(polys):
        if len(p) < 4:
            continue
        side = "R" if i == 0 else "L"
        en = ["waistband"] * (len(p) - 1)
        out.append(PatternPiece(
            id=f"back_band_{side}",
            role="back_band_panel", polygon_uv=list(p),
            count=1, fabric_id=primary_fid, layer_role="shell",
            edge_names=en, notes=f"side={side}",
        ))
    return out


def _make_side_tie_pieces(g, primary_fid: str) -> list[PatternPiece]:
    polys = _side_tie_polygons(g)
    out = []
    for i, p in enumerate(polys):
        if len(p) < 4:
            continue
        side = "R" if i == 0 else "L"
        en = ["side_seam"] * (len(p) - 1)
        out.append(PatternPiece(
            id=f"side_tie_panel_{side}",
            role="side_tie_panel", polygon_uv=list(p),
            count=1, fabric_id=primary_fid, layer_role="shell",
            edge_names=en, notes=f"side={side}",
        ))
    return out


def _connectors_for_triangle_halter(g
                                     ) -> tuple[list[ConnectorRef],
                                                  list[Attachment]]:
    """Halter cord behind neck + 2 side ties + back closure tie."""
    conns: list[ConnectorRef] = []
    atts: list[Attachment] = []
    # Halter cord — anchored at cup inner-tops, routes behind neck.
    if g.top_neck_strap > 0.15:
        halter = _connector_ref("STR_HALTER_CORD")
        conns.append(halter)
        atts.append(Attachment(
            id="att_halter", component_kind="connector",
            component_id=halter.id, target_kind="anatomy_anchor",
            anatomy_anchor="neck_base_back",
        ))
    # Side ties — width chosen by tie_dangle (longer dangle → bigger tie ribbon).
    tie_id = ("TIE_RIBBON_15MM" if g.bot_tie_dangle > 0.5
              else "TIE_CORD_5MM" if g.bot_tie_dangle > 0.2
              else "TIE_CORD_3MM")
    tie = _connector_ref(tie_id)
    conns.append(tie)
    atts.append(Attachment(
        id="att_tie_R", component_kind="connector", component_id=tie.id,
        target_kind="anatomy_anchor", anatomy_anchor="hip_R",
    ))
    atts.append(Attachment(
        id="att_tie_L", component_kind="connector", component_id=tie.id,
        target_kind="anatomy_anchor", anatomy_anchor="hip_L",
    ))
    # Back closure (around-chest) tie if back_coverage is small (string-back).
    if g.top_back_coverage < 0.30:
        back_tie = _connector_ref("TIE_CORD_5MM")
        if back_tie.id != tie.id:
            conns.append(back_tie)
        atts.append(Attachment(
            id="att_back_tie", component_kind="connector",
            component_id=back_tie.id, target_kind="anatomy_anchor",
            anatomy_anchor="back_scapula_R",
        ))
    # Optional O-ring at strap junctions if Genome.has_oring is set.
    if g.has_oring > 0.5:
        oring_size = 0.8 + 1.6 * float(g.oring_size)   # 8..24 mm
        ring_id = snap_oring(oring_size,
                              metal=g.hardware_metal if g.hardware_metal != "none" else "gold")
        ring = _connector_ref(ring_id)
        conns.append(ring)
        atts.append(Attachment(
            id="att_oring_R", component_kind="connector",
            component_id=ring.id, target_kind="seam_at_param",
            seam_id="seam_cup_armhole", seam_param_t=0.0,
        ))
    return conns, atts


def _connectors_for_bandeau(g) -> tuple[list[ConnectorRef],
                                          list[Attachment]]:
    """Underbust full-loop elastic + waist elastic."""
    conns = [_connector_ref("ELS_UNDERBUST_15MM"),
             _connector_ref("ELS_WAIST_15MM")]
    atts = [
        Attachment(id="att_underbust", component_kind="connector",
                    component_id="ELS_UNDERBUST_15MM",
                    target_kind="anatomy_anchor",
                    anatomy_anchor="sternum"),
        Attachment(id="att_waist", component_kind="connector",
                    component_id="ELS_WAIST_15MM",
                    target_kind="anatomy_anchor", anatomy_anchor="navel"),
    ]
    return conns, atts


def _connectors_for_bralette(g) -> tuple[list[ConnectorRef],
                                           list[Attachment]]:
    """2 shoulder straps + underbust + side ties + optional sliders."""
    strap_w = 1.0 + 1.0 * float(g.top_shoulder_strap)   # 10..20 mm
    padded = bool(g.fabric_weight > 0.55)
    strap_id = snap_strap(strap_w, padded=padded)
    strap = _connector_ref(strap_id)
    underbust = _connector_ref("ELS_UNDERBUST_15MM")
    conns: list[ConnectorRef] = [strap, underbust]
    atts: list[Attachment] = [
        Attachment(id="att_strap_R", component_kind="connector",
                    component_id=strap.id, target_kind="anatomy_anchor",
                    anatomy_anchor="front_clavicle_R"),
        Attachment(id="att_strap_L", component_kind="connector",
                    component_id=strap.id, target_kind="anatomy_anchor",
                    anatomy_anchor="front_clavicle_L"),
        Attachment(id="att_underbust", component_kind="connector",
                    component_id=underbust.id,
                    target_kind="anatomy_anchor", anatomy_anchor="sternum"),
    ]
    # Sliders for adjustable straps when strap is wider (industry norm)
    if strap.width_cm >= 1.5:
        slider = _connector_ref(snap_strap_slider(strap.width_cm))
        conns.append(slider)
        atts.append(Attachment(
            id="att_slider_R", component_kind="connector",
            component_id=slider.id, target_kind="anatomy_anchor",
            anatomy_anchor="front_clavicle_R",
            offset_cm=(0.0, -3.0, 0.0),
        ))
    return conns, atts


def snap_strap_slider(width_cm: float) -> str:
    """Pick a slider whose width matches the strap."""
    candidates = [(k, v) for k, v in CONNECTORS.items() if v.kind == "slider"]
    return min(candidates, key=lambda kv: abs(kv[1].width_cm - width_cm))[0]


def _connectors_for_one_piece(g) -> tuple[list[ConnectorRef],
                                            list[Attachment]]:
    """One-piece maillot: shoulder/halter strap routing + underbust
    support. No side ties (panels are continuous through the side
    seam). Optional waist elastic if Genome wants a defined waist.
    """
    conns: list[ConnectorRef] = []
    atts: list[Attachment] = []

    if g.top_shoulder_strap > 0.15:
        strap_w = 1.0 + 1.0 * float(g.top_shoulder_strap)
        strap_id = snap_strap(strap_w, padded=bool(g.fabric_weight > 0.55))
        strap = _connector_ref(strap_id)
        conns.append(strap)
        atts.append(Attachment(
            id="att_strap_R", component_kind="connector",
            component_id=strap.id, target_kind="anatomy_anchor",
            anatomy_anchor="front_clavicle_R"))
        atts.append(Attachment(
            id="att_strap_L", component_kind="connector",
            component_id=strap.id, target_kind="anatomy_anchor",
            anatomy_anchor="front_clavicle_L"))
    elif g.top_neck_strap > 0.15:
        halter = _connector_ref("STR_HALTER_CORD")
        conns.append(halter)
        atts.append(Attachment(
            id="att_halter", component_kind="connector",
            component_id=halter.id, target_kind="anatomy_anchor",
            anatomy_anchor="neck_base_back"))

    underbust = _connector_ref("ELS_UNDERBUST_15MM")
    conns.append(underbust)
    atts.append(Attachment(
        id="att_underbust", component_kind="connector",
        component_id=underbust.id, target_kind="anatomy_anchor",
        anatomy_anchor="sternum"))
    return conns, atts


def _accessories_for_genome(g) -> tuple[list[AccessoryRef],
                                          list[Attachment]]:
    """Optional accessories driven by Genome.has_bow / has_fringe / has_beads / has_shell."""
    accs: list[AccessoryRef] = []
    atts: list[Attachment] = []
    if g.has_bow > 0.5:
        size = _bow_size_to_cm(g)
        bow_id = snap_accessory("bow", size_cm=size)
        if bow_id is not None:
            accs.append(_accessory_ref(bow_id, count=1))
            atts.append(Attachment(
                id="att_bow_front", component_kind="accessory",
                component_id=bow_id, target_kind="anatomy_anchor",
                anatomy_anchor="sternum",
            ))
    if g.has_fringe > 0.5:
        size = _fringe_length_to_cm(g)
        frg_id = snap_accessory("fringe", size_cm=size) or "FRG_BEADED_80MM"
        accs.append(_accessory_ref(frg_id, count=1))
        atts.append(Attachment(
            id="att_fringe", component_kind="accessory",
            component_id=frg_id, target_kind="anatomy_anchor",
            anatomy_anchor="hip_R", offset_cm=(0.0, -3.0, 0.0),
        ))
    if g.has_beads > 0.5:
        bd_id = snap_accessory("beads", size_cm=0.6) or "BD_OVAL_8MM"
        accs.append(_accessory_ref(bd_id, count=12))
        atts.append(Attachment(
            id="att_beads", component_kind="accessory",
            component_id=bd_id, target_kind="anatomy_anchor",
            anatomy_anchor="neck_base_front",
        ))
    if g.has_shell > 0.5:
        shl_id = snap_accessory("shell_charm", size_cm=2.5) or "SHL_TROCHUS_25MM"
        accs.append(_accessory_ref(shl_id, count=1))
        atts.append(Attachment(
            id="att_shell", component_kind="accessory",
            component_id=shl_id, target_kind="anatomy_anchor",
            anatomy_anchor="sternum",
        ))
    return accs, atts


def genome_to_garment(g, anatomy=None) -> Garment:
    """Pure function: Genome -> Garment latent state. Deterministic;
    anatomy parameter is currently informational only (attachments
    reference named anchors that the renderer resolves against
    AnatomyLandmarks at build time).
    """
    archetype = _detect_archetype(g)   # may raise UnsupportedArchetypeV1

    # Pick primary shell fabric.
    primary_fid = _shell_fabric_for_genome(g)

    # Build pieces (shell + optional padding/lining).
    cup_pieces, cup_seams = _make_cup_pieces(g, primary_fid)
    bottom_pieces, bottom_seams = _make_bottom_pieces(g, primary_fid)
    back_band_pieces = _make_back_band_pieces(g, primary_fid)
    side_tie_pieces = _make_side_tie_pieces(g, primary_fid)

    pieces: list[PatternPiece] = []
    pieces.extend(cup_pieces)
    pieces.extend(back_band_pieces)
    pieces.extend(bottom_pieces)
    pieces.extend(side_tie_pieces)

    # Optional powermesh lining behind the shell cup.
    if float(g.fabric_opacity) < 0.92:
        # Sheer fabric → add lining for modesty (industry standard
        # powermesh inner layer).
        pieces.append(PatternPiece(
            id="cup_lining", role="cup",
            polygon_uv=list(_cup_polygon(g, +1)),
            count=2, mirror_axis="u", fabric_id="F_POWERMESH_LINING",
            layer_role="lining", parent_id="cup",
            edge_names=["cup_outer"] * (len(_cup_polygon(g, +1)) - 1),
        ))

    seams: list[Seam] = list(cup_seams) + list(bottom_seams)
    # Inseam: front bottom -> back bottom join (gusset).
    if any(p.id == "bottom_front" for p in pieces) and \
       any(p.id.startswith("bottom_back_") for p in pieces):
        seams.append(Seam(
            id="seam_inseam_R",
            edge_a=EdgeRef("bottom_front", 2, "inseam", "R"),
            edge_b=EdgeRef("bottom_back_R", 3, "inseam", "R"),
            seam_type_id="S_OVERLOCK_4THREAD", finish="topstitch",
        ))

    # Connectors / attachments per archetype.
    if archetype == "triangle_string_halter":
        conns, c_atts = _connectors_for_triangle_halter(g)
    elif archetype == "bandeau_back_band":
        conns, c_atts = _connectors_for_bandeau(g)
    elif archetype == "one_piece_maillot":
        conns, c_atts = _connectors_for_one_piece(g)
    else:   # bralette_shoulder_strap
        conns, c_atts = _connectors_for_bralette(g)

    accs, a_atts = _accessories_for_genome(g)
    attachments = list(c_atts) + list(a_atts)

    # Resolve fabric refs (de-dup'd value copies).
    fabrics = _dedup_fabrics([_fabric_ref(p.fabric_id) for p in pieces])

    return Garment(
        archetype=archetype,
        pieces=pieces, fabrics=fabrics,
        connectors=conns, accessories=accs,
        seams=seams, attachments=attachments,
        metadata={
            "generator_version": GENERATOR_VERSION,
            "primary_fabric_id": primary_fid,
            "validation_warnings": [],
        },
    )


# ---------------------------------------------------------------------------
# Step 4 — validate_garment
# ---------------------------------------------------------------------------

# Industry tolerances. 8 cm² is the smallest cup piece sewable in
# practice (Bra-Makers Supply minimum). Adjacent seam edge tolerance
# 8% is the standard for stretch-knit assembly (panels ease into each
# other; lockstitch wovens use 2%).
MIN_PIECE_AREA_CM2 = 8.0
SEAM_LENGTH_TOLERANCE = 0.08   # ±8% — knit ease industry typical


def _shoelace_area_uv(poly: list[tuple[float, float]]) -> float:
    """Signed polygon area in raw UV-square units (Shoelace formula)."""
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly) - 1):
        s += poly[i][0] * poly[i + 1][1] - poly[i + 1][0] * poly[i][1]
    # Close if not already
    if poly[0] != poly[-1]:
        s += poly[-1][0] * poly[0][1] - poly[0][0] * poly[-1][1]
    return 0.5 * abs(s)


def _uv_area_to_body_cm2(uv_area: float,
                          body_height_cm: float = 100.0,
                          body_circ_cm: float = 90.0) -> float:
    """Convert UV-square units to body surface cm² using the cylindrical
    mapping. Body U covers 2π (full circumference), body V covers torso
    height. Defaults are coarse human-female torso dimensions matching
    the NPC mesh used for testing."""
    return uv_area * (body_circ_cm / 2.0) * body_height_cm


def _polygon_self_intersects(poly: list[tuple[float, float]]) -> bool:
    """Return True if any two non-adjacent edges of the polygon cross."""
    n = len(poly) - (1 if poly and poly[0] == poly[-1] else 0)
    if n < 4:
        return False

    def _seg_intersect(p, q, r, s):
        def cross(a, b, c):
            return ((b[0] - a[0]) * (c[1] - a[1])
                    - (b[1] - a[1]) * (c[0] - a[0]))
        d1 = cross(r, s, p)
        d2 = cross(r, s, q)
        d3 = cross(p, q, r)
        d4 = cross(p, q, s)
        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return True
        return False

    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 2, n):
            # skip adjacent edge pair (wraps around)
            if i == 0 and j == n - 1:
                continue
            c, d = poly[j], poly[(j + 1) % n]
            if _seg_intersect(a, b, c, d):
                return True
    return False


def _edge_length_body_cm(poly: list[tuple[float, float]],
                          edge_index: int,
                          body_height_cm: float = 100.0,
                          body_circ_cm: float = 90.0) -> float:
    """Approximate body-cm length of the edge between poly[edge_index]
    and poly[edge_index+1] under the cylindrical mapping."""
    a = poly[edge_index]
    b = poly[(edge_index + 1) % len(poly)]
    du = b[0] - a[0]
    dv = b[1] - a[1]
    # 1 unit u (full Genome [-1,1]) = body circumference / 2
    # 1 unit v (full Genome [0,1]) = body torso height
    dx = du * body_circ_cm / 2.0
    dy = dv * body_height_cm
    return (dx * dx + dy * dy) ** 0.5


def validate_garment(garment: Garment) -> Garment:
    """Run hard rules + soft rules on a Garment. Hard violations get a
    projection (clamp / drop / replace) and a warning. Soft violations
    record warnings only. Returns the (possibly mutated) Garment.

    Hard rules:
      H1 piece area > MIN_PIECE_AREA_CM2 (drop tiny pieces)
      H2 polygon non-self-intersecting (drop self-intersecting pieces)
      H3 seam-paired edges' body-cm lengths match within ±SEAM_LENGTH_TOLERANCE
      H4 every Connector / Fabric / Accessory id is in catalog

    Soft rules (warning only):
      S1 grain_dir vs. high-tension piece stretch-axis
      S2 seam_type_id vs. fabric weave compatibility
    """
    warnings: list[str] = []

    # ---- H4: every catalog reference resolves ----
    for fab in garment.fabrics:
        if fab.id not in FABRICS:
            warnings.append(f"H4: fabric '{fab.id}' not in catalog")
    for c in garment.connectors:
        if c.id not in CONNECTORS:
            warnings.append(f"H4: connector '{c.id}' not in catalog")
    for a in garment.accessories:
        if a.id not in ACCESSORIES:
            warnings.append(f"H4: accessory '{a.id}' not in catalog")
    for s in garment.seams:
        if s.seam_type_id and s.seam_type_id not in SEAM_TYPES:
            warnings.append(f"H4: seam_type '{s.seam_type_id}' not in catalog")
        if s.elastic_id and s.elastic_id not in CONNECTORS:
            warnings.append(f"H4: elastic '{s.elastic_id}' not in catalog")

    # ---- H1 + H2: piece-level checks. Drop offending pieces. ----
    kept_pieces: list[PatternPiece] = []
    for p in garment.pieces:
        a = _shoelace_area_uv(p.polygon_uv)
        body_a = _uv_area_to_body_cm2(a)
        if body_a < MIN_PIECE_AREA_CM2:
            warnings.append(
                f"H1: piece '{p.id}' area {body_a:.1f} cm² < "
                f"{MIN_PIECE_AREA_CM2} cm² — dropped")
            continue
        if _polygon_self_intersects(p.polygon_uv):
            warnings.append(
                f"H2: piece '{p.id}' polygon self-intersects — dropped")
            continue
        kept_pieces.append(p)
    garment.pieces = kept_pieces

    # Drop seams whose pieces were dropped.
    piece_ids = {p.id for p in garment.pieces}
    kept_seams: list[Seam] = []
    for s in garment.seams:
        if s.edge_a.piece_id not in piece_ids:
            warnings.append(
                f"H1/H2: seam '{s.id}' references dropped piece "
                f"'{s.edge_a.piece_id}' — dropped")
            continue
        if s.edge_b is not None and s.edge_b.piece_id not in piece_ids:
            warnings.append(
                f"H1/H2: seam '{s.id}' references dropped piece "
                f"'{s.edge_b.piece_id}' — dropped")
            continue
        kept_seams.append(s)
    garment.seams = kept_seams

    # ---- H3: seam-pair edge length match (paired seams only) ----
    pieces_by_id = {p.id: p for p in garment.pieces}
    for s in garment.seams:
        if s.edge_b is None:
            continue
        pa = pieces_by_id.get(s.edge_a.piece_id)
        pb = pieces_by_id.get(s.edge_b.piece_id)
        if pa is None or pb is None:
            continue
        try:
            la = _edge_length_body_cm(pa.polygon_uv, s.edge_a.edge_index)
            lb = _edge_length_body_cm(pb.polygon_uv, s.edge_b.edge_index)
        except IndexError:
            warnings.append(f"H3: seam '{s.id}' edge index out of range")
            continue
        if max(la, lb) <= 0:
            continue
        diff = abs(la - lb) / max(la, lb)
        if diff > SEAM_LENGTH_TOLERANCE:
            warnings.append(
                f"H3: seam '{s.id}' edge mismatch {diff*100:.1f}% "
                f"(la={la:.2f} cm, lb={lb:.2f} cm) > "
                f"{SEAM_LENGTH_TOLERANCE*100:.0f}%")

    # ---- S1: high-tension piece grain direction ----
    HIGH_TENSION_ROLES = {"cup", "underband", "back_band_panel"}
    for p in garment.pieces:
        if p.role not in HIGH_TENSION_ROLES:
            continue
        if p.layer_role != "shell":
            continue
        # 0° grain == stretchy axis along u (around body); high-tension
        # pieces should have grain near 0° so that the across-body axis
        # provides the stretch.
        if abs(p.grain_dir_deg) > 30.0 and abs(p.grain_dir_deg - 90.0) > 30.0:
            warnings.append(
                f"S1: piece '{p.id}' grain {p.grain_dir_deg}° "
                f"not aligned to body stretch axis")

    # ---- S2: seam type vs. fabric ----
    fab_by_id = {f.id: f for f in garment.fabrics}
    for s in garment.seams:
        st = SEAM_TYPES.get(s.seam_type_id)
        if st is None:
            continue
        # Look up the fabric on the involved piece(s).
        pa = pieces_by_id.get(s.edge_a.piece_id)
        if pa is None:
            continue
        fab = fab_by_id.get(pa.fabric_id)
        if fab is None:
            continue
        if fab.weave not in st.fabric_compat:
            warnings.append(
                f"S2: seam '{s.id}' type {s.seam_type_id} not compatible "
                f"with fabric weave '{fab.weave}'")

    garment.metadata.setdefault("validation_warnings", []).extend(warnings)
    return garment
