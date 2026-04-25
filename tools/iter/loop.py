"""
Round driver. Each round:
  1. Load params from previous round (or seed defaults at round 0).
  2. Render 8 views + contact sheet.
  3. Wait for me to fill round_<N>/critique.json with my visual review.
  4. Diagnose -> apply -> write next round's params.
"""
from __future__ import annotations

import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seed_loader import load_seed, seed_to_genome
from iter.params import IterParams
from iter.capture import render_views, make_contact_sheet
from iter.diagnose import diagnose


def round_dir(seed: str, n: int) -> str:
    return os.path.join("tools", "output", f"iter_{seed}", f"round_{n:02d}")


def cmd_capture(args):
    seed_data = load_seed(args.seed)
    g = seed_to_genome(seed_data)

    rd = round_dir(args.seed, args.round)
    os.makedirs(rd, exist_ok=True)

    if args.round == 0:
        params = IterParams()
    else:
        prev_path = os.path.join(round_dir(args.seed, args.round - 1),
                                  "params_after.json")
        if not os.path.exists(prev_path):
            print(f"ERROR: previous round not found: {prev_path}", file=sys.stderr)
            sys.exit(1)
        params = IterParams.from_json(prev_path)

    params.to_json(os.path.join(rd, "params_before.json"))
    views_dir = os.path.join(rd, "views")
    paths = render_views(g, params, views_dir)
    sheet = os.path.join(rd, "contact_sheet.png")
    make_contact_sheet(paths, sheet)
    print(f"round {args.round}: rendered {len(paths)} views into {views_dir}")
    print(f"  contact sheet: {sheet}")
    print(f"  next: write {os.path.join(rd, 'critique.json')}")


def cmd_diagnose(args):
    rd = round_dir(args.seed, args.round)
    crit_path = os.path.join(rd, "critique.json")
    if not os.path.exists(crit_path):
        print(f"ERROR: missing {crit_path}", file=sys.stderr); sys.exit(1)
    with open(crit_path) as f:
        critique = json.load(f)
    delta, unresolved = diagnose(critique)
    with open(os.path.join(rd, "diagnosis.json"), "w") as f:
        json.dump({"delta": delta, "unresolved": unresolved}, f, indent=2)
    if unresolved:
        with open(os.path.join(rd, "unresolved_issues.json"), "w") as f:
            json.dump(unresolved, f, indent=2)
    print(f"diagnose: {len(critique.get('issues', []))} issues, "
          f"delta={delta}")
    return delta


def cmd_apply(args):
    rd = round_dir(args.seed, args.round)
    delta_path = os.path.join(rd, "diagnosis.json")
    with open(delta_path) as f:
        delta = json.load(f)["delta"]
    params = IterParams.from_json(os.path.join(rd, "params_before.json"))
    new_params = params.with_delta(delta)
    new_params.to_json(os.path.join(rd, "params_after.json"))

    diff = new_params.diff(params)
    with open(os.path.join(rd, "changelog.md"), "w") as f:
        f.write(f"# round {args.round} changelog\n\n")
        f.write("## numeric deltas applied\n\n")
        if not diff:
            f.write("- (no changes — all clamped or no actionable critique)\n")
        else:
            for k, v in diff.items():
                if k == "genome_patch":
                    f.write(f"- genome_patch:\n")
                    for gk, gv in v.items():
                        f.write(f"  - `{gk}`: {gv:+.4f}\n")
                else:
                    f.write(f"- `{k}`: {v:+.4f}\n")
    print(f"apply: wrote round_{args.round}/params_after.json + changelog.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("capture"); pc.add_argument("--round", type=int, required=True)
    pd = sub.add_parser("diagnose"); pd.add_argument("--round", type=int, required=True)
    pa = sub.add_parser("apply"); pa.add_argument("--round", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "capture":  cmd_capture(args)
    elif args.cmd == "diagnose": cmd_diagnose(args)
    elif args.cmd == "apply":    cmd_apply(args)


if __name__ == "__main__":
    main()
