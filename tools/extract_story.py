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

    # ---- location descriptions (auto) -----------------------------------------------------
    map_ent = {m["id"]: m for m in maps["entities"] if m["entity_type"] == "map"}
    by_label = {s["script_id"]: s for s in scripts["scripts"]}
    text_by_id = {t["text_id"]: t for t in texts}
    loc_maps = defaultdict(list)
    for m in map_ent.values():
        if m.get("location") and m.get("collection") != "unused":
            loc_maps[m["location"]].append(m)
    species_title = {}
    import extract_pokemon
    for e in extract_pokemon.extract()["entities"]:
        if e["entity_type"] == "species":
            species_title[e["id"]] = e["title"]
    wild_by_loc = defaultdict(lambda: defaultdict(float))
    for w in maps["wild_encounters"]:
        loc = map_ent.get(w["map_id"], {}).get("location")
        if loc:
            wild_by_loc[loc][w["species_id"]] += float(w["slot_rate_percent"] or 0) * (3 if w["method"] == "land" else 1)
    loc_title = {e["id"]: e["title"] for e in maps["entities"] if e["entity_type"] == "location"}
    for loc, ms in loc_maps.items():
        outdoor = [m for m in ms if m.get("map_type") in ("town", "city", "route", "ocean-route", "underwater", "underground")]
        sign = ""
        for ev in maps["map_events"]:
            if ev["map_id"] in {m["id"] for m in outdoor} and ev["event_kind"] == "bg_sign":
                sc = by_label.get(ev.get("script", ""))
                if sc and sc.get("texts") and map_ent[ev["map_id"]].get("map_type") in ("town", "city") and re.search(r"(Town|City)Sign$", ev["script"]):
                    t = text_by_id.get(sc["texts"].split("|")[0])
                    if t:
                        sign = t["text"].replace("\n", " ")
                        entities.append({"id": loc, "sign_text": sign, "sign_text_id": t["text_id"]})
                        break
        neighbours = sorted({loc_title.get(map_ent.get(r["target_id"], {}).get("location", ""), "") for m in outdoor
                             for r in maps["relationships"] if r["source_id"] == m["id"] and r["relationship"].startswith("connects_")} - {"", loc_title.get(loc, "")})
        interiors = [m["title"].split(" · ", 1)[-1] for m in ms if m not in outdoor and " · " in m["title"]]
        top = sorted(wild_by_loc.get(loc, {}).items(), key=lambda kv: -kv[1])[:6]
        trainers_here = sum(len(trainer_maps.get(m["id"], [])) for m in ms)
        bits = []
        if sign:
            bits.append(f"Sign: {sign.replace(chr(10), ' ')}")
        kinds = sorted({m.get("map_type", "") for m in ms if m.get("map_type")})
        bits.append(f"{len(ms)} map(s) ({', '.join(kinds)})")
        if neighbours:
            bits.append("connects to " + ", ".join(neighbours))
        if interiors:
            bits.append("buildings/areas: " + ", ".join(dict.fromkeys(interiors))[:300])
        if top:
            bits.append("wild Pokémon: " + ", ".join(species_title.get(sp, sp) for sp, _ in top))
        if trainers_here:
            bits.append(f"{trainers_here} trainer battle(s)")
        entities.append({"id": loc, "description": "; ".join(bits) + ".", "map_ids": "|".join(m["id"] for m in ms)})
        for m in ms:
            rels.append({"source_id": loc, "relationship": "contains_map", "target_id": m["id"]})

    return {"timeline_entities": links, "relationships": rels, "area_progression": prog, "entities": entities}


def _flag_id(const: str) -> str:
    return ("var:" + slug(const, "VAR_")) if const.startswith("VAR_") else ("flag:" + slug(const, "FLAG_"))


if __name__ == "__main__":
    d = extract()
    for k, v in d.items():
        print(k, len(v))
