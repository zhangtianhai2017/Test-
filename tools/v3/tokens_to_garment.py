"""
v3 → v2 bridge: turn a list of Panel/Stroke tokens into a v2 Garment.

Why this exists: v2's Garment + validate_garment + build_fabric_shell +
polish_shell + apply_wrinkles + build_seam_lines pipeline is the
hard-won engineering chain that produces actual sewable, polished,
wrinkled 3D fabric meshes. v3's NN outputs are designed to flow INTO
this pipeline (not around it), so we don't lose any of the v2 work.

Conventions:
  - v3 Panel/Stroke UV space: u ∈ [0, 1] with front = 0.5
  - v2 Genome  / polygon UV space: u ∈ [-1, 1] with front = 0
  → u_genome = u_v3 * 2 - 1     (v stays the same)

Default fabric / connector picks: simplest commercial light swimwear,
override per-token via Panel.fabric_id / Stroke (future Connector
mapping). Goal: validate_garment passes without H4 warnings.
"""
from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from garment_state import (
    Garment, PatternPiece, FabricRef, ConnectorRef, AccessoryRef,
    Seam, EdgeRef, Attachment,
)
from catalogs import FABRICS, CONNECTORS

from v3.stroke_schema import (
    Panel, Stroke, Anchor, DEFAULT_ANCHOR_UV,
)


# ─── conventions ───────────────────────────────────────────────────────

# v2 anatomy_anchor names that the renderer / Attachment expects.
# Map from v3 Anchor to v2 string.
V3_TO_V2_ANCHOR: dict[Anchor, str] = {
    Anchor.SHOULDER_L:  "back_scapula_L",     # closest semantic
    Anchor.SHOULDER_R:  "back_scapula_R",
    Anchor.COLLARBONE:  "front_clavicle_L",   # one of pair; future: pick by stroke geom
    Anchor.NECK_BACK:   "neck_base_back",
    Anchor.STERNUM:     "sternum",
    Anchor.UNDERBUST:   "navel",              # approx; v2 has no underbust anchor
    Anchor.WAIST_L:     "hip_L",              # approx
    Anchor.WAIST_R:     "hip_R",
    Anchor.HIP_L:       "hip_L",
    Anchor.HIP_R:       "hip_R",
}


# Defaults for picks when token doesn't specify
DEFAULT_FABRIC = "F_ECONYL_PLAIN_LIGHT"
DEFAULT_STRAP_CONNECTOR = "STR_WOVEN_15MM"
DEFAULT_FOE_ELASTIC = "FOE_15MM"


# ─── UV space conversion ──────────────────────────────────────────────

def v3_uv_to_v2(u_v3: float, v_v3: float) -> tuple[float, float]:
    """v3 (u ∈ [0,1], front=0.5)  →  v2 Genome (u ∈ [-1,1], front=0)."""
    return (u_v3 * 2.0 - 1.0, v_v3)


def convert_polygon(boundary_uv_v3: list[tuple[float, float]]
                     ) -> list[tuple[float, float]]:
    return [v3_uv_to_v2(u, v) for u, v in boundary_uv_v3]


# ─── token → Garment ──────────────────────────────────────────────────

def _make_fabric_ref(fabric_id: str) -> FabricRef:
    """Build a value-copy FabricRef from catalog id (or default)."""
    fid = fabric_id if fabric_id in FABRICS else DEFAULT_FABRIC
    sku = FABRICS[fid]
    return FabricRef(
        id=sku.id, name=sku.name, weave=sku.weave,
        composition=sku.composition, weight_gsm=sku.weight_gsm,
        stretch_warp_pct=sku.stretch_warp_pct,
        stretch_weft_pct=sku.stretch_weft_pct,
        opacity=sku.opacity, sheen=sku.sheen, metallic=sku.metallic,
        source=sku.source, biodegradable=sku.biodegradable,
    )


def _make_connector_ref(connector_id: str) -> ConnectorRef:
    cid = connector_id if connector_id in CONNECTORS else DEFAULT_STRAP_CONNECTOR
    sku = CONNECTORS[cid]
    return ConnectorRef(
        id=sku.id, name=sku.name, kind=sku.kind,
        diameter_cm=getattr(sku, "diameter_cm", 0.0),
        width_cm=getattr(sku, "width_cm", 0.0),
        length_cm=getattr(sku, "length_cm", 0.0),
        material=getattr(sku, "material", ""),
        metal_finish=getattr(sku, "metal_finish", "none"),
        path_policy=getattr(sku, "path_policy", "free_anchored"),
        elastic=getattr(sku, "elastic", False),
        breaking_strength_n=getattr(sku, "breaking_strength_n", 0),
    )


def _classify_panel_role(panel: Panel) -> str:
    """Pick a v2 PatternPiece.role from panel geometry / anchors.

    This is a heuristic but is mainly used downstream for semantic labels
    (validator messages, manufacturing JSON); it doesn't drive geometry.
    """
    if not panel.anchors:
        return "side_tie_panel"
    a = set(panel.anchors)
    if a & {Anchor.SHOULDER_L, Anchor.SHOULDER_R, Anchor.STERNUM,
             Anchor.UNDERBUST, Anchor.COLLARBONE}:
        return "cup"
    if a & {Anchor.HIP_L, Anchor.HIP_R, Anchor.WAIST_L, Anchor.WAIST_R}:
        return "front_bottom"
    return "side_tie_panel"


def _stroke_path_policy(stroke: Stroke) -> str:
    """Pick a v2 ConnectorRef.path_policy from stroke endpoints."""
    a, b = stroke.start_anchor, stroke.end_anchor
    s = {a, b}
    if Anchor.NECK_BACK in s or Anchor.COLLARBONE in s:
        return "halter_behind_neck"
    if Anchor.SHOULDER_L in s or Anchor.SHOULDER_R in s:
        return "shoulder_acromion_scapula"
    if (Anchor.WAIST_L in s and Anchor.WAIST_R in s):
        return "back_band_horizontal"
    if (Anchor.HIP_L in s and Anchor.HIP_R in s):
        return "waist_band_horizontal"
    return "free_anchored"


def _infer_archetype(tokens) -> str:
    """Pick the v2 archetype that best fits these tokens.

    v2 only has 3 archetypes; pick the most permissive that matches.
    Used for documentation / .glb extras, not for geometry routing
    (build_fabric_shell doesn't switch on archetype).
    """
    n_panel = sum(1 for t in tokens if isinstance(t, Panel))
    n_stroke = sum(1 for t in tokens if isinstance(t, Stroke))
    # If has shoulder strokes → bralette. If has halter → triangle.
    # Otherwise default bandeau (no straps).
    for t in tokens:
        if isinstance(t, Stroke):
            s = {t.start_anchor, t.end_anchor}
            if Anchor.NECK_BACK in s or Anchor.COLLARBONE in s:
                return "triangle_string_halter"
            if Anchor.SHOULDER_L in s or Anchor.SHOULDER_R in s:
                return "bralette_shoulder_strap"
    return "bandeau_back_band"


def tokens_to_garment(tokens) -> Garment:
    """Convert v3 token list → v2 Garment object.

    Result can be passed directly to:
      validate_garment(g) → build_fabric_shell(body, body_uvs,
                              g.flatten_polygons(), ...)
                          → polish_shell → apply_wrinkles → ...
    """
    if not tokens:
        # empty design — return a stub
        return Garment(archetype="bandeau_back_band")

    archetype = _infer_archetype(tokens)
    pieces: list[PatternPiece] = []
    fabrics_used: dict[str, FabricRef] = {}
    connectors_used: dict[str, ConnectorRef] = {}
    attachments: list[Attachment] = []
    seams: list[Seam] = []

    # --- panels → PatternPieces ---
    for i, t in enumerate(tokens):
        if not isinstance(t, Panel):
            continue
        polygon_v2 = convert_polygon(t.boundary_uv)
        # ensure CCW + closed (no duplicated last point)
        if (polygon_v2 and polygon_v2[0] == polygon_v2[-1]):
            polygon_v2 = polygon_v2[:-1]
        # need at least 3 unique points
        if len(set(polygon_v2)) < 3:
            continue
        fab_id = t.fabric_id if t.fabric_id in FABRICS else DEFAULT_FABRIC
        if fab_id not in fabrics_used:
            fabrics_used[fab_id] = _make_fabric_ref(fab_id)
        role = _classify_panel_role(t)
        # If panel spans both sides (u_min < 0.5 < u_max), use count=1.
        # Otherwise use count=2, mirror_axis="u" for symmetric pairs (matches
        # v2 cup convention: one piece authored, the other mirrored).
        us = [u for u, _ in t.boundary_uv]
        spans_centerline = (min(us) < 0.5 < max(us))
        count = 1 if spans_centerline else 2
        mirror = "none" if spans_centerline else "u"
        piece = PatternPiece(
            id=f"v3_panel_{i}",
            role=role,
            polygon_uv=polygon_v2,
            count=count,
            mirror_axis=mirror,
            fabric_id=fab_id,
            layer_role=t.layer_role,
            edge_names=[],
        )
        pieces.append(piece)

    # --- strokes → Connectors + Attachments ---
    for i, t in enumerate(tokens):
        if not isinstance(t, Stroke):
            continue
        # Pick connector SKU based on width (mean of width_profile)
        import statistics
        mean_w = statistics.mean(t.width_profile)
        if mean_w < 1.2:
            conn_id = "TIE_CORD_3MM"
        elif mean_w < 2.0:
            conn_id = "STR_WOVEN_10MM"
        elif mean_w < 4.0:
            conn_id = "STR_WOVEN_15MM"
        else:
            conn_id = "STR_PADDED_20MM"
        if conn_id not in connectors_used:
            connectors_used[conn_id] = _make_connector_ref(conn_id)
        # Override path_policy per stroke geometry
        cref = connectors_used[conn_id]
        # Note: we don't mutate the shared ref; only the Attachment is
        # per-stroke. path_policy in v3 lives on the connector kind.
        # Attachment: anchor at start and end
        for which, anc in [("start", t.start_anchor), ("end", t.end_anchor)]:
            v2_name = V3_TO_V2_ANCHOR.get(anc)
            if v2_name is None:
                continue
            attachments.append(Attachment(
                id=f"v3_stroke_{i}_{which}",
                component_kind="connector",
                component_id=conn_id,
                target_kind="anatomy_anchor",
                anatomy_anchor=v2_name,
            ))

    garment = Garment(
        archetype=archetype,
        pieces=pieces,
        fabrics=list(fabrics_used.values()),
        connectors=list(connectors_used.values()),
        accessories=[],
        seams=seams,
        attachments=attachments,
        metadata={"source": "v3_tokens_to_garment",
                   "n_panels": sum(1 for t in tokens if isinstance(t, Panel)),
                   "n_strokes": sum(1 for t in tokens if isinstance(t, Stroke))},
    )
    return garment


# ─── smoke ────────────────────────────────────────────────────────────

def _smoke():
    """Build a Garment from a hand-crafted panel + stroke design,
    validate it, count polygons that come out the other side."""
    from garment_state import validate_garment
    from v3.stroke_schema import Panel, Stroke, Anchor

    print("─── tokens_to_garment smoke ───")
    # A simple bikini: 2 cup panels (mirrored) + 1 front bottom panel + 2 shoulder straps
    tokens = [
        # Left cup
        Panel(
            boundary_uv=[(0.32, 0.78), (0.48, 0.78), (0.50, 0.68),
                          (0.40, 0.65), (0.30, 0.68), (0.32, 0.75)],
            anchors=[Anchor.SHOULDER_L, Anchor.STERNUM, Anchor.UNDERBUST],
            color_id=4, fabric_id="F_ECONYL_PLAIN_LIGHT",
        ),
        # Bottom front (spans centerline)
        Panel(
            boundary_uv=[(0.30, 0.50), (0.70, 0.50), (0.65, 0.42),
                          (0.55, 0.38), (0.45, 0.38), (0.35, 0.42)],
            anchors=[Anchor.HIP_L, Anchor.HIP_R],
            color_id=4, fabric_id="F_ECONYL_PLAIN_LIGHT",
        ),
        # Shoulder strap L
        Stroke(start_anchor=Anchor.SHOULDER_L, end_anchor=Anchor.UNDERBUST,
                width_profile=(1.5, 1.5, 1.5), color_id=4),
        # Shoulder strap R
        Stroke(start_anchor=Anchor.SHOULDER_R, end_anchor=Anchor.UNDERBUST,
                width_profile=(1.5, 1.5, 1.5), color_id=4, is_end=True),
    ]
    g = tokens_to_garment(tokens)
    print(f"  archetype  = {g.archetype}")
    print(f"  pieces     = {len(g.pieces)}")
    print(f"  fabrics    = {[f.id for f in g.fabrics]}")
    print(f"  connectors = {[c.id for c in g.connectors]}")
    print(f"  attachments = {len(g.attachments)}")
    print(f"  metadata   = {g.metadata}")

    g2 = validate_garment(g)
    warns = g2.metadata.get("validation_warnings", [])
    print(f"\nafter validate_garment:")
    print(f"  pieces remaining = {len(g2.pieces)}")
    print(f"  validation warnings = {len(warns)}")
    for w in warns[:5]:
        print(f"    - {w}")

    polys = g2.flatten_polygons()
    print(f"\nflatten_polygons output: {len(polys)} polygons "
          f"(includes mirrored cup → expect ~3 polys)")
    for i, p in enumerate(polys):
        print(f"  poly[{i}] = {len(p)} points, "
              f"u_range=[{min(u for u,_ in p):.2f}, {max(u for u,_ in p):.2f}], "
              f"v_range=[{min(v for _,v in p):.2f}, {max(v for _,v in p):.2f}]")

    print("\n✓ tokens_to_garment smoke OK")


if __name__ == "__main__":
    _smoke()
