#!/usr/bin/env bash
# Launch warm-start training that survives PowerShell-WSL session exit.
# Usage:  setsid bash tools/_launch_warm_training.sh &
# Or:     wsl bash -c 'setsid /mnt/c/Users/Administrator/Test-/tools/_launch_warm_training.sh </dev/null >/dev/null 2>&1 &'
set -u
cd /mnt/c/Users/Administrator/Test-

LOGFILE="${LOGFILE:-tools/output/2026-05-24/_rl_warm.log}"
RESUME="${RESUME:-tools/output/2026-05-24/2050_rl_run/generator_final.pt}"
ITERS="${ITERS:-60}"
BATCH="${BATCH:-32}"

mkdir -p "$(dirname "$LOGFILE")"

source ~/venvs/swim-train/bin/activate
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

exec python -u tools/rl_runner.py \
  --iters "$ITERS" --batch "$BATCH" \
  --hidden-dim 128 --encoder sbert \
  --judge cv_clip \
  --w-sym 1.0 --w-rl 0.05 \
  --entropy-coef 0.5 \
  --batch-div-coef 1.0 --geom-var-coef 1.0 \
  --hue-circ-coef 1.0 --brief-arch-align-coef 1.0 \
  --resume "$RESUME" \
  >> "$LOGFILE" 2>&1
