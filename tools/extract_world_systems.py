"""Side systems: natures, decorations, ribbons, easy chat words, Battle Frontier
(facility classes, frontier trainers + their mon pools, frontier brain parties,
Battle Tents), contest opponents, Trainer Hill trainers."""
from __future__ import annotations

import re

from common import (array_body, brace_list, c_string, clean_text, designated_entries, entity, game_name, read, rel,
                    slug, string_arrays, strip_c_comments, struct_fields, title_case, match_brace)
from extract_pokemon import iid, mid, sid
from extract_trainers import tcid, tpid, trid


def easy_chat_words() -> tuple[dict[str, str], list[dict]]:
    from common import SRC
    words, rows = {}, []
    for p in sorted((SRC / "src/data/easy_chat").glob("easy_chat_group_*.h")):
        text = p.read_text()
        strings = string_arrays(text)
        group = p.stem.removeprefix("easy_chat_group_")
        for m in re.finditer(r"\[EC_INDEX\((EC_WORD_\w+)\)\]\s*=\s*\{\s*\.text\s*=\s*(\w+),.*?\.enabled\s*=\s*(\w+)", text, re.S):
            w = strings.get(m.group(2), "")
            words[m.group(1)] = w
            rows.append({"word_id": m.group(1), "group": group, "text": w, "enabled": m.group(3).lower(),
                         "source_file": str(p.relative_to(SRC))})
    return words, rows


def decode_speech(tokens: list[str], words: dict[str, str]) -> str:
    out = []
    for t in tokens:
        if t in ("EC_EMPTY_WORD", "0xFFFF"):
            continue
        m = re.match(r"EC_(POKEMON|POKEMON_NATIONAL|MOVE|MOVE2)\((\w+)\)", t)
        out.append(m.group(2) if m else words.get(t, t))
    return " ".join(out)


def extract() -> dict[str, list[dict]]:
    entities, rels, mons_rows, pools, brain_parties = [], [], [], [], []

    # ---- natures --------------------------------------------------------------
    nn = read("src/data/text/nature_names.h")
    nsyms = string_arrays(nn)
    nptr = designated_entries(array_body(strip_c_comments(nn), "gNatureNamePointers"))
    stat_text = strip_c_comments(read("src/pokemon.c"))
    stats = {k: [int(x) for x in brace_list(v)] for k, v in designated_entries(array_body(stat_text, "gNatureStatTable")).items()}
    labels = ["attack", "defense", "speed", "sp_attack", "sp_defense"]
    for const, sym in nptr.items():
        mods = stats.get(const, [0] * 5)
        up = [labels[i] for i, v in enumerate(mods) if v > 0]
        down = [labels[i] for i, v in enumerate(mods) if v < 0]
        name = nsyms.get(sym.strip(), const)
        entities.append(entity("nature:" + slug(const, "NATURE_"), "nature", "natures", title_case(name), source_constant=const,
                               source_file="src/pokemon.c", game_name=name, raises_stat=up[0] if up else "",
                               lowers_stat=down[0] if down else "",
                               description=f"Nature: +10% {up[0].replace('_', ' ')}, -10% {down[0].replace('_', ' ')}." if up else "Neutral nature (no stat change)."))

    # ---- decorations -----------------------------------------------------------
    ddesc = string_arrays(read("src/data/decoration/description.h"))
    for const, body in designated_entries(array_body(strip_c_comments(read("src/data/decoration/header.h")), "gDecorations")).items():
        if const == "DECOR_NONE":
            continue
        f = struct_fields(body)
        name = game_name(c_string(f.get("name", "")))
        entities.append(entity("decoration:" + slug(const, "DECOR_"), "decoration", "decorations", title_case(name),
                               collection=slug(f.get("category", ""), "DECORCAT_"), source_constant=const,
                               source_file="src/data/decoration/header.h", game_name=name, price=f.get("price", ""),
                               decoration_shape=slug(f.get("shape", ""), "DECORSHAPE_"),
                               decoration_permission=slug(f.get("permission", ""), "DECORPERM_"),
                               description=clean_text(ddesc.get(f.get("description", ""), ""))))

    # ---- ribbons -----------------------------------------------------------------
    rd = string_arrays(read("src/data/text/ribbon_descriptions.h"))
    seen = {}
    for sym, txt in rd.items():
        m = re.match(r"gRibbonDescriptionPart([12])_(\w+)", sym)
        if m:
            seen.setdefault(m.group(2), ["", ""])[int(m.group(1)) - 1] = txt
    for key, (a, b) in seen.items():
        if not a:
            continue
        entities.append(entity("ribbon:" + slug(re.sub(r"(?<=[a-z])(?=[A-Z])", "-", key)), "ribbon", "ribbons",
                               re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key) + " Ribbon", source_constant=key,
                               source_file="src/data/text/ribbon_descriptions.h", description=clean_text(f"{a} {b}".strip())))

    # ---- easy chat ---------------------------------------------------------------------
    words, word_rows = easy_chat_words()

    # ---- facility classes ----------------------------------------------------------------
    lookups = strip_c_comments(read("src/data/pokemon/trainer_class_lookups.h"))
    fc_to_class = designated_entries(array_body(lookups, "gFacilityClassToTrainerClass"))
    fc_to_pic = designated_entries(array_body(lookups, "gFacilityClassToPicIndex"))

    # ---- frontier mons ------------------------------------------------------------------
    fm = designated_entries(array_body(strip_c_comments(read("src/data/battle_frontier/battle_frontier_mons.h")), "gBattleFrontierMons"))
    for const, body in fm.items():
        f = struct_fields(body)
        mons_rows.append({"mon_set_id": const, "pool": "battle_frontier", "species_id": sid(f.get("species", "")),
                          "moves": "|".join(mid(m) for m in brace_list(f.get("moves", "{}")) if m != "MOVE_NONE"),
                          "held_item": f.get("itemTableId", ""), "nature_id": "nature:" + slug(f.get("nature", ""), "NATURE_"),
                          "ev_spread": f.get("evSpread", "")})
    tm_text = strip_c_comments(read("src/data/battle_frontier/battle_frontier_trainer_mons.h"))
    macros = {}
    for m in re.finditer(r"#define (FRONTIER_MONS_\w+)\s*\\\n(.*?)(?=\n\s*\n|\n#define|\Z)", read("src/data/battle_frontier/battle_frontier_trainer_mons.h"), re.S):
        macros[m.group(1)] = re.findall(r"FRONTIER_MON_\w+", m.group(2))
    trainer_mon_arrays = {}
    for m in re.finditer(r"const u16 (gBattleFrontierTrainerMons_\w+)\[\] =\s*\{(.*?)\};", tm_text, re.S):
        ids = []
        for tok in re.findall(r"\w+", m.group(2)):
            if tok in macros:
                ids += macros[tok]
            elif tok.startswith("FRONTIER_MON_"):
                ids.append(tok)
        trainer_mon_arrays[m.group(1)] = ids

    # ---- frontier + tent trainers ----------------------------------------------------------
    sources = [("src/data/battle_frontier/battle_frontier_trainers.h", "gBattleFrontierTrainers", "battle-frontier"),
               ("src/data/battle_frontier/battle_tent.h", "gSlateportBattleTentTrainers", "slateport-battle-tent"),
               ("src/data/battle_frontier/battle_tent.h", "gVerdanturfBattleTentTrainers", "verdanturf-battle-tent"),
               ("src/data/battle_frontier/battle_tent.h", "gFallarborBattleTentTrainers", "fallarbor-battle-tent")]
    tent_text = strip_c_comments(read("src/data/battle_frontier/battle_tent.h"))
    tent_arrays = {m.group(1): re.findall(r"\b\w+_TENT_MON_\w+", m.group(2)) for m in re.finditer(r"const u16 (\w+TrainerMons_\w+)\[\] =\s*\{(.*?)\};", tent_text, re.S)}
    for path, table, coll in sources:
        body = array_body(strip_c_comments(read(path)), table)
        for const, block in designated_entries(body).items():
            f = struct_fields(block)
            name = game_name(c_string(f.get("trainerName", "")))
            fc = f.get("facilityClass", "")
            e = f"facility-trainer:{coll}:{slug(const, 'FRONTIER_TRAINER_')}"
            pool = f.get("monSet", "").strip()
            pool_ids = trainer_mon_arrays.get(pool) or tent_arrays.get(pool) or []
            entities.append(entity(e, "facility_trainer", "facility-trainers", f"{title_case(name)} ({coll.replace('-', ' ').title()})",
                                   collection=coll, source_constant=const, source_file=path, game_name=name,
                                   facility_class=slug(fc, "FACILITY_CLASS_"),
                                   trainer_class=tcid(fc_to_class.get(fc, "")) if fc in fc_to_class else "",
                                   trainer_pic=tpid(fc_to_pic.get(fc, "")) if fc in fc_to_pic else "",
                                   speech_before=decode_speech(brace_list(f.get("speechBefore", "{}")), words),
                                   speech_win=decode_speech(brace_list(f.get("speechWin", "{}")), words),
                                   speech_lose=decode_speech(brace_list(f.get("speechLose", "{}")), words),
                                   mon_pool_symbol=pool, mon_pool_size=len(pool_ids),
                                   description=f"Randomly-drawn {coll.replace('-', ' ')} opponent; says: \"{decode_speech(brace_list(f.get('speechBefore', '{}')), words)}\""))
            if fc in fc_to_class:
                rels.append(rel(e, "trainer_class", tcid(fc_to_class[fc])))
            for i, pid in enumerate(pool_ids, 1):
                pools.append({"facility_trainer_id": e, "order": i, "mon_set_id": pid})
    for m in re.finditer(r"const struct FacilityMon (g\w+BattleTentMons)\[\w*\] =\s*\{", tent_text):
        start = m.end() - 1
        block = tent_text[start + 1:match_brace(tent_text, start)]
        for const, body in designated_entries(block).items():
            f = struct_fields(body)
            mons_rows.append({"mon_set_id": const, "pool": m.group(1), "species_id": sid(f.get("species", "")),
                              "moves": "|".join(mid(x) for x in brace_list(f.get("moves", "{}")) if x != "MOVE_NONE"),
                              "held_item": f.get("itemTableId", ""), "nature_id": "nature:" + slug(f.get("nature", ""), "NATURE_"),
                              "ev_spread": f.get("evSpread", "")})

    # ---- frontier brains -----------------------------------------------------------------
    fu = strip_c_comments(read("src/frontier_util.c"))
    brains = designated_entries(array_body(fu, "sFrontierBrainTrainerIds"))
    brain_mons = designated_entries(array_body(fu, "sFrontierBrainsMons"))
    for fac, tr in brains.items():
        sets = brace_list(brain_mons.get(fac, "{}"))
        for tier, s in zip(("silver", "gold"), sets):
            for slot, mon in enumerate(brace_list(s), 1):
                f = struct_fields(mon)
                brain_parties.append({"trainer_id": trid(tr), "slot": slot, "species_id": sid(f.get("species", "")), "level": "50/open",
                                      "iv": f.get("fixedIV", ""), "held_item_id": iid(f.get("heldItem", "ITEM_NONE")) if f.get("heldItem", "ITEM_NONE") != "ITEM_NONE" else "",
                                      "moves": "|".join(mid(x) for x in brace_list(f.get("moves", "{}"))),
                                      "party_symbol": f"sFrontierBrainsMons[{fac}][{tier}]", "tier": tier,
                                      "nature_id": "nature:" + slug(f.get("nature", ""), "NATURE_"), "evs": f.get("evs", "")})
        rels.append(rel(trid(tr), "frontier_brain_of", "facility:" + slug(fac, "FRONTIER_FACILITY_")))
    for fac in brains:
        name = slug(fac, "FRONTIER_FACILITY_")
        entities.append(entity("facility:" + name, "facility", "battle-facilities", "Battle " + name.title(),
                               source_constant=fac, source_file="src/frontier_util.c", collection="battle-frontier",
                               description=f"Battle Frontier facility (Battle {name.title()}). Frontier Brain: {title_case(slug(brains[fac], 'TRAINER_'))}."))

    # ---- contest opponents ------------------------------------------------------------------
    co = strip_c_comments(read("src/data/contest_opponents.h"))
    for const, body in designated_entries(array_body(co, "gContestOpponents")).items():
        f = struct_fields(body)
        name = game_name(c_string(f.get("trainerName", "")))
        cats = [c for c in ("Cool", "Beauty", "Cute", "Smart", "Tough") if f.get("aiPool_" + c) == "TRUE"]
        e = "contest-opponent:" + slug(const, "CONTEST_OPPONENT_")
        entities.append(entity(e, "contest_opponent", "contest-opponents", title_case(name), collection=slug(f.get("whichRank", ""), "CONTEST_RANK_"),
                               source_constant=const, source_file="src/data/contest_opponents.h", game_name=name,
                               species=sid(f.get("species", "")), nickname=c_string(f.get("nickname", "")),
                               sprite="object-gfx:" + slug(f.get("trainerGfxId", ""), "OBJ_EVENT_GFX_"), contest_categories=cats,
                               moves=[mid(m) for m in brace_list(f.get("moves", "{}")) if m != "MOVE_NONE"],
                               description=f"Contest rival with {title_case(c_string(f.get('nickname', '')))} the {title_case(slug(f.get('species', ''), 'SPECIES_').replace('-', ' '))} ({', '.join(cats)})."))
        rels.append(rel(e, "uses_species", sid(f.get("species", ""))))

    # ---- trainer hill -----------------------------------------------------------------------------
    th = read("src/data/battle_frontier/trainer_hill.h")
    for m in re.finditer(r"static const struct TrainerHillFloor (sFloors_(\w+))\[\] = \{", th):
        mode = m.group(2)
        if mode.startswith("JP"):
            continue
        start = m.end() - 1
        block = th[start + 1:match_brace(th, start)]
        for tm in re.finditer(r"\.name = _\(\"([^\"]*)\"\),\s*\.facilityClass = (\w+),.*?\.speechBefore = \{([^}]*)\}.*?\.speechWin = \{([^}]*)\}.*?\.speechLose = \{([^}]*)\}.*?\.speechAfter = \{([^}]*)\}", block, re.S):
            name = tm.group(1).rstrip("$ ").strip()
            e = f"facility-trainer:trainer-hill-{slug(mode)}:{slug(name)}"
            entities.append(entity(e, "facility_trainer", "facility-trainers", f"{title_case(name)} (Trainer Hill {mode})",
                                   collection="trainer-hill-" + slug(mode), source_file="src/data/battle_frontier/trainer_hill.h",
                                   game_name=name, facility_class=slug(tm.group(2), "FACILITY_CLASS_"),
                                   speech_before=decode_speech([x.strip() for x in tm.group(3).split(",")], words),
                                   speech_win=decode_speech([x.strip() for x in tm.group(4).split(",")], words),
                                   speech_lose=decode_speech([x.strip() for x in tm.group(5).split(",")], words),
                                   speech_after=decode_speech([x.strip() for x in tm.group(6).split(",")], words)))

    return {"entities": entities, "relationships": rels, "easy_chat_words": word_rows, "facility_mons": mons_rows,
            "facility_trainer_pools": pools, "trainer_parties": brain_parties}


if __name__ == "__main__":
    d = extract()
    for k, v in d.items():
        print(k, len(v))
    import collections
    print(collections.Counter(e["entity_type"] for e in d["entities"]))
    for e in d["entities"]:
        if e["id"] in ("facility-trainer:battle-frontier:brady", "nature:adamant", "contest-opponent:jimmy", "facility:tower"):
            print(e)
