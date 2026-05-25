"""Library regression render: for each library entry, build a minimal-
valid outfit that USES that entry, subprocess-render one front view,
log success/fail + render time + visual.

Purpose: find bugs hiding in the 200+ library entries that the NN
never samples. NN today picks ~10% of entries; the other 90% are
untested.

Output:
  <out_dir>/cup/<entry_id>/01_front.png       — per-cup catalog
  <out_dir>/bottom/<entry_id>/01_front.png    — per-bottom catalog
  <out_dir>/accessory/<entry_id>/01_front.png — per-accessory catalog
  <out_dir>/hardware/<entry_id>/01_front.png  — per-hardware catalog
  <out_dir>/regression_report.json            — { entry_id: {status, time_s, error} }

Run: python tools/library_regression_render.py [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from outfit import Outfit, SlotAssignment, random_outfit
from library import ARCHETYPE_SLOTS
from library_data import LIBRARY


# Per-kind: which archetype to use as the fixture, and which slot to
# override with the target entry.
#
# We pick one archetype per kind that exercises that slot most cleanly:
# - cup_piece: bralette_shoulder_strap (cup is central, has straps/back)
# - bottom_piece: bralette_shoulder_strap (front + back bottom both present)
# - accessory: triangle_string_halter (minimal context, accessory visible)
# - hardware: triangle_string_halter (oring junction visible)
KIND_FIXTURE = {
    "cup_piece":      ("bralette_shoulder_strap", "cup"),
    "bottom_piece":   ("bralette_shoulder_strap", "bottom_front"),
    "accessory":      ("triangle_string_halter",  None),  # added as extra slot
    "hardware":       ("triangle_string_halter",  None),  # added as extra slot
}


def _default_local_params(entry):
    """Pick a midpoint local_params dict from the entry's schema."""
    params = {}
    for k, spec in (entry.local_params_schema or {}).items():
        if isinstance(spec, tuple) and len(spec) >= 3:
            params[k] = float(spec[2])  # default (third element)
        elif isinstance(spec, tuple) and len(spec) == 2:
            params[k] = float((spec[0] + spec[1]) / 2)
    return params


def build_outfit_with(entry, archetype, slot_name):
    """Build a minimal-valid outfit forcing `entry` into `slot_name` of
    `archetype`. If slot_name is None, the entry is appended as a
    standalone assignment (used for accessory/hardware probing)."""
    import random
    base = random_outfit(archetype, rng=random.Random(0))
    new_assigns = []
    replaced = False
    for a in base.slot_assignments:
        if slot_name and a.slot_name == slot_name:
            new_assigns.append(SlotAssignment(
                slot_name=slot_name,
                library_id=entry.id,
                local_params=_default_local_params(entry),
            ))
            replaced = True
        else:
            new_assigns.append(a)
    if slot_name and not replaced:
        # archetype doesn't have this slot — fall back to append (won't
        # render the piece but won't crash either)
        new_assigns.append(SlotAssignment(
            slot_name=slot_name,
            library_id=entry.id,
            local_params=_default_local_params(entry),
        ))
    if slot_name is None:
        # accessory/hardware path: append as a new assignment
        slot_for_kind = {
            "accessory": "accessory",
            "hardware":  "oring",
        }.get(entry.kind, entry.kind)
        new_assigns.append(SlotAssignment(
            slot_name=slot_for_kind,
            library_id=entry.id,
            local_params=_default_local_params(entry),
        ))
    return Outfit(
        archetype=archetype,
        slot_assignments=new_assigns,
        global_design=dict(base.global_design),
    )


def save_outfit_json(outfit, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "archetype": outfit.archetype,
            "slot_assignments": [
                {"slot_name": a.slot_name,
                 "library_id": a.library_id,
                 "local_params": dict(a.local_params)}
                for a in outfit.slot_assignments],
            "global_design": dict(outfit.global_design),
        }, f, indent=2)


def render_one(outfit_json, out_dir, renderer_script, timeout=120):
    """Run _render_one_outfit.py in a subprocess. Returns (status, dt, err).

    NOTE: Open3D Filament in this WSL setup tends to SIGSEGV on exit
    cleanup AFTER successfully writing the PNG. So we judge success by
    PNG presence + non-trivial size, NOT by subprocess returncode.
    Status taxonomy:
      ok          — PNG present, sane size (> 1KB). Most common path.
      empty_png   — subprocess exited 0 but no PNG (real geom failure)
      crashed_no_png — subprocess crashed AND no PNG (real failure)
      crashed_w_png  — subprocess crashed but PNG IS present (exit-time
                       cleanup crash only; treated as success-ish)
      timeout     — subprocess >timeout
      exception   — subprocess.run itself threw
    """
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, "01_front.png")
    # remove any stale PNG so existence check is meaningful
    if os.path.exists(png):
        os.remove(png)
    t0 = time.time()
    try:
        rc = subprocess.run(
            [sys.executable, renderer_script, outfit_json, out_dir, "01_front"],
            timeout=timeout,
            capture_output=True, text=True,
        )
        dt = time.time() - t0
        png_ok = os.path.exists(png) and os.path.getsize(png) > 1000
        if rc.returncode == 0:
            return ("ok", dt, None) if png_ok else \
                ("empty_png", dt, "subprocess returned 0 but PNG missing/tiny")
        # non-zero rc
        err = (rc.stderr or "")[-400:]
        if png_ok:
            return ("crashed_w_png", dt, f"rc={rc.returncode}; png ok")
        return (f"crashed_no_png_rc{rc.returncode}", dt, err.strip())
    except subprocess.TimeoutExpired:
        return ("timeout", time.time() - t0, f">{timeout}s")
    except Exception as exc:
        return ("exception", time.time() - t0, repr(exc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--kinds", default="cup_piece,bottom_piece,accessory,hardware",
                     help="comma-list of LibraryEntry.kind values to probe")
    ap.add_argument("--limit", type=int, default=0,
                     help="cap entries per kind (debug); 0 = all")
    args = ap.parse_args()

    renderer = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "_render_one_outfit.py")
    if not os.path.isfile(renderer):
        sys.exit(f"missing renderer: {renderer}")

    kinds = [k.strip() for k in args.kinds.split(",")]
    os.makedirs(args.out_dir, exist_ok=True)
    report = {}

    for kind in kinds:
        if kind not in KIND_FIXTURE:
            print(f"[skip] unsupported kind {kind}")
            continue
        archetype, slot_name = KIND_FIXTURE[kind]
        entries = [e for e in LIBRARY.values() if e.kind == kind]
        if args.limit:
            entries = entries[: args.limit]
        print(f"\n=== {kind}: {len(entries)} entries (archetype={archetype}, slot={slot_name}) ===")
        kind_root = os.path.join(args.out_dir, kind)
        os.makedirs(kind_root, exist_ok=True)
        for i, entry in enumerate(entries):
            sub = os.path.join(kind_root, entry.id)
            outfit_json = os.path.join(sub, "outfit.json")
            try:
                outfit = build_outfit_with(entry, archetype, slot_name)
                save_outfit_json(outfit, outfit_json)
            except Exception as exc:
                report[entry.id] = {
                    "kind": kind, "status": "build_fail",
                    "time_s": 0.0, "error": repr(exc),
                }
                print(f"  [{i+1:3d}/{len(entries)}] {entry.id:40s} BUILD_FAIL: {exc}")
                continue
            status, dt, err = render_one(outfit_json, sub, renderer)
            report[entry.id] = {
                "kind": kind, "status": status,
                "time_s": round(dt, 2), "error": err,
            }
            tag = "✓" if status == "ok" else "✗"
            print(f"  [{i+1:3d}/{len(entries)}] {entry.id:40s} {tag} {status:12s} {dt:5.1f}s",
                  flush=True)

    report_path = os.path.join(args.out_dir, "regression_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nwrote {report_path}")

    # Summary
    by_status = {}
    for r in report.values():
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print("\nstatus breakdown:")
    for s, n in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {s:15s} {n:4d}")
    deaths = [k for k, r in report.items() if r["status"] != "ok"]
    print(f"\ndeaths: {len(deaths)} / {len(report)} entries")
    if deaths:
        print("first 10:")
        for k in deaths[:10]:
            r = report[k]
            print(f"  {k:40s} {r['status']:15s} {(r.get('error') or '')[:100]}")


if __name__ == "__main__":
    main()
