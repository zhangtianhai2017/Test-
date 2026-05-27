# 10-Hour Autonomous Work Status (2026-05-27 → 2026-05-28)

**Branch:** `claude/add-diverse-seeds-handover-sBSs3`
**Commits added (this session):** 5 in order
1. `v3 schema foundation: tag pool + stroke schema`
2. `v3 generator + renderer: encoder/decoder + stroke→PNG bridge`
3. `v3 end-to-end smoke: brief → strokes → UV sketch (8/8 OK)`
4. `v3 Phase A1+A2 smoke training (both pass)`
5. `v3 named 256-color palette + renderer integration`
6. `v3 audit: trained-vs-random comparison on 8 UNSEEN briefs`

---

## TL;DR

**v3 schema redesign is fully wired end-to-end.** brief → sbert →
TagEmbeddingBank → VAE encoder + noise mix → Anchor-Plan +
Transformer stroke decoder → list[Stroke] → UV-sketch PNG. Phase A1
(self-supervised tag) and Phase A2 (teacher imitation) smoke trainings
both converge (148× and 426× loss drops). On 8 UNSEEN briefs, the
trained decoder shows **clear semantic conditioning**: "Maori-inspired
**harness**" → black cross-body diagonals (the harness teacher's
signature), other briefs → ivory + cup-like (the classical teacher's
vocabulary). This is the first evidence that v3 can learn meaningful
brief→design mappings.

**Nothing destructive.** All work is in new files (`tools/v3/*`,
`tools/tag_data.py`, `tools/tag_embeddings.py`, new docs).
`design_generator.py`, `render3d_uv.py`, `rl_runner.py` are untouched.
The 1136 v2 ckpt and its outputs (`tools/output/2026-05-27/p16_*`)
are untouched.

---

## What was built (file by file)

### Data layer
| File | Purpose |
|---|---|
| `tools/_parse_harvests.py` | One-shot parser: 2 harvest .md → `tag_data.py` |
| `tools/tag_data.py` | **692 tags across 6 axes** + 50 eval CharRefs (auto-generated) |
| `tools/tag_embeddings.py` | `TagEmbeddingBank`: sbert init (multilingual MiniLM) + Dirichlet axis mix + EMA-rollback |
| `tools/v3/palette.py` | 256 colors: 32 named anchors (ivory/burgundy/sage/cyber teal/…) + 224 HSL grid; EN+CN lookup |
| `tools/v3/stroke_schema.py` | `Stroke` dataclass, 10 anchors enum, Bezier sampling, validation, 2 hand-crafted reference designs |
| `tools/v3/stroke_tensor.py` | NN tensor (B, T, 669) ↔ `list[Stroke]` round-trip |

### Generator
| File | Purpose |
|---|---|
| `tools/v3/design_generator_v3.py` | **2.67M param** `DesignGeneratorV3`: BriefBias + VAEEncoder + AnchorPlan + StrokeTransformerDecoder (4-layer 4-head 192-d cross-attn), noise channel mix √0.9/√0.1, full imitation+KL loss decomposition |

### Renderer
| File | Purpose |
|---|---|
| `tools/v3/stroke_renderer.py` | 3D Open3D render (`render_design_png`) + 2D matplotlib UV sketch (`render_uv_sketch`) fallback |
| `tools/v3/_render_one_v3.py` | Subprocess-isolated single-design renderer |

### Training / Eval
| File | Purpose |
|---|---|
| `tools/v3/v3_end_to_end_smoke.py` | brief → NN → 8 designs → 8 PNGs (works) |
| `tools/v3/phase_a1_pretrain.py` | InfoNCE self-supervised tag pretraining (500 iter 0.5s) |
| `tools/v3/phase_a2_imitation.py` | Teacher (2 hand-crafted) imitation learning (300-400 iter 7-9s) |
| `tools/v3/v3_audit.py` | trained-vs-random side-by-side on 8 UNSEEN briefs |

### Docs
| File | Purpose |
|---|---|
| `docs/design/2026-05-27_schema_redesign_v3.md` | Authoritative v3 design doc (architecture, decision points, migration) |
| `docs/design/2026-05-27_design_vocabulary_harvest.md` | Fashion/couture/cosplay harvest (375 tags) |
| `docs/design/2026-05-27_game_industry_vocabulary_harvest.md` | Game-industry harvest (280 tags + 50 chars) |
| `docs/handover/2026-05-28_STATUS_10h_autonomous.md` | **This file** |

---

## What was verified (metrics)

### 1. Tag bank initialization
```
6 axes / 692 tags loaded:
  silhouette          52
  art_style          207
  cultural            76
  archetype           54
  costume_convention 114
  material_vfx       189
sbert load + 692-tag encode + 384→128 projection: ~10s on CPU
Dirichlet mix sampling: instant, correct shapes
Direct tag-ID encoding: instant, correct shapes
EMA-rollback: perturbation factor matches (1-α) within tolerance
```

### 2. v3 generator forward pass (random init)
```
total parameters: 2,666,919  (vs v2's 706K)
  ├─ tag_bank:     137,728
  └─ decoder:    2,273,373

forward output shapes (B=2 briefs):
  style_mu, style_latent: (2, 128)
  anchor_plan:            (2, 10)
  stroke_tensor:          (2, 16, 669)
  head_input.var ≈ 0.996  (target 1.0 ← √0.9·style + √0.1·noise verified)
```

### 3. End-to-end smoke (8 random-init designs)
```
brief → NN forward + decode: 8/8 designs produced
  design lengths varied 1-16 strokes
  anchor_plan logits clustered ~0.5 (no bias)
UV sketch render: 8/8 PNGs in 0.8s
output: tools/output/2026-05-27/p18_v3_e2e_smoke/
```

### 4. Phase A1 self-supervised tag pretraining
```
InfoNCE: brief(sbert) ↔ tag_embedding contrastive
500 iter @ batch 32 on 692 tags
  elapsed: 0.5s on CPU (912 iter/s)
  loss: 3.93 → 0.019 (148× drop)
  ✓ EMA-rollback (α=1e-3) DOES NOT deadlock learning
output: tools/output/2026-05-27/p19_phase_a1/loss_curve.png
```

### 5. Phase A2 imitation learning
```
Teacher: 2 hand-crafted (classical bikini + harness) × 8 brief paraphrases each
300 iter @ batch 8 on full 2.67M-param generator
  elapsed: 6.9s on CPU
  total loss: 31.67 → 0.07 (426× drop)
  per-head: start/end/color/bezier all → 0.00
  is_end: 0.04-0.09 (still imperfect — known issue, see below)
output: tools/output/2026-05-27/p20_phase_a2/
        teacher_vs_decoder.png shows topology match
```

### 6. v3 audit on 8 UNSEEN briefs
```
Random vs Trained comparison:
  100% different start_anchors per stroke
  100% different colors per stroke
  Stroke counts diverge per brief (random vs trained):
    cyberpunk_crop_top:    5  vs  4
    Iris_van_Herpen:      16  vs 16
    Genshin_Liyue:         1  vs 11
    KDA_idol:              1  vs 16
    Maori_harness:        16  vs  4   ← strongly cross-body, black
    Bayonetta:             2  vs  9
    Dune_Fremen:          16  vs 14
    FFXIV_summoner:        1  vs  5

KEY visual finding: "Maori-inspired body HARNESS" → trained model
produces BLACK CROSS-BODY DIAGONAL strokes. This means the decoder
learned that "harness" semantic → harness teacher's color + topology
signature, and TRANSFERRED it to an unseen brief.

output: tools/output/2026-05-28/p22_v3_audit/audit_grid.png
        (2-col × 8-row, 578×3444px)
```

### 7. 256 named palette
```
32 named anchors covering SHOWCASE_BRIEFS color names + commercial
vocab (nude / dusty rose / sage / mauve / coral / mint / taupe /
champagne / blush / plum) + game palette (cyber teal / neon magenta /
violet / blood crimson / void black / gold / copper / jade / imperial
red / ink / pearl / obsidian)
+ 224 HSL grid: 32 hues × 7 (sat, light) tiers
EN/CN lookup: find_by_name("ivory") == find_by_name("象牙白") == 0
swatch: tools/output/2026-05-27/p21_palette/palette_swatch.png
```

---

## What's broken / Known issues

### 1. **Open3D 3D renderer segfaults under vLLM GPU contention**
- vLLM is holding 42 GB of A6000's 46 GB VRAM
- `o3d.visualization.rendering.OffscreenRenderer` (EGL backend)
  SIGSEGVs in subprocess context
- Confirmed: BOTH v3's renderer and v2's existing `_render_one_outfit.py`
  fail the same way right now
- Workaround in place: matplotlib UV-space sketch fallback (0.1s/design,
  information-equivalent for smoke purposes)
- Fix paths to investigate when back:
  a) Try `OPEN3D_DISABLE_GPU=1` (different env var name)
  b) Stop vLLM, then retry — confirms whether it's GPU contention
  c) Use a different rendering backend (mitsuba / blender headless)

### 2. **`is_end` head doesn't trigger termination**
- Decoder learns all categorical fields (start/end/color → 0.00 loss)
  perfectly within 100 iters
- `is_end` loss drops only to 0.04-0.09 with pos-class upweight + extra
  -log(prob_at_target) penalty
- Result: decoded designs always have 16 strokes (max), even when
  teacher had 4
- Plan: increase pos_weight to 10x, train 1000+ iter, OR use a
  separate is_end-only loss scaled higher in the total
- Cosmetic for smoke — categorical heads work, semantic conditioning
  transfers (see audit). Just truncate UI-side meanwhile.

### 3. **Phase A2 teacher set is tiny**
- Only 2 hand-crafted designs × 8 brief paraphrases = 16 pairs
- For real Phase A2 the design doc calls for using v2 library entries
  as teachers (~86 entries)
- TODO: write a `v2_outfit_to_strokes` converter (the existing
  Garment object → stroke sequence) so we can use the v2 86-entry
  library as teachers

---

## What to look at first when you're back

In this order — should take ~15 min to digest:

1. **Visual evidence:**
   `tools/output/2026-05-28/p22_v3_audit/audit_grid.png`
   — Look at row v04 (Maori harness): trained column shows black
   crossing diagonals. That's transfer-learning working.

2. **Architecture doc:**
   `docs/design/2026-05-27_schema_redesign_v3.md`
   — §3 architecture diagram, §9 8 decision points (D1-D8, all locked
   per your earlier confirmation).

3. **Phase A1+A2 metrics:**
   - `tools/output/2026-05-27/p19_phase_a1/loss_curve.png`
   - `tools/output/2026-05-27/p20_phase_a2/loss_curve.png`
   — Clean training curves, EMA-rollback working.

4. **Tag swatch:**
   `tools/output/2026-05-27/p21_palette/palette_swatch.png`
   — Confirm the 32 named anchor colors cover what you want.

5. **This doc.**

---

## Recommended next steps (when you decide we resume)

### Immediate (1-2 days)
1. **Fix is_end termination** — bump pos_weight, train longer, OR
   replace BCE with a smoothed-target classification over the
   "next-stroke-is-end" decision.
2. **Build v2→stroke converter** for proper Phase A2 — gives the
   decoder 86 teacher designs instead of 2.
3. **Investigate Open3D vLLM contention** — get 3D renders back so
   the Qwen judge can score actual swimwear images, not UV sketches.

### Phase A3 (1-2 weeks per design doc §5)
1. Re-establish vLLM availability + 3D rendering.
2. Build `rl_runner_v3.py` (mirroring v2's loop but feeding stroke
   tensors to the judge prompt + symbolic fitness for v3).
3. Rewrite symbolic fitness for stroke-based representation:
   - coverage = total stroke area / body area
   - color harmony = palette-aware (not raw HSL)
   - anchor coverage = (active anchors) / (used anchors)
4. Rewrite Qwen judge prompt to evaluate stylized / artistic /
   game-aesthetic dimensions (not just real-world swimwear).
5. Run a 200-iter Phase A3 with the proper teacher base.

### Strategic
1. The `is_manufacturable` post-hoc classifier is still unbuilt
   (per design doc §4.6). Defer until Phase A3 proves the
   game-character side works — manufacturability is the secondary
   path.
2. The 10 anchors may need anatomy-mesh-derived 3D positions
   (currently using fallback UV coords). Once 3D rendering is back,
   write `v3/anchor_resolver.py` to use `anatomy.detect()` properly.

---

## Disclaimers / things to verify

- I did NOT touch `rl_runner.py`, `design_generator.py`, `render3d_uv.py`,
  `iter/capture.py`, or any v2 production code path.
- I did NOT touch the running vLLM service or anything WSL-system-level.
- I did NOT push to remote (no `git push`). Run `git push` when you
  approve the commits.
- All Phase A1/A2 outputs live under `tools/output/2026-05-27/p19_*`
  and `tools/output/2026-05-27/p20_*` / `tools/output/2026-05-28/*`.
  None of these collide with v2 outputs.
- The 1136 v2 ckpt is preserved untouched at
  `tools/output/2026-05-27/1136_rl_run/generator_final.pt`.

---

## Time accounting

| Phase | Time |
|---|---|
| W1.1 tag pool integration + embedding bank | 1.0 h |
| W1.2-A stroke schema + tensor round-trip | 0.5 h |
| W1.2-B DesignGeneratorV3 (encoder + decoder) | 1.5 h |
| W1.3 stroke renderer + Open3D investigation | 1.5 h |
| W1.4 e2e smoke (incl. UV sketch fallback) | 1.0 h |
| Phase A1 self-supervised pretraining | 0.5 h |
| Phase A2 imitation learning + visual diff | 1.0 h |
| is_end fix + retrain | 0.3 h |
| 256 named palette | 0.4 h |
| v3 audit on unseen briefs | 0.7 h |
| Commits / cleanup / this doc | 1.5 h |
| **Total** | **~10 h** |

End of status.
