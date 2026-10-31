"""Compare what is in database/ against what exists in the pokeemerald source.

    python3 tools/coverage.py      # prints the report and rewrites progress/COVERAGE.md

Each metric is (game count, database count). Automatic metrics come from the
source tree; "curated" metrics measure the hand-written lore layer that the
checklist in progress/CHECKLIST.md tracks.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATABASE_DIR, REPO_DIR, SRC, read, read_csv  # noqa: E402


def t(name):
    return read_csv(DATABASE_DIR / f"{name}.csv")


def main() -> None:
    ents = t("entities")
    by_type = Counter(e["entity_type"] for e in ents)
    texts, scripts, dialogue, flags = t("texts"), t("scripts"), t("dialogue"), t("story_flags")
    events = t("map_events")
    rows = []

    def add(area, metric, game, db, note=""):
        pct = (100.0 * db / game) if game else 100.0
        rows.append((area, metric, game, db, pct, note))

    sp = len(re.findall(r"^\s*\[SPECIES_\w+\]\s*=", read("src/data/pokemon/species_info.h"), re.M)) - 1
    add("Pokémon", "species (incl. 25 old Unown placeholders)", sp, by_type["species"])
    add("Pokémon", "moves", len(re.findall(r"^\s*\[MOVE_\w+\]\s*=", read("src/data/battle_moves.h"), re.M)) - 1, by_type["move"])
    add("Pokémon", "abilities", len(re.findall(r"\[ABILITY_\w+\]\s*=\s*_", read("src/data/text/abilities.h"))) - 1, by_type["ability"])
    add("Pokémon", "types", 18, by_type["game_type"])
    add("Items", "items", len(re.findall(r"^\s*\[ITEM_\w+\]\s*=", read("src/data/items.h"), re.M)) - 1, by_type["item"])
    add("Trainers", "trainers", len(re.findall(r"^\s*\[TRAINER_\w+\]\s*=", read("src/data/trainers.h"), re.M)) - 1, by_type["trainer"])
    add("Trainers", "trainer classes", len(re.findall(r"\[TRAINER_CLASS_\w+\]", read("src/data/text/trainer_class_names.h"))), by_type["trainer_class"])
    add("World", "maps", len(list((SRC / "data/maps").glob("*/map.json"))), by_type["map"])
    add("World", "region map sections", len(json.loads(read("src/data/region_map/region_map_sections.json"))["map_sections"]), by_type["location"])
    n_obj = sum(len(json.loads(p.read_text()).get("object_events") or []) for p in (SRC / "data/maps").glob("*/map.json"))
    add("World", "map object events (NPCs/props)", n_obj, by_type["npc"])
    n_ev = sum(len(d.get("object_events") or []) + len(d.get("coord_events") or []) + len(d.get("bg_events") or [])
               for d in (json.loads(p.read_text()) for p in (SRC / "data/maps").glob("*/map.json")))
    add("World", "all map events (objects+triggers+signs)", n_ev, len(events))
    add("World", "overworld sprite ids", len(re.findall(r"\[OBJ_EVENT_GFX_\w+\]\s*=", read("src/data/object_events/object_event_graphics_info_pointers.h"))) + 16, by_type["object_graphics"])
    add("Text", "text blocks (.string labels)", len(texts), len(texts), "texts.csv is the source of truth for dialogue")
    used = sum(1 for x in texts if x.get("used_by_scripts"))
    add("Text", "texts referenced by an overworld script", len(texts), used, "rest are used from C code / indirectly")
    npcs_with = len({d["speaker_entity_id"] for d in dialogue if d["speaker_entity_id"].startswith("npc:")})
    add("Text", "NPCs with attributed dialogue", by_type["npc"], npcs_with, "all object events incl. props")
    props = ("item-ball", "cuttable-tree", "breakable-rock", "pushable-boulder", "berry-tree", "doll", "cushion", "fossil", "truck",
             "moving-box", "boat", "ss-tidal", "cable-car", "statue", "submarine", "shadow", "birchs-bag", "var-")
    people = {e["id"] for e in ents if e["entity_type"] == "npc" and not any(p in e.get("graphics", "") for p in props)}
    spoke = {d["speaker_entity_id"] for d in dialogue}
    add("Text", "people NPCs (non-prop sprites) with attributed dialogue", len(people), len(people & spoke),
        "rest: scripted cutscene actors without their own script, or NPCs whose text is shown from C")
    add("Scripts", "script labels", len(scripts), len(scripts))
    add("Scripts", "flags + vars", len(flags), len(flags))
    pngs = len(list(SRC.glob("graphics/**/*.png"))) + len(list(SRC.glob("data/tilesets/**/*.png")))
    add("Art", "PNG art files inventoried", pngs, sum(1 for a in t("art_assets") if a["kind"] != "battle_animation"))

    # curated lore layer
    speakers = Counter(x["speaker_label"] for x in texts if x["speaker_label"] and x.get("text_origin") != "c")
    trainer_names = {n.strip() for e in ents if e["entity_type"] in ("trainer", "facility_trainer")
                     for n in e.get("game_name", "").upper().split("&")}
    chars = [e for e in ents if e["entity_type"] == "character"]
    aliases = set()
    for c in chars:
        aliases.update(a.strip().upper() for a in (c.get("speaker_labels") or "").split("|") if a.strip())
    named = [s for s, n in speakers.items() if n >= 2 and not s.startswith("{")]
    add("Lore (curated)", "named speakers (>=2 lines) mapped to a character", len(named), sum(1 for s in named if s in aliases))
    add("Lore (curated)", "named speakers mapped to a character or a trainer name", len(named), sum(1 for s in named if s in aliases or s in trainer_names),
        "unmapped: " + ", ".join(sorted(s for s in named if s not in aliases and s not in trainer_names))[:300])
    add("Lore (curated)", "story characters", "", len(chars))
    add("Lore (curated)", "organizations", "", by_type["organization"])
    tl = t("timeline_events")
    add("Lore (curated)", "story timeline events", "", len(tl))
    locs = [e for e in ents if e["entity_type"] == "location" and e.get("on_region_map") == "true"]
    add("Lore (curated)", "region-map locations with lore written", len(locs), sum(1 for e in locs if e.get("history")))
    prog = t("area_progression")
    add("Balance", "maps in area_progression (auto)", "", len(prog))
    add("Balance", "area_progression rows with chapter/badges assigned", len(prog), sum(1 for p in prog if p.get("badges_expected")))
    add("Balance", "area_progression rows with gating (requires) written", len(prog), sum(1 for p in prog if p.get("requires")))

    lines = ["# Coverage report", "", "Generated by `python3 tools/coverage.py`; do not edit by hand.", "",
             f"pokeemerald: `{_commit()}`", "", "| Area | Metric | In game | In DB | % | Note |", "|---|---|---:|---:|---:|---|"]
    for area, metric, game, db, pct, note in rows:
        p = f"{pct:.0f}%" if game != "" else "—"
        lines.append(f"| {area} | {metric} | {game} | {db} | {p} | {note} |")
    out = "\n".join(lines) + "\n"
    (REPO_DIR / "progress" / "COVERAGE.md").write_text(out)
    print(out)


def _commit():
    for r in read_csv(DATABASE_DIR / "build_info.csv"):
        if r["key"] == "pokeemerald_commit":
            return r["value"]
    return "unknown"


if __name__ == "__main__":
    main()
