"""Compare two JUDGE_PROMPT variants against a folder of rendered swimsuit PNGs.

Why this exists: 2026-05-19 smoke showed the current prompt mislabels
"top only, no bottom" renders as valid swimsuits ~70% of the time. Goal is
to find a prompt that catches missing pelvic coverage without flagging
intentionally minimal designs.

Reuses the existing `make_judge('vllm')` plumbing in tools/vision_judge.py
so we test the exact call path the trainer uses. Patches JUDGE_PROMPT for
the "new" variant.

Usage:
    cd ~/Test-
    source ~/venvs/swim-train/bin/activate
    export VISION_JUDGE_URL=http://127.0.0.1:8000/v1
    export VISION_JUDGE_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
    export NO_PROXY=127.0.0.1,localhost
    python tools/judge_eval.py --img-dir /path/to/renders [--labels labels.json]

`labels.json` (optional ground truth):
    {"i0_v0": "valid", "i0_v1": "invalid", ...}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vision_judge as vj


# V2 prompt — original 5-dim multi-dim rubric (chest/pelvic/anatomy/
# assembly/aesthetic). Kept here as the baseline for V3 A/B comparison.
# Current vision_judge.JUDGE_PROMPT is V3 (8 dims).
V2_JUDGE_PROMPT = """You are inspecting a 3D rendered image of a swimsuit on a mannequin.
Look carefully at the FABRIC visible on the body and answer five short
questions with numeric scores 0-10. Be willing to use the full range.

For each, first describe ONE phrase of what you see on that body region,
then give a score from 0 to 10.

Rubric (each 0-10):

1. chest_coverage   — how well the BREAST area is covered by fabric:
   0 = bare breasts, no fabric at all
   3 = tiny pasties / nipple covers only
   5 = minimal cups or strapless bandeau, partial coverage
   7 = standard bikini cups or bralette, well-defined coverage
   9 = full bralette, halter, or one-piece top with broad coverage
   10 = generous coverage (sports bra style, T-shirt style)

2. pelvic_coverage  — how well the PELVIC / GROIN area is covered:
   0 = completely bare, no fabric in pelvic region at all
   3 = thong / G-string (visible string only, minimal panel)
   5 = micro bikini bottom or small triangle, partial coverage
   7 = standard bikini brief or hipster
   9 = full brief, boy-short, or one-piece crotch panel
   10 = high-waist brief or skirted bottom

3. anatomy_clean    — how cleanly the fabric stays on torso/hip/shoulder
   (no overflow onto bare arms, legs, head, neck, or floating in space):
   0 = major overflow onto multiple non-torso body parts
   5 = minor overflow on one region (e.g. fabric trailing onto arm)
   10 = all fabric stays on intended body regions

4. assembly_quality — straps connected, no obvious geometry clipping,
   no broken / floating pieces:
   0 = many disconnected pieces or severe clipping
   5 = one minor issue (one disconnected strap)
   10 = clean assembly

5. aesthetic        — overall visual appeal (color harmony, proportion,
   silhouette, balance). Use the full 1-10 range:
   1 = visually broken / unappealing
   5 = average / forgettable
   10 = strikingly attractive

A design counts as a VALID SWIMSUIT only if chest_coverage >= 4 AND
pelvic_coverage >= 4 AND anatomy_clean >= 5 AND assembly_quality >= 5.

Output STRICT JSON only, no prose or markdown. Use this exact schema:
{
  "chest_observation":      "<one short phrase>",
  "chest_coverage":         <int 0-10>,
  "pelvic_observation":     "<one short phrase>",
  "pelvic_coverage":        <int 0-10>,
  "anatomy_observation":    "<one short phrase>",
  "anatomy_clean":          <int 0-10>,
  "assembly_observation":   "<one short phrase>",
  "assembly_quality":       <int 0-10>,
  "aesthetic_observation":  "<one short phrase>",
  "aesthetic":              <int 0-10>,
  "is_valid_swimsuit":      <true|false>,
  "validity_score":         <int 0-10>,
  "aesthetic_score":        <int 0-10>,
  "structural_issues":      [<list of short tags>],
  "anatomical_overflow":    [<list of body parts>],
  "missing_required_parts": [<list, e.g. "bottom_panel">],
  "style_descriptors":      [<list of short tags>],
  "overall_assessment":     "<one sentence>"
}

For the legacy fields:
  validity_score = round((chest_coverage + pelvic_coverage + anatomy_clean + assembly_quality) / 4)
  aesthetic_score = aesthetic
  is_valid_swimsuit derived from the rule above.

Begin with `{` end with `}`."""


def judge_dir(img_dir: Path, prompt: str, label: str) -> list[dict]:
    """Run the vllm judge with a specific prompt against every PNG in img_dir."""
    # patch the module-level JUDGE_PROMPT
    orig = vj.JUDGE_PROMPT
    vj.JUDGE_PROMPT = prompt
    try:
        judge = vj.make_judge("vllm")
        pngs = sorted(img_dir.glob("*.png"))
        out = []
        for i, p in enumerate(pngs, 1):
            t0 = time.time()
            r = judge.judge(str(p))
            dt = time.time() - t0
            print(f"  [{label}] {i:>2}/{len(pngs)} {p.name:14s} "
                  f"valid={r.is_valid_swimsuit} v={r.validity_score} "
                  f"a={r.aesthetic_score} {dt:.1f}s")
            out.append({
                "name": p.stem,
                "is_valid": r.is_valid_swimsuit,
                "v_score": r.validity_score,
                "a_score": r.aesthetic_score,
                # V2 structural sub-scores
                "chest_coverage": r.chest_coverage,
                "pelvic_coverage": r.pelvic_coverage,
                "anatomy_clean": r.anatomy_clean,
                "assembly_quality": r.assembly_quality,
                "aesthetic": r.aesthetic,
                # V3 aesthetic sub-scores (added 2026-05-20)
                "color_harmony": r.color_harmony,
                "proportion": r.proportion,
                "silhouette": r.silhouette,
                # context
                "missing": r.missing_required_parts,
                "issues": r.structural_issues,
                "overflow": r.anatomical_overflow,
                "assessment": r.overall_assessment,
                "elapsed_s": dt,
            })
        return out
    finally:
        vj.JUDGE_PROMPT = orig


def compare(old_res: list[dict], new_res: list[dict],
            labels: dict[str, str] | None) -> None:
    by_name_old = {r["name"]: r for r in old_res}
    by_name_new = {r["name"]: r for r in new_res}
    names = sorted(set(by_name_old) | set(by_name_new))
    print()
    print(f"{'name':16s} {'truth':>8s} {'OLD':>22s} {'NEW':>22s}  flip")
    print("-" * 80)
    old_correct = new_correct = total_with_label = 0
    flips_to_invalid = flips_to_valid = 0
    score_range_old = set()
    score_range_new = set()
    for n in names:
        o = by_name_old.get(n, {})
        nw = by_name_new.get(n, {})
        truth = labels.get(n, "-") if labels else "-"
        ol = "VAL" if o.get("is_valid") else "INV"
        nl = "VAL" if nw.get("is_valid") else "INV"
        score_range_old.add((o.get("v_score"), o.get("a_score")))
        score_range_new.add((nw.get("v_score"), nw.get("a_score")))
        old_str = f"{ol} v={o.get('v_score')} a={o.get('a_score')}"
        new_str = f"{nl} v={nw.get('v_score')} a={nw.get('a_score')}"
        flip = ""
        if ol != nl:
            flip = "->INV" if nl == "INV" else "->VAL"
            if nl == "INV":
                flips_to_invalid += 1
            else:
                flips_to_valid += 1
        if labels and n in labels:
            total_with_label += 1
            t = labels[n].lower()
            if (t.startswith("v") and o.get("is_valid")) or (t.startswith("i") and not o.get("is_valid")):
                old_correct += 1
            if (t.startswith("v") and nw.get("is_valid")) or (t.startswith("i") and not nw.get("is_valid")):
                new_correct += 1
        print(f"{n:16s} {truth:>8s} {old_str:>22s} {new_str:>22s}  {flip}")
    print("-" * 80)
    print(f"distinct (v,a) pairs:  OLD={len(score_range_old)}  NEW={len(score_range_new)}  "
          f"(more = more informative)")
    print(f"flips: OLD->NEW   to_invalid={flips_to_invalid}  to_valid={flips_to_valid}")
    if total_with_label:
        print(f"accuracy vs labels:  OLD {old_correct}/{total_with_label}  "
              f"NEW {new_correct}/{total_with_label}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img-dir", type=Path, required=True)
    ap.add_argument("--labels", type=Path, default=None,
                    help="JSON {name -> 'valid'|'invalid'}")
    ap.add_argument("--only", choices=["old", "new", "both"], default="both")
    ap.add_argument("--save", type=Path, default=None,
                    help="Write full per-PNG results to this JSON")
    args = ap.parse_args()

    labels = None
    if args.labels and args.labels.is_file():
        labels = json.loads(args.labels.read_text())
        print(f"loaded {len(labels)} labels")

    # 'OLD' slot now holds V2; 'NEW' slot holds the current
    # vision_judge.JUDGE_PROMPT (V3 at time of writing).
    old_res = new_res = []
    if args.only in ("old", "both"):
        print(f"\n=== V2 prompt (baseline) on {args.img_dir} ===")
        old_res = judge_dir(args.img_dir, V2_JUDGE_PROMPT, "V2")
    if args.only in ("new", "both"):
        print(f"\n=== current vision_judge.JUDGE_PROMPT on {args.img_dir} ===")
        new_res = judge_dir(args.img_dir, vj.JUDGE_PROMPT, "CURR")

    if args.only == "both":
        compare(old_res, new_res, labels)

    if args.save:
        args.save.write_text(json.dumps({"old": old_res, "new": new_res,
                                          "labels": labels}, indent=2))
        print(f"\nsaved -> {args.save}")


if __name__ == "__main__":
    main()
