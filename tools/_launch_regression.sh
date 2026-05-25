#!/usr/bin/env bash
set -u
cd /mnt/c/Users/Administrator/Test-

OUT_DIR="${OUT_DIR:-tools/output/2026-05-25/p11_regression}"
LOG="${LOG:-${OUT_DIR}/_regression.log}"
DONE="${DONE:-${OUT_DIR}/_regression.done}"
PID="${PID:-${OUT_DIR}/_regression.pid}"

mkdir -p "$OUT_DIR"
rm -f "$DONE" "$PID"

cleanup() {
    local rc=$?
    echo "rc=$rc at $(date -Is)" > "$DONE"
}
trap cleanup EXIT INT TERM
echo $$ > "$PID"

source ~/venvs/swim-train/bin/activate
python -u tools/library_regression_render.py \
    --out-dir "$OUT_DIR" \
    --kinds cup_piece,bottom_piece,accessory,hardware \
    >> "$LOG" 2>&1
