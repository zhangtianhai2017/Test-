"""Minimal repro: just subprocess _render_one_outfit. Nothing else."""
import subprocess
import sys
import time

t0 = time.time()
import os
ARGS = [sys.executable,
        "tools/_render_one_outfit.py",
        "tools/output/2026-05-25/regression_smoke/cup_piece/CUP_TRIANGLE_S/outfit.json",
        "/tmp/subproc_probe_b",
        "01_front"]
print("=== A: no capture (stdio inherits parent) ===")
rc = subprocess.run(ARGS, timeout=120)
print(f"  rc={rc.returncode}  dt={time.time()-t0:.1f}s\n")

print("=== B: capture_output, with start_new_session ===")
t1 = time.time()
rc = subprocess.run(ARGS, capture_output=True, text=True,
                     start_new_session=True, timeout=120)
print(f"  rc={rc.returncode}  dt={time.time()-t1:.1f}s")
print(f"  stderr: {rc.stderr[-200:]}")

print("=== C: capture_output, redirect to files ===")
t2 = time.time()
with open("/tmp/render_stdout.txt", "w") as so, open("/tmp/render_stderr.txt", "w") as se:
    rc = subprocess.run(ARGS, stdout=so, stderr=se, timeout=120)
print(f"  rc={rc.returncode}  dt={time.time()-t2:.1f}s")
print(f"  stderr file tail: {open('/tmp/render_stderr.txt').read()[-200:]}")

print("=== D: bash wrapper (exec replaces bash with python) ===")
t3 = time.time()
cmd = "exec " + " ".join(f"'{a}'" for a in ARGS)
rc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=120)
print(f"  rc={rc.returncode}  dt={time.time()-t3:.1f}s")
print(f"  stderr: {rc.stderr[-200:]}")
print(f"  png exists: {os.path.exists('/tmp/subproc_probe_b/01_front.png')}")

print("=== E: bash WITHOUT exec (bash keeps as middle parent) ===")
t4 = time.time()
cmd = " ".join(f"'{a}'" for a in ARGS)
rc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=120)
print(f"  rc={rc.returncode}  dt={time.time()-t4:.1f}s")
print(f"  stderr: {rc.stderr[-200:]}")
