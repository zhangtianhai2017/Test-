"""Internal: render ONE outfit with N views in a fresh subprocess.

Why subprocess: Filament+OSMesa accumulates state across render cycles
(see notes in tools/rl_runner_wsl.py). Single-view+many-designs works
because each design has only 4-7 add_geometry calls. Multi-view+many-
designs (e.g. 4 views x 8 designs = 32+ cycles) segfaults around cycle
4-5. Per-design subprocess isolation avoids the leak.

Usage:
    python tools/_render_one_outfit.py <outfit_json_path> <out_dir> [views...]
"""
import json
import os
import sys

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUTFIT_PATH = sys.argv[1]
OUT_DIR = sys.argv[2]
VIEW_NAMES = set(sys.argv[3:]) if len(sys.argv) > 3 else {"01_front"}

with open(OUTFIT_PATH, encoding="utf-8") as f:
    od = json.load(f)

import iter.capture as cap
cap.VIEWS = [v for v in cap.VIEWS if v.name in VIEW_NAMES]

from outfit import Outfit, SlotAssignment, outfit_to_genome
from iter.params import IterParams
from render3d_uv import load_body_mesh

slots = [SlotAssignment(slot_name=a["slot_name"],
                          library_id=a["library_id"],
                          local_params=a["local_params"])
          for a in od["slot_assignments"]]
outfit = Outfit(archetype=od["archetype"],
                 slot_assignments=slots,
                 global_design=od["global_design"])
genome = outfit_to_genome(outfit)
params = IterParams()
params.outfit = outfit
body = load_body_mesh()

os.makedirs(OUT_DIR, exist_ok=True)
view_paths = cap.render_views(genome, params, OUT_DIR, body_mesh=body)
print("OK", len(view_paths), "views rendered to", OUT_DIR)
