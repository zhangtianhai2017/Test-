"""
Build a self-contained static HTML index for a dated output folder.

Usage:
    # one task folder
    python3 tools/build_html_index.py tools/output/2026-04-29/0820_diverse_seeds

    # whole day (rebuilds the day's top-level index too)
    python3 tools/build_html_index.py --day tools/output/2026-04-29

The script does NOT use any external CSS/JS — everything is inlined,
so the generated index.html opens correctly straight from the local
filesystem or via GitHub raw / GitHub Pages without any build step.

It scans the task folder for:
  - all PNG images at depth 1 + 2 (so per-seed subfolders work)
  - report.md (markdown rendered inline as <pre>)
  - matching seeds in assets/seeds/<basename>.json (optional)

Layout:
  - One header row with the task title + breadcrumb back to the day index
  - One stats card (counts of images, archetypes, fitness range pulled
    from report.md when present)
  - Per-folder section: <task>/<seed>/ each gets its own card with the
    8 view PNGs as thumbnails. Clicking a thumbnail enlarges via a
    minimal lightbox (vanilla JS).
"""
from __future__ import annotations

import argparse, glob, json, os, sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS_DIR = os.path.join(ROOT, "assets", "seeds")


CSS = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                Helvetica, Arial, sans-serif;
  margin: 0; padding: 0; background: #14161c; color: #d8dde8;
}
header {
  position: sticky; top: 0; z-index: 10;
  background: #1d2030; border-bottom: 1px solid #2a2f44;
  padding: 14px 22px;
}
header h1 { margin: 0; font-size: 20px; color: #ffd166; font-weight: 600; }
header .crumbs a { color: #99c2ff; text-decoration: none; }
header .crumbs { font-size: 12px; opacity: 0.8; margin-top: 4px; }

.summary {
  margin: 22px; padding: 14px; background: #1d2030; border-radius: 8px;
  border: 1px solid #2a2f44; font-size: 13px;
}
.summary table { width: 100%; border-collapse: collapse; }
.summary th, .summary td {
  padding: 6px 8px; text-align: left;
  border-bottom: 1px solid #2a2f44;
}
.summary th { color: #99c2ff; font-weight: 500; font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.04em; }
.summary tr:last-child td { border-bottom: none; }

.section { margin: 22px; }
.section h2 { color: #88e0a0; font-size: 16px; font-weight: 500;
  margin: 14px 0 10px 0; }

.cards { display: grid; gap: 14px;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
.card {
  background: #1d2030; border: 1px solid #2a2f44; border-radius: 8px;
  padding: 12px; overflow: hidden;
}
.card h3 { margin: 0 0 4px 0; font-size: 14px; color: #e8f0ff; }
.card .meta { font-size: 11px; color: #8090b0; margin-bottom: 8px; }
.card .meta b { color: #ffe399; font-weight: 600; }
.thumbs { display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 4px; }
.thumbs a { display: block; }
.thumbs img {
  width: 100%; height: 110px; object-fit: cover;
  background: #0c0e16; border-radius: 4px;
  border: 1px solid #2a2f44;
  cursor: pointer; transition: transform 0.1s;
}
.thumbs img:hover { transform: scale(1.05); border-color: #99c2ff; }
.thumbs span { display: block; font-size: 9px; color: #6b7895;
  text-align: center; margin-top: 2px; }

#lightbox {
  display: none; position: fixed; inset: 0;
  background: rgba(8, 10, 16, 0.95); z-index: 100;
  align-items: center; justify-content: center; padding: 30px;
  cursor: pointer;
}
#lightbox.show { display: flex; }
#lightbox img { max-width: 90vw; max-height: 90vh; object-fit: contain;
  border-radius: 8px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7); }
#lightbox .lb-cap { position: absolute; bottom: 20px; left: 0; right: 0;
  text-align: center; color: #d8dde8; font-size: 13px; }

.report {
  margin: 22px; padding: 14px;
  background: #181b25; border: 1px solid #2a2f44; border-radius: 8px;
  font-family: ui-monospace, SF Mono, Consolas, monospace;
  font-size: 12px; white-space: pre-wrap; word-break: break-word;
  color: #c0c8d8; max-height: 320px; overflow: auto;
}

a { color: #99c2ff; }
"""

LIGHTBOX_JS = """
function showLB(src, cap) {
  var lb = document.getElementById('lightbox');
  lb.querySelector('img').src = src;
  lb.querySelector('.lb-cap').textContent = cap || '';
  lb.classList.add('show');
}
function hideLB() {
  document.getElementById('lightbox').classList.remove('show');
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') hideLB();
});
"""


def _seed_meta(seed_basename: str) -> dict | None:
    p = os.path.join(SEEDS_DIR, f"{seed_basename}.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def _genome_summary(seed: dict | None) -> str:
    if not seed:
        return ""
    g = seed.get("genome", {})
    bits = []
    if g.get("style_archetype"):
        bits.append(f"style={g['style_archetype']}")
    if g.get("pattern"):
        bits.append(f"pattern={g['pattern']}")
    if g.get("fabric_source"):
        bits.append(f"src={g['fabric_source']}")
    if g.get("fabric_weave"):
        bits.append(f"weave={g['fabric_weave']}")
    return "  ".join(bits)


def _scan_task(task_dir: str) -> dict:
    """Discover seeds (subfolders) + their image lists."""
    out = {"seeds": [], "stray_pngs": [], "report_md": None}
    for entry in sorted(os.listdir(task_dir)):
        full = os.path.join(task_dir, entry)
        if entry == "report.md":
            out["report_md"] = full
            continue
        if entry.endswith(".png") and os.path.isfile(full):
            out["stray_pngs"].append(full)
            continue
        if entry == "renders" and os.path.isdir(full):
            for sub in sorted(os.listdir(full)):
                sub_path = os.path.join(full, sub)
                if not os.path.isdir(sub_path):
                    continue
                pngs = sorted(glob.glob(os.path.join(sub_path, "*.png")))
                if pngs:
                    out["seeds"].append({"name": sub, "dir": sub_path,
                                            "pngs": pngs})
        elif os.path.isdir(full):
            pngs = sorted(glob.glob(os.path.join(full, "*.png")))
            if pngs:
                out["seeds"].append({"name": entry, "dir": full, "pngs": pngs})
    return out


def _rel(path: str, start: str) -> str:
    """Browser-friendly relative path."""
    return os.path.relpath(path, start).replace(os.sep, "/")


def build_task_index(task_dir: str) -> str:
    """Generate index.html inside `task_dir`. Returns its path."""
    task_dir = os.path.abspath(task_dir)
    info = _scan_task(task_dir)
    task_name = os.path.basename(task_dir)
    day_dir = os.path.dirname(task_dir)
    day_name = os.path.basename(day_dir)

    title = f"{task_name} — {day_name}"

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{title}</title>",
        f"<style>{CSS}</style>",
        "</head><body>",
        "<header>",
        f"<h1>{task_name}</h1>",
        f"<div class='crumbs'>"
        f"<a href='../index.html'>{day_name}</a> &rsaquo; {task_name}</div>",
        "</header>",
    ]

    # Stats
    n_seeds = len(info["seeds"])
    n_pngs = sum(len(s["pngs"]) for s in info["seeds"]) + len(info["stray_pngs"])
    parts.append("<div class='summary'><table>")
    parts.append("<tr><th>seeds</th><th>images</th><th>folder</th></tr>")
    parts.append(f"<tr><td>{n_seeds}</td><td>{n_pngs}</td>"
                  f"<td><code>{task_dir}</code></td></tr>")
    parts.append("</table></div>")

    # Stray top-level PNGs (overview, headlines)
    if info["stray_pngs"]:
        parts.append("<div class='section'><h2>Top-level images</h2>")
        parts.append("<div class='cards'>")
        for p in info["stray_pngs"]:
            rel = _rel(p, task_dir)
            parts.append(
                f"<div class='card'><h3>{os.path.basename(p)}</h3>"
                f"<a href='{rel}'><img src='{rel}' "
                f"style='width:100%;max-height:480px;object-fit:contain;'/></a>"
                f"</div>")
        parts.append("</div></div>")

    # Per-seed cards
    if info["seeds"]:
        parts.append("<div class='section'><h2>"
                      f"Seeds ({n_seeds})</h2>")
        parts.append("<div class='cards'>")
        for s in info["seeds"]:
            seed_meta = _seed_meta(s["name"])
            summ = _genome_summary(seed_meta)
            parts.append(
                f"<div class='card'><h3>{s['name']}</h3>"
                f"<div class='meta'>{summ}</div>"
                f"<div class='thumbs'>")
            for png in s["pngs"]:
                rel = _rel(png, task_dir)
                view_label = os.path.basename(png).replace(".png", "")
                parts.append(
                    f"<a onclick=\"showLB('{rel}', '{s['name']} / "
                    f"{view_label}'); return false;\" href='{rel}'>"
                    f"<img loading='lazy' src='{rel}' alt='{view_label}'/>"
                    f"<span>{view_label}</span></a>")
            parts.append("</div></div>")
        parts.append("</div></div>")

    # Report (verbatim Markdown — the browser renders it as preformatted text)
    if info["report_md"]:
        with open(info["report_md"]) as f:
            md = f.read()
        parts.append("<div class='section'><h2>report.md</h2>")
        parts.append(f"<div class='report'>{_html_escape(md)}</div>")
        parts.append("</div>")

    # Lightbox
    parts.append(
        "<div id='lightbox' onclick='hideLB()'>"
        "<img src=''/><div class='lb-cap'></div></div>"
        f"<script>{LIGHTBOX_JS}</script>")

    parts.append("</body></html>")
    out_path = os.path.join(task_dir, "index.html")
    with open(out_path, "w") as f:
        f.write("".join(parts))
    return out_path


def build_day_index(day_dir: str) -> str:
    """Generate the day-level index.html that lists all tasks (HHMM_*)."""
    day_dir = os.path.abspath(day_dir)
    day_name = os.path.basename(day_dir)
    tasks = sorted(d for d in os.listdir(day_dir)
                   if os.path.isdir(os.path.join(day_dir, d))
                   and d != "__pycache__")

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{day_name} — output index</title>",
        f"<style>{CSS}</style>",
        "</head><body>",
        f"<header><h1>{day_name}</h1>"
        f"<div class='crumbs'>"
        f"<a href='../index.html'>tools/output</a> &rsaquo; {day_name}"
        f"</div></header>",
        "<div class='section'><h2>Tasks</h2><div class='cards'>"
    ]
    for t in tasks:
        full = os.path.join(day_dir, t)
        info = _scan_task(full)
        n_seeds = len(info["seeds"])
        n_pngs = sum(len(s["pngs"]) for s in info["seeds"]) + len(info["stray_pngs"])
        parts.append(
            f"<div class='card'><h3><a href='{t}/index.html'>{t}</a></h3>"
            f"<div class='meta'>{n_seeds} seed dirs · {n_pngs} images</div>"
            f"</div>")
    parts.append("</div></div></body></html>")

    out_path = os.path.join(day_dir, "index.html")
    with open(out_path, "w") as f:
        f.write("".join(parts))
    return out_path


def build_root_index(root_dir: str) -> str:
    """Top-level tools/output/index.html — lists each YYYY-MM-DD."""
    root_dir = os.path.abspath(root_dir)
    days = sorted([d for d in os.listdir(root_dir)
                   if os.path.isdir(os.path.join(root_dir, d))
                   and len(d) == 10 and d.count("-") == 2],
                  reverse=True)
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>tools/output</title>",
        f"<style>{CSS}</style>",
        "</head><body>",
        "<header><h1>tools/output</h1>"
        "<div class='crumbs'>dated runs (newest first)</div></header>",
        "<div class='section'><h2>By day</h2><div class='cards'>"
    ]
    for d in days:
        full = os.path.join(root_dir, d)
        n_tasks = sum(1 for x in os.listdir(full)
                       if os.path.isdir(os.path.join(full, x)))
        parts.append(
            f"<div class='card'><h3><a href='{d}/index.html'>{d}</a></h3>"
            f"<div class='meta'>{n_tasks} tasks</div></div>")
    parts.append("</div></div></body></html>")
    out_path = os.path.join(root_dir, "index.html")
    with open(out_path, "w") as f:
        f.write("".join(parts))
    return out_path


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="task folder OR day folder")
    ap.add_argument("--day", help="rebuild day-level index too", action="store_true")
    ap.add_argument("--all", help="rebuild every dated subfolder under tools/output/",
                    action="store_true")
    args = ap.parse_args()

    output_root = os.path.join(ROOT, "tools", "output")
    if args.all:
        for day in sorted(os.listdir(output_root)):
            day_dir = os.path.join(output_root, day)
            if not (os.path.isdir(day_dir) and len(day) == 10
                    and day.count("-") == 2):
                continue
            for entry in os.listdir(day_dir):
                full = os.path.join(day_dir, entry)
                if os.path.isdir(full):
                    p = build_task_index(full)
                    print(f"  {p}")
            p = build_day_index(day_dir)
            print(f"  {p}")
        p = build_root_index(output_root)
        print(f"  {p}")
        return

    if args.path is None:
        print("usage: build_html_index.py <task_or_day_dir> [--day]", file=sys.stderr)
        sys.exit(1)

    target = os.path.abspath(args.path)
    base = os.path.basename(target)
    is_day = (len(base) == 10 and base.count("-") == 2)

    if is_day:
        for entry in sorted(os.listdir(target)):
            full = os.path.join(target, entry)
            if os.path.isdir(full):
                p = build_task_index(full)
                print(f"  task index: {p}")
        p = build_day_index(target)
        print(f"  day index:  {p}")
    else:
        p = build_task_index(target)
        print(f"  task index: {p}")
        if args.day:
            day_dir = os.path.dirname(target)
            p = build_day_index(day_dir)
            print(f"  day index:  {p}")

    p = build_root_index(output_root)
    print(f"  root index: {p}")


if __name__ == "__main__":
    main()
