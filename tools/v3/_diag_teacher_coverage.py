"""DIAGNOSTIC: do the imitation TARGETS (teachers) themselves cover
pelvic + chest? This forks the p40-improvement decision:

  - teachers score LOW coverage  -> DATA problem: fix the teacher designs
    (add guaranteed pelvic + chest covering panels to every teacher).
  - teachers score HIGH coverage but p40 doesn't reproduce it -> MODEL
    problem: imitation is not faithful (training/decode issue).

Renders + judges each teacher design on its own first brief, reports
per-teacher pelvic/chest/anatomy/q10 + panel/stroke counts, and flags
stroke-only (zero-fabric) teachers.
"""
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_THIS_DIR)
for p in [_TOOLS_DIR, _THIS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")
os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from v3.stroke_schema import all_reference_designs_v31, Panel, Stroke
from v3.full_chain_render import render_design_3d
from v3.v2_lib_to_teachers import make_v2_lib_teachers, make_teacher_brief
from vision_judge import make_judge

# first-brief per hand-crafted teacher (mirrors phase_a2 TEACHER_BRIEFS_BY_NAME)
HANDCRAFTED_BRIEF = {
    "avant_garde_harness": "avant-garde black cross-body harness, two diagonals",
    "sculptural_one_piece": "sculptural orange one-piece, van Herpen style",
    "cyberpunk_cage": "cyberpunk magenta + black cage harness, multi-strap",
    "ethnic_body_chain": "ethnic gold body chain + burgundy triangle cups",
    "draped_wrap": "draped one-shoulder mauve wrap, sari-inspired",
    "chainmail_armor": "chainmail bikini armor, silver plate + gold chain",
    "nier_gothic_lace": "NieR 2B gothic asymmetric monokini, void black lace",
    "maori_feather_tribal": "Maori tribal wrap, bone-white + copper accents",
    "iridescent_holo": "holographic iridescent cyber monokini, full-body teal",
    "liquid_chrome": "Mugler liquid metal silver monokini, chrome mirror",
    "turquoise_dakini": "Tibetan dakini ritual armor, turquoise + bronze",
    "vaporwave_holographic": "vaporwave Y2K holographic two-tone, teal + magenta",
}


def q10(jr):
    return (0.30 * jr.pelvic_coverage + 0.20 * jr.chest_coverage
            + 0.15 * jr.anatomy_clean + 0.15 * jr.assembly_quality
            + 0.10 * jr.aesthetic_score + 0.10 * jr.brief_match)


def counts(tokens):
    np_ = sum(1 for t in tokens if isinstance(t, Panel))
    ns_ = sum(1 for t in tokens if isinstance(t, Stroke))
    return np_, ns_


def main():
    judge = make_judge("vllm")
    out_root = "tools/output/2026-05-30/_diag_teacher_coverage"
    os.makedirs(out_root, exist_ok=True)

    refs = dict(all_reference_designs_v31())
    v2lib = make_v2_lib_teachers(n=8, seed=7)

    items = []  # (label, brief, tokens)
    for name, tokens in refs.items():
        brief = HANDCRAFTED_BRIEF.get(name, name.replace("_", " "))
        items.append((f"HC:{name}", brief, tokens))
    for name, tokens in v2lib.items():
        brief = make_teacher_brief(name, tokens[0].color_id)[0]
        items.append((f"V2:{name[:28]}", brief, tokens))

    rows = []
    for label, brief, tokens in items:
        np_, ns_ = counts(tokens)
        png = os.path.join(out_root, label.replace(":", "_").replace("/", "_") + ".png")
        ok = False
        try:
            render_design_3d(tokens, png, verbose=False)
            ok = os.path.exists(png) and os.path.getsize(png) > 1000
        except Exception as e:
            print(f"  [{label}] render FAIL: {e}", flush=True)
        jr = judge.judge(png, brief=brief) if ok else None
        if jr is not None and jr.backend not in ("unknown", "error", "parse_unknown"):
            rows.append((label, np_, ns_, jr))
            print(f"  [{label:<34}] {np_}P/{ns_}S  q10={q10(jr):.2f}  "
                  f"pelvic={jr.pelvic_coverage} chest={jr.chest_coverage} "
                  f"anat={jr.anatomy_clean} aes={jr.aesthetic_score} "
                  f"brief={jr.brief_match}", flush=True)
        else:
            print(f"  [{label:<34}] {np_}P/{ns_}S  JUDGE UNKNOWN / RENDER FAIL",
                  flush=True)

    print("\n================ TEACHER COVERAGE SUMMARY ================")
    if rows:
        n = len(rows)
        mp = sum(r[3].pelvic_coverage for r in rows) / n
        mc = sum(r[3].chest_coverage for r in rows) / n
        ma = sum(r[3].anatomy_clean for r in rows) / n
        mq = sum(q10(r[3]) for r in rows) / n
        stroke_only = [r[0] for r in rows if r[1] == 0]
        low_pelvic = [r[0] for r in rows if r[3].pelvic_coverage <= 2]
        low_chest = [r[0] for r in rows if r[3].chest_coverage <= 2]
        print(f"  n={n}  mean pelvic={mp:.1f}  chest={mc:.1f}  "
              f"anatomy={ma:.1f}  q10={mq:.2f}")
        print(f"  stroke-only (0 panels): {len(stroke_only)} -> {stroke_only}")
        print(f"  low pelvic (<=2): {len(low_pelvic)} -> {low_pelvic}")
        print(f"  low chest  (<=2): {len(low_chest)} -> {low_chest}")
    else:
        print("  NO VALID ROWS")


if __name__ == "__main__":
    main()
