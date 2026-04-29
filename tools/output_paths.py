"""
Dated output-path helper.

Use ``dated_dir(task_name)`` to get a path of the form

    tools/output/YYYY-MM-DD/HHMM_<task_name>/

and call it once per task. The helper creates the directory and
returns its path. Time prefix is fixed at first call per process so
all artifacts of one task share the same prefix.

Why: historical flat layout in tools/output/ became hard to navigate
once we accumulated ~30 subdirectories. Dating at the day level keeps
the working set small and lets the operator find "today's stuff"
without scanning everything.

Convention going forward (set 2026-04-29):
  - one task = one HHMM_<name> directory
  - subdirectories inside it for round_NN / views / etc. as before
  - top-level tools/output/ still hosts shared artifacts (cross-task
    galleries, headline images) that aren't tied to a single run

Existing flat directories under tools/output/ are NOT moved — commit
history and earlier docs still reference those paths.
"""
from __future__ import annotations

import os
from datetime import datetime

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools", "output")

# Captured at first import so siblings of one task share the same HHMM.
_PROCESS_NOW = datetime.now()


def dated_dir(task_name: str, *, create: bool = True,
                ts: datetime | None = None) -> str:
    """Return tools/output/YYYY-MM-DD/HHMM_<task_name>/ and create it."""
    when = ts or _PROCESS_NOW
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in task_name)
    path = os.path.join(ROOT, when.strftime("%Y-%m-%d"),
                          f"{when.strftime('%H%M')}_{safe}")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def today_root(*, create: bool = True) -> str:
    """Return tools/output/YYYY-MM-DD/ for today."""
    path = os.path.join(ROOT, _PROCESS_NOW.strftime("%Y-%m-%d"))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


if __name__ == "__main__":
    # Quick demo
    print("today root:", today_root(create=False))
    print("dated dir :", dated_dir("demo_task", create=False))
