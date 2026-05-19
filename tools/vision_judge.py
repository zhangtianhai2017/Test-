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


@dataclass
class JudgeResult:
    is_valid_swimsuit:       bool
    validity_score:          int   # 0-10
    aesthetic_score:         int   # 0-10
    structural_issues:       list[str]
    anatomical_overflow:     list[str]
    missing_required_parts:  list[str]
    style_descriptors:       list[str]
    overall_assessment:      str
    # ---- metadata (not from the model) ----
    image_path:              str = ""
    elapsed_s:               float = 0.0
    backend:                 str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict, image_path: str = "",
                  elapsed_s: float = 0.0, backend: str = "") -> "JudgeResult":
        return cls(
            is_valid_swimsuit=bool(d.get("is_valid_swimsuit", False)),
            validity_score=int(d.get("validity_score", 0)),
            aesthetic_score=int(d.get("aesthetic_score", 0)),
            structural_issues=list(d.get("structural_issues", [])),
            anatomical_overflow=list(d.get("anatomical_overflow", [])),
            missing_required_parts=list(d.get("missing_required_parts", [])),
            style_descriptors=list(d.get("style_descriptors", [])),
            overall_assessment=str(d.get("overall_assessment", "")),
            image_path=image_path,
            elapsed_s=elapsed_s,
            backend=backend,
        )


# ---------------------------------------------------------------------------
# Prompt — drives the model toward structural-validity-only judgment
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """You are inspecting a 3D rendered image of a swimsuit on a mannequin.
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
            max_tokens=400,
        )
        raw = response.choices[0].message.content or ""
        parsed = _extract_json(raw)
        return JudgeResult.from_dict(
            parsed,
            image_path=image_path,
            elapsed_s=time.time() - t0,
            backend=self.backend_name,
        )


def _extract_json(text: str) -> dict:
    """The model is told to emit pure JSON, but real responses sometimes
    wrap it in ``` fences or add a stray sentence.  Pull the first
    {...} block, decode."""
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
