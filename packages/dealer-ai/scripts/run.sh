#!/usr/bin/env bash
# Dev launcher — picks the right mode based on env/model presence.
set -euo pipefail

cd "$(dirname "$0")/.."

MODEL_DIR="${MODEL_DIR:-./models}"
DEFAULT_MODEL="qwen2.5-1.5b-instruct-q4_k_m.gguf"

if [[ -f "${MODEL_DIR}/${DEFAULT_MODEL}" ]]; then
  export DEALER_AI_MODEL="${MODEL_DIR}/${DEFAULT_MODEL}"
  echo ">>> Running with real LLM: $DEALER_AI_MODEL"
else
  export DEALER_AI_USE_MOCK=1
  echo ">>> No GGUF found at $MODEL_DIR/ — running with MOCK LLM"
  echo "    (download one via: python scripts/download_model.py 1.5B)"
fi

exec python -m dealer_ai.main "$@"
