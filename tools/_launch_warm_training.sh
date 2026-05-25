#!/usr/bin/env bash
# Launch warm-start training that:
#   - survives PowerShell-WSL session exit (use Start-Process to babysit)
#   - writes a _PID file so caller can kill cleanly
#   - writes a _DONE file (with exit code) when finished, normally or not
#   - traps signals so even on crash / kill the _DONE marker lands
set -u

cd /mnt/c/Users/Administrator/Test-

LOGFILE="${LOGFILE:-tools/output/2026-05-25/_rl_warm.log}"
PIDFILE="${PIDFILE:-tools/output/2026-05-25/_rl_warm.pid}"
DONEFILE="${DONEFILE:-tools/output/2026-05-25/_rl_warm.done}"
RESUME="${RESUME:-tools/output/2026-05-24/2050_rl_run/generator_final.pt}"
ITERS="${ITERS:-60}"
BATCH="${BATCH:-32}"
CKPT_EVERY="${CKPT_EVERY:-5}"

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

python -u tools/rl_runner.py \
  --iters "$ITERS" --batch "$BATCH" \
  --hidden-dim 128 --encoder sbert \
  --judge cv_clip \
  --w-sym 1.0 --w-rl 0.05 \
  --entropy-coef 0.5 \
  --batch-div-coef 1.0 --geom-var-coef 1.0 \
  --hue-circ-coef 1.0 --brief-arch-align-coef 1.0 \
  --resume "$RESUME" \
  >> "$LOGFILE" 2>&1
