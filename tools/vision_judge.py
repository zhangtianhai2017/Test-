"""Vision judge — runs a multimodal LLM over a rendered outfit image to
return a structured pass/fail + score + defect list.

Per docs/design/2026-05-17_option_D_architecture.md (option D, J layer):
- Default backend: Qwen2.5-VL-7B, served locally via vLLM with an
  OpenAI-compatible endpoint (user runs `vllm serve` on their 3090).
- For tests / CI / bootstrap: MockVisionJudge returns plausible
  deterministic values without any external service.

The judge's contract is **structural validity only**:
- it MUST flag fabric extending to arms, legs, head/neck, geometry
  clipping into body, missing required panels, disconnected straps.
- it MUST NOT punish: asymmetric designs, minimal coverage, deep
  cutouts, bold colours.  Those are style choices, not bugs.

Output schema (every judge returns this dict shape):
    {
      "is_valid_swimsuit":   bool,
      "validity_score":      int in [0, 10],
      "aesthetic_score":     int in [0, 10],
      "structural_issues":   list[str],
      "anatomical_overflow": list[str],
      "missing_required_parts": list[str],
      "style_descriptors":   list[str],
      "overall_assessment":  str,
    }
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import hashlib
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Iterable, Optional

from PIL import Image


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

DEFAULT_BACKEND_URL = os.environ.get("VISION_JUDGE_URL",
                                       "http://localhost:8000/v1")
DEFAULT_MODEL_NAME  = os.environ.get("VISION_JUDGE_MODEL",
                                       "Qwen/Qwen2.5-VL-7B-Instruct")


def _safe_int(v, default: int = 0, lo: int = 0, hi: int = 10) -> int:
    """Coerce a model-emitted number into [lo, hi].

    - returns `default` on non-numeric input
    - returns `lo` for slightly negative
    - returns `hi` for slight overshoot (LLM sometimes says 11 for 10)
    - returns `default` for wildly out-of-range (LLM token-repetition
      degenerate output, e.g. assembly_quality: 11111111111111111111)
    """
    try:
        i = int(float(v))
    except (TypeError, ValueError):
        return default
    if i < lo:
        return lo
    if i > hi:
        if i <= hi + 5:
            return hi
        return default      # 16+ on a 0-10 scale = garbage, low-trust
    return i


@dataclass
class JudgeResult:
    is_valid_swimsuit:       bool
    validity_score:          int   # 0-10  (legacy, derived in V2)
    aesthetic_score:         int   # 0-10  (legacy, == aesthetic in V2)
    structural_issues:       list[str]
    anatomical_overflow:     list[str]
    missing_required_parts:  list[str]
    style_descriptors:       list[str]
    overall_assessment:      str
    # ---- V2 structural sub-scores (each 0-10) ----
    chest_coverage:          int = 0
    pelvic_coverage:         int = 0
    anatomy_clean:           int = 0
    assembly_quality:        int = 0
    aesthetic:               int = 0
    # ---- V3 aesthetic sub-scores (each 0-10, added 2026-05-20) ----
    color_harmony:           int = 0
    proportion:              int = 0
    silhouette:              int = 0
    # ---- V4 brief-match score (added 2026-05-21) ----
    brief_match:             int = 0
    # ---- observation phrases ----
    chest_observation:       str = ""
    pelvic_observation:      str = ""
    color_observation:       str = ""
    proportion_observation:  str = ""
    silhouette_observation:  str = ""
    brief_match_observation: str = ""
    # ---- metadata (not from the model) ----
    image_path:              str = ""
    elapsed_s:               float = 0.0
    backend:                 str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict, image_path: str = "",
                  elapsed_s: float = 0.0, backend: str = "") -> "JudgeResult":
        # Structural sub-scores (V2)
        chest = _safe_int(d.get("chest_coverage"))
        pelvic = _safe_int(d.get("pelvic_coverage"))
        anatomy = _safe_int(d.get("anatomy_clean"))
        assembly = _safe_int(d.get("assembly_quality"))
        aesthetic = _safe_int(d.get("aesthetic"))
        # Aesthetic sub-scores (V3, added 2026-05-20)
        color_harmony = _safe_int(d.get("color_harmony"))
        proportion = _safe_int(d.get("proportion"))
        silhouette = _safe_int(d.get("silhouette"))
        brief_match = _safe_int(d.get("brief_match"))
        # Legacy validity_score: prefer model's value, else derive from
        # the 4 structural sub-scores (V2/V3 prompt instructs same).
        if "validity_score" in d:
            v_score = _safe_int(d.get("validity_score"))
        else:
            v_score = round((chest + pelvic + anatomy + assembly) / 4)
        if "aesthetic_score" in d:
            a_score = _safe_int(d.get("aesthetic_score"))
        else:
            a_score = aesthetic
        # Derive is_valid Python-side from the 4 structural sub-scores.
        # Threshold 4 (not 5) on chest/pelvic so that thong / micro
        # bikini (which Qwen scores at 3) doesn't get automatically
        # marked invalid — they're real swimsuit categories. Anatomy
        # and assembly stay at 5 since those measure render defects.
        if any(k in d for k in ("chest_coverage", "pelvic_coverage")):
            is_valid = (chest >= 4 and pelvic >= 4
                         and anatomy >= 5 and assembly >= 5)
        else:
            is_valid = bool(d.get("is_valid_swimsuit", False))
        return cls(
            is_valid_swimsuit=is_valid,
            validity_score=v_score,
            aesthetic_score=a_score,
            structural_issues=list(d.get("structural_issues", []) or []),
            anatomical_overflow=list(d.get("anatomical_overflow", []) or []),
            missing_required_parts=list(d.get("missing_required_parts", []) or []),
            style_descriptors=list(d.get("style_descriptors", []) or []),
            overall_assessment=str(d.get("overall_assessment", "")),
            chest_coverage=chest,
            pelvic_coverage=pelvic,
            anatomy_clean=anatomy,
            assembly_quality=assembly,
            aesthetic=aesthetic,
            color_harmony=color_harmony,
            proportion=proportion,
            silhouette=silhouette,
            brief_match=brief_match,
            chest_observation=str(d.get("chest_observation", "")),
            pelvic_observation=str(d.get("pelvic_observation", "")),
            color_observation=str(d.get("color_observation", "")),
            proportion_observation=str(d.get("proportion_observation", "")),
            silhouette_observation=str(d.get("silhouette_observation", "")),
            brief_match_observation=str(d.get("brief_match_observation", "")),
            image_path=image_path,
            elapsed_s=elapsed_s,
            backend=backend,
        )


# ---------------------------------------------------------------------------
# Prompt — drives the model toward structural-validity-only judgment
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """You are inspecting a 3D rendered image of a swimsuit on a mannequin.
The designer was asked to produce this design from the following text brief:

  BRIEF: "{brief}"

Score 9 dimensions (each 0-10). For each, first describe ONE phrase
of what you see, then assign the score.

STRUCTURAL (low scores reject the design):

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

3. anatomy_clean    — fabric stays on torso/hip/shoulder/breast, no
   overflow onto bare arms, legs, head, neck, or floating in space:
   0 = major overflow onto multiple non-torso body parts
   5 = minor overflow on one region (e.g. fabric trailing onto arm)
   10 = all fabric stays on intended body regions

4. assembly_quality — straps connected, no obvious geometry clipping
   into body, no broken / floating pieces:
   0 = many disconnected pieces or severe clipping
   5 = one minor issue (e.g. one disconnected strap)
   10 = clean assembly

AESTHETIC (do not gate validity; widen the quality signal):

5. color_harmony    — palette coherence between primary, secondary,
   pattern, hardware:
   0 = clashing / muddy
   3 = one color dominates awkwardly
   5 = competent but unmemorable
   7 = clean coordinated palette
   9 = striking complementary or analogous combo
   10 = exceptional

6. proportion       — top-to-bottom balance, where the eye lands,
   how the silhouette flatters the body:
   0 = jarringly mismatched halves
   3 = one half visually overwhelms
   5 = even but unsculpted
   7 = pleasing balance
   9 = intentional accent (e.g. high-cut bottom lengthening leg)
   10 = exceptional

7. silhouette       — outline shape against the body, how the design
   reads from across a room:
   0 = blob / no recognizable silhouette
   3 = one feature dominates incoherently
   5 = readable but generic
   7 = distinctive shape
   9 = striking / signature silhouette
   10 = exceptional

8. aesthetic        — overall visual appeal in one number, weighing
   color + proportion + silhouette together:
   1 = visually broken / unappealing
   5 = average / forgettable
   7 = pleasing
   9 = strikingly attractive
   10 = exceptional

9. brief_match     — how well the design MATCHES the BRIEF above.
   This dimension scores ONLY the color + style + named details.
   It does NOT compensate for missing fabric or broken structure.

   HARD RULES (override everything else below):
   - If the design has NO BOTTOM PANEL or NO TOP COVERAGE
     (chest_coverage <= 2 OR pelvic_coverage <= 2), brief_match
     CANNOT exceed 3. A naked or near-naked design is NEVER a
     legitimate realization of a brief, no matter how avant-garde
     the brief sounds. The brief assumes a wearable swimsuit.
   - "Avant-garde", "minimal", "futuristic", "experimental",
     "deconstructed" briefs do NOT excuse missing required panels.
     A real avant-garde swimsuit is still a swimsuit.

   Otherwise, scale based on color + style + named details:
   0 = design contradicts the brief on every dimension
       (e.g. brief says "ivory white French elegance" but design is
       neon-purple aggressive thong)
   3 = design ignores most of the brief, gets one element right
   5 = design respects the brief loosely (right "vibe" / general
       coverage tier) but WRONG COLOR
   7 = design hits color hue family AND style category, missing
       finer details
   9 = strong match on color + style + mood + named details
   10 = exact realization of the brief

   IMPORTANT: COLOR match is the single biggest signal. If the brief
   names a color ("ivory", "emerald green", "neon yellow", "burgundy",
   "navy", "silver"), the design must visibly be that color family
   to score above 5. Wrong color = brief_match <= 5 even if every
   other element matches.

A design counts as VALID only if chest_coverage >= 4 AND
pelvic_coverage >= 4 AND anatomy_clean >= 5 AND assembly_quality >= 5.
(Threshold 4 lets thongs and micro bikinis pass — they're real
swimsuits, just minimal.) The 4 aesthetic dimensions never gate
validity — they widen the quality signal.

Output STRICT JSON only, no prose or markdown. Use exactly this schema
in this order:
{
  "chest_observation":     "<phrase>",
  "chest_coverage":        <int>,
  "pelvic_observation":    "<phrase>",
  "pelvic_coverage":       <int>,
  "anatomy_observation":   "<phrase>",
  "anatomy_clean":         <int>,
  "assembly_observation":  "<phrase>",
  "assembly_quality":      <int>,
  "color_observation":     "<phrase>",
  "color_harmony":         <int>,
  "proportion_observation":"<phrase>",
  "proportion":            <int>,
  "silhouette_observation":"<phrase>",
  "silhouette":            <int>,
  "aesthetic_observation": "<phrase>",
  "aesthetic":             <int>,
  "brief_match_observation":"<one short phrase noting what matches/contradicts the brief>",
  "brief_match":           <int>,
  "is_valid_swimsuit":     <true|false>,
  "validity_score":        <int>,
  "aesthetic_score":       <int>,
  "structural_issues":     [<short tags>],
  "anatomical_overflow":   [<body parts>],
  "missing_required_parts":[<short tags>],
  "style_descriptors":     [<short tags>],
  "overall_assessment":    "<one sentence>"
}

Legacy field derivation:
  validity_score  = round((chest_coverage + pelvic_coverage + anatomy_clean + assembly_quality) / 4)
  aesthetic_score = aesthetic

Begin with `{` end with `}`."""


# ---------------------------------------------------------------------------
# Backend base class
# ---------------------------------------------------------------------------

class VisionJudge(ABC):
    backend_name: str = "abstract"

    # When >1, judge_batch fires this many judge() calls concurrently
    # via ThreadPoolExecutor. Qwen2.5-VL via vLLM/oai server handles
    # continuous batching server-side, so concurrent calls don't 8x
    # the wall time. Measured 2026-05-22: 8 sequential calls ~100s,
    # 8 concurrent calls ~40s (2.5x speedup).
    concurrent_calls: int = 1

    @abstractmethod
    def judge(self, image_path: str, brief: str = "") -> JudgeResult: ...

    def judge_batch(self, image_paths: Iterable[str],
                     briefs: Optional[Iterable[str]] = None,
                     verbose: bool = False) -> list[JudgeResult]:
        """If `briefs` is supplied, must align 1:1 with image_paths.
        Pass-through to judge(); empty brief = old behaviour."""
        paths = list(image_paths)
        briefs_list = (list(briefs) if briefs is not None
                        else [""] * len(paths))
        if self.concurrent_calls > 1 and len(paths) > 1:
            from concurrent.futures import ThreadPoolExecutor
            workers = min(self.concurrent_calls, len(paths))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                out = list(ex.map(
                    lambda pb: self.judge(pb[0], brief=pb[1]),
                    list(zip(paths, briefs_list))))
        else:
            out = [self.judge(p, brief=b) for p, b in zip(paths, briefs_list)]
        if verbose:
            for r in out:
                tag = "PASS" if r.is_valid_swimsuit else "FAIL"
                print(f"  [{tag}] v={r.validity_score} a={r.aesthetic_score} "
                      f"bm={r.brief_match} "
                      f"{os.path.basename(r.image_path):40s} "
                      f"{r.elapsed_s:.2f}s ({len(r.structural_issues)} issues)")
        return out


# ---------------------------------------------------------------------------
# Mock backend — deterministic, no service needed
# ---------------------------------------------------------------------------

class MockVisionJudge(VisionJudge):
    """Pseudo-random but deterministic judge.  Lets us wire up the rest
    of the pipeline (train_loop, audit, etc.) before vLLM is up."""

    backend_name = "mock"

    def __init__(self, fail_rate: float = 0.15, seed: int = 7):
        self.fail_rate = fail_rate
        self.seed = seed

    def judge(self, image_path: str, brief: str = "") -> JudgeResult:
        t0 = time.time()
        h = hashlib.sha256((image_path + str(self.seed)).encode()).digest()
        rng = random.Random(int.from_bytes(h[:8], "big"))
        is_valid = rng.random() > self.fail_rate
        validity_score = rng.randint(7, 10) if is_valid else rng.randint(2, 6)
        aesthetic_score = rng.randint(4, 9)
        issues = []
        overflow = []
        missing = []
        if not is_valid:
            issues = rng.sample(
                ["fabric_extending_to_armpit", "fabric_extending_to_inner_knee",
                 "disconnected_strap", "missing_bottom_panel",
                 "fabric_clipping_neck"], k=rng.randint(1, 2))
            overflow = rng.sample(
                ["left_arm", "right_arm", "left_knee", "right_knee", "neck"],
                k=rng.randint(0, 2))
            if "missing_bottom_panel" in issues:
                missing = ["bottom_panel"]
        style = rng.sample(
            ["triangle", "balconette", "bandeau", "asymmetric", "minimal",
             "boho", "sport", "deep_v", "high_neck"], k=rng.randint(1, 3))
        verdict = ("structurally valid swimsuit"
                   if is_valid else "fabric extends into prohibited region")
        return JudgeResult(
            is_valid_swimsuit=is_valid,
            validity_score=validity_score,
            aesthetic_score=aesthetic_score,
            structural_issues=issues,
            anatomical_overflow=overflow,
            missing_required_parts=missing,
            style_descriptors=style,
            overall_assessment=verdict,
            image_path=image_path,
            elapsed_s=time.time() - t0,
            backend=self.backend_name,
        )


# ---------------------------------------------------------------------------
# vLLM backend — talks to a local Qwen2.5-VL via OpenAI-compatible API
# ---------------------------------------------------------------------------

class VLLMVisionJudge(VisionJudge):
    """Calls a locally-served vision LLM (e.g. Qwen2.5-VL-7B via vLLM).

    Expects an OpenAI-compatible endpoint.  Start one with:
        vllm serve Qwen/Qwen2.5-VL-7B-Instruct --port 8000

    Then point VISION_JUDGE_URL at http://localhost:8000/v1 (default).
    """

    backend_name = "vllm-qwen2.5-vl"

    def __init__(self,
                 base_url: str = DEFAULT_BACKEND_URL,
                 model: str = DEFAULT_MODEL_NAME,
                 api_key: str = "dummy",
                 max_image_dim: int = 768,
                 request_timeout: float = 60.0,
                 concurrent_calls: int = 1):
        from openai import OpenAI                  # lazy import
        self.client = OpenAI(base_url=base_url, api_key=api_key,
                              timeout=request_timeout)
        self.model = model
        self.max_image_dim = max_image_dim
        self.base_url = base_url
        self.concurrent_calls = concurrent_calls

    def _encode_image(self, image_path: str) -> str:
        """Downscale (cap longest side at max_image_dim) and base64-encode
        as a data URL.  Smaller image = faster, cheaper, still enough
        for structural validity."""
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        scale = min(1.0, self.max_image_dim / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)),
                              Image.LANCZOS)
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def judge(self, image_path: str, brief: str = "") -> JudgeResult:
        t0 = time.time()
        data_url = self._encode_image(image_path)
        # Substitute brief into the {brief} slot in JUDGE_PROMPT.
        # Empty brief is OK — Qwen just reads "BRIEF: \"\"" and the
        # brief_match dimension will default to a neutral score.
        prompt = JUDGE_PROMPT.replace("{brief}", brief or "(no brief)")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }],
            temperature=0.0,    # deterministic structural judgement
            max_tokens=1400,    # V4: ~27 keys (added brief_match dim)
        )
        raw = response.choices[0].message.content or ""
        parsed = _extract_json(raw)
        return JudgeResult.from_dict(
            parsed,
            image_path=image_path,
            elapsed_s=time.time() - t0,
            backend=self.backend_name,
        )


def _repair_json(text: str) -> str:
    """Best-effort fixups for common Qwen JSON mistakes we've actually
    observed in production (2026-05-19): missing commas between
    "key":value pairs, runaway digit repetition collapsing a value,
    duplicate trailing word in a key.

    Cheap regex passes — if any of these don't apply, the string is
    unchanged. Caller must still try json.loads after."""
    # 1. Missing comma between "string" newline "key": -> add comma
    text = re.sub(r'("\s*)\n(\s*"[A-Za-z_])', r'\1,\n\2', text)
    # 2. Runaway digits in a numeric value: a long run of one repeated
    #    digit (>20 chars) collapses to first 2 digits.
    text = re.sub(r':\s*(\d)\1{20,}', r': \1\1', text)
    # 3. Duplicate trailing word in key: "style_descriptorscriptors":
    #    -> "style_descriptors":   (only common Qwen mistake we've seen)
    text = re.sub(r'"([a-z_]+?)([a-z]+)\2":', r'"\1\2":', text)
    return text


def _extract_json(text: str) -> dict:
    """The model is told to emit pure JSON, but real responses sometimes
    wrap it in ``` fences or add a stray sentence. Pull the first
    {...} block, decode. On strict-parse failure, try _repair_json once."""
    text = text.strip()
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        if m:
            text = m.group(1)
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_repair_json(text))
    except json.JSONDecodeError:
        # malformed — return a safe "unparseable" result so the
        # batch pipeline doesn't crash on one bad sample
        return {
            "is_valid_swimsuit": False,
            "validity_score": 0,
            "aesthetic_score": 0,
            "structural_issues": ["parse_error"],
            "anatomical_overflow": [],
            "missing_required_parts": [],
            "style_descriptors": [],
            "overall_assessment": "could not parse model JSON",
        }


# ---------------------------------------------------------------------------
# Factory + smoke test
# ---------------------------------------------------------------------------

class CLIPVisionJudge(VisionJudge):
    """Fast brief-match judge. Uses sentence-transformers' M-CLIP
    pairing:
      - text encoder: clip-ViT-B-32-multilingual-v1 (ZH + EN)
      - image encoder: clip-ViT-B-32 (OpenAI CLIP image side)
    Both are aligned in the same 512-d embedding space.

    Computes cosine(image_emb, brief_emb), maps to brief_match 0-10.
    Other JudgeResult fields default to neutral mid-values; structural
    correctness comes from symbolic_fitness in train_loop.

    ~100ms per call vs ~10s for Qwen2.5-VL — 100x speedup.
    Trade-off: no fabric-coverage / anatomy-overflow detection.
    Use only when symbolic_fitness handles structure (it does)."""

    backend_name = "clip-mclip-vit-b32"

    def __init__(self,
                 text_model_name: str = "sentence-transformers/clip-ViT-B-32-multilingual-v1",
                 image_model_name: str = "clip-ViT-B-32",
                 brief_score_floor: float = 0.10,
                 brief_score_ceil: float = 0.35,
                 device: str = "cuda" if __import__("torch").cuda.is_available() else "cpu"):
        from sentence_transformers import SentenceTransformer
        import torch
        self.torch = torch
        self.text_model = SentenceTransformer(text_model_name, device=device)
        self.image_model = SentenceTransformer(image_model_name, device=device)
        self.device = device
        # Cosine -> 0-10 linear mapping. M-CLIP paired-pair cosines
        # typically run ~0.10 (random) to ~0.35 (good match).
        self.floor = brief_score_floor
        self.ceil = brief_score_ceil
        self._brief_cache: dict[str, "torch.Tensor"] = {}

    def _embed_brief(self, brief: str):
        if brief in self._brief_cache:
            return self._brief_cache[brief]
        text = brief or "a swimsuit"
        with self.torch.no_grad():
            emb = self.text_model.encode([text], convert_to_tensor=True,
                                           normalize_embeddings=True)[0]
        self._brief_cache[brief] = emb
        return emb

    def judge(self, image_path: str, brief: str = "") -> JudgeResult:
        from PIL import Image
        t0 = time.time()
        img = Image.open(image_path).convert("RGB")
        with self.torch.no_grad():
            img_emb = self.image_model.encode(
                [img], convert_to_tensor=True,
                normalize_embeddings=True)[0]
        brief_emb = self._embed_brief(brief)
        cos = float((img_emb * brief_emb).sum().item())
        # Map cosine -> 0-10
        bm = max(0, min(10, int(round(
            (cos - self.floor) / (self.ceil - self.floor) * 10))))
        return JudgeResult.from_dict({
            # CLIP doesn't know about structure — set neutral so the
            # reward formula's structural component is constant. The
            # actual structural gradient comes from symbolic_fitness.
            "chest_coverage": 7, "pelvic_coverage": 7,
            "anatomy_clean": 8, "assembly_quality": 8,
            "aesthetic": 7, "color_harmony": 7,
            "proportion": 7, "silhouette": 7,
            "brief_match": bm,
            "is_valid_swimsuit": True,
            "validity_score": 7, "aesthetic_score": 7,
            "structural_issues": [], "anatomical_overflow": [],
            "missing_required_parts": [], "style_descriptors": [],
            "overall_assessment": (
                f"CLIP cos={cos:.3f} brief_match={bm}/10"),
        }, image_path=image_path,
           elapsed_s=time.time() - t0,
           backend=self.backend_name)


class CVPlusCLIPJudge(VisionJudge):
    """Pixel-mask structural judge + CLIP brief judge. Combined.

    Replaces Qwen2.5-VL at ~50-100 ms / image (vs ~10s) while still
    gating structure properly (CLIP-only doesn't).

    Why pure CV instead of fashion-YOLO:
      - mannequin pose / camera / background / lighting are all FIXED.
        We control the rendering pipeline. There is nothing to LEARN —
        coverage = "ratio of non-skin non-bg pixels in chest band".
      - Tried valentinafeve/yolos-fashionpedia 2026-05-23: blocked by
        CVE-2025-32434 (transformers requires torch>=2.6 to load .bin
        weights; we have 2.5.1). Ultralytics route adds a 30+MB package
        + a different model to download. Pure numpy avoids both.

    Calibration constants (measured on 2026-04-29 renders):
      - background  = (225, 225, 227) ± small  → grey near-white
      - skin tones  = (193,183,173) face, (173,157,140) thigh,
                       (216,212,210) arm — all R > G > B, R ∈ [145, 220]
      - mannequin centered, image 720x480, body x ∈ [0.30, 0.70]

    Coverage zones (relative to image H, W):
      chest band  = y ∈ [0.28, 0.45], x ∈ [0.38, 0.62]
      pelvic band = y ∈ [0.44, 0.58], x ∈ [0.38, 0.62]
      (recalibrated 2026-05-23: mannequin's actual y_pelvis maps
       to image y_rel ~ 0.50; the prior [0.55, 0.68] band was the
       upper-thigh zone, missing the hip ridge entirely.)
    Overflow zones (anatomy_clean penalty):
      arms        = y ∈ [0.30, 0.50], x ∈ [0.10, 0.30] ∪ [0.70, 0.90]
      head/neck   = y ∈ [0.02, 0.20], x ∈ [0.30, 0.70]
      lower legs  = y ∈ [0.75, 0.92], x ∈ [0.30, 0.70]
    Constant noise floors (anti-aliasing on fixed silhouette):
      arm 600 px, head 200 px, leg 600 px

    Falls back to CLIP-only for brief_match. Hard rule: if chest<=2 or
    pelvic<=2, brief_match capped at 3 (matches Qwen V4 prompt rule)."""

    backend_name = "cv-mask-mclip"

    # Coverage band ROIs (relative coords)
    CHEST_Y = (0.28, 0.45)
    PELV_Y  = (0.44, 0.58)   # recalibrated 2026-05-23 to actual y_pelvis
    BODY_X  = (0.38, 0.62)
    # Overflow zones
    ARM_Y      = (0.30, 0.50)
    ARM_L_X    = (0.10, 0.30)
    ARM_R_X    = (0.70, 0.90)
    HEAD_Y     = (0.02, 0.20)
    HEAD_X     = (0.30, 0.70)
    LEG_Y      = (0.75, 0.92)
    LEG_X      = (0.30, 0.70)
    # Anti-aliasing noise floor (px) subtracted from each overflow zone
    ARM_NOISE  = 600
    HEAD_NOISE = 200
    LEG_NOISE  = 600

    # Coverage saturation point for the 0-10 mapping. chest_coverage of
    # ~0.85 = full bra/halter, ~0.30 = minimal cup, ~0.05 = nothing.
    CHEST_SAT = 0.85
    PELV_SAT  = 0.75

    def __init__(self,
                 text_model_name: str = "sentence-transformers/clip-ViT-B-32-multilingual-v1",
                 image_model_name: str = "clip-ViT-B-32",
                 brief_score_floor: float = 0.10,
                 brief_score_ceil: float = 0.35,
                 device: str = "cuda" if __import__("torch").cuda.is_available() else "cpu"):
        from sentence_transformers import SentenceTransformer
        import torch
        self.torch = torch
        self.text_model = SentenceTransformer(text_model_name, device=device)
        self.image_model = SentenceTransformer(image_model_name, device=device)
        self.device = device
        self.brief_floor = brief_score_floor
        self.brief_ceil = brief_score_ceil
        self._brief_cache: dict[str, "torch.Tensor"] = {}

    @staticmethod
    def _fabric_mask(img_np):
        """non-background AND non-skin -> fabric."""
        import numpy as np
        R = img_np[..., 0].astype(int)
        G = img_np[..., 1].astype(int)
        B = img_np[..., 2].astype(int)
        # Background: near-white grey (R,G,B all >210, low chroma)
        is_bg = ((R > 210) & (G > 210) & (B > 210)
                  & (np.abs(R - G) < 12)
                  & (np.abs(G - B) < 12)
                  & (np.abs(R - B) < 12))
        # Skin: warm beige (R > G > B, R in mid range, low-mid saturation)
        is_skin = ((R > 145) & (R < 225)
                    & (R > G) & (G > B)
                    & ((R - B) > 12) & ((R - B) < 80))
        return ~(is_bg | is_skin)

    def _structural_scores(self, img_np):
        """returns (chest, pelvic, anatomy, assembly, diagnostics_dict).

        All scores in [0, 10]. diagnostics holds the raw coverages /
        overflow counts / component count for the assessment string."""
        import numpy as np
        H, W = img_np.shape[:2]
        mask = self._fabric_mask(img_np)

        def _r(lo, hi, dim): return int(lo * dim), int(hi * dim)
        cy0, cy1 = _r(*self.CHEST_Y, H)
        py0, py1 = _r(*self.PELV_Y,  H)
        bx0, bx1 = _r(*self.BODY_X,  W)
        chest_area = max(1, (cy1 - cy0) * (bx1 - bx0))
        pelv_area  = max(1, (py1 - py0) * (bx1 - bx0))
        chest_cov  = mask[cy0:cy1, bx0:bx1].sum() / chest_area
        pelv_cov   = mask[py0:py1, bx0:bx1].sum() / pelv_area

        # Overflow zones (subtract anti-alias baseline)
        ay0, ay1 = _r(*self.ARM_Y, H)
        al0, al1 = _r(*self.ARM_L_X, W)
        ar0, ar1 = _r(*self.ARM_R_X, W)
        hy0, hy1 = _r(*self.HEAD_Y, H)
        hx0, hx1 = _r(*self.HEAD_X, W)
        ly0, ly1 = _r(*self.LEG_Y,  H)
        lx0, lx1 = _r(*self.LEG_X,  W)
        arm_l = max(0, int(mask[ay0:ay1, al0:al1].sum()) - self.ARM_NOISE)
        arm_r = max(0, int(mask[ay0:ay1, ar0:ar1].sum()) - self.ARM_NOISE)
        head  = max(0, int(mask[hy0:hy1, hx0:hx1].sum()) - self.HEAD_NOISE)
        leg   = max(0, int(mask[ly0:ly1, lx0:lx1].sum()) - self.LEG_NOISE)
        total_fab = max(1, int(mask.sum()))
        overflow_ratio = (arm_l + arm_r + head + leg) / total_fab
        # 0% overflow -> 10. 30% overflow -> 0. Linear in between.
        anatomy = max(0, min(10, int(round(10 * (1.0 - overflow_ratio / 0.30)))))

        # Assembly: fraction of fabric mass in the top-3 connected
        # components. The raw component count is useless because real
        # renders have hundreds of single-pixel speckles from pattern
        # overlays + AA edges — even after 2x2 opening, ncomp = 25-80
        # for clean designs. But the top-3 component mass fraction is
        # tight: 0.89-0.98 across the diverse_seeds test set. A truly
        # fragmented design (panels broken into many small islands)
        # drops this number sharply.
        try:
            from scipy.ndimage import label, binary_opening
            import numpy as _np
            denoised = binary_opening(mask, structure=_np.ones((2, 2)))
            lbl, ncomp = label(denoised)
            sizes = _np.bincount(lbl.ravel())[1:]  # drop bg label 0
            if sizes.size:
                top3 = _np.sort(sizes)[-3:].sum()
                top3_frac = top3 / max(1, sizes.sum())
            else:
                top3_frac = 0.0
        except Exception:
            top3_frac = 1.0
            ncomp = 1
        if top3_frac >= 0.85:
            assembly = 10
        elif top3_frac >= 0.70:
            assembly = 7
        elif top3_frac >= 0.50:
            assembly = 4
        else:
            assembly = 1

        # Coverage -> 0-10 (linear, saturated at SAT)
        def _cov_score(cov, sat):
            if cov <= 0.03: return 0
            if cov >= sat:  return 10
            return max(0, min(10, int(round(10 * cov / sat))))
        chest_score = _cov_score(chest_cov, self.CHEST_SAT)
        pelv_score  = _cov_score(pelv_cov,  self.PELV_SAT)

        diag = {
            "chest_cov": chest_cov, "pelv_cov": pelv_cov,
            "overflow_ratio": overflow_ratio, "ncomp": int(ncomp),
            "top3_frac": float(top3_frac),
            "arm_l": arm_l, "arm_r": arm_r, "head": head, "leg": leg,
            "total_fab": total_fab,
        }
        return chest_score, pelv_score, anatomy, assembly, diag

    def _embed_brief(self, brief: str):
        if brief in self._brief_cache:
            return self._brief_cache[brief]
        text = brief or "a swimsuit"
        with self.torch.no_grad():
            emb = self.text_model.encode(
                [text], convert_to_tensor=True,
                normalize_embeddings=True)[0]
        self._brief_cache[brief] = emb
        return emb

    def judge(self, image_path: str, brief: str = "") -> JudgeResult:
        import numpy as np
        t0 = time.time()
        img_pil = Image.open(image_path).convert("RGB")
        img_np = np.asarray(img_pil)
        chest, pelv, anat, asm, diag = self._structural_scores(img_np)

        # brief_match via CLIP image-text cosine
        with self.torch.no_grad():
            img_emb = self.image_model.encode(
                [img_pil], convert_to_tensor=True,
                normalize_embeddings=True)[0]
        brief_emb = self._embed_brief(brief)
        cos = float((img_emb * brief_emb).sum().item())
        bm = max(0, min(10, int(round(
            (cos - self.brief_floor) / (self.brief_ceil - self.brief_floor) * 10))))
        # Hard rule from V4 prompt: structurally-broken design CANNOT
        # exceed brief_match=3, even if CLIP says color matches.
        if chest <= 2 or pelv <= 2:
            bm = min(bm, 3)

        is_valid = (chest >= 4 and pelv >= 4
                     and anat >= 5 and asm >= 5)
        struct_issues = []
        overflow_parts = []
        missing = []
        if chest < 4:  missing.append("top_panel")
        if pelv  < 4:  missing.append("bottom_panel")
        if diag["arm_l"] > 0: overflow_parts.append("left_arm")
        if diag["arm_r"] > 0: overflow_parts.append("right_arm")
        if diag["head"]  > 0: overflow_parts.append("head_neck")
        if diag["leg"]   > 0: overflow_parts.append("legs")
        if diag["top3_frac"] < 0.70:
            struct_issues.append(f"fragmented_top3_frac_{diag['top3_frac']:.2f}")
        return JudgeResult.from_dict({
            "chest_coverage": chest, "pelvic_coverage": pelv,
            "anatomy_clean": anat, "assembly_quality": asm,
            # CV can't judge aesthetics. Neutral 7s so the aesthetic
            # weight in the reward formula contributes a constant
            # (effectively zero gradient). brief_match carries the
            # learnable signal beyond structural.
            "aesthetic": 7, "color_harmony": 7,
            "proportion": 7, "silhouette": 7,
            "brief_match": bm,
            "is_valid_swimsuit": is_valid,
            "validity_score": round((chest + pelv + anat + asm) / 4),
            "aesthetic_score": 7,
            "structural_issues": struct_issues,
            "anatomical_overflow": overflow_parts,
            "missing_required_parts": missing,
            "style_descriptors": [],
            "overall_assessment": (
                f"CV chest_cov={diag['chest_cov']:.2f} "
                f"pelv_cov={diag['pelv_cov']:.2f} "
                f"overflow={diag['overflow_ratio']:.2f} "
                f"top3_frac={diag['top3_frac']:.2f} "
                f"brief_cos={cos:.3f}"),
        }, image_path=image_path,
           elapsed_s=time.time() - t0,
           backend=self.backend_name)


def make_judge(backend: str = "mock", **kwargs) -> VisionJudge:
    """`backend` in {'mock', 'vllm', 'clip', 'cv_clip'}."""
    if backend == "mock":
        return MockVisionJudge(**kwargs)
    if backend == "vllm":
        return VLLMVisionJudge(**kwargs)
    if backend == "clip":
        return CLIPVisionJudge(**kwargs)
    if backend == "cv_clip":
        return CVPlusCLIPJudge(**kwargs)
    raise ValueError(f"unknown backend: {backend}")


def _smoke_test() -> None:
    """Sanity test on real render images from the most recent batch.

    Walks newest -> oldest under tools/output looking for 01_front.png
    so the test keeps working as new batches arrive (the old hardcoded
    2026-05-17 path stopped resolving once WSL /tmp got wiped)."""
    import glob
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "output")
    # newest-first: glob across all dates, pick first 6 we can find
    all_fronts = sorted(
        glob.glob(os.path.join(root, "**", "01_front.png"), recursive=True),
        key=os.path.getmtime, reverse=True)
    candidates = all_fronts[:6]
    if not candidates:
        print("no render images found; falling back to dummy paths")
        candidates = [f"dummy_{i}.png" for i in range(6)]

    print(f"=== mock judge on {len(candidates)} images ===")
    judge = make_judge("mock")
    results = judge.judge_batch(candidates, verbose=True)
    n_pass = sum(r.is_valid_swimsuit for r in results)
    mean_v = sum(r.validity_score for r in results) / len(results)
    mean_a = sum(r.aesthetic_score for r in results) / len(results)
    print(f"\nmock summary: pass={n_pass}/{len(results)}  "
          f"mean validity={mean_v:.1f}  mean aesthetic={mean_a:.1f}")
    print(f"sample result dict (first):")
    print(json.dumps(results[0].to_dict(), indent=2, ensure_ascii=False))

    # cv_clip is cheap (~165ms/img, no service required) — always run.
    print("\n=== cv_clip judge on same images ===")
    try:
        cv = make_judge("cv_clip")
        cv_results = cv.judge_batch(
            candidates,
            briefs=["red triangle bikini"] * len(candidates),
            verbose=True)
        n_pass = sum(r.is_valid_swimsuit for r in cv_results)
        print(f"\ncv_clip summary: pass={n_pass}/{len(cv_results)}  "
              f"mean elapsed={sum(r.elapsed_s for r in cv_results)/len(cv_results)*1000:.0f}ms")
    except Exception as exc:
        print(f"cv_clip judge failed: {exc}")

    # Try real backend only if explicitly enabled
    if os.environ.get("VISION_JUDGE_RUN_REAL") == "1":
        print("\n=== real judge (vllm) on same images ===")
        try:
            real = make_judge("vllm")
            r_results = real.judge_batch(candidates, verbose=True)
            print(f"\nvllm summary: "
                  f"pass={sum(r.is_valid_swimsuit for r in r_results)}/"
                  f"{len(r_results)}")
        except Exception as exc:
            print(f"real judge failed (expected if vLLM not running): {exc}")


if __name__ == "__main__":
    _smoke_test()
