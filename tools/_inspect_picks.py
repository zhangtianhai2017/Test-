"""Dump archetype + per-slot library picks for designs in a dir."""
import json
import os
import sys

base = sys.argv[1]
for d in sorted(os.listdir(base)):
    p = os.path.join(base, d, "outfit.json")
    if not os.path.exists(p):
        continue
    o = json.load(open(p, encoding="utf-8"))
    arch = o.get("archetype", "?")
    gd = o.get("global_design", {})
    print(f"=== {d}  arch={arch}  cutout={gd.get('cutout_mode','?')} ===")
    for s in o.get("slot_assignments", []):
        print(f"  {s['slot_name']:18s} -> {s['library_id']}")
