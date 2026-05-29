# Status Handover — v3 / v3.1 Schema Redesign Full Session

**Date:** 2026-05-28
**Branch:** `claude/add-diverse-seeds-handover-sBSs3`
**Commits added (this session):** 24
**Final state:** v3.1 schema fully closed-loop, Phase A3 RL running on vLLM (running in background, ETA ~30 min from `f731b084`)

---

## TL;DR

The v3 schema redesign went through **two phases**:

1. **v3 (10h autonomous, 2026-05-27)** — built tag-pool, Panel/Stroke schema, NN architecture, Phase A1+A2 imitation. **Got non-trivial color/topology transfer on unseen briefs but produced TUBE-LIKE outputs, not real fabric.**

2. **v3.1 (this session, 2026-05-28)** — caught the architectural drift: v3 had bypassed v2's entire fabric-engineering chain (`validate_garment → build_fabric_shell → polish_shell → wrinkles → binding`). Pivoted to add **Panel** as a second token type that flows through v2's full chain → **real 3D fabric meshes**.

By session end:
- 9 → 12 → 52 hand-crafted + library-derived teachers
- Length head (single dense per-design signal) solved is_end termination 12/12
- Differentiable manufacturability LOSS proven to make things WORSE
- REINFORCE on validate_garment → **0 manufacturability violations**
- vLLM judge re-arrived → full Phase A3 RL (manuf + visual) running

---

## Commit chain (24 in order)

### Phase 1: v3 foundation (commits 1-9, ~10h autonomous on 2026-05-27)
Already covered in `docs/handover/2026-05-28_STATUS_10h_autonomous.md`. Summary:

| # | Commit | Content |
|---|---|---|
| 1 | `bbf5b325` | v3 schema foundation: tag pool + stroke schema |
| 2 | `e7d5357c` | v3 generator + renderer: encoder/decoder + stroke→PNG bridge |
| 3 | `011d2529` | v3 end-to-end smoke: brief → strokes → UV sketch (8/8 OK) |
| 4 | `8b1efdcc` | v3 Phase A1+A2 smoke training (both pass) |
| 5 | `592c1569` | v3 named 256-color palette + renderer integration |
| 6 | `0a6fafcf` | v3 audit: trained-vs-random comparison on 8 UNSEEN briefs |
| 7 | `b45be405` | STATUS: 10h autonomous v3 build (handover doc) |
| 8 | `dbfe82c8` | Phase A2 expanded: 7 diverse teachers, strong semantic transfer |
| 9 | `d5da098b` | STATUS: update with diverse-teacher Phase A2 result |

### Phase 2: v3 cleanup (10-12, between 10h autonomous and pivot)

| # | Commit | Content |
|---|---|---|
| 10 | `9998d528` | generate_batch: add --n-trunk-layers flag for v2 deeper-trunk ckpts |
| 11 | `396bc272` | v3 3D renderer FIXED + stroke width visibility tune (Open3D scene-clear pattern) |
| 12 | `9ecaa0e8` | Phase A2 long GPU run + 3D demo grid (vLLM freed) |

### Phase 3: v3.1 PIVOT — Panel + v2 chain (13-15)

User identified critical drift: v3 outputs looked like tubes/sketches, not clothing. The v2 engineering chain was being bypassed.

| # | Commit | Content |
|---|---|---|
| 13 | `e06c057c` | **v3.1 PIVOT**: Panel data + v2-chain bridge → real fabric rendering |
| 14 | `0b1fc3b1` | v3.1 reference designs (Panel+Stroke) → REAL FABRIC RENDERS |
| 15 | `a78c0193` | v3.1 references: drop conservative, add 4 stylized (diversity audit fix) |

**Key files added in v3.1 pivot:**
- `tools/v3/stroke_schema.py`: added `Panel` dataclass + serialization
- `tools/v3/tokens_to_garment.py`: **THE KEY BRIDGE** — converts list[Token] → v2 Garment object
- `tools/v3/full_chain_render.py`: tokens → validate_garment → build_fabric_shell → polish_shell → wrinkles → binding → PNG
- 9 v3.1 reference designs (later 12) using Panel for fabric panels + Stroke for straps/harness/chains

### Phase 4: v3.1 NN end-to-end (16-18)

| # | Commit | Content |
|---|---|---|
| 16 | `ecafa608` | v3.1 NN end-to-end: Panel+Stroke output → real 3D fabric (FINAL) |
| 17 | `8bdb0f92` | v3.1 wider palette: 3 color-gap teachers (silver/turquoise/iridescent) |
| 18 | `85d59d53` | v3.1 length_head: solves multi-token termination (12/12 perfect) |

**Key file added:** `tools/v3/token_tensor.py` (replaces stroke_tensor.py, TOKEN_TENSOR_DIM = 709 supporting both Panel + Stroke with type discriminator).

**length_head architecture:** instead of trying to learn per-position is_end (sparse), output the WHOLE design's token count from encoder side. Hard-truncates decode at predicted length. Solved 12/12 perfectly.

### Phase 5: Manufacturability — differentiable FAILS, REINFORCE WORKS (19-20)

| # | Commit | Content |
|---|---|---|
| 19 | `353496b1` | manuf loss experiment: differentiable H1+H2 DOESN'T WORK (kept for record) |
| 20 | `b18e870c` | Phase A3-manuf REINFORCE: all H1/H2 violations → 0 (no vLLM needed) |

**Negative result documented:** Differentiable manufacturability proxies are surprisingly tricky. H1 area-penalty alone made H2 self-intersections WORSE (8→20 on 24 random briefs). Mechanism: H1 grad pushes vertices outward → easy area gain = one extruded vertex → self-intersection. The convexity ratio (perim²/area) is the wrong signal.

**REINFORCE works:** Same constraint as a non-differentiable reward (validate_garment violation count), via stochastic categorical sampling + Gaussian noise on boundary. 200 iter → H1=0, H2=0, drop_rate=0 (from 24% baseline).

**Key file added:** `tools/v3/phase_a3_manuf_rl.py` — proper REINFORCE infrastructure with running-mean baseline.

### Phase 6: Data scale-up via v2 library (21)

| # | Commit | Content |
|---|---|---|
| 21 | `b338f659` | v2 library → v3 teachers: 12 → 52 teachers, multi-piece outputs unlocked |

**Key file added:** `tools/v3/v2_lib_to_teachers.py` — calls v2's polygon recipes (cup_triangle / cup_balconette / cup_bandeau / cup_sweetheart / cup_wrap / cup_corset_bands × bottom_thong / bottom_brief × 3 size variants), converts to v3 Panel. Plus 8 strap patterns → v3 Strokes.

Result: 12 hand-crafted + 40 v2-converted = 52 teachers (156 brief pairs). NN now produces MULTI-PIECE designs (4-6 panels) for bikini-style briefs, not just single-panel monokinis.

### Phase 7: Phase A3 FULL RL with vLLM (22-24)

vLLM came back online (22GB VRAM, HTTP 200, 1.14s round-trip).

| # | Commit | Content |
|---|---|---|
| 22 | `f731b084` | Phase A3 FULL RL: vLLM Qwen judge + manuf REINFORCE (pipeline working) |
| 23 | `3695a950` | audit: vLLM-judged pre-vs-post RL comparison (8 fresh briefs) |
| 24 | (in flight) | 30-iter Phase A3 full RL training (background) |

**Key file added:** `tools/v3/phase_a3_full_rl.py` — combines manuf REINFORCE (already worked) + visual judge REINFORCE in single loop. Same reward channel, additive: `total_reward = manuf + α × judge`. 5-iter smoke verified pipeline. 30-iter real training running.

---

## Architectural shifts in this session

### Shift 1: Panel as second output token type (v3 → v3.1)

**Before (v3):**
```
NN output → list[Stroke]
Stroke = 1D bezier path + width
Renderer = _arc_tube (sweep cylinder along path)
→ thin tube ribbons "drawn" on body
```

**After (v3.1):**
```
NN output → list[Token where Token = Panel | Stroke]
Panel = closed UV polygon (6 boundary points + anchors + fabric_id + color)
Stroke = 1D bezier path (unchanged)
Renderer = tokens_to_garment → v2 Garment → build_fabric_shell → polish_shell → wrinkles
→ REAL FABRIC PANELS on body, with seams + binding + wrinkles
```

### Shift 2: length_head for termination (replaces autoregressive is_end)

**Before:**
- Per-position binary is_end signal
- 1 positive vs N negatives per design → too sparse
- pos_weight=20x didn't help; multi-token designs always overshoot to 16

**After:**
- Single per-design length prediction from encoder
- Cross-entropy on the count (1..16)
- Decode hard-truncates at predicted length
- 12/12 perfect termination

### Shift 3: REINFORCE for manuf (replaces differentiable proxy)

**Before:**
- H1 (area > 8 cm²) shoelace area MSE loss + H2 (perim²/area) proxy
- H1 alone makes H2 worse 2.5× because vertices get extruded

**After:**
- Sample stochastically (categorical for type/color/fabric/anchors, Gaussian for boundary)
- Compute reward = -(n_dropped + 0.5 × n_warnings) via validate_garment
- REINFORCE with running baseline
- 200 iter → 0 violations on 24 briefs

### Shift 4: Same RL channel for vLLM judge

REINFORCE infrastructure is reward-source-agnostic. Same code that handles validate_garment also handles vLLM judge — just add another term to the reward. Phase A3 full RL = manuf REINFORCE + judge REINFORCE, single loss.

---

## What each ckpt is

| ckpt | What it is | Use |
|---|---|---|
| `p20c_phase_a2_diverse/decoder_pretrained.pt` | v3 7-teacher Phase A2 (pre-Panel) | obsolete |
| `p35_length_head/decoder_pretrained.pt` | v3.1 12-teacher + length_head | first to terminate correctly |
| `p38_manuf_h1only` | v3.1 + failed diff manuf | **kept as negative-result reference** |
| `p39_manuf_rl/decoder_rl.pt` | v3.1 12-teacher + REINFORCE manuf | 0 violations on manuf |
| `p40_phase_a2_v2lib/decoder_pretrained.pt` | v3.1 **52-teacher** (12 + 40 v2lib) | **best PRE-RL ckpt** |
| `p43_full_rl_30/decoder_rl.pt` | p40 + 30-iter Phase A3 full RL | running now, will be the **best** |

For new sessions, start from `p43_full_rl_30/decoder_rl.pt` once training completes.

---

## How to use the v3.1 pipeline

### Just generate (inference, with trained ckpt)

```python
from design_generator import SentenceTransformerEncoder
from v3.design_generator_v3 import DesignGeneratorV3
from v3.full_chain_render import render_design_3d
import torch

enc = SentenceTransformerEncoder()
gen = DesignGeneratorV3()
gen.init_tag_bank(sbert=enc.model)
ckpt = torch.load("tools/output/2026-05-28/p43_full_rl_30/decoder_rl.pt",
                   map_location="cpu", weights_only=False)
gen.load_state_dict(ckpt["gen_state"], strict=False)
gen.eval()

briefs = ["cyberpunk magenta + chrome neon"]
emb = enc.encode(briefs)
if not isinstance(emb, torch.Tensor):
    emb = torch.tensor(emb).float()
with torch.no_grad():
    out = gen(emb, noise_sigma=0.3)
designs = gen.decode_strokes(out.stroke_tensor.cpu(),
                              length_logits=out.length_logits.cpu())
# strip after first is_end
tokens = designs[0]
end_at = next((i+1 for i, t in enumerate(tokens) if t.is_end), len(tokens))
tokens = tokens[:end_at]

render_design_3d(tokens, "out.png")
```

### Continue training (Phase A3 RL)

```bash
# Manuf-only (no vLLM needed)
python -m tools.v3.phase_a3_manuf_rl \
    --init-ckpt tools/output/2026-05-28/p43_full_rl_30/decoder_rl.pt \
    --iters 500 --batch 16 --lr 5e-5

# Manuf + visual judge (needs vLLM up)
python -m tools.v3.phase_a3_full_rl \
    --init-ckpt tools/output/2026-05-28/p43_full_rl_30/decoder_rl.pt \
    --iters 100 --batch 4 --judge-weight 0.6
```

### Add more teachers (Phase A2 with new refs)

```bash
python -m tools.v3.phase_a2_imitation \
    --iters 5000 --batch 32 --v2-lib-teachers 80 \
    --out-dir tools/output/.../my_new_ckpt
```

---

## Files / where things live

### New v3.1 modules
```
tools/v3/
├── __init__.py
├── stroke_schema.py             — Panel, Stroke, anchors, reference designs
├── token_tensor.py              — 709-dim encode/decode (Panel + Stroke)
├── tokens_to_garment.py         — KEY BRIDGE v3 tokens → v2 Garment
├── full_chain_render.py         — tokens → fabric mesh via v2 chain
├── stroke_renderer.py           — 2D UV sketch fallback + simple 3D tube
├── design_generator_v3.py       — NN (encoder + length_head + decoder + losses)
├── palette.py                   — 256 named colors (32 anchors + 224 HSL)
├── v2_lib_to_teachers.py        — v2 polygon recipes → v3 teachers
├── phase_a1_pretrain.py         — InfoNCE tag pretraining
├── phase_a2_imitation.py        — teacher imitation (12 + N v2lib)
├── phase_a3_manuf_rl.py         — REINFORCE on validate_garment
├── phase_a3_full_rl.py          — REINFORCE on manuf + vLLM judge
├── _audit_full_rl.py            — pre-vs-post RL judge comparison
├── _verify_manuf.py             — H1/H2 violation counts per ckpt
└── _render_v31_trained.py       — 8-brief 3D demo
```

### Modified existing files
- `tools/generate_batch.py` — `--n-trunk-layers` flag (v2 compat)
- `tools/tag_data.py` — auto-generated 692-tag bank (committed early)
- `tools/tag_embeddings.py` — TagEmbeddingBank with sbert init + EMA

### v2 chain (untouched — critical!)
- `tools/render3d_uv.py` — build_fabric_shell, polish_shell, apply_wrinkles, build_binding_mesh, _arc_tube
- `tools/garment_state.py` — Garment, PatternPiece, validate_garment, genome_to_garment
- `tools/polygon_recipes.py` — cup/bottom recipe library
- `tools/catalogs.py` — fabric/connector/accessory SKU catalog
- `tools/library.py` + `tools/library_data.py` — 86 library entries
- `tools/vision_judge.py` — VLLMVisionJudge with 9-dim rubric

---

## Critical design decisions that LOCKED (don't relitigate)

1. **Panel + Stroke dual token output** — confirmed by user, not just Stroke
2. **length_head over autoregressive is_end** — empirically proven 12/12
3. **REINFORCE for any non-differentiable constraint** — confirmed by H1+H2 failed-diff experiment
4. **REUSE v2 chain unchanged** — no rewrites of polish_shell, validate_garment, build_fabric_shell
5. **Anti-conservative bias** — no classical_bikini / athletic_sports / basic-everyday in teacher set
6. **256 palette with 32 named anchors** — covers SHOWCASE_BRIEFS color names
7. **vLLM judge in Phase A3, not A2** — A2 stays clean imitation; A3 adds reward

---

## Known issues / not-yet-done

1. **Phase A3 full RL is at 30 iter only.** May need 100-500 iter for significant judge_score improvement. Background training (bmjfrhh24) running now.

2. **The v2 → v3 anchor mapping is heuristic.** `V3_TO_V2_ANCHOR` dict in `tokens_to_garment.py` maps each of 10 v3 anchors to a v2 string anchor. Some collisions (e.g. COLLARBONE → front_clavicle_L, dropping R). Cosmetic for now; would matter if validate_garment ever cares about specific anchor placement.

3. **Stroke straps don't appear in v2's fabric_shell output.** The renderer adds them separately via _arc_tube. v2's chain doesn't know about them — they're not in `garment.connectors` data flow. For real manufacturing data export, would need to push v3 Strokes into v2 Connectors properly.

4. **fabric_id is auto-mapped from color cluster.** Currently uses a default fabric. Could be smarter (e.g., velvet for burgundy, ribbed for sport-bright).

5. **Image background and skin tone are hardcoded.** Renderer doesn't yet support different body meshes / skin tones.

6. **No multi-view render.** Just front 480x720. v2 has 8 standard views (`tools/iter/capture.py VIEWS`); v3 could opt into the same.

7. **No HTML/README batch artifact yet.** Per CLAUDE.md convention, batches should auto-generate overview.png + README.md + index.html. v3 demos currently just save the PNGs directly.

---

## What I'd do next (concrete)

When Phase A3 30-iter training completes (~30 min from when `f731b084` committed):

1. **Run `_audit_full_rl.py`** — confirm pre-vs-post improvement on judge score + manuf
2. **If judge improved >0.5 pts**: train another 100 iter (overnight-friendly, ~2h)
3. **If judge plateaued**: investigate brief→judge mismatch, possibly add brief-conditional rendering hints

Beyond:
- Stroke connector schema improvement (issue #3 above)
- Multi-view render (issue #6)
- HTML batch artifact (issue #7)
- Anchor mapping fidelity (issue #2)
- Real product-line filter (split outputs by is_manufacturable from validate_garment)

---

## How to read this session

If you're a new Claude session opening this branch, do:

1. Read this doc
2. Read `docs/handover/2026-05-28_STATUS_10h_autonomous.md` (the v3 build before the v3.1 pivot)
3. Read `docs/design/2026-05-27_schema_redesign_v3.md` (the v3 design doc)
4. `git log --oneline -25` (commit chronology)
5. Run smoke test: `python -m tools.v3.full_chain_render` (should output `p28_full_chain/test_bikini_navy.png` with REAL fabric)
6. Run smoke: `python -m tools.v3._render_v31_trained` (will fail if vLLM not up; in that case use UV sketch fallback)

End of status.
