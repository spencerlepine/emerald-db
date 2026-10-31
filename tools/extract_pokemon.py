"""Species, evolutions, learnsets, abilities, types, pokedex text."""
from __future__ import annotations

import re

from common import (array_body, brace_list, c_string, clean_text, defines, designated_entries, entity, enum_values,
                    eval_defines, meta, read, rel, slug, string_arrays, strip_c_comments, struct_fields, title_case)

SPECIES_INFO = "src/data/pokemon/species_info.h"
FRIENDSHIP = {"STANDARD_FRIENDSHIP": "70"}


def sid(const: str) -> str:
    return "species:" + slug(const, "SPECIES_")


def mid(const: str) -> str:
    return "move:" + slug(const, "MOVE_")


def iid(const: str) -> str:
    return "item:" + slug(const, "ITEM_")


def tid(const: str) -> str:
    return "type:" + slug(const, "TYPE_")


def aid(const: str) -> str:
    return "ability:" + slug(const, "ABILITY_")


def extract() -> dict[str, list[dict]]:
    entities, rels, metas = [], [], []
    learnsets, evolutions, type_chart = [], [], []

    # ---- types -------------------------------------------------------------
    battle_main = strip_c_comments(read("src/battle_main.c"))
    type_names = {k: c_string(v) for k, v in designated_entries(array_body(battle_main, "gTypeNames")).items()}
    type_defs = eval_defines(defines("include/constants/pokemon.h", "TYPE_"))
    for const, name in type_names.items():
        entities.append(entity(tid(const), "game_type", "types", title_case(name), source_constant=const,
                               source_file="src/battle_main.c", game_name=name, type_index=type_defs.get(const, ""),
                               damage_category="physical" if type_defs.get(const, 99) < 9 else "special" if const != "TYPE_MYSTERY" else "",
                               description=f"Elemental type {name}. Types 0-8 deal physical damage and 10-17 special damage in Gen III."))
    mul = {"TYPE_MUL_NO_EFFECT": 0, "TYPE_MUL_NOT_EFFECTIVE": 0.5, "TYPE_MUL_NORMAL": 1, "TYPE_MUL_SUPER_EFFECTIVE": 2}
    toks = [t for t in brace_list("{" + array_body(battle_main, "gTypeEffectiveness") + "}")]
    foresight = False
    for i in range(0, len(toks) - 2, 3):
        a, d, m = toks[i:i + 3]
        if a == "TYPE_FORESIGHT":
            foresight = True
            continue
        if a == "TYPE_ENDTABLE":
            break
        type_chart.append({"attacking_type_id": tid(a), "defending_type_id": tid(d), "multiplier": mul.get(m, m),
                           "ignored_by_foresight": "true" if foresight else "false"})

    # ---- names / dex -------------------------------------------------------
    names = {k: c_string(v) for k, v in designated_entries(array_body(strip_c_comments(read("src/data/text/species_names.h")), "gSpeciesNames")).items()}
    species_defs = eval_defines(defines("include/constants/species.h", "SPECIES_"))
    natdex = enum_values("include/constants/pokedex.h", "NATIONAL_DEX_NONE")
    hoenndex = enum_values("include/constants/pokedex.h", "HOENN_DEX_NONE")
    hoenn_count = hoenndex["HOENN_DEX_DEOXYS"]
    dex_text = string_arrays(read("src/data/pokemon/pokedex_text.h"))
    dex_entries = {k: struct_fields(v) for k, v in designated_entries(array_body(strip_c_comments(read("src/data/pokemon/pokedex_entries.h")), "gPokedexEntries")).items()}

    # ---- abilities ---------------------------------------------------------
    ab_text = strip_c_comments(read("src/data/text/abilities.h"))
    ab_desc_syms = {m.group(1): m.group(2) for m in re.finditer(r"const u8 (\w+)\[\] = _\((\".*?\")\);", ab_text, re.S)}
    ab_names = {k: c_string(v) for k, v in designated_entries(array_body(ab_text, "gAbilityNames")).items()}
    ab_descs = {k: c_string(ab_desc_syms.get(v.strip(), "")) for k, v in designated_entries(array_body(ab_text, "gAbilityDescriptionPointers")).items()}
    ab_defs = eval_defines(defines("include/constants/abilities.h", "ABILITY_"))
    for const, name in ab_names.items():
        if const == "ABILITY_NONE":
            continue
        entities.append(entity(aid(const), "ability", "abilities", title_case(name), description=clean_text(ab_descs.get(const, "")),
                               source_constant=const, source_file="src/data/text/abilities.h", game_name=name,
                               ability_index=ab_defs.get(const, "")))

    # ---- species info ------------------------------------------------------
    info = designated_entries(array_body(strip_c_comments(read(SPECIES_INFO)), "gSpeciesInfo"))
    unown = re.search(r"#define OLD_UNOWN_SPECIES_INFO\s*\\?\s*(\{.*?\})\s*\n\s*\n", read(SPECIES_INFO), re.S)
    unown_fields = struct_fields(unown.group(1).replace("\\\n", "\n")) if unown else {}
    for const, body in info.items():
        if const == "SPECIES_NONE":
            continue
        f = unown_fields if body.strip() == "OLD_UNOWN_SPECIES_INFO" else struct_fields(body)
        if not f:
            continue
        name = names.get(const, const)
        key = const.removeprefix("SPECIES_")
        nd = natdex.get("NATIONAL_DEX_" + key)
        hd = hoenndex.get("HOENN_DEX_" + key)
        dex = dex_entries.get("NATIONAL_DEX_" + key, {})
        desc = clean_text(dex_text.get(dex.get("description", "").strip(), "")) if dex else ""
        types = brace_list(f.get("types", "{}"))
        abilities = [a for a in brace_list(f.get("abilities", "{}")) if a != "ABILITY_NONE"]
        egg_groups = sorted(set(brace_list(f.get("eggGroups", "{}"))), key=brace_list(f.get("eggGroups", "{}")).index)
        gender = f.get("genderRatio", "")
        gm = re.match(r"PERCENT_FEMALE\(([\d.]+)\)", gender)
        gender_pct = gm.group(1) if gm else {"MON_GENDERLESS": "genderless", "MON_MALE": "0", "MON_FEMALE": "100"}.get(gender, gender)
        stats = {k: f.get(k, "") for k in ["baseHP", "baseAttack", "baseDefense", "baseSpeed", "baseSpAttack", "baseSpDefense"]}
        total = sum(int(v) for v in stats.values() if v.isdigit())
        placeholder = name.startswith("?") or "OLD_UNOWN" in body
        e = sid(const)
        entities.append(entity(
            e, "species", "species", title_case(name) if not placeholder else const,
            collection="unused-placeholder" if placeholder else ("hoenn-regional-dex" if hd and hd <= hoenn_count else "national-dex-only"),
            description=desc,
            source_constant=const, source_file=SPECIES_INFO, game_name=name,
            species_index=species_defs.get(const, ""), national_dex=nd or "", hoenn_dex=hd or "",
            dex_category=title_case(c_string(dex.get("categoryName", ""))) if dex else "",
            height_m=(int(dex["height"]) / 10) if dex.get("height", "").isdigit() else "",
            weight_kg=(int(dex["weight"]) / 10) if dex.get("weight", "").isdigit() else "",
            type1=tid(types[0]) if types else "", type2=tid(types[1]) if len(types) > 1 and types[1] != types[0] else "",
            base_hp=stats["baseHP"], base_attack=stats["baseAttack"], base_defense=stats["baseDefense"],
            base_speed=stats["baseSpeed"], base_sp_attack=stats["baseSpAttack"], base_sp_defense=stats["baseSpDefense"],
            base_stat_total=total, catch_rate=f.get("catchRate", ""), exp_yield=f.get("expYield", ""),
            ev_yield={k.removeprefix("evYield_"): int(v) for k, v in f.items() if k.startswith("evYield_") and v.isdigit() and int(v)},
            held_item_common=iid(f["itemCommon"]) if f.get("itemCommon", "ITEM_NONE") != "ITEM_NONE" else "",
            held_item_rare=iid(f["itemRare"]) if f.get("itemRare", "ITEM_NONE") != "ITEM_NONE" else "",
            gender_percent_female=gender_pct, egg_cycles=f.get("eggCycles", ""), base_friendship=FRIENDSHIP.get(f.get("friendship", ""), f.get("friendship", "")),
            growth_rate=slug(f.get("growthRate", ""), "GROWTH_"),
            egg_groups=[slug(g, "EGG_GROUP_") for g in egg_groups],
            abilities=[aid(a) for a in abilities],
            safari_flee_rate=f.get("safariZoneFleeRate", ""), body_color=slug(f.get("bodyColor", ""), "BODY_COLOR_"),
        ))
        for t in dict.fromkeys(types):
            rels.append(rel(e, "has_type", tid(t)))
        for slot, a in enumerate(abilities, 1):
            rels.append(rel(e, "has_ability", aid(a)))
        for k in ("itemCommon", "itemRare"):
            if f.get(k, "ITEM_NONE") != "ITEM_NONE":
                rels.append(rel(e, "may_hold_item", iid(f[k])))

    # ---- evolutions --------------------------------------------------------
    evo = designated_entries(array_body(strip_c_comments(read("src/data/pokemon/evolution.h")), "gEvolutionTable"))
    for const, body in evo.items():
        for item in brace_list(body):
            parts = brace_list(item)
            if len(parts) != 3:
                continue
            method, param, target = parts
            evolutions.append({"species_id": sid(const), "method": slug(method, "EVO_"), "parameter": param,
                               "parameter_entity_id": iid(param) if param.startswith("ITEM_") else "",
                               "evolves_to_id": sid(target)})
            rels.append(rel(sid(const), "evolves_to", sid(target)))
            if param.startswith("ITEM_"):
                rels.append(rel(sid(const), "evolves_with_item", iid(param)))

    # ---- learnsets ---------------------------------------------------------
    lu_text = strip_c_comments(read("src/data/pokemon/level_up_learnsets.h"))
    lu_arrays = {m.group(1): m.group(2) for m in re.finditer(r"static const u16 (\w+)\[\] = \{(.*?)\};", lu_text, re.S)}
    ptrs = designated_entries(array_body(strip_c_comments(read("src/data/pokemon/level_up_learnset_pointers.h")), "gLevelUpLearnsets"))
    for const, sym in ptrs.items():
        if const == "SPECIES_NONE":
            continue
        for order, m in enumerate(re.finditer(r"LEVEL_UP_MOVE\(\s*(\d+)\s*,\s*(MOVE_\w+)\)", lu_arrays.get(sym.strip(), "")), 1):
            learnsets.append({"species_id": sid(const), "method": "level_up", "level": m.group(1), "order": order,
                              "move_id": mid(m.group(2)), "source_symbol": sym.strip()})
    tm_text = strip_c_comments(read("src/data/pokemon/tmhm_learnsets.h"))
    tm_items = _tmhm_map()
    for const, body in designated_entries(array_body(tm_text, "gTMHMLearnsets")).items():
        for m in re.finditer(r"\.(\w+)\s*=\s*TRUE", body):
            mv = m.group(1)
            if mv == "learnset":
                continue
            learnsets.append({"species_id": sid(const), "method": "tm_hm", "level": "", "order": tm_items.get(mv, ("", ""))[1],
                              "move_id": mid("MOVE_" + mv), "source_symbol": tm_items.get(mv, ("", ""))[0]})
    egg_text = strip_c_comments(read("src/data/pokemon/egg_moves.h"))
    for m in re.finditer(r"egg_moves\(\s*(\w+)\s*,(.*?)\)", egg_text, re.S):
        for order, mv in enumerate(re.findall(r"MOVE_\w+", m.group(2)), 1):
            learnsets.append({"species_id": sid("SPECIES_" + m.group(1)), "method": "egg", "level": "", "order": order, "move_id": mid(mv), "source_symbol": "gEggMoves"})
    tut_text = strip_c_comments(read("src/data/pokemon/tutor_learnsets.h"))
    for const, body in designated_entries(array_body(tut_text, "sTutorLearnsets")).items():
        for order, mv in enumerate(re.findall(r"TUTOR\((MOVE_\w+)\)", body), 1):
            learnsets.append({"species_id": sid(const), "method": "tutor", "level": "", "order": order, "move_id": mid(mv), "source_symbol": "sTutorLearnsets"})

    # ---- growth rates (experience tables) ---------------------------------
    for g in ["GROWTH_MEDIUM_FAST", "GROWTH_ERRATIC", "GROWTH_FLUCTUATING", "GROWTH_MEDIUM_SLOW", "GROWTH_FAST", "GROWTH_SLOW"]:
        entities.append(entity("growth-rate:" + slug(g, "GROWTH_"), "growth_rate", "mechanics", title_case(slug(g, "GROWTH_").replace("-", " ")),
                               source_constant=g, source_file="src/data/pokemon/experience_tables.h",
                               description="Experience curve used to level species (see gExperienceTables)."))

    return {"entities": entities, "relationships": rels, "metadata": metas, "species_learnsets": learnsets,
            "species_evolutions": evolutions, "type_effectiveness": type_chart}


def tmhm_list() -> list[tuple[str, str]]:
    """[(ITEM_TM_<MOVE> item constant, MOVE name)] in TM/HM order (TM01..TM50, HM01..HM08)."""
    text = read("include/constants/tms_hms.h")
    tms = re.findall(r"F\((\w+)\)", text.split("#define FOREACH_HM")[0])
    hms = re.findall(r"F\((\w+)\)", text.split("#define FOREACH_HM")[1].split("#define FOREACH_TMHM")[0])
    return [(f"ITEM_TM_{m}", m) for m in tms] + [(f"ITEM_HM_{m}", m) for m in hms]


def tmhm_label(n: int) -> str:
    return f"TM{n:02d}" if n <= 50 else f"HM{n - 50:02d}"


def _tmhm_map() -> dict[str, tuple[str, int]]:
    return {mv: (item, n) for n, (item, mv) in enumerate(tmhm_list(), 1)}


if __name__ == "__main__":
    for k, v in extract().items():
        print(k, len(v))
