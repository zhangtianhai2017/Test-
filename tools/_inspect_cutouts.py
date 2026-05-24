"""One-off: list cutout_mode + archetype per design in an output dir."""
import json
import os
import sys

base = sys.argv[1] if len(sys.argv) > 1 else "tools/output/2026-05-24/p3_aliased"
rows = []
for d in sorted(os.listdir(base)):
    p = os.path.join(base, d, "outfit.json")
    if not os.path.exists(p):
        continue
    j = json.load(open(p, encoding="utf-8"))
    rows.append((d, j.get("archetype", "?"),
                 j.get("global_design", {}).get("cutout_mode", "?")))
print(f"{'vid':<6}{'archetype':<32}cutout_mode")
print("-" * 72)
for r in rows:
    print(f"{r[0]:<6}{r[1]:<32}{r[2]}")
n_none = sum(1 for _, _, c in rows if c == "none")
n_active = sum(1 for _, _, c in rows
               if c in {"collar_v", "back_panel_remove",
                        "asym_panel_left", "asym_panel_right",
                        "mid_torso_window"})
n_aliased = sum(1 for _, _, c in rows
                if c in {"side_left_circle", "side_right_circle",
                         "under_bust_band", "navel_circle",
                         "navel_diamond", "collar_keyhole", "collar_o",
                         "waist_diagonal", "hip_window"})
print(f"\nnone: {n_none}  | active: {n_active}  | aliased no-op: {n_aliased}")
