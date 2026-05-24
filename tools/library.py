"""
Component Library — v2 latent space schema.

The very first layer of the v2 cascaded stack:

    Component Library  →  Outfit  →  Garment  →  BodyDeployment  →  mesh

A LibraryEntry describes ONE real-world component (a Brazilian
triangle cup pattern, a 1" FOE elastic, a chrome 12mm O-ring, a
gold drop earring, etc.) with three classes of attributes:

  1. Identity / category — id / kind / name / tags
  2. Local latent space — local_params_schema declaring named bounded
     continuous (or discrete) variations the component can have while
     remaining itself (size, color, finish). A point in this space is
     a real instance of that real component, never a "smooth morph
     between component A and component B".
  3. Composition meta — compatible_with (which other library entries
     it pairs with) + anatomy_hints (default body anchor names where
     it naturally attaches).

Higher up, ARCHETYPE_SLOTS declares for each garment archetype which
SlotSpec slots exist (cup / bottom_front / halter_strap / fabric /
body_jewelry...). The Outfit chromosome (defined in tools/outfit.py)
fills each slot with one (or up to max_count) library_id + local_params.

Why this structure
------------------
Current Genome's continuous fields like top_half_u / top_half_v map
to polygons via _cup_polygon math. Intermediate values can produce
"in-between" cup shapes that don't correspond to any real garment —
neither Brazilian nor Balconette but a math interpolation. The library
constrains every variation to live within "real Brazilian variations",
"real Balconette variations" etc.; cross-category jumps are explicit
library_id swaps, not smooth interpolation.

This file defines:
  - LibraryEntry / SlotSpec dataclasses
  - ARCHETYPE_SLOTS table for the 4 v1 archetypes
  - validate_outfit hard rule checks (slot required / library_id known
    / compatible_with non-empty intersection)

Companion files:
  - tools/library_data.py — ~80 hand-authored entries (the actual catalog)
  - tools/polygon_recipes.py — geometry generators referenced by
    base_polygon_recipe on cup_piece / bottom_piece / strap_piece entries
  - tools/outfit.py — Outfit dataclass + outfit_to_garment
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Closed-set vocabularies
# ---------------------------------------------------------------------------

# Modesty constraint applied to bottom_piece selection.
#   0.0 — unconstrained: any bottom_piece allowed_tags lets through
#   0.33+ — drop minimal-coverage entries (thong, brazilian)
#   0.66+ — only coverage_class="full" (brief / high_waisted),
#           local_params clamped to upper-end of front_top_v / front_half_u
#   1.0 — strict: same as 0.66+ plus front-coverage local_params pinned
#         to schema max
# random_outfit / genome_to_outfit / mutate consult this when picking
# the bottom_front slot. Module-global so callers can set once and have
# all sampling/migration/GA respect it; functions also accept a kwarg.
BOTTOM_COVERAGE_STRICT: float = 0.0

# Modesty constraint applied to cup_piece selection.
#   0.0 — unconstrained: any cup_piece allowed_tags lets through
#   0.33+ — drop pure triangle (minimal); prefer balconette/bandeau/molded
#   0.66+ — only molded_foam / softcup; falls back to balconette/bandeau
#           if archetype's slot tags don't allow molded
#   1.0 — strict: same as 0.66+ plus cup-coverage local_params pinned
#         (half_u/half_v to schema max, inner_u to schema min so the
#         cups close in toward the sternum)
CUP_COVERAGE_STRICT: float = 0.0


def set_bottom_coverage_strict(value: float) -> None:
    """Set the global bottom modesty constraint. See BOTTOM_COVERAGE_STRICT."""
    global BOTTOM_COVERAGE_STRICT
    BOTTOM_COVERAGE_STRICT = max(0.0, min(1.0, float(value)))


def set_cup_coverage_strict(value: float) -> None:
    """Set the global cup modesty constraint. See CUP_COVERAGE_STRICT."""
    global CUP_COVERAGE_STRICT
    CUP_COVERAGE_STRICT = max(0.0, min(1.0, float(value)))


def filter_bottoms_by_coverage(candidates, strict: float):
    """Drop bottom_piece entries whose coverage_class is below the
    threshold implied by `strict`. Falls back through the coverage
    ladder so an archetype whose slot tags don't include any 'full'
    entries (e.g. triangle_string_halter) still returns its highest
    available coverage tier (medium > minimal) instead of giving up."""
    if strict <= 0:
        return candidates
    full = [c for c in candidates if c.coverage_class == "full"]
    medium = [c for c in candidates if c.coverage_class == "medium"]
    if strict >= 0.66:
        return full or medium or candidates
    if strict >= 0.33:
        return (full + medium) or candidates
    return candidates


# Cup coverage tiers driven by geometry_kind. cup_piece entries don't
# carry a coverage_class field, so we map by shape: molded foam
# physically wraps the most fabric, balconette/bandeau cover wide,
# triangle is the bare minimum.
_CUP_FULL_GEOS = ("molded_foam", "softcup_squareneck")
_CUP_MEDIUM_GEOS = ("balconette", "bandeau_unified", "bandeau")


def filter_cups_by_coverage(candidates, strict: float):
    """Drop cup_piece entries whose geometry_kind is below the threshold
    implied by `strict`. Falls back through full → medium → all so an
    archetype whose slot tags don't include molded foam (e.g. pure
    triangle_string_halter) still returns its highest available tier."""
    if strict <= 0:
        return candidates
    full = [c for c in candidates if c.geometry_kind in _CUP_FULL_GEOS]
    medium = [c for c in candidates if c.geometry_kind in _CUP_MEDIUM_GEOS]
    if strict >= 0.66:
        return full or medium or candidates
    if strict >= 0.33:
        return (full + medium) or candidates
    return candidates


# Library kinds — every LibraryEntry must declare exactly one.
LIBRARY_KINDS = (
    "cup_piece",        # bra cup pattern (triangle / balconette / bandeau / molded foam / softcup)
    "bottom_piece",     # bottom pattern (thong / brazilian / cheeky / brief / high_waisted)
    "strap_piece",      # halter cord / shoulder strap / side tie / FOE elastic
    "hardware",         # O ring / D ring / slider / buckle
    "accessory",        # bow / shell charm / pendant / fringe / beads / tassel
    "fabric",           # swim lycra / mesh / powermesh / EVA foam / crochet
    "body_jewelry",     # bracelet / necklace / earring / body chain / anklet
    "seam_type",        # construction stitch type (4-thread overlock, FOE, etc.)
)


# ---------------------------------------------------------------------------
# Library entry
# ---------------------------------------------------------------------------

@dataclass
class LibraryEntry:
    """A single component in the library. Kind-specific fields are kept
    flat (kitchen-sink dataclass) for easy authoring; only fields
    relevant to the entry's kind get populated, the rest stay at default.

    The local_params_schema dict declares the entry's internal latent
    space: each (name, (min, max, default)) tuple is a continuous
    parameter the entry is allowed to vary along while remaining the
    same component. Outfits sample concrete values inside these bounds.
    """
    id: str
    kind: str                          # one of LIBRARY_KINDS
    name: str

    # --- Composition meta (used by validate_outfit + slot fill) ---
    tags: tuple[str, ...] = ()
    compatible_with: tuple[str, ...] = ()    # other LibraryEntry.id allowed
    anatomy_hints: tuple[str, ...] = ()      # default anatomy_anchor names
    # local_params_schema: {param_name: (min, max, default)}
    local_params_schema: dict = field(default_factory=dict)

    # --- Geometry / piece kinds (cup_piece, bottom_piece, strap_piece) ---
    geometry_kind: str = ""              # subcategory: "triangle" / "balconette" / etc.
    base_polygon_recipe: str = ""        # registry key in polygon_recipes
    cup_size_class: str = ""             # XS/S/M/L/XL  (cup_piece only)
    coverage_class: str = ""             # minimal/medium/full (bottom_piece only)
    foam_thickness_mm: float = 0.0       # cup_piece only

    # --- Per-template polygon data (Phase 2 rewrite, 2026-05-24) ---
    # These replace the old shared `back_bottom_strips` / `center_gore` /
    # `side_tie` recipes. Each template self-describes its complete
    # polygon set instead of inheriting one shared shape.
    # back_polygon_recipe: name of recipe for THIS template's back-panel
    #                     (bottoms only). Each geometry_kind has its own
    #                     back recipe (back_thong / back_brief / etc.)
    #                     in tools/back_polygons.py.
    # connector_recipe:   for bottoms with side/hip connectors. Defaults
    #                     to no connector. Per-template authoring lets a
    #                     tie-side bottom say "I have a knot at u=±0.4
    #                     v=0.32" instead of relying on shared side_tie.
    # inner_bridge_recipe: for cups, the bridge between left+right
    #                     (replaces shared center_gore). None = no bridge.
    # anchor_specs:       for hardware/accessory entries, list of
    #                     (u, v, name) where the mesh attaches. Replaces
    #                     hardcoded 3-anchor placement in
    #                     _build_oring_meshes. List of (u, v, name).
    back_polygon_recipe: str = ""
    connector_recipe: str = ""
    inner_bridge_recipe: str = ""
    anchor_specs: tuple = ()

    # --- Hardware placement recipes (Phase 2 #5, 2026-05-25) ---
    # For hardware/accessory entries that resolve to body-jewelry meshes
    # (bow / beads / shell / fringe). Each names a placement function in
    # tools/hardware_placements.py that decides *where* on the body the
    # piece sits + how many anchor points it gets. Empty = legacy single-
    # anchor formula in render3d_uv.py.
    bow_placement:    str = ""
    beads_placement:  str = ""
    shell_placement:  str = ""
    fringe_placement: str = ""

    # --- Hardware / strap dimensions ---
    width_cm: float = 0.0                # strap / FOE / hardware
    diameter_cm: float = 0.0             # ring / slider
    length_cm: float = 0.0               # cord / chain (0 = derive at runtime)
    elastic: bool = False                # straps / FOE
    metal_finish: str = "none"           # gold / silver / nickel / pearl / chrome

    # --- Fabric ---
    weave: str = ""                      # plain / ribbed / mesh / velvet / crinkle / shiny_knit / crochet
    composition: str = ""                # text, e.g. "80% nylon / 20% spandex"
    weight_gsm: int = 0
    stretch_warp_pct: int = 0
    stretch_weft_pct: int = 0
    opacity: float = 1.0
    sheen: float = 0.0
    metallic: float = 0.0
    fabric_source: str = ""              # econyl / qnova / virgin / biopolymer / amni_soul / cotton_blend
    biodegradable: bool = False
    # Edge-finishing policy — what the cut edge of this fabric needs.
    #   "must_bind"     — raw edge frays/rolls; needs binding tape or coverstitch
    #   "raw_ok"        — neoprene / foam / coated — laser-cut edge is fine
    #   "selvedge_only" — crochet / lace / macrame — the structure terminates
    #                     itself; a separate bound edge would be redundant
    edge_finish_policy: str = "must_bind"

    # --- Body jewelry ---
    jewelry_form: str = ""               # bracelet_chain / necklace_choker / earring_drop / etc.

    # --- Seam type (construction) ---
    machine: str = ""                    # overlock / coverstitch / lockstitch / bartack
    threads: int = 0
    spi: int = 0                         # stitches per inch
    structural: bool = True              # True = panel-to-panel, False = decorative
    fabric_compat: tuple[str, ...] = ()  # weave families this seam works on

    notes: str = ""

    def sample_local_params(self, rng=None) -> dict[str, float]:
        """Pick a deterministic-default or random value for each param."""
        out = {}
        for name, (lo, hi, default) in self.local_params_schema.items():
            if rng is None:
                out[name] = float(default)
            else:
                out[name] = float(rng.uniform(lo, hi))
        return out

    def clamp_local_params(self, params: dict) -> dict[str, float]:
        """Project a params dict onto the entry's schema (drops unknown
        keys, clamps to (min, max), fills defaults for missing keys)."""
        out = {}
        for name, (lo, hi, default) in self.local_params_schema.items():
            if name in params:
                out[name] = float(max(lo, min(hi, params[name])))
            else:
                out[name] = float(default)
        return out


# ---------------------------------------------------------------------------
# Slot spec (per archetype)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SlotSpec:
    """One slot in an archetype's outfit template.

    Outfits fill each slot with one (required) or up to max_count
    (optional) LibraryEntries whose `kind` matches `kind` and whose
    tags overlap `allowed_tags` (empty allowed_tags = any tag OK).
    """
    name: str
    kind: str                                # must match LibraryEntry.kind
    required: bool = True
    allowed_tags: tuple[str, ...] = ()       # empty = no tag filter
    excluded_tags: tuple[str, ...] = ()      # blacklist (e.g. foam/lining out of primary_fabric)
    max_count: int = 1                       # body_jewelry / accessory can stack
    notes: str = ""

    def matches(self, entry: LibraryEntry) -> bool:
        if entry.kind != self.kind:
            return False
        if self.allowed_tags:
            if not (set(self.allowed_tags) & set(entry.tags)):
                return False
        if self.excluded_tags:
            if set(self.excluded_tags) & set(entry.tags):
                return False
        return True


# ---------------------------------------------------------------------------
# Archetype slot templates — the 4 v1 archetypes plus monokini
# ---------------------------------------------------------------------------

ARCHETYPE_SLOTS: dict[str, list[SlotSpec]] = {
    "triangle_string_halter": [
        SlotSpec("cup",            "cup_piece",
                  allowed_tags=("triangle", "brazilian")),
        SlotSpec("bottom_front",   "bottom_piece",
                  allowed_tags=("thong", "brazilian", "cheeky")),
        SlotSpec("bottom_back",    "bottom_piece", required=False,
                  allowed_tags=("thong", "brazilian", "cheeky")),
        SlotSpec("halter_strap",   "strap_piece",
                  allowed_tags=("halter",)),
        SlotSpec("side_tie",       "strap_piece", required=False,
                  allowed_tags=("tie", "side_tie")),
        SlotSpec("oring",          "hardware",    required=False,
                  allowed_tags=("o_ring",)),
        SlotSpec("primary_fabric", "fabric", excluded_tags=("foam","powermesh","lining","padding")),
        SlotSpec("seam_type",      "seam_type",   required=False),
        SlotSpec("accessory",      "accessory",   required=False, max_count=2),
        SlotSpec("body_jewelry",   "body_jewelry", required=False, max_count=3),
    ],
    "bandeau_back_band": [
        SlotSpec("cup",            "cup_piece",
                  allowed_tags=("bandeau", "balconette")),
        SlotSpec("bottom_front",   "bottom_piece"),
        SlotSpec("bottom_back",    "bottom_piece", required=False),
        SlotSpec("back_band",      "strap_piece",
                  allowed_tags=("back_band",)),
        SlotSpec("hip_strap",      "strap_piece", required=False,
                  allowed_tags=("hip_side",)),
        SlotSpec("primary_fabric", "fabric", excluded_tags=("foam","powermesh","lining","padding")),
        SlotSpec("lining_fabric",  "fabric", required=False),
        SlotSpec("seam_type",      "seam_type",   required=False),
        SlotSpec("accessory",      "accessory",   required=False, max_count=2),
        SlotSpec("body_jewelry",   "body_jewelry", required=False, max_count=3),
    ],
    "bralette_shoulder_strap": [
        SlotSpec("cup",            "cup_piece",
                  allowed_tags=("balconette", "softcup", "molded_foam",
                                  "triangle")),
        SlotSpec("bottom_front",   "bottom_piece"),
        SlotSpec("bottom_back",    "bottom_piece", required=False),
        SlotSpec("shoulder_strap", "strap_piece",
                  allowed_tags=("shoulder",)),
        SlotSpec("underbust",      "strap_piece", required=False,
                  allowed_tags=("underbust", "FOE")),
        SlotSpec("hip_strap",      "strap_piece", required=False,
                  allowed_tags=("hip_side",)),
        SlotSpec("slider",         "hardware", required=False,
                  allowed_tags=("slider",)),
        SlotSpec("primary_fabric", "fabric", excluded_tags=("foam","powermesh","lining","padding")),
        SlotSpec("lining_fabric",  "fabric", required=False),
        SlotSpec("seam_type",      "seam_type",   required=False),
        SlotSpec("accessory",      "accessory",   required=False, max_count=2),
        SlotSpec("body_jewelry",   "body_jewelry", required=False, max_count=3),
    ],
    "one_piece_maillot": [
        SlotSpec("cup",            "cup_piece",
                  allowed_tags=("balconette", "softcup", "triangle",
                                  "molded_foam")),
        SlotSpec("bottom_front",   "bottom_piece",
                  allowed_tags=("brief", "high_waisted", "cheeky")),
        SlotSpec("bottom_back",    "bottom_piece", required=False,
                  allowed_tags=("brief", "high_waisted", "cheeky")),
        SlotSpec("shoulder_strap", "strap_piece", required=False,
                  allowed_tags=("shoulder", "halter")),
        SlotSpec("underbust",      "strap_piece", required=False,
                  allowed_tags=("underbust", "FOE")),
        SlotSpec("hip_strap",      "strap_piece", required=False,
                  allowed_tags=("hip_side",)),
        SlotSpec("primary_fabric", "fabric", excluded_tags=("foam","powermesh","lining","padding")),
        SlotSpec("lining_fabric",  "fabric", required=False),
        SlotSpec("seam_type",      "seam_type",   required=False),
        SlotSpec("accessory",      "accessory",   required=False, max_count=2),
        SlotSpec("body_jewelry",   "body_jewelry", required=False, max_count=3),
    ],
}


# ---------------------------------------------------------------------------
# validate_outfit — hard rule check on a filled-out Outfit
# ---------------------------------------------------------------------------

def validate_outfit(outfit, library: dict[str, LibraryEntry]) -> list[str]:
    """Return list of human-readable hard-rule violations. Empty list = legal.

    Hard rules:
      O1  archetype known
      O2  every required slot is filled
      O3  every slot's library_id exists in library
      O4  every slot's library_id matches SlotSpec (kind + allowed_tags)
      O5  every selected entry's compatible_with set has non-empty
          intersection with the union of selected ids in the same outfit,
          OR is empty (no constraint)
      O6  per-slot count ≤ SlotSpec.max_count
      O7  wearability — when a `cup` is filled, the outfit must include
          at least one strap-class anchor (halter, shoulder, back_band,
          or underbust) so the cup physically stays on the body. Without
          a strap the cup would fall off.
    """
    out: list[str] = []
    if outfit.archetype not in ARCHETYPE_SLOTS:
        return [f"O1: archetype '{outfit.archetype}' not in ARCHETYPE_SLOTS"]
    slot_specs = {s.name: s for s in ARCHETYPE_SLOTS[outfit.archetype]}

    # Group assignments by slot_name
    by_slot: dict[str, list] = {}
    for a in outfit.slot_assignments:
        by_slot.setdefault(a.slot_name, []).append(a)

    selected_ids: set[str] = set()
    for spec in slot_specs.values():
        atts = by_slot.get(spec.name, [])
        if spec.required and not atts:
            out.append(f"O2: required slot '{spec.name}' not filled")
            continue
        if len(atts) > spec.max_count:
            out.append(f"O6: slot '{spec.name}' has {len(atts)} entries, "
                        f"max_count = {spec.max_count}")
        for a in atts:
            entry = library.get(a.library_id)
            if entry is None:
                out.append(f"O3: slot '{spec.name}' library_id "
                            f"'{a.library_id}' not in library")
                continue
            if not spec.matches(entry):
                out.append(f"O4: slot '{spec.name}' filled by "
                            f"'{a.library_id}' which is kind={entry.kind} "
                            f"tags={entry.tags}; expected kind={spec.kind} "
                            f"allowed_tags={spec.allowed_tags}")
            selected_ids.add(a.library_id)

    # O5: compatibility intersection (only check entries that DECLARE
    # constraints; an empty compatible_with means "any pairing allowed")
    for a in outfit.slot_assignments:
        entry = library.get(a.library_id)
        if entry is None or not entry.compatible_with:
            continue
        if not (set(entry.compatible_with) & selected_ids):
            out.append(f"O5: '{a.library_id}' requires partner from "
                        f"{entry.compatible_with} but none selected "
                        f"(selected: {sorted(selected_ids)})")

    # O7: wearability — a cup floating without any strap to hold it
    # would fall off, so any outfit with a cup needs at least one
    # anchor strap present. The acceptable anchor slots vary by
    # archetype (halter, shoulder, back_band, or underbust all qualify).
    cup_slots = [s for s in slot_specs.values() if s.kind == "cup_piece"]
    if cup_slots and any(by_slot.get(s.name) for s in cup_slots):
        anchor_slots = ("halter_strap", "shoulder_strap", "back_band",
                          "underbust")
        has_anchor = any(by_slot.get(name) for name in anchor_slots
                          if name in slot_specs)
        if not has_anchor:
            out.append("O7: wearability — cup is filled but no anchor "
                       "strap (halter/shoulder/back_band/underbust) is "
                       "present; the cup would fall off the body")
    return out


# Sanity assertions
assert all(s.kind in LIBRARY_KINDS
            for slots in ARCHETYPE_SLOTS.values() for s in slots), \
       "every SlotSpec.kind must be a known LIBRARY_KIND"
