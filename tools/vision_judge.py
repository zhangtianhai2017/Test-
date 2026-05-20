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
    # ---- observation phrases ----
    chest_observation:       str = ""
    pelvic_observation:      str = ""
    color_observation:       str = ""
    proportion_observation:  str = ""
    silhouette_observation:  str = ""
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
        # Derive is_valid Python-side; trust the 4 structural fields,
        # not the model's own is_valid_swimsuit (which can be lenient).
        if any(k in d for k in ("chest_coverage", "pelvic_coverage")):
            is_valid = (chest >= 5 and pelvic >= 5
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
            chest_observation=str(d.get("chest_observation", "")),
            pelvic_observation=str(d.get("pelvic_observation", "")),
            color_observation=str(d.get("color_observation", "")),
            proportion_observation=str(d.get("proportion_observation", "")),
            silhouette_observation=str(d.get("silhouette_observation", "")),
            image_path=image_path,
            elapsed_s=elapsed_s,
            backend=backend,
        )


# ---------------------------------------------------------------------------
# Prompt — drives the model toward structural-validity-only judgment
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """You are inspecting a 3D rendered image of a swimsuit on a mannequin.
Score 8 dimensions (each 0-10). Use the FULL 0-10 range; don't default
to 5 or 7 — push apart designs that are different.

For each dimension, give one short observation phrase, then the score.

STRUCTURAL (rejects design when too low):

1. chest_coverage   — how much fabric covers the BREAST area:
   0 = bare. 3 = pasties only. 5 = minimal cups. 7 = standard bikini
   cups. 9 = full bralette/halter. 10 = sports-bra coverage.

2. pelvic_coverage  — how much fabric covers the PELVIC / GROIN area:
   0 = completely bare. 3 = thong string only. 5 = micro bottom.
   7 = standard brief. 9 = full brief / boy-short. 10 = high waist.

3. anatomy_clean    — fabric stays on torso/hip/shoulder, no overflow
   onto arms/legs/head/neck or floating:
   0 = major overflow multiple body parts. 5 = minor overflow one
   region. 10 = all clean.

4. assembly_quality — straps connected, no clipping, no broken pieces:
   0 = many disconnected / clipping severe. 5 = one minor issue.
   10 = clean.

AESTHETIC (does not affect validity but drives quality reward):

5. color_harmony    — palette coherence between primary, secondary,
   pattern, hardware:
   0 = clashing / muddy colors. 3 = one color dominates awkwardly.
   5 = competent but unmemorable. 7 = clean coordinated palette.
   9 = striking complementary or analogous combo. 10 = exceptional.

6. proportion       — top-to-bottom balance, where the eye lands, how
   the silhouette flatters the body:
   0 = jarringly mismatched halves. 3 = one half visually overwhelms.
   5 = even but unsculpted. 7 = pleasing balance. 9 = intentional
   accent (e.g. high-cut bottom lengthening leg). 10 = exceptional.

7. silhouette       — outline shape against the body, how the design
   reads from across a room:
   0 = blob / no recognizable silhouette. 3 = one feature dominates
   incoherently. 5 = readable but generic. 7 = distinctive shape.
   9 = striking / signature silhouette. 10 = exceptional.

8. aesthetic        — overall visual appeal in one number:
   1 = visually broken. 5 = average / forgettable. 7 = pleasing.
   9 = strikingly attractive. 10 = exceptional.

A design counts as VALID only if chest_coverage >= 5 AND
pelvic_coverage >= 5 AND anatomy_clean >= 5 AND assembly_quality >= 5.
The 4 aesthetic dimensions never gate validity — they widen the
quality signal.

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

    @abstractmethod
    def judge(self, image_path: str) -> JudgeResult: ...

    def judge_batch(self, image_paths: Iterable[str],
                     verbose: bool = False) -> list[JudgeResult]:
        out: list[JudgeResult] = []
        for p in image_paths:
            r = self.judge(p)
            if verbose:
                tag = "PASS" if r.is_valid_swimsuit else "FAIL"
                print(f"  [{tag}] v={r.validity_score} a={r.aesthetic_score} "
                      f"{os.path.basename(p):40s} {r.elapsed_s:.2f}s "
                      f"({len(r.structural_issues)} issues)")
            out.append(r)
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

    def judge(self, image_path: str) -> JudgeResult:
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
                 max_image_dim: int = 480,
                 request_timeout: float = 60.0):
        from openai import OpenAI                  # lazy import
        self.client = OpenAI(base_url=base_url, api_key=api_key,
                              timeout=request_timeout)
        self.model = model
        self.max_image_dim = max_image_dim
        self.base_url = base_url

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

    def judge(self, image_path: str) -> JudgeResult:
        t0 = time.time()
        data_url = self._encode_image(image_path)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": data_url}},
                    {"type": "text", "text": JUDGE_PROMPT},
                ],
            }],
            temperature=0.0,    # deterministic structural judgement
            max_tokens=1200,    # V3 schema has ~25 keys (8 dims x 2 + legacy)
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

def make_judge(backend: str = "mock", **kwargs) -> VisionJudge:
    """`backend` in {'mock', 'vllm'}."""
    if backend == "mock":
        return MockVisionJudge(**kwargs)
    if backend == "vllm":
        return VLLMVisionJudge(**kwargs)
    raise ValueError(f"unknown backend: {backend}")


def _smoke_test() -> None:
    """Sanity test on real render images from the most recent batch."""
    import glob
    candidates = sorted(glob.glob(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tools", "output", "2026-05-17",
                      "*_diverse_batch_v2_8x15", "*/*/01_front.png"),
        recursive=False))[:6]
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
