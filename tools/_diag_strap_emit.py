"""Diagnose: what meshes does build_strap_meshes actually emit
for the bow+oring outfit?"""
import json
import os
import sys
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, "tools")

from outfit import Outfit, SlotAssignment, outfit_to_genome
from render3d_uv import build_strap_meshes, load_body_mesh

PATH = "tools/output/2026-05-25/p11_regression/hardware/HW_OR_TRIO_12MM_SILVER/outfit.json"
j = json.load(open(PATH, encoding="utf-8"))
slots = [SlotAssignment(slot_name=s["slot_name"],
                          library_id=s["library_id"],
                          local_params=s["local_params"])
          for s in j["slot_assignments"]]
outfit = Outfit(archetype=j["archetype"], slot_assignments=slots,
                 global_design=j["global_design"])
g = outfit_to_genome(outfit)
print(f"genome: has_bow={g.has_bow}  has_beads={g.has_beads}  "
      f"has_oring={g.has_oring}")

body = load_body_mesh()
import numpy as np
V = np.asarray(body.vertices)
y_crotch = float(np.percentile(V[:, 1], 2))
y_neck = float(np.percentile(V[:, 1], 98))
print(f"y_crotch={y_crotch:.1f}  y_neck={y_neck:.1f}")

# Build strap meshes
try:
    from garment_state import (genome_to_garment, validate_garment,
                                 deploy_to_body, validate_deployment,
                                 UnsupportedArchetypeV1)
    from outfit import outfit_to_garment
    garm = validate_garment(outfit_to_garment(outfit))
    deployment = validate_deployment(garm, deploy_to_body(garm, body))
    print(f"garment path active, accessories={len(garm.accessories)}, "
          f"connectors={len(garm.connectors)}")
except Exception as exc:
    print(f"garment path failed: {exc}")
    garm = None
    deployment = None

straps = build_strap_meshes(body, g, y_crotch, y_neck, body_deployment=deployment)
print(f"\nstrap_meshes returned {len(straps)} pieces:")
for name, mesh in straps:
    n_v = len(mesh.vertices) if mesh is not None else 0
    n_t = len(mesh.triangles) if mesh is not None else 0
    print(f"  {name:35s}  verts={n_v}  tris={n_t}")
