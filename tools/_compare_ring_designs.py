"""Compare global_design across designs to find pattern of ring artifact."""
import json
import os

import sys
base = sys.argv[1] if len(sys.argv) > 1 else "tools/output/2026-05-25/p4_showcase"
for vid in sorted(os.listdir(base)):
    p = os.path.join(base, vid, "outfit.json")
    if not os.path.isfile(p):
        continue
    o = json.load(open(p, encoding="utf-8"))
    gd = o.get("global_design", {})
    cup_assn = next((s for s in o["slot_assignments"] if s["slot_name"] == "cup"), None)
    cup_id = cup_assn["library_id"] if cup_assn else "?"
    cup_params = cup_assn.get("local_params", {}) if cup_assn else {}
    pat = gd.get("pattern_overlay", "?")
    h = gd.get("hue", 0.0); s = gd.get("saturation", 0.0); l = gd.get("lightness", 0.0)
    sh = gd.get("secondary_hue", 0.0); ss = gd.get("secondary_saturation", 0.0)
    sl = gd.get("secondary_lightness", 0.0)
    ps = gd.get("pattern_scale", 0.0)
    pa = gd.get("pattern_angle", 0.0)
    print(f"{vid}  cup={cup_id}")
    print(f"      pattern={pat:15s} scale={ps:.2f} angle={pa:.2f}")
    print(f"      primary  h={h:.2f} s={s:.2f} l={l:.2f}")
    print(f"      second   h={sh:.2f} s={ss:.2f} l={sl:.2f}")
    print(f"      cup_params: {cup_params}")
