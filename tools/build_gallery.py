"""
Generate a bigger gallery of synthetic seeds covering all 4 v1
archetypes (triangle_string_halter / bandeau_back_band /
bralette_shoulder_strap / one_piece_maillot), then render every one
through the post-cutover garment pipeline and report fitness.

Output:
    assets/seeds/gallery_<archetype>_<i>.json   — 12 new seeds
    tools/output/gallery_renders/<seed>/        — 8 view PNGs each
    tools/output/gallery_overview.png           — big contact sheet
    tools/output/gallery_report.md              — fitness table
"""
from __future__ import annotations

import argparse, json, os, sys, math
from dataclasses import asdict, replace

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verify_ga_uv import Genome, _enforce_constraints
from garment_state import (genome_to_garment, validate_garment,
                              UnsupportedArchetypeV1)


SEEDS_DIR = "assets/seeds"
RENDER_DIR = "tools/output/gallery_renders"


# Base templates for each archetype. Each template is a dict of Genome
# field overrides on top of a default genome. We deliberately push
# specific Genome fields to ensure dispatch lands on the chosen
# archetype: top_back_coverage / top_shoulder_strap / top_neck_strap.
def _default_genome_dict() -> dict:
    return {
        "pattern": "solid",
        "top_center_v": 0.74, "top_half_v": 0.10, "top_half_u": 0.16,
        "top_inner_u": 0.10, "top_apex_lift": 0.15, "top_underband_dip": 0.05,
        "top_back_coverage": 0.10, "top_neck_strap": 0.0,
        "top_shoulder_strap": 0.0,
        "bot_front_top_v": 0.25, "bot_front_half_u": 0.18,
        "bot_front_leg_curve": 0.65, "bot_back_top_v": 0.25,
        "bot_back_half_u": 0.12, "bot_tie_dangle": 0.20,
        "hue": 0.5, "saturation": 0.6, "lightness": 0.5,
        "secondary_hue": 0.5, "secondary_saturation": 0.4,
        "secondary_lightness": 0.4,
        "pattern_scale": 0.5, "pattern_angle": 0.0, "trim_color_mode": 0.3,
        "fabric_sheen": 0.4, "fabric_metallic": 0.0, "fabric_opacity": 1.0,
        "fabric_weight": 0.5, "fabric_weave": "plain",
        "palette_preset": "free", "fabric_source": "econyl",
        "biodegradable": 0.0, "single_material": 1.0,
        "has_oring": 0.0, "oring_size": 0.4, "has_bow": 0.0, "bow_size": 0.3,
        "has_fringe": 0.0, "fringe_length": 0.2,
        "has_beads": 0.0, "has_shell": 0.0,
        "style_archetype": "free", "hardware_metal": "none",
    }


GALLERY = [
    # ---- triangle_string_halter (top_neck_strap > 0.4 AND top_inner_u > 0.05) ----
    ("gallery_triangle_aquamarine", {
        "top_neck_strap": 0.85, "top_inner_u": 0.10, "top_back_coverage": 0.05,
        "bot_back_half_u": 0.07, "bot_tie_dangle": 0.55,
        "hue": 0.50, "saturation": 0.75, "lightness": 0.55,
        "fabric_source": "econyl",
        "style_archetype": "brazilian", "pattern": "solid",
    }),
    ("gallery_triangle_floral_pink", {
        "top_neck_strap": 0.75, "top_inner_u": 0.12, "top_back_coverage": 0.06,
        "bot_back_half_u": 0.10, "bot_tie_dangle": 0.40,
        "pattern": "floral", "pattern_scale": 0.7,
        "hue": 0.95, "saturation": 0.55, "lightness": 0.78,
        "secondary_hue": 0.30, "secondary_saturation": 0.6,
        "fabric_source": "biopolymer", "biodegradable": 1.0,
        "style_archetype": "boho_cultgaia",
    }),
    ("gallery_triangle_chevron_yellow", {
        "top_neck_strap": 0.80, "top_inner_u": 0.08, "top_back_coverage": 0.04,
        "bot_back_half_u": 0.06, "bot_tie_dangle": 0.30,
        "pattern": "chevron", "pattern_scale": 0.55,
        "hue": 0.13, "saturation": 0.85, "lightness": 0.62,
        "secondary_hue": 0.0, "secondary_saturation": 0.7,
        "secondary_lightness": 0.45,
        "fabric_source": "qnova",
        "style_archetype": "retro_missoni",
        "has_oring": 1.0, "oring_size": 0.50, "hardware_metal": "gold",
    }),

    # ---- bandeau_back_band (no halter, no shoulder, top_inner_u ~ 0) ----
    ("gallery_bandeau_navy_solid", {
        "top_neck_strap": 0.0, "top_shoulder_strap": 0.0, "top_inner_u": 0.0,
        "top_half_u": 0.22, "top_half_v": 0.09, "top_back_coverage": 0.55,
        "bot_back_half_u": 0.16,
        "hue": 0.62, "saturation": 0.75, "lightness": 0.30,
        "fabric_weight": 0.65, "fabric_sheen": 0.50,
        "style_archetype": "scandi_minimal",
    }),
    ("gallery_bandeau_velvet_burgundy", {
        "top_neck_strap": 0.0, "top_shoulder_strap": 0.0, "top_inner_u": 0.0,
        "top_half_u": 0.20, "top_half_v": 0.11, "top_back_coverage": 0.65,
        "bot_back_half_u": 0.15,
        "fabric_weave": "velvet", "fabric_sheen": 0.75,
        "fabric_weight": 0.75,
        "hue": 0.97, "saturation": 0.6, "lightness": 0.22,
        "style_archetype": "italian_luxe",
        "has_bow": 1.0, "bow_size": 0.5,
    }),
    ("gallery_bandeau_crinkle_aqua", {
        "top_neck_strap": 0.0, "top_shoulder_strap": 0.0, "top_inner_u": 0.0,
        "top_half_u": 0.21, "top_half_v": 0.10, "top_back_coverage": 0.60,
        "bot_back_half_u": 0.13,
        "fabric_weave": "crinkle",
        "hue": 0.46, "saturation": 0.58, "lightness": 0.62,
        "fabric_source": "qnova",
        "style_archetype": "hunzag_crinkle",
    }),

    # ---- bralette_shoulder_strap (top_shoulder_strap > 0.5) ----
    ("gallery_bralette_sport_white", {
        "top_shoulder_strap": 0.85, "top_neck_strap": 0.0,
        "top_half_u": 0.20, "top_half_v": 0.11,
        "top_back_coverage": 0.45,
        "fabric_weight": 0.65,
        "hue": 0.58, "saturation": 0.05, "lightness": 0.95,
        "secondary_hue": 0.62, "secondary_saturation": 0.85,
        "secondary_lightness": 0.40,
        "style_archetype": "american_sporty",
        "pattern": "stripe", "pattern_scale": 0.4, "trim_color_mode": 0.85,
    }),
    ("gallery_bralette_chromat_red", {
        "top_shoulder_strap": 0.95, "top_neck_strap": 0.0,
        "top_half_u": 0.18, "top_half_v": 0.10,
        "top_back_coverage": 0.50, "top_apex_lift": 0.0,
        "fabric_weight": 0.55,
        "hue": 0.99, "saturation": 0.85, "lightness": 0.45,
        "fabric_source": "econyl",
        "style_archetype": "sporty_chromat",
        "has_oring": 1.0, "oring_size": 0.65, "hardware_metal": "silver",
    }),
    ("gallery_bralette_softcup_lavender", {
        "top_shoulder_strap": 0.65, "top_neck_strap": 0.0,
        "top_half_u": 0.21, "top_half_v": 0.12,
        "top_back_coverage": 0.40,
        "hue": 0.78, "saturation": 0.35, "lightness": 0.78,
        "fabric_weight": 0.45,
        "fabric_weave": "ribbed",
        "style_archetype": "korean_feminine",
        "has_bow": 1.0, "bow_size": 0.3,
    }),

    # ---- one_piece_maillot (top_back_coverage > 0.7 AND
    #      bot_front_top_v near cup_bottom) ----
    ("gallery_onepiece_classic_black", {
        "top_back_coverage": 0.95, "top_shoulder_strap": 0.85,
        "top_neck_strap": 0.0,
        "top_half_u": 0.22, "top_half_v": 0.16,
        "bot_front_top_v": 0.62, "bot_front_half_u": 0.21,
        "bot_back_half_u": 0.18, "bot_back_top_v": 0.45,
        "top_underband_dip": -0.05,
        "hue": 0.0, "saturation": 0.05, "lightness": 0.10,
        "fabric_weight": 0.55,
        "style_archetype": "scandi_minimal",
    }),
    ("gallery_onepiece_floral_emerald", {
        "top_back_coverage": 1.0, "top_shoulder_strap": 1.0,
        "top_neck_strap": 0.0,
        "top_half_u": 0.20, "top_half_v": 0.18,
        "top_inner_u": 0.05,
        "bot_front_top_v": 0.62, "bot_front_half_u": 0.20,
        "bot_back_half_u": 0.18, "bot_back_top_v": 0.45,
        "top_underband_dip": -0.08,
        "pattern": "floral", "pattern_scale": 0.85,
        "hue": 0.32, "saturation": 0.05, "lightness": 0.95,
        "secondary_hue": 0.32, "secondary_saturation": 0.65,
        "secondary_lightness": 0.30,
        "fabric_source": "biopolymer", "biodegradable": 1.0,
        "style_archetype": "boho_cultgaia",
    }),
    ("gallery_onepiece_halter_terracotta", {
        "top_back_coverage": 0.85, "top_shoulder_strap": 0.0,
        "top_neck_strap": 0.85,
        "top_inner_u": 0.10, "top_half_u": 0.18, "top_half_v": 0.14,
        "bot_front_top_v": 0.58, "bot_front_half_u": 0.20,
        "bot_back_half_u": 0.16, "bot_back_top_v": 0.50,
        "hue": 0.05, "saturation": 0.55, "lightness": 0.55,
        "fabric_weave": "ribbed",
        "fabric_source": "amni_soul", "biodegradable": 1.0,
        "style_archetype": "spanish_mediterranean",
    }),
]


def _build_genome(overrides: dict) -> Genome:
    d = _default_genome_dict()
    d.update(overrides)
    g = Genome(**d).clipped()
    return _enforce_constraints(g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-seeds", action="store_true",
                    help="write JSON seed files for the gallery")
    ap.add_argument("--render", action="store_true",
                    help="run the 8-view render for each seed")
    ap.add_argument("--report-only", action="store_true",
                    help="just dump fitness + dispatch results, no I/O")
    args = ap.parse_args()

    rows = []
    for name, ov in GALLERY:
        g = _build_genome(ov)
        try:
            garm = validate_garment(genome_to_garment(g))
            archetype = garm.archetype
            n_pieces = len(garm.pieces)
            n_conn = len(garm.connectors)
            n_acc = len(garm.accessories)
            n_warn = len(garm.metadata.get("validation_warnings", []))
        except UnsupportedArchetypeV1 as e:
            archetype = f"raised: {e}"
            n_pieces = n_conn = n_acc = n_warn = -1

        import fitness as fitness_mod
        fit = fitness_mod.evaluate(g)
        rows.append({
            "name": name, "archetype": archetype,
            "pieces": n_pieces, "connectors": n_conn,
            "accessories": n_acc, "warnings": n_warn,
            "overall": round(fit["overall"], 3),
            "with_garment": round(fit["overall_with_garment"], 3),
            "manuf": round(fit["manufacturability"], 2),
            "sust": round(fit["sustainability"], 2),
            "sku_consist": round(fit["sku_consistency"], 2),
            "simpl": round(fit["construction_simplicity"], 2),
            "genome": asdict(g) if args.write_seeds else None,
        })

    print(f"{'name':38s} {'archetype':24s} {'pieces':>6s} {'conn':>4s} "
          f"{'acc':>3s} {'warn':>4s} {'overall':>8s} {'+garm':>6s}")
    for r in rows:
        print(f"{r['name']:38s} {r['archetype']:24s} {r['pieces']:>6} "
              f"{r['connectors']:>4} {r['accessories']:>3} {r['warnings']:>4} "
              f"{r['overall']:>8} {r['with_garment']:>6}")

    if args.write_seeds:
        os.makedirs(SEEDS_DIR, exist_ok=True)
        for r in rows:
            path = os.path.join(SEEDS_DIR, f"{r['name']}.json")
            seed = {
                "meta": {
                    "name": r["name"],
                    "source_views": {},
                    "analysis_notes": (
                        f"Synthetic gallery seed. archetype={r['archetype']}, "
                        f"pieces={r['pieces']}, connectors={r['connectors']}, "
                        f"accessories={r['accessories']}."),
                    "confidence": {"shape": 1.0, "color": 1.0, "pattern": 1.0,
                                     "fabric": 0.8, "hardware": 0.8,
                                     "style_archetype": 1.0},
                },
                "genome": r["genome"],
            }
            with open(path, "w") as f:
                json.dump(seed, f, indent=2)
        print(f"\nwrote {len(rows)} seeds to {SEEDS_DIR}/")

    return rows


if __name__ == "__main__":
    main()
