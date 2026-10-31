"""Derived lore layer. Reads curated/*.csv (hand-written) plus extracted game
data and produces the link tables the wiki and later steps need:

- timeline_entities: every map / trainer / character / item / species / flag
  named on a curated timeline event.
- relationships for curated characters (battles_as, speaks_on, uses_sprite)
  and organizations (member_of via character rows).
- area_progression: per outdoor/dungeon map, wild + trainer level ranges and
  the first story chapter that visits it (curated rows add gating notes).
- location descriptions from the town/route sign text when no curated text exists.
"""
from __future__ import annotations

import re
from collections import defaultdict

from common import CURATED_DIR, read_csv, slug

PROGRESSION_TYPES = ("route", "town", "city", "underground", "underwater", "ocean-route")


def extract() -> dict[str, list[dict]]:
    import extract_maps, extract_scripts, extract_trainers
    maps = extract_maps.extract()
    scripts = extract_scripts.extract()
    trainers = extract_trainers.extract()
    events = read_csv(CURATED_DIR / "timeline_events.csv")
    rels, links, entities = [], [], []
    curated = read_csv(CURATED_DIR / "entities.csv")
    chars = [e for e in curated if e.get("entity_type") == "character"]
    for o in curated:
        if o.get("entity_type") == "organization" and o.get("home_map"):
            rels.append({"source_id": o["id"], "relationship": "based_in", "target_id": o["home_map"]})

    # ---- timeline links --------------------------------------------------------------
    first_chapter: dict[str, tuple[int, str, str]] = {}
    for ev in events:
        for col, role in (("map_ids", "location"), ("trainer_ids", "battle"), ("character_ids", "character"),
                          ("related_entity_ids", "involved")):
            for eid in [x for x in ev.get(col, "").split("|") if x]:
                links.append({"event_id": ev["id"], "entity_id": eid, "relationship": role})
                if col == "map_ids":
                    first_chapter.setdefault(eid, (int(ev["year"]), ev["id"], ev["release_year"]))
        for col in ("trigger_flag", "completion_flag"):
            if ev.get(col):
                links.append({"event_id": ev["id"], "entity_id": _flag_id(ev[col]), "relationship": col})

    # ---- characters ----------------------------------------------------------------------
    texts = scripts["texts"]
    label_maps = defaultdict(lambda: defaultdict(int))
    for t in texts:
        if t["speaker_label"] and t["map_id"]:
            label_maps[t["speaker_label"].upper()][t["map_id"]] += 1
    for c in chars:
        cid = c["id"]
        for tr in [x for x in c.get("trainer_ids", "").split("|") if x]:
            rels.append({"source_id": cid, "relationship": "battles_as", "target_id": tr})
        for g in [x for x in c.get("sprite_ids", "").split("|") if x]:
            rels.append({"source_id": cid, "relationship": "uses_sprite", "target_id": g})
        for org in [x for x in c.get("organization_ids", "").split("|") if x]:
            rels.append({"source_id": cid, "relationship": "member_of", "target_id": org})
        if c.get("home_map"):
            rels.append({"source_id": cid, "relationship": "lives_in", "target_id": c["home_map"]})
        total = 0
        for lab in [x.strip().upper() for x in c.get("speaker_labels", "").split("|") if x.strip()]:
            for m, n in label_maps.get(lab, {}).items():
                rels.append({"source_id": cid, "relationship": "speaks_on", "target_id": m})
                total += n
        entities.append({"id": cid, "named_dialogue_lines": total})

    # ---- area progression ----------------------------------------------------------------
    wild = defaultdict(list)
    for w in maps["wild_encounters"]:
        if w["map_id"]:
            wild[w["map_id"]].append((int(w["min_level"]), int(w["max_level"]), w["method"]))
    trainer_maps = defaultdict(set)
    for r in scripts["relationships"]:
        if r["relationship"] == "battled_on":
            trainer_maps[r["target_id"]].add(r["source_id"])
    tlevels = {}
    for e in trainers["entities"]:
        if e["entity_type"] == "trainer" and e.get("max_level"):
            tlevels[e["id"]] = (int(e["min_level"]), int(e["max_level"]))
    prog = []
    for m in maps["entities"]:
        if m["entity_type"] != "map":
            continue
        mid = m["id"]
        if m.get("collection") not in PROGRESSION_TYPES and mid not in wild and mid not in trainer_maps:
            continue
        if m.get("collection") == "unused":
            continue
        land = [x for x in wild.get(mid, []) if x[2] == "land"]
        allw = wild.get(mid, [])
        # rematch tiers (_2.._5) are late-game; base levels use first-tier trainers only
        base_tr = [t for t in trainer_maps.get(mid, []) if not re.search(r"-[2-5]$", t)]
        lv = [tlevels[t] for t in base_tr if t in tlevels]
        ch = first_chapter.get(mid)
        prog.append({"map_id": mid, "map_title": m["title"], "map_type": m.get("map_type", ""),
                     "location_id": m.get("location", ""),
                     "first_story_chapter": ch[0] if ch else "", "first_story_event": ch[1] if ch else "",
                     "badges_expected": ch[2] if ch else "",
                     "wild_land_min": min((x[0] for x in land), default=""), "wild_land_max": max((x[1] for x in land), default=""),
                     "wild_any_min": min((x[0] for x in allw), default=""), "wild_any_max": max((x[1] for x in allw), default=""),
                     "wild_methods": "|".join(sorted({x[2] for x in allw})),
                     "trainer_count": len(base_tr),
                     "trainer_level_min": min((x[0] for x in lv), default=""), "trainer_level_max": max((x[1] for x in lv), default=""),
                     "requires": "", "gating_notes": ""})

    # ---- location descriptions from signs ---------------------------------------------------
    sign_text = {}
    for ev in maps["map_events"]:
        if ev["event_kind"] == "bg_sign" and re.search(r"TownSign|CitySign|RouteSign|_Sign$", ev.get("script", "")):
            sign_text.setdefault(ev["map_id"], ev["script"])
    by_label = {s["script_id"]: s for s in scripts["scripts"]}
    text_by_id = {t["text_id"]: t for t in texts}
    map_loc = {m["id"]: m.get("location", "") for m in maps["entities"] if m["entity_type"] == "map"}
    for mp, script in sign_text.items():
        s = by_label.get(script)
        if not s or not s.get("texts"):
            continue
        t = text_by_id.get(s["texts"].split("|")[0])
        loc = map_loc.get(mp)
        if t and loc and re.search(r"TOWN|CITY", t["text"]):
            entities.append({"id": loc, "sign_text": t["text"], "sign_text_id": t["text_id"]})
    return {"timeline_entities": links, "relationships": rels, "area_progression": prog, "entities": entities}


def _flag_id(const: str) -> str:
    return ("var:" + slug(const, "VAR_")) if const.startswith("VAR_") else ("flag:" + slug(const, "FLAG_"))


if __name__ == "__main__":
    d = extract()
    for k, v in d.items():
        print(k, len(v))
