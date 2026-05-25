"""Diagnose why all 60 cup library entries render the same shape."""
import json
import sys
sys.path.insert(0, "tools")

from library_data import LIBRARY
from outfit import Outfit, SlotAssignment, outfit_to_genome
from cup_polygons import resolve_cup_recipe

# Three cups that SHOULD look very different
SAMPLES = ["CUP_TRIANGLE_S", "CUP_SOFTCUP_HIGH_NECK_L",
           "CUP_BANDEAU_TWIST_M", "CUP_MICRO_TRIANGLE_S",
           "CUP_PUSH_UP_L"]

for cup_id in SAMPLES:
    e = LIBRARY[cup_id]
    print(f"=== {cup_id} ===")
    print(f"  geometry_kind: {e.geometry_kind}")
    print(f"  base_recipe:   {e.base_polygon_recipe}")
    print(f"  schema:        {e.local_params_schema}")
    # Get the recipe function the resolver picks
    fn = resolve_cup_recipe(e.geometry_kind, fallback=e.base_polygon_recipe)
    print(f"  resolved fn:   {fn.__name__}")
    # Pick defaults from schema
    params = {}
    for k, spec in (e.local_params_schema or {}).items():
        if isinstance(spec, tuple) and len(spec) >= 3:
            params[k] = float(spec[2])
    poly = fn(params, side=1)
    u = [p[0] for p in poly]
    v = [p[1] for p in poly]
    print(f"  polygon ({len(poly)} pts): u=[{min(u):.3f}, {max(u):.3f}]  "
          f"v=[{min(v):.3f}, {max(v):.3f}]")
    print()

# Also: what archetype gives WHICH polygon? When the SAME outfit is
# built via random_outfit + override, does the cup_polygon stored in
# the outfit JSON match what the renderer USES?
print("\n=== JSON inspection of regression output ===")
for cup_id in SAMPLES:
    path = f"tools/output/2026-05-25/p11_regression/cup_piece/{cup_id}/outfit.json"
    try:
        j = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        print(f"  {cup_id}: outfit.json missing")
        continue
    cup_slot = next((s for s in j["slot_assignments"]
                     if s["slot_name"] == "cup"), None)
    if cup_slot is None:
        print(f"  {cup_id}: NO 'cup' slot in outfit!")
    else:
        print(f"  {cup_id}: cup.library_id={cup_slot['library_id']}  "
              f"params={cup_slot['local_params']}")
