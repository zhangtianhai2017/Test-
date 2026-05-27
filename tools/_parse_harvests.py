"""
Parse the two harvest markdown files into a unified tag list.

Inputs:
  docs/design/2026-05-27_design_vocabulary_harvest.md  (fashion, 6 axes, `- en / cn` format)
  docs/design/2026-05-27_game_industry_vocabulary_harvest.md  (game, 6 axes, `N. **en [cn]** — def — *ex*` format)

Output:
  Writes tools/tag_data.py with:
    - AXES list (6 unified generation axes)
    - TAGS list[Tag] — unified pool
    - CHAR_REFS list[CharRef] — eval-only (from game axis F)

Schema mapping (per docs/design/2026-05-27_schema_redesign_v3.md, slightly expanded to 6 axes):
  silhouette          = fashion Axis 1
  art_style           = fashion Axis 2 (punk/sci-fi/fantasy/mood/designer-coded/alt-subculture)
                       + fashion Axis 6 (references)
                       + game Axis A (game art tradition)
  cultural            = fashion Axis 2 cultural-historical sub-family
                       + game Axis D (cultural-mythological fusion)
  archetype           = game Axis B (character class)
  costume_convention  = fashion Axis 5 (body relationship)
                       + game Axis C (costume convention)
  material_vfx        = fashion Axis 3 (material)
                       + fashion Axis 4 (decoration)
                       + game Axis E (material/VFX)
"""
import re
from pathlib import Path
from collections import OrderedDict

ROOT = Path("/mnt/c/Users/Administrator/Test-")
FASHION_MD = ROOT / "docs/design/2026-05-27_design_vocabulary_harvest.md"
GAME_MD = ROOT / "docs/design/2026-05-27_game_industry_vocabulary_harvest.md"
OUT_PY = ROOT / "tools/tag_data.py"

AXES = [
    "silhouette",
    "art_style",
    "cultural",
    "archetype",
    "costume_convention",
    "material_vfx",
]


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def parse_fashion(text: str):
    """Fashion harvest format:
        ## Axis N — Name
        ### Sub-cat
        - english / 中文
        - english / 中文 (optional extra)
    """
    tags = []
    current_axis_no = None
    current_axis_name = None
    current_sub = None
    in_axis_section = False  # True only inside `## Axis N — Name` sections
    for line in text.splitlines():
        m = re.match(r"^##\s+Axis\s+(\d+)\s+[—-]\s+(.+)$", line)
        if m:
            current_axis_no = int(m.group(1))
            current_axis_name = m.group(2).strip()
            current_sub = None
            in_axis_section = True
            continue
        # any other `## ` heading (Usage notes / Source coverage / etc.) exits axis section
        if re.match(r"^##\s+", line) and not re.match(r"^##\s+Axis\s", line):
            in_axis_section = False
            continue
        if not in_axis_section:
            continue
        m = re.match(r"^###\s+(.+)$", line)
        if m:
            current_sub = m.group(1).strip()
            continue
        m = re.match(r"^-\s+(.+)$", line)
        if m and current_axis_no is not None:
            body = m.group(1).strip()
            # split on " / " — first segment EN, second CN (possibly with paren extra)
            if " / " in body:
                en_part, cn_part = body.split(" / ", 1)
            else:
                en_part, cn_part = body, body
            # strip parenthetical extras for definition; keep them in def_extra
            def_extra = ""
            m_paren_en = re.search(r"\(([^)]+)\)", en_part)
            if m_paren_en:
                def_extra = m_paren_en.group(1).strip()
                en_part = re.sub(r"\s*\([^)]*\)\s*", "", en_part).strip()
            m_paren_cn = re.search(r"\(([^)]+)\)", cn_part)
            if m_paren_cn:
                if def_extra:
                    def_extra += "; " + m_paren_cn.group(1).strip()
                else:
                    def_extra = m_paren_cn.group(1).strip()
                cn_part = re.sub(r"\s*\([^)]*\)\s*", "", cn_part).strip()
            tags.append({
                "source_axis": current_axis_no,
                "source_axis_name": current_axis_name,
                "sub": current_sub or "",
                "en": en_part.strip(),
                "cn": cn_part.strip(),
                "definition": def_extra,
                "examples": "",
            })
    return tags


def parse_game(text: str):
    """Game harvest format:
        ## AXIS A — Name
        ### A1. Sub-cat
        1. **English [中文]** — definition — *example*
        — or sometimes [中文]) missing or different bracket conventions
    """
    tags = []
    char_refs = []
    current_axis_letter = None
    current_axis_name = None
    current_sub = None
    in_char_table = False
    for line in text.splitlines():
        m = re.match(r"^##\s+AXIS\s+([A-F])\s+[—-]\s+(.+)$", line)
        if m:
            current_axis_letter = m.group(1)
            current_axis_name = m.group(2).strip()
            current_sub = None
            in_char_table = (current_axis_letter == "F")
            continue
        if not in_char_table:
            m = re.match(r"^###\s+([A-Z]\d+\.\s*)?(.+)$", line)
            if m:
                current_sub = m.group(2).strip()
                continue
            # N. **English [中文]** — def — *ex*
            m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*\s*(.*)$", line)
            if m and current_axis_letter:
                bold = m.group(1).strip()
                rest = m.group(2).strip()
                # split bold on [...] to get en + cn
                m_br = re.match(r"^(.+?)\s*\[([^\]]+)\]\s*$", bold)
                if m_br:
                    en = m_br.group(1).strip()
                    cn = m_br.group(2).strip()
                else:
                    en = bold
                    cn = bold
                # rest: "— definition — *example*"
                definition, examples = "", ""
                parts = re.split(r"\s*—\s*", rest)
                # drop leading empty
                parts = [p.strip() for p in parts if p.strip()]
                if parts:
                    definition = parts[0]
                if len(parts) > 1:
                    examples = parts[1].strip("*_ ")
                tags.append({
                    "source_axis": current_axis_letter,
                    "source_axis_name": current_axis_name,
                    "sub": current_sub or "",
                    "en": en,
                    "cn": cn,
                    "definition": definition,
                    "examples": examples,
                })
        else:
            # F: characters table row | # | **Name** | Game | Signature |
            m = re.match(r"^\|\s*\d+\s*\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
            if m:
                char_refs.append({
                    "name": m.group(1).strip(),
                    "game": m.group(2).strip(),
                    "signature": m.group(3).strip(),
                })
    return tags, char_refs


def map_fashion_to_unified_axis(t: dict) -> str:
    """Map a parsed fashion tag to one of the 6 unified axes."""
    src = t["source_axis"]
    sub = t["sub"].lower()
    if src == 1:
        return "silhouette"
    if src == 2:
        if "cultural" in sub or "historical" in sub:
            return "cultural"
        return "art_style"   # punk-family / sci-fi / fantasy / designer / alt-subculture / mood
    if src == 3:
        return "material_vfx"
    if src == 4:
        return "material_vfx"
    if src == 5:
        return "costume_convention"
    if src == 6:
        # cultural anchor moments → cultural; rest → art_style
        if "cultural" in sub or "anchor" in sub:
            return "cultural"
        return "art_style"
    return "art_style"


def map_game_to_unified_axis(t: dict) -> str:
    """Map a parsed game tag to one of the 6 unified axes."""
    src = t["source_axis"]
    if src == "A":
        return "art_style"
    if src == "B":
        return "archetype"
    if src == "C":
        return "costume_convention"
    if src == "D":
        return "cultural"
    if src == "E":
        return "material_vfx"
    return "art_style"


def main():
    fashion_text = FASHION_MD.read_text(encoding="utf-8")
    game_text = GAME_MD.read_text(encoding="utf-8")

    fashion_tags = parse_fashion(fashion_text)
    game_tags, char_refs = parse_game(game_text)
    print(f"parsed fashion={len(fashion_tags)} game_tags={len(game_tags)} "
          f"char_refs={len(char_refs)}")

    # Build unified tag pool with dedup by (axis, en_lower)
    unified = OrderedDict()
    for t in fashion_tags:
        axis = map_fashion_to_unified_axis(t)
        key = (axis, t["en"].lower())
        if key not in unified:
            unified[key] = {
                "axis": axis,
                "en": t["en"],
                "cn": t["cn"],
                "definition": t["definition"],
                "examples": t["examples"],
                "source": "fashion",
            }
    for t in game_tags:
        axis = map_game_to_unified_axis(t)
        key = (axis, t["en"].lower())
        if key not in unified:
            unified[key] = {
                "axis": axis,
                "en": t["en"],
                "cn": t["cn"],
                "definition": t["definition"],
                "examples": t["examples"],
                "source": "game",
            }
        else:
            # already exists — augment definition/examples if missing
            existing = unified[key]
            if not existing["definition"] and t["definition"]:
                existing["definition"] = t["definition"]
            if not existing["examples"] and t["examples"]:
                existing["examples"] = t["examples"]

    by_axis = {ax: [] for ax in AXES}
    for v in unified.values():
        by_axis[v["axis"]].append(v)

    print("\nUnified tag counts by axis:")
    for ax in AXES:
        print(f"  {ax:<22} {len(by_axis[ax])}")
    print(f"  TOTAL                  {sum(len(v) for v in by_axis.values())}")

    # Write tag_data.py
    lines = [
        '"""',
        "Design vocabulary tag pool — unified game + fashion harvest.",
        "Auto-generated by tools/_parse_harvests.py — DO NOT hand-edit.",
        "",
        "Sources:",
        "  docs/design/2026-05-27_design_vocabulary_harvest.md",
        "  docs/design/2026-05-27_game_industry_vocabulary_harvest.md",
        "",
        "Schema: docs/design/2026-05-27_schema_redesign_v3.md (6 generation axes).",
        '"""',
        "from dataclasses import dataclass",
        "",
        "",
        "AXES = [",
    ]
    for ax in AXES:
        lines.append(f'    "{ax}",')
    lines.append("]")
    lines.append("")
    lines.append("")
    lines.append("@dataclass(frozen=True)")
    lines.append("class Tag:")
    lines.append('    id: str')
    lines.append('    axis: str')
    lines.append('    en: str')
    lines.append('    cn: str')
    lines.append('    definition: str = ""')
    lines.append('    examples: str = ""')
    lines.append('    source: str = ""  # "fashion" or "game"')
    lines.append("")
    lines.append("")
    lines.append("@dataclass(frozen=True)")
    lines.append("class CharRef:")
    lines.append('    name: str')
    lines.append('    game: str')
    lines.append('    signature: str')
    lines.append("")
    lines.append("")
    lines.append("TAGS: list[Tag] = [")
    seen_ids = set()
    for ax in AXES:
        lines.append(f"    # ─── axis: {ax}  ({len(by_axis[ax])} tags) ───")
        for t in by_axis[ax]:
            slug = slugify(t["en"])
            tid = f"{ax}__{slug}"
            # dedup id (rare collision after slugify)
            base = tid
            i = 2
            while tid in seen_ids:
                tid = f"{base}_{i}"
                i += 1
            seen_ids.add(tid)
            en = t["en"].replace('"', '\\"')
            cn = t["cn"].replace('"', '\\"')
            df = t["definition"].replace('"', '\\"')
            ex = t["examples"].replace('"', '\\"')
            src = t["source"]
            lines.append(
                f'    Tag("{tid}", "{ax}", "{en}", "{cn}", '
                f'"{df}", "{ex}", "{src}"),'
            )
    lines.append("]")
    lines.append("")
    lines.append("")
    lines.append("CHAR_REFS: list[CharRef] = [")
    for c in char_refs:
        name = c["name"].replace('"', '\\"')
        game = c["game"].replace('"', '\\"')
        sig = c["signature"].replace('"', '\\"')
        lines.append(f'    CharRef("{name}", "{game}", "{sig}"),')
    lines.append("]")
    lines.append("")
    lines.append("")
    lines.append("def get_tags_by_axis(axis: str) -> list[Tag]:")
    lines.append('    return [t for t in TAGS if t.axis == axis]')
    lines.append("")
    lines.append("")
    lines.append("def get_all_tag_ids() -> list[str]:")
    lines.append('    return [t.id for t in TAGS]')
    lines.append("")
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append('    print(f"axes: {AXES}")')
    lines.append('    print(f"total tags: {len(TAGS)}")')
    lines.append('    print(f"char refs: {len(CHAR_REFS)}")')
    lines.append('    for ax in AXES:')
    lines.append('        n = len(get_tags_by_axis(ax))')
    lines.append('        print(f"  {ax:<22} {n}")')
    lines.append("")
    OUT_PY.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {OUT_PY}")


if __name__ == "__main__":
    main()
