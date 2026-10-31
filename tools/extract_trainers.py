"""Trainers, trainer parties, trainer classes, trainer pics, rematches."""
from __future__ import annotations

import re

from common import (array_body, brace_list, c_string, designated_entries, entity, game_name, incbin_index, read, rel,
                    slug, strip_c_comments, struct_fields, title_case)
from extract_pokemon import iid, mid, sid


def trid(const: str) -> str:
    return "trainer:" + slug(const, "TRAINER_")


def tcid(const: str) -> str:
    return "trainer-class:" + slug(const, "TRAINER_CLASS_")


def tpid(const: str) -> str:
    return "trainer-pic:" + slug(const, "TRAINER_PIC_")


def extract() -> dict[str, list[dict]]:
    entities, rels, parties, assets = [], [], [], []
    gfx = incbin_index()

    # classes
    class_names = {k: game_name(c_string(v)) for k, v in designated_entries(array_body(strip_c_comments(read("src/data/text/trainer_class_names.h")), "gTrainerClassNames")).items()}
    bm = strip_c_comments(read("src/battle_main.c"))
    money = dict(re.findall(r"\{(TRAINER_CLASS_\w+),\s*(\d+)\}", array_body(bm, "gTrainerMoneyTable")))
    for const, name in class_names.items():
        entities.append(entity(tcid(const), "trainer_class", "trainer-classes", title_case(name), source_constant=const,
                               source_file="src/data/text/trainer_class_names.h", game_name=name,
                               prize_money_multiplier=money.get(const, ""),
                               description=f"Trainer class shown before a trainer's name in battle ({name})."))

    # pics
    pics = re.findall(r"TRAINER_SPRITE\((\w+),\s*(\w+)", read("src/data/trainer_graphics/front_pic_tables.h"))
    for key, sym in pics:
        const = "TRAINER_PIC_" + key
        path = gfx.get(sym, "")
        entities.append(entity(tpid(const), "trainer_pic", "trainer-pics", title_case(key.replace("_", " ")), source_constant=const,
                               source_file="src/data/trainer_graphics/front_pic_tables.h", image_symbol=sym, image_source_path=path,
                               description="Battle front sprite used by one or more trainers."))
        if path:
            assets.append({"entity_id": tpid(const), "asset_id": path, "role": "trainer_front_pic"})

    # parties
    party_text = strip_c_comments(read("src/data/trainer_parties.h"))
    party_arrays = {}
    for m in re.finditer(r"static const struct (TrainerMon\w+) (\w+)\[\] = \{", party_text):
        start = m.end() - 1
        from common import match_brace
        body = party_text[start + 1:match_brace(party_text, start)]
        party_arrays[m.group(2)] = (m.group(1), [struct_fields(b) for b in brace_list("{" + body + "}")])

    trainers = designated_entries(array_body(strip_c_comments(read("src/data/trainers.h")), "gTrainers"))
    for const, body in trainers.items():
        if const == "TRAINER_NONE":
            continue
        f = struct_fields(body)
        name = game_name(c_string(f.get("trainerName", "")))
        cls = f.get("trainerClass", "")
        pm = re.search(r"(\w+)\((\w+)\)", f.get("party", ""))
        party_kind, party_sym = (pm.group(1), pm.group(2)) if pm else ("", "")
        mons = party_arrays.get(party_sym, ("", []))[1]
        music = f.get("encounterMusic_gender", "")
        e = trid(const)
        cls_name = class_names.get(cls, "")
        items = [iid(x) for x in brace_list(f.get("items", "{}")) if x not in ("ITEM_NONE", "0")]
        levels = [int(m.get("lvl", 0)) for m in mons if m.get("lvl", "").isdigit()]
        tier = re.search(r"_(\d+)$", const)
        title = f"{title_case(cls_name)} {title_case(name)}".strip() if name else const
        if tier and int(tier.group(1)) > 1:
            title += f" (Rematch {int(tier.group(1)) - 1})"
        entities.append(entity(
            e, "trainer", "trainers", title,
            source_constant=const, source_file="src/data/trainers.h", game_name=name,
            trainer_class=tcid(cls), trainer_pic=tpid(f.get("trainerPic", "")),
            gender="female" if "F_TRAINER_FEMALE" in music else "male",
            encounter_music=slug(re.sub(r"F_TRAINER_FEMALE\s*\|?\s*", "", music), "TRAINER_ENCOUNTER_MUSIC_"),
            double_battle=f.get("doubleBattle", "") == "TRUE", trainer_items=items,
            ai_flags=[slug(x.strip(), "AI_SCRIPT_") for x in f.get("aiFlags", "0").split("|") if x.strip() != "0"],
            party_symbol=party_sym, party_format=party_kind, party_size=len(mons),
            max_level=max(levels) if levels else "", min_level=min(levels) if levels else "",
            description=f"Trainer data for {cls_name} {name}: {len(mons)} Pokémon, levels {min(levels) if levels else '?'}-{max(levels) if levels else '?'}.",
        ))
        rels.append(rel(e, "trainer_class", tcid(cls)))
        rels.append(rel(e, "uses_trainer_pic", tpid(f.get("trainerPic", ""))))
        for slot, m in enumerate(mons, 1):
            moves = [mid(x) for x in brace_list(m.get("moves", "{}")) if x not in ("MOVE_NONE", "0")]
            parties.append({"trainer_id": e, "slot": slot, "species_id": sid(m.get("species", "")), "level": m.get("lvl", ""),
                            "iv": m.get("iv", ""), "held_item_id": iid(m["heldItem"]) if m.get("heldItem", "ITEM_NONE") != "ITEM_NONE" else "",
                            "moves": "|".join(moves), "party_symbol": party_sym})
            rels.append(rel(e, "uses_species", sid(m.get("species", ""))))

    # rematches
    bs = strip_c_comments(read("src/battle_setup.c"))
    for key, val in designated_entries(array_body(bs, "gRematchTable")).items():
        args = [a.strip() for a in re.search(r"REMATCH\((.*)\)", val, re.S).group(1).split(",")]
        *tiers, map_const = args
        tiers = [t for t in tiers if t and t != "0"]
        for n, t in enumerate(tiers[1:], 2):
            rels.append(rel(trid(tiers[0]), f"rematch_{n}", trid(t)))
        rels.append(rel(trid(tiers[0]), "rematch_location", "map:" + slug(map_const, "MAP_")))
    return {"entities": entities, "relationships": rels, "trainer_parties": parties, "entity_art": assets}


if __name__ == "__main__":
    d = extract()
    for k, v in d.items():
        print(k, len(v))
    for r in d["entities"]:
        if r["id"] in ("trainer:roxanne-1", "trainer-class:leader", "trainer-pic:leader-roxanne"):
            print(r)
    print([p for p in d["trainer_parties"] if p["trainer_id"] == "trainer:roxanne-1"])
