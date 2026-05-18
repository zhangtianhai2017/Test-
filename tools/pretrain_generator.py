"""Pretrain the DesignGenerator on historical batch outputs.

Step 5 of the option-D plan. Treats the ~700 outfit.json files
already in tools/output/ as a supervised corpus:

  for each historical outfit:
    brief    = synthesise_brief(outfit)        (text derived from
                                                outfit metadata)
    target   = (continuous params, discrete library_ids)
    loss     = MSE(continuous) + CrossEntropy(discrete logits)

After pretraining the generator starts the option-D online RL loop
from a "knows what an outfit looks like" point instead of from
random weights -- avoids the cold-start phase where every output is
random nonsense and J returns ~0 reward for every sample.

Output: tools/output/generator_pretrained.pt  (state_dict)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from design_generator import (DesignGenerator, MockTextEncoder,
                                CONTINUOUS_SPECS)
from symbolic_fitness import total_fitness as sym_fitness
import library_data as ld


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# ID -> index maps (one per discrete head)
# ---------------------------------------------------------------------------

def build_id_maps() -> dict[str, dict[str, int]]:
    """library_id -> integer index, one map per discrete-head."""
    return {
        "cup":       {k: i for i, k in enumerate(ld.CUP_PIECES.keys())},
        "bottom":    {k: i for i, k in enumerate(ld.BOTTOM_PIECES.keys())},
        "strap":     {k: i for i, k in enumerate(ld.STRAP_PIECES.keys())},
        "fabric":    {k: i for i, k in enumerate(ld.FABRICS.keys())},
        "accessory": {k: i for i, k in enumerate(ld.ACCESSORIES.keys())},
        "hardware":  {k: i for i, k in enumerate(ld.HARDWARE.keys())},
        "archetype": {a: i for i, a in enumerate([
            "triangle_string_halter", "bandeau_back_band",
            "bralette_shoulder_strap", "one_piece_maillot"])},
        "pattern":   {p: i for i, p in enumerate([
            "solid", "stripe", "polka", "gingham", "chevron",
            "floral", "tropical", "leopard", "tie_dye", "ombre",
            "checker", "herringbone"])},
        "weave":     {w: i for i, w in enumerate([
            "plain", "ribbed", "crinkle", "shiny_knit", "velvet",
            "mesh", "fishnet", "lace", "crochet", "foam", "sequined",
            "seersucker", "slub", "terry", "neoprene", "jacquard"])},
    }


# ---------------------------------------------------------------------------
# Brief synthesis: outfit metadata -> human-readable text
# ---------------------------------------------------------------------------

_HUE_NAMES = [
    (0.04, "red"), (0.08, "orange"), (0.14, "yellow-orange"),
    (0.18, "yellow"), (0.32, "green"), (0.45, "cyan"),
    (0.62, "blue"), (0.75, "purple"), (0.88, "magenta"),
    (0.96, "pink"), (1.01, "red"),
]


def hue_name(h: float) -> str:
    h = h % 1.0
    for upper, name in _HUE_NAMES:
        if h <= upper:
            return name
    return "neutral"


def light_label(l: float) -> str:
    if l < 0.35: return "deep"
    if l > 0.70: return "light"
    return "mid"


def sat_label(s: float) -> str:
    if s < 0.30: return "muted"
    if s > 0.75: return "vivid"
    return ""


def cup_family_label(cup_id: str | None) -> str:
    if not cup_id:
        return ""
    if "TRIANGLE" in cup_id or "BRAZILIAN" in cup_id: return "triangle"
    if "BANDEAU" in cup_id:    return "bandeau"
    if "BALCONETTE" in cup_id: return "balconette"
    if "FOAM" in cup_id:       return "molded foam cup"
    if "SOFTCUP" in cup_id:    return "soft cup"
    return ""


def synthesise_brief(outfit: dict) -> str:
    """Build a one-line English brief from outfit metadata."""
    arch = outfit.get("archetype", "").replace("_", " ")
    gd = outfit.get("global_design", {}) or {}
    h = float(gd.get("hue", 0.5))
    s = float(gd.get("saturation", 0.5))
    l = float(gd.get("lightness", 0.5))
    pattern = gd.get("pattern_overlay", gd.get("pattern", "solid"))
    cup_id = next((a["library_id"] for a in outfit.get("slot_assignments", [])
                   if a.get("slot_name") == "cup"), None)
    parts = [
        light_label(l),
        sat_label(s),
        hue_name(h),
        pattern if pattern != "solid" else "",
        cup_family_label(cup_id),
        arch,
    ]
    return " ".join(p for p in parts if p).strip()


# ---------------------------------------------------------------------------
# Outfit -> training target tensors
# ---------------------------------------------------------------------------

# Continuous param mapping:  generator output name -> (where to find
# it in outfit dict, default if missing)
CONT_EXTRACTORS: list[tuple[str, str, str, float]] = [
    # (gen_name, source_dict, source_key, default)
    ("hue",                "global_design",   "hue",           0.5),
    ("saturation",         "global_design",   "saturation",    0.5),
    ("lightness",          "global_design",   "lightness",     0.5),
    ("secondary_hue",      "global_design",   "secondary_hue", 0.5),
    ("pattern_scale",      "global_design",   "pattern_scale", 0.5),
    ("asym_amount",        "global_design",   "asym_amount",   0.0),
    ("geom_ratio_pull",    "global_design",   "geom_ratio_pull", 0.0),
    ("top_center_v",       "cup_lp",          "center_v",      0.74),
    ("top_half_u",         "cup_lp",          "half_u",        0.16),
    ("top_half_v",         "cup_lp",          "half_v",        0.07),
    ("top_inner_u",        "cup_lp",          "inner_u",       0.10),
    ("top_apex_lift",      "cup_lp",          "apex_lift",     0.15),
    ("top_underband_dip",  "cup_lp",          "underband_dip", 0.05),
    ("bot_front_top_v",    "bot_lp",          "front_top_v",   0.30),
    ("bot_front_half_u",   "bot_lp",          "front_half_u",  0.30),
    ("bot_front_leg_curve","bot_lp",          "front_leg_curve", 0.50),
    ("bot_back_top_v",     "bot_lp",          "back_top_v",    0.30),
    ("bot_back_half_u",    "bot_lp",          "back_half_u",   0.20),
]


def extract_targets(outfit: dict, id_maps: dict
                     ) -> tuple[dict[str, float], dict[str, int]] | None:
    """Pull continuous + discrete targets out of one outfit.json dict.
    Returns None when essential fields are missing (skip this sample)."""
    arch = outfit.get("archetype")
    if not arch or arch not in id_maps["archetype"]:
        return None

    # Per-slot local_params
    cup_lp = {}
    bot_lp = {}
    cup_id = None
    bot_id = None
    fab_id = None
    strap_id = None
    accessory_id = None
    hardware_id = None
    for a in outfit.get("slot_assignments", []):
        slot = a.get("slot_name", "")
        lp = a.get("local_params", {}) or {}
        lib_id = a.get("library_id")
        if slot == "cup":
            cup_lp = lp; cup_id = lib_id
        elif slot.startswith("bottom"):
            bot_lp = lp; bot_id = lib_id
        elif slot == "primary_fabric":
            fab_id = lib_id
        elif "strap" in slot or "halter" in slot or "tie" in slot:
            strap_id = lib_id
        elif slot == "accessory":
            accessory_id = lib_id
        elif slot.startswith("hardware") or slot in ("oring", "slider"):
            hardware_id = lib_id

    sources = {
        "global_design": outfit.get("global_design", {}) or {},
        "cup_lp": cup_lp,
        "bot_lp": bot_lp,
    }

    cont = {}
    for gen_name, src_dict, src_key, default in CONT_EXTRACTORS:
        v = sources[src_dict].get(src_key, default)
        try:
            cont[gen_name] = float(v)
        except (TypeError, ValueError):
            cont[gen_name] = float(default)

    # Discrete -- only include if we can resolve the id, else skip head
    disc: dict[str, int] = {"archetype": id_maps["archetype"][arch]}
    for head_name, lib_id in [("cup", cup_id), ("bottom", bot_id),
                                ("strap", strap_id), ("fabric", fab_id),
                                ("accessory", accessory_id),
                                ("hardware", hardware_id)]:
        if lib_id and lib_id in id_maps[head_name]:
            disc[head_name] = id_maps[head_name][lib_id]

    pattern = sources["global_design"].get("pattern_overlay",
              sources["global_design"].get("pattern", "solid"))
    if pattern in id_maps["pattern"]:
        disc["pattern"] = id_maps["pattern"][pattern]

    return cont, disc


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

@dataclass
class TrainExample:
    brief: str
    cont:  dict[str, float]
    disc:  dict[str, int]


def collect_examples(output_glob: str | None = None) -> list[TrainExample]:
    """Walk tools/output/**/outfit.json, extract examples."""
    paths: list[str] = []
    if output_glob:
        paths = sorted(glob.glob(output_glob, recursive=True))
    else:
        # default: every outfit.json under tools/output/
        paths = sorted(glob.glob(
            os.path.join(ROOT, "tools", "output", "**", "outfit.json"),
            recursive=True))
    id_maps = build_id_maps()
    out: list[TrainExample] = []
    for p in paths:
        try:
            with open(p) as f:
                o = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        targets = extract_targets(o, id_maps)
        if targets is None:
            continue
        cont, disc = targets
        out.append(TrainExample(
            brief=synthesise_brief(o), cont=cont, disc=disc))
    return out


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def collate_batch(examples: list[TrainExample], device: str = "cpu"
                   ) -> tuple[list[str], dict[str, torch.Tensor],
                                dict[str, tuple[torch.Tensor, torch.Tensor]]]:
    """Returns:
      briefs    : list[str]
      cont_targets : dict gen_name -> (B,) tensor
      disc_targets : dict head_name -> ((B,) long tensor of indices,
                                          (B,) bool mask of present)
    """
    briefs = [e.brief for e in examples]
    B = len(examples)

    cont_targets: dict[str, torch.Tensor] = {}
    for spec in CONTINUOUS_SPECS:
        name, lo, hi = spec
        vals = torch.tensor(
            [e.cont.get(name, (lo + hi) / 2) for e in examples],
            dtype=torch.float32, device=device)
        # clamp to valid generator output range so MSE doesn't explode
        cont_targets[name] = vals.clamp(min=lo, max=hi)

    id_maps = build_id_maps()
    disc_targets: dict[str, tuple[torch.Tensor, torch.Tensor]] = {}
    for head, _ in id_maps.items():
        idx = []
        mask = []
        for e in examples:
            if head in e.disc:
                idx.append(e.disc[head]); mask.append(True)
            else:
                idx.append(0); mask.append(False)
        disc_targets[head] = (
            torch.tensor(idx, dtype=torch.long, device=device),
            torch.tensor(mask, dtype=torch.bool, device=device),
        )
    return briefs, cont_targets, disc_targets


def pretrain(epochs: int = 50,
              batch_size: int = 32,
              lr: float = 2e-3,
              w_continuous: float = 1.0,
              w_discrete: float = 0.5,
              hidden_dim: int = 256,
              text_dim: int = 384,
              seed: int = 0,
              save_path: str | None = None,
              ) -> tuple[DesignGenerator, dict]:
    torch.manual_seed(seed)

    examples = collect_examples()
    print(f"loaded {len(examples)} training examples")
    if not examples:
        raise SystemExit("no examples found; run a batch first")
    archetype_dist = Counter(e.disc.get("archetype", -1) for e in examples)
    print(f"archetype distribution (idx -> count): {dict(archetype_dist)}")

    enc = MockTextEncoder(dim=text_dim)
    gen = DesignGenerator(text_dim=text_dim, hidden_dim=hidden_dim)
    opt = AdamW(gen.parameters(), lr=lr)

    # Pre-encode all briefs once (mock encoder is deterministic + fast)
    all_briefs = [e.brief for e in examples]
    print(f"sample briefs: {all_briefs[:3]}")
    all_emb = enc.encode(all_briefs)

    metrics_history = []
    rng = random.Random(seed)
    n_batches = max(1, len(examples) // batch_size)
    for epoch in range(epochs):
        rng.shuffle(examples)
        epoch_losses = {"cont": 0.0, "disc": 0.0, "total": 0.0}
        t0 = time.time()
        for b in range(n_batches):
            batch = examples[b * batch_size:(b + 1) * batch_size]
            if not batch:
                continue
            briefs, cont_targets, disc_targets = collate_batch(batch)
            emb = enc.encode(briefs)
            config = gen(emb)

            # Continuous loss: MSE
            loss_c = torch.tensor(0.0)
            for name, target in cont_targets.items():
                pred = config[name]
                loss_c = loss_c + F.mse_loss(pred, target)
            loss_c = loss_c / len(cont_targets)

            # Discrete loss: cross-entropy, masked
            loss_d = torch.tensor(0.0)
            n_disc_terms = 0
            for head, (idx, mask) in disc_targets.items():
                if not mask.any():
                    continue
                logits = config[f"{head}_logits"]
                loss_d = loss_d + F.cross_entropy(
                    logits[mask], idx[mask])
                n_disc_terms += 1
            loss_d = loss_d / max(n_disc_terms, 1)

            loss = w_continuous * loss_c + w_discrete * loss_d
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(gen.parameters(), max_norm=1.0)
            opt.step()

            epoch_losses["cont"] += loss_c.item()
            epoch_losses["disc"] += loss_d.item()
            epoch_losses["total"] += loss.item()

        for k in epoch_losses:
            epoch_losses[k] /= n_batches
        epoch_losses["epoch"] = epoch
        epoch_losses["dt_s"] = time.time() - t0
        metrics_history.append(epoch_losses)
        if epoch % 5 == 0 or epoch == epochs - 1:
            print(f"  epoch {epoch:3d}  "
                  f"loss={epoch_losses['total']:.4f}  "
                  f"cont_mse={epoch_losses['cont']:.4f}  "
                  f"disc_ce={epoch_losses['disc']:.4f}  "
                  f"({epoch_losses['dt_s']:.1f}s)")

    # Save
    if save_path is None:
        save_path = os.path.join(ROOT, "tools", "output",
                                   "generator_pretrained.pt")
    torch.save({
        "generator_state": gen.state_dict(),
        "text_dim": text_dim,
        "hidden_dim": hidden_dim,
        "discrete_sizes": gen.discrete_sizes,
        "metrics_history": metrics_history,
    }, save_path)
    print(f"\nsaved pretrained generator -> {save_path}")

    return gen, {"history": metrics_history, "n_examples": len(examples)}


# ---------------------------------------------------------------------------
# Validation: generate fresh briefs, score with symbolic_fitness
# ---------------------------------------------------------------------------

def validate(gen: DesignGenerator,
              enc: MockTextEncoder,
              briefs: list[str] | None = None) -> dict:
    if briefs is None:
        briefs = [
            "elegant balconette, deep navy, vintage feel",
            "vivid pink triangle bikini, beach holiday",
            "boho crochet cream, asymmetric halter",
            "sport racerback, deep emerald, full coverage",
            "minimalist matte black one-piece, deep V",
            "tropical floral cheeky, bright orange",
            "sequin metallic gold bandeau, evening",
            "fishnet overlay over solid black, edgy",
        ]
    enc_local = enc
    emb = enc_local.encode(briefs)
    with torch.no_grad():
        config = gen(emb)
    fit = sym_fitness(config)
    return {
        "briefs": briefs,
        "fitness_per_brief": fit["total"].numpy().tolist(),
        "mean_fitness": fit["total"].mean().item(),
        "config_sample": {
            k: v[0].item() if v.ndim == 1 else v[0].argmax().item()
            for k, v in config.items()
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--hidden-dim", type=int, default=256)
    ap.add_argument("--save", default=None)
    args = ap.parse_args()

    gen, info = pretrain(epochs=args.epochs,
                          batch_size=args.batch_size,
                          lr=args.lr,
                          hidden_dim=args.hidden_dim,
                          save_path=args.save)

    # Compare pre- vs post-train fitness
    print("\n=== validation (random vs pretrained) ===")
    enc = MockTextEncoder(dim=384)
    random_gen = DesignGenerator(text_dim=384, hidden_dim=args.hidden_dim)
    random_val = validate(random_gen, enc)
    trained_val = validate(gen, enc)
    print(f"random init  mean fitness: {random_val['mean_fitness']:.3f}")
    print(f"pretrained   mean fitness: {trained_val['mean_fitness']:.3f}")
    print(f"improvement              : {trained_val['mean_fitness'] - random_val['mean_fitness']:+.3f}")
    print(f"\nper-brief (pretrained):")
    for b, s in zip(trained_val["briefs"], trained_val["fitness_per_brief"]):
        print(f"  {s:.3f}  {b}")


if __name__ == "__main__":
    main()
