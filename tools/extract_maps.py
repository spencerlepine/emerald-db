"""Maps, region map sections (locations), layouts, tilesets, connections, warps,
map objects (NPCs, signs, triggers, hidden items), wild encounters, heal locations."""
from __future__ import annotations

import json
import re

from common import SRC, entity, incbin_index, load_json, read, rel, slug, strip_c_comments, title_case
from extract_pokemon import iid, sid


def map_id(const: str) -> str:
    return "map:" + slug(const, "MAP_")


def mapsec_id(const: str) -> str:
    return "location:" + slug(const, "MAPSEC_")


def npc_id(map_const: str, index: int) -> str:
    return f"npc:{slug(map_const, 'MAP_')}:{index}"


def humanize_map_folder(folder: str) -> str:
    parts = folder.split("_")
    out = []
    for p in parts:
        w = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z][a-z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", p)
        w = re.sub(r"\bRoute(\d+)", r"Route \1", w)
        out.append(w)
    return " · ".join(out)


def gfx_id(const: str) -> str:
    return "object-gfx:" + slug(const, "OBJ_EVENT_GFX_")


def extract() -> dict[str, list[dict]]:
    entities, rels, objects, encounters, connections = [], [], [], [], []
    gfx = incbin_index()

    # ---- region map sections -> locations ------------------------------------
    secs = load_json("src/data/region_map/region_map_sections.json")["map_sections"]
    for s in secs:
        name = s.get("name", "")
        entities.append(entity(mapsec_id(s["id"]), "location", "locations", title_case(name) if name else s["id"],
                               source_constant=s["id"], source_file="src/data/region_map/region_map_sections.json",
                               game_name=name, region_map_x=s.get("x", ""), region_map_y=s.get("y", ""),
                               region_map_width=s.get("width", ""), region_map_height=s.get("height", ""),
                               on_region_map="x" in s,
                               description=f"Region-map section {name or s['id']}; groups every map (outdoor and interior) shown under this name."))

    # ---- tilesets ------------------------------------------------------------------
    headers = strip_c_comments(read("src/data/tilesets/headers.h"))
    for m in re.finditer(r"const struct Tileset (\w+) =\s*\{(.*?)\};", headers, re.S):
        sym, body = m.group(1), m.group(2)
        tiles = re.search(r"\.tiles = (\w+)", body)
        secondary = "isSecondary = TRUE" in body
        path = gfx.get(tiles.group(1), "") if tiles else ""
        tsid = "tileset:" + slug(sym.removeprefix("gTileset_"))
        entities.append(entity(tsid, "tileset", "tilesets", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", sym.removeprefix("gTileset_")),
                               collection="secondary" if secondary else "primary", source_constant=sym,
                               source_file="src/data/tilesets/headers.h", tiles_path=path,
                               tileset_dir=str(path).rsplit("/", 1)[0] if path else "",
                               description=("Secondary (area-specific)" if secondary else "Primary (shared)") + " tileset: tile art, palettes and metatiles."))

    # ---- layouts ------------------------------------------------------------------
    layouts = {l["id"]: l for l in load_json("data/layouts/layouts.json")["layouts"] if l}

    # ---- map groups -----------------------------------------------------------------
    groups = load_json("data/maps/map_groups.json")
    group_of = {}
    for gi, g in enumerate(groups["group_order"]):
        for mi, folder in enumerate(groups[g]):
            group_of[folder] = (g, gi, mi)

    # ---- maps ------------------------------------------------------------------------
    folder_by_const = {}
    for path in sorted((SRC / "data/maps").glob("*/map.json")):
        d = json.loads(path.read_text())
        folder_by_const[d["id"]] = path.parent.name
    heal = {h["map"]: h for h in load_json("src/data/heal_locations.json")["heal_locations"]}

    for path in sorted((SRC / "data/maps").glob("*/map.json")):
        d = json.loads(path.read_text())
        folder = path.parent.name
        const = d["id"]
        e = map_id(const)
        lay = layouts.get(d.get("layout"), {})
        g = group_of.get(folder, ("", "", ""))
        unused = "Unused" in folder or "UNUSED" in const
        entities.append(entity(
            e, "map", "maps", humanize_map_folder(folder),
            collection="unused" if unused else slug(d.get("map_type", ""), "MAP_TYPE_"),
            source_constant=const, source_file=f"data/maps/{folder}/map.json", map_folder=folder,
            location=mapsec_id(d.get("region_map_section", "")), map_type=slug(d.get("map_type", ""), "MAP_TYPE_"),
            music=d.get("music", ""), weather=slug(d.get("weather", ""), "WEATHER_"),
            requires_flash=d.get("requires_flash", False), allow_cycling=d.get("allow_cycling", ""),
            allow_escaping=d.get("allow_escaping", ""), allow_running=d.get("allow_running", ""),
            show_map_name=d.get("show_map_name", ""), battle_scene=slug(d.get("battle_scene", ""), "MAP_BATTLE_SCENE_"),
            floor_number=d.get("floor_number", ""), map_group=g[0], map_group_index=g[1], map_index_in_group=g[2],
            layout=d.get("layout", ""), width=lay.get("width", ""), height=lay.get("height", ""),
            primary_tileset="tileset:" + slug(lay.get("primary_tileset", "").removeprefix("gTileset_")) if lay else "",
            secondary_tileset="tileset:" + slug(lay.get("secondary_tileset", "").removeprefix("gTileset_")) if lay else "",
            heal_location=heal[const]["id"] if const in heal else "",
            npc_count=len(d.get("object_events") or []), warp_count=len(d.get("warp_events") or []),
            description=_map_description(d, folder),
        ))
        rels.append(rel(e, "located_in", mapsec_id(d.get("region_map_section", ""))))
        if lay:
            rels.append(rel(e, "uses_tileset", "tileset:" + slug(lay["primary_tileset"].removeprefix("gTileset_"))))
            rels.append(rel(e, "uses_tileset", "tileset:" + slug(lay["secondary_tileset"].removeprefix("gTileset_"))))
        for c in d.get("connections") or []:
            connections.append({"map_id": e, "kind": "connection", "direction": c["direction"], "target_map_id": map_id(c["map"]),
                                "offset": c.get("offset", ""), "dest_warp_id": ""})
            rels.append(rel(e, "connects_" + c["direction"], map_id(c["map"])))
        for wi, w in enumerate(d.get("warp_events") or []):
            dest = w["dest_map"]
            if dest == "MAP_DYNAMIC":
                target = "map:dynamic"
            else:
                target = map_id(dest)
            connections.append({"map_id": e, "kind": "warp", "direction": "", "target_map_id": target, "offset": "",
                                "dest_warp_id": w.get("dest_warp_id", ""), "warp_index": wi, "x": w["x"], "y": w["y"]})
            if target != "map:dynamic":
                rels.append(rel(e, "warps_to", target))

        for oi, o in enumerate(d.get("object_events") or [], 1):
            kind = o.get("type", "object")
            nid = npc_id(const, oi)
            gfx_const = o.get("graphics_id", "")
            is_trainer = o.get("trainer_type", "TRAINER_TYPE_NONE") not in ("TRAINER_TYPE_NONE", "0")
            objects.append({"object_id": nid, "map_id": e, "event_kind": "object" if kind == "object" else kind,
                            "index": oi, "local_id": o.get("local_id", ""), "x": o.get("x", ""), "y": o.get("y", ""),
                            "elevation": o.get("elevation", ""), "graphics_id": gfx_id(gfx_const) if gfx_const else "",
                            "movement_type": slug(o.get("movement_type", ""), "MOVEMENT_TYPE_"),
                            "trainer_type": slug(o.get("trainer_type", ""), "TRAINER_TYPE_"),
                            "sight_or_berry_tree": o.get("trainer_sight_or_berry_tree_id", ""),
                            "script": o.get("script", ""), "flag": o.get("flag", "") if o.get("flag") != "0" else "",
                            "target_map_id": map_id(o["target_map"]) if o.get("target_map") else "",
                            "var": "", "var_value": "", "item_id": ""})
            if kind == "object":
                gname = title_case(slug(gfx_const, "OBJ_EVENT_GFX_").replace("-", " "))
                entities.append(entity(nid, "npc", "npcs", f"{gname} ({humanize_map_folder(folder)})",
                                       collection="trainer-npc" if is_trainer else "npc",
                                       source_constant=o.get("local_id", "") or f"{const}#{oi}",
                                       source_file=f"data/maps/{folder}/map.json", map=e, graphics=gfx_id(gfx_const),
                                       script=o.get("script", ""), visibility_flag=o.get("flag", "") if o.get("flag") != "0" else "",
                                       movement_type=slug(o.get("movement_type", ""), "MOVEMENT_TYPE_"),
                                       is_trainer=is_trainer, x=o.get("x", ""), y=o.get("y", ""),
                                       description=""))
                rels.append(rel(nid, "appears_on", e))
                rels.append(rel(nid, "uses_sprite", gfx_id(gfx_const)))
        for ci, c in enumerate(d.get("coord_events") or [], 1):
            objects.append({"object_id": f"coord:{slug(const, 'MAP_')}:{ci}", "map_id": e, "event_kind": "coord_" + c.get("type", ""),
                            "index": ci, "x": c.get("x", ""), "y": c.get("y", ""), "elevation": c.get("elevation", ""),
                            "script": c.get("script", ""), "var": c.get("var", ""), "var_value": c.get("var_value", ""),
                            "flag": "", "weather": c.get("weather", "")})
        for bi, b in enumerate(d.get("bg_events") or [], 1):
            item = b.get("item", "")
            objects.append({"object_id": f"bg:{slug(const, 'MAP_')}:{bi}", "map_id": e, "event_kind": "bg_" + b.get("type", ""),
                            "index": bi, "x": b.get("x", ""), "y": b.get("y", ""), "elevation": b.get("elevation", ""),
                            "script": b.get("script", ""), "flag": b.get("flag", ""), "item_id": iid(item) if item else "",
                            "secret_base_id": b.get("secret_base_id", ""),
                            "player_facing_dir": slug(b.get("player_facing_dir", ""), "BG_EVENT_PLAYER_FACING_")})
            if item:
                rels.append(rel(e, "hidden_item", iid(item)))

    # ---- wild encounters ----------------------------------------------------------
    wild = load_json("src/data/wild_encounters.json")["wild_encounter_groups"]
    for grp in wild:
        fields = {f["type"]: f for f in grp.get("fields", wild[0]["fields"])}
        for enc in grp["encounters"]:
            m = enc.get("map", "")
            target = map_id(m) if m else ""
            for method, block in enc.items():
                if not isinstance(block, dict) or "mons" not in block:
                    continue
                rates = fields.get(method, {}).get("encounter_rates", [])
                rod = {}
                for rname, idxs in (fields.get(method, {}).get("groups") or {}).items():
                    for i in idxs:
                        rod[i] = rname
                for slot, mon in enumerate(block["mons"]):
                    encounters.append({"group": grp["label"], "base_label": enc.get("base_label", ""), "map_id": target,
                                       "method": method.replace("_mons", "") if slot not in rod else rod[slot],
                                       "area_rate": block.get("encounter_rate", ""), "slot": slot,
                                       "slot_rate_percent": rates[slot] if slot < len(rates) else "",
                                       "species_id": sid(mon["species"]), "min_level": mon["min_level"], "max_level": mon["max_level"]})
            if target:
                for sp in sorted({mon["species"] for b in enc.values() if isinstance(b, dict) for mon in b.get("mons", [])}):
                    rels.append(rel(sid(sp), "found_wild_in", target))
    return {"entities": entities, "relationships": rels, "map_events": objects, "wild_encounters": encounters,
            "map_connections": connections}


def _map_description(d: dict, folder: str) -> str:
    bits = [f"{slug(d.get('map_type', ''), 'MAP_TYPE_').replace('-', ' ')} map"]
    if d.get("weather") and d["weather"] not in ("WEATHER_NONE",):
        bits.append(f"weather {slug(d['weather'], 'WEATHER_').replace('-', ' ')}")
    if d.get("connections"):
        bits.append("connects " + ", ".join(f"{c['direction']} to {humanize_map_folder(c['map'].removeprefix('MAP_').title().replace('_', ''))}" for c in d["connections"]))
    n = len(d.get("object_events") or [])
    if n:
        bits.append(f"{n} object events")
    return "; ".join(bits).capitalize() + "."


if __name__ == "__main__":
    d = extract()
    for k, v in d.items():
        print(k, len(v))
    for r in d["entities"]:
        if r["id"] in ("map:littleroot-town", "location:littleroot-town", "tileset:general", "npc:littleroot-town:1"):
            print(r)
