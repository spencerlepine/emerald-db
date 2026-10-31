"""Strings that live in C rather than in .inc scripts: UI text, battle
messages, Pokénav / match call profiles, Birch's intro, landmarks, union room,
contest and frontier text. Files whose strings are already attached to an
entity (dex text, move/item/ability/decoration descriptions, easy chat words,
berry text, names) are skipped."""
from __future__ import annotations

import re

from common import SRC, clean_text

SKIP = {"src/data/pokemon/pokedex_text.h", "src/data/text/move_descriptions.h", "src/data/text/item_descriptions.h",
        "src/data/decoration/description.h", "src/berry.c", "src/data/text/abilities.h", "src/data/text/nature_names.h",
        "src/data/text/species_names.h", "src/data/text/move_names.h", "src/data/text/ribbon_descriptions.h"}
PAT = re.compile(r"(?:static\s+)?const\s+u8\s+(\w+)\s*\[[^\]]*\]\s*=\s*_\((.*?)\)\s*;", re.S)
LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')


def extract() -> dict[str, list[dict]]:
    rows = []
    for p in sorted(list(SRC.glob("src/**/*.c")) + list(SRC.glob("src/**/*.h"))):
        rel = str(p.relative_to(SRC))
        if rel in SKIP or rel.startswith("src/data/easy_chat/"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if "_(" not in text:
            continue
        for m in PAT.finditer(text):
            raw = "".join(LIT.findall(m.group(2)))
            line = text.count("\n", 0, m.start()) + 1
            mc = re.match(r"gText_MatchCall([A-Za-z]+)_([A-Za-z]+)_(\w+)", m.group(1))
            rows.append({"text_id": m.group(1), "map_id": "", "source_file": rel, "source_line": line,
                         "speaker_label": mc.group(2).upper() if mc else "", "braille": "false",
                         "text": clean_text(raw), "text_raw": raw, "used_by_scripts": "",
                         "word_count": len(clean_text(raw).split()), "text_origin": "c",
                         "text_context": _context(rel, m.group(1))})
    return {"texts": rows}


def _context(rel: str, sym: str) -> str:
    name = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if "MatchCall" in sym:
        return "match_call_profile"
    if rel == "src/battle_message.c":
        return "battle_message"
    if rel == "src/strings.c":
        return "ui_string"
    return name


if __name__ == "__main__":
    d = extract()
    print(len(d["texts"]))
    import collections
    print(collections.Counter(r["text_context"] for r in d["texts"]).most_common(15))
