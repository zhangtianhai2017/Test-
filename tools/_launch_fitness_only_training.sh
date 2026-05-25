#!/usr/bin/env bash
# Fitness-only training: no rendering, no visual judge, just symbolic
# gradient signal. Useful when Open3D is unstable in this WSL session
# (Filament/EGL state corruption when rl_runner parent has Open3D + CLIP
# loaded and tries to subprocess more Open3D inits → SIGSEGV).
#
# Trade-off: NN learns coverage / ratio / color-harmony only. No archetype
# semantic alignment, no fabric-on-body-area visual signal. Use as a
# warm-up before a real cv_clip retrain once render is stable again.
#
# Writes _PID + _DONE markers like _launch_warm_training.sh.
set -u

cd /mnt/c/Users/Administrator/Test-

LOGFILE="${LOGFILE:-tools/output/2026-05-25/_fitness_warm.log}"
PIDFILE="${PIDFILE:-tools/output/2026-05-25/_fitness_warm.pid}"
DONEFILE="${DONEFILE:-tools/output/2026-05-25/_fitness_warm.done}"
RESUME="${RESUME:-tools/output/2026-05-24/2050_rl_run/generator_final.pt}"
ITERS="${ITERS:-200}"
BATCH="${BATCH:-32}"
CKPT_EVERY="${CKPT_EVERY:-20}"

mkdir -p "$(dirname "$LOGFILE")"
rm -f "$PIDFILE" "$DONEFILE"

cleanup() {
    local rc=$?
    echo "rc=$rc at $(date -Is)" > "$DONEFILE"
    echo "[wrapper] exit code $rc at $(date)" >> "$LOGFILE"
}
trap cleanup EXIT INT TERM

echo $$ > "$PIDFILE"

source ~/venvs/swim-train/bin/activate
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export CKPT_EVERY
# Skip render entirely. judge=mock + w_rl=0 mean NN only sees the
# symbolic_fitness gradient. Each iter is now ~2s (no render, no judge).
export SKIP_RENDER=1

python -u tools/rl_runner.py \
  --iters "$ITERS" --batch "$BATCH" \
  --hidden-dim 128 --encoder sbert \
  --judge mock \
  --w-sym 1.0 --w-rl 0.0 \
  --entropy-coef 0.5 \
  --batch-div-coef 1.0 --geom-var-coef 1.0 \
  --hue-circ-coef 1.0 --brief-arch-align-coef 1.0 \
  --resume "$RESUME" \
  >> "$LOGFILE" 2>&1
