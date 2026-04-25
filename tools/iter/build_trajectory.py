"""Stitch round_NN/contact_sheet.png across all rounds into a single
trajectory image for at-a-glance review of the iteration history."""
from __future__ import annotations

import argparse, glob, os, json
from PIL import Image, ImageDraw, ImageFont


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", required=True)
    ap.add_argument("--root", default="tools/output")
    args = ap.parse_args()

    seed_dir = os.path.join(args.root, f"iter_{args.seed}")
    rounds = sorted(glob.glob(os.path.join(seed_dir, "round_*")))
    if not rounds:
        print(f"no rounds in {seed_dir}"); return

    cells = []
    for r in rounds:
        round_idx = int(os.path.basename(r).split("_")[-1])
        sheet = os.path.join(r, "contact_sheet.png")
        crit = os.path.join(r, "critique.json")
        if not os.path.exists(sheet):
            continue
        cdata = {}
        if os.path.exists(crit):
            try:
                with open(crit) as f:
                    cdata = json.load(f)
            except Exception:
                pass
        n_issues = len(cdata.get("issues", [])) if cdata else 0
        gq = cdata.get("global_quality") if cdata else None
        cells.append({
            "round": round_idx,
            "sheet": sheet,
            "n_issues": n_issues,
            "gq": gq,
        })

    # Each cell shrunk to fixed thumb width
    thumb_w = 700
    images = [(c, Image.open(c["sheet"]).convert("RGB")) for c in cells]
    if not images:
        return
    aspect = images[0][1].size[1] / images[0][1].size[0]
    thumb_h = int(thumb_w * aspect)

    cols = 2
    rows = (len(images) + cols - 1) // cols
    head = 110
    label_h = 60
    pad = 14
    W = cols * thumb_w + (cols + 1) * pad
    H = head + rows * (thumb_h + label_h + pad) + pad
    out = Image.new("RGB", (W, H), (18, 18, 22))
    draw = ImageDraw.Draw(out)
    try:
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        f  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except Exception:
        fb = f = ImageFont.load_default()

    draw.text((20, 20), f"Iteration trajectory — seed '{args.seed}'", fill=(255, 220, 100), font=fb)
    draw.text((20, 60),
              "10 rounds of capture -> critique -> diagnose -> apply -> recapture",
              fill=(200, 200, 200), font=f)

    for i, (c, im) in enumerate(images):
        r, k = divmod(i, cols)
        x = pad + k * (thumb_w + pad)
        y = head + r * (thumb_h + label_h + pad)
        gq_str = f"  quality={c['gq']:.2f}" if c["gq"] is not None else ""
        draw.rectangle([(x, y), (x + thumb_w, y + label_h)], fill=(38, 38, 50))
        draw.text((x + 14, y + 8),
                  f"Round {c['round']:02d}{gq_str}",
                  fill=(255, 255, 255), font=fb)
        draw.text((x + 14, y + 36),
                  f"{c['n_issues']} issues critiqued",
                  fill=(180, 200, 220), font=f)
        out.paste(im.resize((thumb_w, thumb_h)), (x, y + label_h))

    out_path = os.path.join(seed_dir, "trajectory.png")
    out.save(out_path, optimize=True)
    print(f"wrote {out_path}  ({W}x{H})")


if __name__ == "__main__":
    main()
