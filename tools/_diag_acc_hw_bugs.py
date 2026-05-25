"""Diagnose why accessory + hardware meshes don't render."""
import json
import sys
sys.path.insert(0, "tools")

from library_data import LIBRARY
from outfit import Outfit, SlotAssignment, outfit_to_genome, outfit_to_garment

PATHS = [
    ("hardware HW_OR_TRIO_12MM_SILVER",
     "tools/output/2026-05-25/p11_regression/hardware/HW_OR_TRIO_12MM_SILVER/outfit.json"),
    ("accessory ACC_BOW_HIP_PAIR_30MM",
     "tools/output/2026-05-25/p11_regression/accessory/ACC_BOW_HIP_PAIR_30MM/outfit.json"),
]

for label, path in PATHS:
    print(f"=== {label} ===")
    j = json.load(open(path, encoding="utf-8"))
    slots = [SlotAssignment(slot_name=s["slot_name"],
                              library_id=s["library_id"],
                              local_params=s["local_params"])
              for s in j["slot_assignments"]]
    outfit = Outfit(archetype=j["archetype"], slot_assignments=slots,
                     global_design=j["global_design"])

    # 1. genome flags
    g = outfit_to_genome(outfit)
    print(f"  has_bow={g.has_bow} has_beads={g.has_beads} "
          f"has_shell={g.has_shell} has_fringe={g.has_fringe} "
          f"has_oring={g.has_oring}")

    # 2. garment connectors + accessories
    try:
        garm = outfit_to_garment(outfit)
        print(f"  garment.connectors ({len(garm.connectors)}):")
        for c in garm.connectors:
            print(f"    kind={c.kind:18s} id={c.id} diameter={c.diameter_cm}")
        print(f"  garment.accessories ({len(garm.accessories)}):")
        for a in garm.accessories:
            print(f"    kind={a.kind:18s} id={a.id} size={a.size_cm}")
    except Exception as exc:
        print(f"  outfit_to_garment EXCEPTION: {exc}")
    print()
