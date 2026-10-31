"""Moves (battle + contest data, animations) and items (incl. TMs/HMs, berries, icons)."""
from __future__ import annotations

import re

from common import (array_body, brace_list, c_string, clean_text, designated_entries, entity, eval_defines, defines,
                    game_name, incbin_index, read, rel, slug, string_arrays, strip_c_comments, struct_fields, title_case)
from extract_pokemon import iid, mid, tid, tmhm_label, tmhm_list


def extract() -> dict[str, list[dict]]:
    entities, rels, assets, links = [], [], [], []
    gfx = incbin_index()

    # ---- moves ------------------------------------------------------------
    moves = designated_entries(array_body(strip_c_comments(read("src/data/battle_moves.h")), "gBattleMoves"))
    names = {k: c_string(v) for k, v in designated_entries(array_body(strip_c_comments(read("src/data/text/move_names.h")), "gMoveNames")).items()}
    desc_text = read("src/data/text/move_descriptions.h")
    desc_syms = string_arrays(desc_text)
    desc_ptrs = {k.replace(" - 1", "").strip(): v.strip() for k, v in designated_entries(array_body(strip_c_comments(desc_text), "gMoveDescriptionPointers")).items()}
    contest = {k: struct_fields(v) for k, v in designated_entries(array_body(strip_c_comments(read("src/data/contest_moves.h")), "gContestMoves")).items()}
    anims = re.findall(r"\.4byte (Move_\w+)", read("data/battle_anim_scripts.s").split("gBattleAnims_Moves::")[1].split("::")[0])
    move_defs = eval_defines(defines("include/constants/moves.h", "MOVE_"))
    tm_by_move = {"MOVE_" + mv: item for item, mv in tmhm_list()}
    for const, body in moves.items():
        if const == "MOVE_NONE":
            continue
        f = struct_fields(body)
        c = contest.get(const, {})
        idx = move_defs.get(const)
        anim = anims[idx] if idx is not None and idx < len(anims) else ""
        e = mid(const)
        flags = [slug(x.strip(), "FLAG_") for x in f.get("flags", "0").split("|") if x.strip() not in ("0", "")]
        entities.append(entity(
            e, "move", "moves", title_case(names.get(const, const)),
            description=clean_text(desc_syms.get(desc_ptrs.get(const, ""), "")),
            source_constant=const, source_file="src/data/battle_moves.h", game_name=names.get(const, ""),
            move_index=idx if idx is not None else "", move_type=tid(f.get("type", "TYPE_NORMAL")),
            power=f.get("power", ""), accuracy=f.get("accuracy", ""), pp=f.get("pp", ""),
            effect=slug(f.get("effect", ""), "EFFECT_"), effect_constant=f.get("effect", ""),
            secondary_effect_chance=f.get("secondaryEffectChance", ""), target=slug(f.get("target", ""), "MOVE_TARGET_"),
            priority=f.get("priority", ""), move_flags=flags,
            contest_category=slug(c.get("contestCategory", ""), "CONTEST_CATEGORY_"),
            contest_effect=slug(c.get("effect", ""), "CONTEST_EFFECT_"),
            contest_combo_starter=slug(c.get("comboStarterId", "0"), "COMBO_STARTER_") if c.get("comboStarterId", "0") != "0" else "",
            contest_combo_moves=[slug(x, "COMBO_STARTER_") for x in brace_list(c.get("comboMoves", "{0}")) if x != "0"],
            battle_animation_script=anim, taught_by_item=iid(tm_by_move[const]) if const in tm_by_move else "",
        ))
        rels.append(rel(e, "has_type", tid(f.get("type", "TYPE_NORMAL"))))
        if anim:
            assets.append({"asset_id": "anim:" + anim, "kind": "battle_animation", "subkind": "move",
                           "path": "data/battle_anim_scripts.s", "symbols": anim, "referenced_in_code": "true", "art_status": "ORIGINAL"})
            links.append({"entity_id": e, "asset_id": "anim:" + anim, "role": "battle_animation"})

    # ---- items ------------------------------------------------------------
    item_text = strip_c_comments(read("src/data/items.h"))
    items = designated_entries(array_body(item_text, "gItems"))
    idesc = string_arrays(read("src/data/text/item_descriptions.h"))
    icons = designated_entries(array_body(strip_c_comments(read("src/data/item_icon_table.h")), "gItemIconTable"))
    tm_moves = dict(tmhm_list())
    berries = _berries()
    for const, body in items.items():
        if const == "ITEM_NONE":
            continue
        f = struct_fields(body)
        name = game_name(c_string(f.get("name", "")))
        e = iid(const)
        pocket = slug(f.get("pocket", ""), "POCKET_")
        category = {"poke-balls": "poke-balls", "tm-hm": "tms-hms", "berries": "berries", "key-items": "key-items"}.get(pocket, "items")
        icon_syms = brace_list(icons.get(const, "{}"))
        icon = gfx.get(icon_syms[0], "") if icon_syms else ""
        extra = {}
        if const in tm_moves:
            extra["tm_hm_number"] = tmhm_label(list(tm_moves).index(const) + 1)
            extra["teaches_move"] = mid("MOVE_" + tm_moves[const])
            rels.append(rel(e, "teaches_move", mid("MOVE_" + tm_moves[const])))
        b = berries.get(const)
        if b:
            extra.update(b)
        unused = name in ("????????", "") or const.startswith("ITEM_0")
        title = title_case(name) if not unused else const
        if const in tm_moves:
            title = f"{extra['tm_hm_number']} {title_case(names.get('MOVE_' + tm_moves[const], tm_moves[const]))}"
        entities.append(entity(
            e, "item", category, title,
            collection="unused" if unused else pocket,
            description=clean_text(idesc.get(f.get("description", "").strip(), "")),
            source_constant=const, source_file="src/data/items.h", game_name=name,
            price=f.get("price", ""), pocket=pocket, hold_effect=slug(f.get("holdEffect", ""), "HOLD_EFFECT_"),
            hold_effect_param=f.get("holdEffectParam", ""), importance=f.get("importance", ""),
            item_use_type=f.get("type", ""), field_use_func=f.get("fieldUseFunc", ""),
            battle_usage=slug(f.get("battleUsage", ""), "ITEM_B_USE_"), battle_use_func=f.get("battleUseFunc", ""),
            secondary_id=f.get("secondaryId", ""), icon_symbol=icon_syms[0] if icon_syms else "",
            icon_path=icon, **extra,
        ))
        if icon:
            links.append({"entity_id": e, "asset_id": icon, "role": "item_icon"})
    return {"entities": entities, "relationships": rels, "art_assets": assets, "entity_art": links}


def _berries() -> dict[str, dict]:
    text = read("src/berry.c")
    strings = string_arrays(text)
    body = array_body(strip_c_comments(text), "gBerries")
    out = {}
    for key, block in designated_entries(body).items():
        const = key.replace("- FIRST_BERRY_INDEX", "").strip()
        f = struct_fields(block)
        out[const] = {
            "berry_name": c_string(f.get("name", "")),
            "berry_description": clean_text(strings.get(f.get("description1", ""), "") + " " + strings.get(f.get("description2", ""), "")),
            "berry_firmness": slug(f.get("firmness", ""), "BERRY_FIRMNESS_"), "berry_size_mm": f.get("size", ""),
            "berry_yield": f"{f.get('minYield', '')}-{f.get('maxYield', '')}", "berry_stage_hours": f.get("stageDuration", ""),
            "flavor_spicy": f.get("spicy", ""), "flavor_dry": f.get("dry", ""), "flavor_sweet": f.get("sweet", ""),
            "flavor_bitter": f.get("bitter", ""), "flavor_sour": f.get("sour", ""), "berry_smoothness": f.get("smoothness", ""),
        }
    return out


if __name__ == "__main__":
    d = extract()
    for k, v in d.items():
        print(k, len(v))
    for r in d["entities"]:
        if r["id"] in ("move:pound", "item:poke-ball", "item:tm01", "item:cheri-berry", "item:mach-bike"):
            print(r)
