"""Verify _lift_above_breast fires on ring-case params."""
import sys
sys.path.insert(0, "tools")
from cup_polygons import resolve_cup_recipe, BREAST_TOP_FLOOR

fn = resolve_cup_recipe("softcup_squareneck")
# v00 (ring case)
ring = {"half_u": 0.225, "half_v": 0.125, "inner_u": 0.06,
        "apex_lift": 0.44, "underband_dip": 0.05, "center_v": 0.66}
poly = fn(ring, side=1)
top = max(v for _, v in poly)
bot = min(v for _, v in poly)
print(f"ring-case  cv=0.66 hv=0.125  -> v=[{bot:.3f}, {top:.3f}]  "
      f"clears breast peak (>=0.79)? {top >= BREAST_TOP_FLOOR}")

# Normal case
normal = {**ring, "center_v": 0.78}
poly2 = fn(normal, side=1)
top2 = max(v for _, v in poly2)
bot2 = min(v for _, v in poly2)
print(f"normal     cv=0.78           -> v=[{bot2:.3f}, {top2:.3f}]  "
      f"(no lift needed)")
