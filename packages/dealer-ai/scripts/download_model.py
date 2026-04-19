"""Download a default Qwen GGUF model into ./models/.

Usage (on a machine with HF access):
    python scripts/download_model.py                 # default: 1.5B Q4_K_M
    python scripts/download_model.py 0.5B
    python scripts/download_model.py 3B
    python scripts/download_model.py 7B
"""
from __future__ import annotations

import sys
from pathlib import Path

MODELS = {
    "0.5B": ("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "qwen2.5-0.5b-instruct-q4_k_m.gguf"),
    "1.5B": ("Qwen/Qwen2.5-1.5B-Instruct-GGUF", "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
    "3B":   ("Qwen/Qwen2.5-3B-Instruct-GGUF",   "qwen2.5-3b-instruct-q4_k_m.gguf"),
    "7B":   ("Qwen/Qwen2.5-7B-Instruct-GGUF",   "qwen2.5-7b-instruct-q4_k_m.gguf"),
}


def main() -> int:
    size = sys.argv[1] if len(sys.argv) > 1 else "1.5B"
    if size not in MODELS:
        print(f"Unknown size {size!r}. Options: {list(MODELS)}")
        return 2
    repo, filename = MODELS[size]
    out_dir = Path(__file__).parent.parent / "models"
    out_dir.mkdir(exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("pip install huggingface_hub   # first")
        return 2
    print(f"Downloading {repo}/{filename} -> {out_dir}")
    path = hf_hub_download(repo_id=repo, filename=filename, local_dir=str(out_dir))
    print(f"\nDownloaded: {path}")
    print(f"\nRun:")
    print(f"    DEALER_AI_MODEL={path} python -m dealer_ai.main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
