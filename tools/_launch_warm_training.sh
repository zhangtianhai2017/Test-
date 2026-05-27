#!/usr/bin/env bash
# Launch warm-start training that:
#   - survives PowerShell-WSL session exit (use Start-Process to babysit)
#   - writes a _PID file so caller can kill cleanly
#   - writes a _DONE file (with exit code) when finished, normally or not
#   - traps signals so even on crash / kill the _DONE marker lands
set -u

cd /mnt/c/Users/Administrator/Test-

LOGFILE="${LOGFILE:-tools/output/2026-05-26/_rl_warm.log}"
PIDFILE="${PIDFILE:-tools/output/2026-05-26/_rl_warm.pid}"
DONEFILE="${DONEFILE:-tools/output/2026-05-26/_rl_warm.done}"
RESUME="${RESUME:-tools/output/2026-05-24/2050_rl_run/generator_final.pt}"
ITERS="${ITERS:-60}"
BATCH="${BATCH:-32}"
CKPT_EVERY="${CKPT_EVERY:-5}"
LR="${LR:-5e-4}"
W_SYM="${W_SYM:-1.0}"
W_RL="${W_RL:-0.05}"
ENTROPY_COEF="${ENTROPY_COEF:-0.5}"
BATCH_DIV_COEF="${BATCH_DIV_COEF:-1.0}"
GEOM_VAR_COEF="${GEOM_VAR_COEF:-1.0}"
HUE_CIRC_COEF="${HUE_CIRC_COEF:-1.0}"
BRIEF_ARCH_ALIGN_COEF="${BRIEF_ARCH_ALIGN_COEF:-1.0}"
JUDGE="${JUDGE:-cv_clip}"
N_TRUNK_LAYERS="${N_TRUNK_LAYERS:-8}"

mkdir -p "$(dirname "$LOGFILE")"
rm -f "$PIDFILE" "$DONEFILE"

cleanup() {
    local rc=$?
    echo "rc=$rc at $(date -Is)" > "$DONEFILE"
    echo "[wrapper] exit code $rc at $(date)" >> "$LOGFILE"
}
trap cleanup EXIT INT TERM

# write own PID for caller to kill
echo $$ > "$PIDFILE"

source ~/venvs/swim-train/bin/activate
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export CKPT_EVERY
# Subprocess-per-design render: Filament/Open3D state leaks across
# in-process renders within an iter cause SIGSEGV after the first
# successful design. Isolating each render in its own subprocess
# (matches generate_batch.py's existing pattern) avoids the leak.
# Cost: ~5s overhead per design (load_body_mesh + Open3D init).
export RL_RENDER_SUBPROC="${RL_RENDER_SUBPROC:-1}"
# Bypass any system proxy when talking to local vLLM
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

echo "[wrapper] start ITERS=$ITERS BATCH=$BATCH LR=$LR " \
     "JUDGE=$JUDGE N_TRUNK=$N_TRUNK_LAYERS " \
     "BATCH_DIV=$BATCH_DIV_COEF GEOM_VAR=$GEOM_VAR_COEF " \
     "at $(date)" >> "$LOGFILE"

python -u tools/rl_runner.py \
  --iters "$ITERS" --batch "$BATCH" --lr "$LR" \
  --hidden-dim 128 --encoder sbert \
  --judge "$JUDGE" \
  --n-trunk-layers "$N_TRUNK_LAYERS" \
  --w-sym "$W_SYM" --w-rl "$W_RL" \
  --entropy-coef "$ENTROPY_COEF" \
  --batch-div-coef "$BATCH_DIV_COEF" --geom-var-coef "$GEOM_VAR_COEF" \
  --hue-circ-coef "$HUE_CIRC_COEF" \
  --brief-arch-align-coef "$BRIEF_ARCH_ALIGN_COEF" \
  --resume "$RESUME" \
  >> "$LOGFILE" 2>&1
