"""Accessory sub-pipeline — methodologically parallel to the outfit
pipeline (library -> assembly -> 3D bake -> manifest).

Goals:
  - keep accessory generation decoupled from outfit assembly so each
    side can iterate independently;
  - reuse the MetaHuman skeleton + the refit spec already in place for
    outfits, so accessory GLBs are game-ready by the same rules;
  - produce a manifest analogous to assets/glb/manifest.json so the
    game side can wire any accessory the same way as any outfit.

Layout:
  tools/accessory_pipeline/
    __init__.py           — public re-exports + version stamp
    schema.py             — AccessoryEntry dataclass + family enum
    catalog.py            — hand-authored AccessoryEntry catalogue
    builders/
      __init__.py
      ring.py             — first family builder (parametric torus)
    bake.py               — drives catalogue -> GLB + manifest
"""
__all__ = ["schema", "catalog", "builders", "bake"]
ACCESSORY_PIPELINE_VERSION = 1
