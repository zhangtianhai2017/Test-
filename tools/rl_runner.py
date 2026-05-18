"""Online RL training runner.

Bridges the option-D generator (continuous + discrete logits) to the
existing render pipeline + vision judge, and runs N iterations of
step_full from TrainLoop.

The key piece is `config_to_outfit`: it converts a single generator
output into a concrete Outfit object that outfit_to_genome + the
shell builder + render_mesh know how to handle.

Strategy for archetype-specific slots: rather than hand-wire every
slot, we ask random_outfit() to make a structurally-valid skeleton
for the chosen archetype, then OVERRIDE the slots the generator
controls (cup, bottom, fabric, plus colour/geometry in
global_design + local_params).  Anything the generator doesn't
emit (seam_type, accessories, etc.) keeps random_outfit's choices.
This avoids duplicating slot logic.

Usage:
    # mock judge (no Qwen needed) -- validates the loop:
    python3 tools/rl_runner.py --iters 4 --batch 4 --judge mock

    # real judge once vLLM is up on the 3090:
    python3 tools/rl_runner.py --iters 100 --batch 8 --judge vllm
"""
from __future__ import annotations

import argparse
import json
import os
import random as rd
import sys
import time

os.environ.setdefault("OPEN3D_CPU_RENDERING", "true")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch

import iter.capture as cap
cap.VIEWS = [v for v in cap.VIEWS if v.name == "01_front"]

from outfit import Outfit, SlotAssignment, random_outfit, outfit_to_genome
from iter.params import IterParams
from render3d_uv import load_body_mesh
import library as lib
import library_data as ld
from output_paths import dated_dir

from design_generator import DesignGenerator, MockTextEncoder
from vision_judge import make_judge
from train_loop import TrainLoop, DEFAULT_BRIEFS


# ---------------------------------------------------------------------------
# Index -> library_id maps (must match DesignGenerator's discrete head order)
# ---------------------------------------------------------------------------

def get_id_lists() -> dict[str, list]:
    return {
        "archetype": [
            "triangle_string_halter", "bandeau_back_band",
            "bralette_shoulder_strap", "one_piece_maillot"],
        "cup":       list(ld.CUP_PIECES.keys()),
        "bottom":    list(ld.BOTTOM_PIECES.keys()),
        "strap":     list(ld.STRAP_PIECES.keys()),
        "fabric":    list(ld.FABRICS.keys()),
        "accessory": list(ld.ACCESSORIES.keys()),
        "hardware":  list(ld.HARDWARE.keys()),
        "pattern":   ["solid", "stripe", "polka", "gingham", "chevron",
                       "floral", "tropical", "leopard", "tie_dye", "ombre",
                       "checker", "herringbone"],
        "weave":     ["plain", "ribbed", "crinkle", "shiny_knit", "velvet",
                       "mesh", "fishnet", "lace", "crochet", "foam", "sequined",
                       "seersucker", "slub", "terry", "neoprene", "jacquard"],
    }


# ---------------------------------------------------------------------------
# Bridge: generator output -> concrete Outfit
# ---------------------------------------------------------------------------

class ConfigToOutfit:
    """Converts a single generator output (one batch row) into an
    Outfit instance the existing pipeline understands."""

    def __init__(self, id_lists: dict[str, list]):
        self.ids = id_lists

    def _pick(self, head: str, picks: dict, i: int) -> str:
        idx = int(picks[head][i].item())
        idx = max(0, min(idx, len(self.ids[head]) - 1))
        return self.ids[head][idx]

    def __call__(self, config: dict, picks: dict, i: int) -> Outfit:
        archetype = self._pick("archetype", picks, i)

        # 1. Start with random_outfit for the chosen archetype -- gives us
        #    a structurally valid slot skeleton (straps, seam_type, etc.)
        seed_rng = rd.Random(int(picks["cup"][i].item()) * 7919
                                + int(picks["fabric"][i].item()))
        try:
            outfit = random_outfit(archetype, seed_rng)
        except Exception as exc:
            raise RuntimeError(f"random_outfit failed for {archetype}: {exc}")

        # 2. Override cup with generator's pick + continuous local_params
        cup_id = self._pick("cup", picks, i)
        cup_lp = {
            "center_v":      float(config["top_center_v"][i].item()),
            "half_u":        float(config["top_half_u"][i].item()),
            "half_v":        float(config["top_half_v"][i].item()),
            "inner_u":       float(config["top_inner_u"][i].item()),
            "apex_lift":     float(config["top_apex_lift"][i].item()),
            "underband_dip": float(config["top_underband_dip"][i].item()),
        }
        cup_entry = ld.LIBRARY.get(cup_id)
        for sa in outfit.slot_assignments:
            if sa.slot_name == "cup":
                # only use the cup_id if its tags work for the archetype's
                # cup slot; else leave random_outfit's choice
                spec = next((s for s in lib.ARCHETYPE_SLOTS[archetype]
                              if s.kind == "cup_piece"), None)
                if spec and cup_entry and spec.matches(cup_entry):
                    sa.library_id = cup_id
                # always override local_params (clamped to entry schema)
                if cup_entry is not None:
                    sa.local_params = cup_entry.clamp_local_params(cup_lp)
                break

        # 3. Override bottom_front
        bot_id = self._pick("bottom", picks, i)
        bot_lp = {
            "front_top_v":     float(config["bot_front_top_v"][i].item()),
            "front_half_u":    float(config["bot_front_half_u"][i].item()),
            "front_leg_curve": float(config["bot_front_leg_curve"][i].item()),
            "back_top_v":      float(config["bot_back_top_v"][i].item()),
            "back_half_u":     float(config["bot_back_half_u"][i].item()),
        }
        bot_entry = ld.LIBRARY.get(bot_id)
        for sa in outfit.slot_assignments:
            if sa.slot_name == "bottom_front":
                spec = next((s for s in lib.ARCHETYPE_SLOTS[archetype]
                              if s.kind == "bottom_piece"), None)
                if spec and bot_entry and spec.matches(bot_entry):
                    sa.library_id = bot_id
                if bot_entry is not None:
                    sa.local_params = bot_entry.clamp_local_params(bot_lp)
                break

        # 4. Override primary fabric
        fab_id = self._pick("fabric", picks, i)
        fab_entry = ld.LIBRARY.get(fab_id)
        for sa in outfit.slot_assignments:
            if sa.slot_name == "primary_fabric" and fab_entry is not None:
                sa.library_id = fab_id
                break

        # 5. Override global_design with generator's continuous values
        outfit.global_design["hue"]            = float(config["hue"][i].item())
        outfit.global_design["saturation"]     = float(config["saturation"][i].item())
        outfit.global_design["lightness"]      = float(config["lightness"][i].item())
        outfit.global_design["secondary_hue"]  = float(config["secondary_hue"][i].item())
        outfit.global_design["pattern_overlay"] = self._pick("pattern", picks, i)
        outfit.global_design["pattern_scale"]  = float(config["pattern_scale"][i].item())
        outfit.global_design["asym_amount"]    = float(config["asym_amount"][i].item())
        outfit.global_design["geom_ratio_pull"] = float(config["geom_ratio_pull"][i].item())

        return outfit


# ---------------------------------------------------------------------------
# Renderer wrapping
# ---------------------------------------------------------------------------

class RenderRunner:
    """Stateful callable used as render_fn in TrainLoop.step_full().
    Manages its own iteration counter so per-iter renders go to
    distinct subdirs."""

    def __init__(self, out_dir: str, id_lists: dict, body_mesh):
        self.out_dir = out_dir
        self.body = body_mesh
        self.iter = 0
        self.converter = ConfigToOutfit(id_lists)

    def __call__(self, config: dict, picks: dict) -> list[str]:
        B = next(iter(picks.values())).shape[0]
        iter_dir = os.path.join(self.out_dir, f"iter_{self.iter:04d}")
        os.makedirs(iter_dir, exist_ok=True)
        paths: list[str] = []
        for i in range(B):
            sub = os.path.join(iter_dir, f"v{i:02d}")
            os.makedirs(sub, exist_ok=True)
            try:
                outfit = self.converter(config, picks, i)
                g = outfit_to_genome(outfit)
                params = IterParams()
                params.outfit = outfit
                # save outfit json for traceability
                with open(os.path.join(sub, "outfit.json"), "w") as f:
                    json.dump({
                        "archetype": outfit.archetype,
                        "slot_assignments": [
                            {"slot_name": a.slot_name,
                             "library_id": a.library_id,
                             "local_params": dict(a.local_params)}
                            for a in outfit.slot_assignments],
                        "global_design": dict(outfit.global_design),
                    }, f, indent=2)
                cap.render_views(g, params, sub, body_mesh=self.body)
                paths.append(os.path.join(sub, "01_front.png"))
            except Exception as exc:
                print(f"  [iter {self.iter} v{i}] render fail: {exc}")
                paths.append("")  # empty -> judge will mark invalid
        self.iter += 1
        return paths


# ---------------------------------------------------------------------------
# Main RL run
# ---------------------------------------------------------------------------

def run(iters: int = 20,
         batch_size: int = 8,
         lr: float = 5e-4,
         w_sym: float = 1.0,
         w_rl: float = 0.05,           # scaled down per train_loop note
         judge_backend: str = "mock",
         hidden_dim: int = 256,
         text_dim: int = 384,
         seed: int = 20260518,
         resume_from: str | None = None,
         ) -> None:
    out_root = dated_dir("rl_run")
    print(f"OUT = {out_root}")
    print(f"iters={iters} batch={batch_size} judge={judge_backend} "
          f"w_sym={w_sym} w_rl={w_rl} lr={lr}")

    torch.manual_seed(seed)
    enc = MockTextEncoder(dim=text_dim)
    gen = DesignGenerator(text_dim=text_dim, hidden_dim=hidden_dim)
    if resume_from and os.path.isfile(resume_from):
        gen.load_state_dict(torch.load(resume_from)["generator_state"])
        print(f"resumed weights from {resume_from}")

    judge = make_judge(judge_backend)
    body = load_body_mesh()
    id_lists = get_id_lists()
    render_runner = RenderRunner(out_root, id_lists, body)

    loop = TrainLoop(gen, enc, judge=judge,
                      lr=lr, w_sym=w_sym, w_rl=w_rl,
                      run_dir=out_root)

    rng = rd.Random(seed)
    history = []
    t_total = time.time()
    for it in range(iters):
        briefs = rng.choices(DEFAULT_BRIEFS, k=batch_size)
        t0 = time.time()
        rec = loop.step_full(briefs, render_fn=render_runner)
        dt = time.time() - t0
        history.append(rec)
        n_pass = sum(1 for r in rec.judge_results if r.get("is_valid_swimsuit"))
        print(f"  iter {it:3d}  fitness={rec.mean_fitness:.3f}  "
              f"reward={rec.mean_reward:.3f}  "
              f"pass={n_pass}/{batch_size}  "
              f"loss_sym={rec.loss_sym:.3f} loss_rl={rec.loss_rl:.3f}  "
              f"{dt:.1f}s")

    # Save final checkpoint
    ckpt = os.path.join(out_root, "generator_final.pt")
    loop.save(ckpt)
    print(f"\nsaved final generator -> {ckpt}")

    # Summary
    total_pass = sum(sum(1 for r in rec.judge_results if r.get("is_valid_swimsuit"))
                      for rec in history)
    total_seen = iters * batch_size
    print(f"\n=== summary ===")
    print(f"iters={iters}  batch={batch_size}  total renders={total_seen}")
    print(f"J pass overall  : {total_pass}/{total_seen} "
          f"({100*total_pass/total_seen:.1f}%)")
    print(f"first-iter mean reward: {history[0].mean_reward:.3f}")
    print(f"last-iter  mean reward: {history[-1].mean_reward:.3f}")
    print(f"first-iter mean fitness: {history[0].mean_fitness:.3f}")
    print(f"last-iter  mean fitness: {history[-1].mean_fitness:.3f}")
    print(f"total wall time: {time.time()-t_total:.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=10)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--w-sym", type=float, default=1.0)
    ap.add_argument("--w-rl", type=float, default=0.05)
    ap.add_argument("--judge", choices=["mock", "vllm"], default="mock")
    ap.add_argument("--hidden-dim", type=int, default=256)
    ap.add_argument("--resume", default=None)
    args = ap.parse_args()
    run(iters=args.iters, batch_size=args.batch, lr=args.lr,
         w_sym=args.w_sym, w_rl=args.w_rl,
         judge_backend=args.judge, hidden_dim=args.hidden_dim,
         resume_from=args.resume)


if __name__ == "__main__":
    main()
