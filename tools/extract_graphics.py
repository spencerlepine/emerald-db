"""Art inventory: every PNG under graphics/ and data/tilesets/, overworld sprite
(object event graphics) entities, species/trainer/item art links, and copies of
key images into database/images for the wiki.

art_assets.csv  - one row per art file (asset_id = source path). art_status is
                  ORIGINAL for every row here; downstream DBs flip it to
                  PENDING_ART / REDRAWN.
entity_art.csv  - (entity_id, asset_id, role) links between entities and art.
entity_images.csv - wiki gallery rows (copied images under database/images).
"""
from __future__ import annotations

import re
import shutil
import struct

from common import (DATABASE_DIR, SRC, array_body, designated_entries, entity, incbin_index, read, slug,
                    strip_c_comments, struct_fields, title_case)
from extract_pokemon import sid
from extract_maps import gfx_id

COPY_IMAGES = True


def png_size(path) -> tuple[int, int] | tuple[str, str]:
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
    except OSError:
        pass
    return "", ""


def extract() -> dict[str, list[dict]]:
    gfx = incbin_index()
    sym_by_path: dict[str, list[str]] = {}
    for sym, p in gfx.items():
        sym_by_path.setdefault(p, []).append(sym)
    entities, links, images = [], [], []

    # ---- overworld sprites ---------------------------------------------------------
    ptrs = designated_entries(array_body(strip_c_comments(read("src/data/object_events/object_event_graphics_info_pointers.h")), "gObjectEventGraphicsInfoPointers"))
    info_text = strip_c_comments(read("src/data/object_events/object_event_graphics_info.h"))
    infos = {m.group(1): m.group(2) for m in re.finditer(r"const struct ObjectEventGraphicsInfo (\w+) = (\{.*?\});", info_text, re.S)}
    pic_text = strip_c_comments(read("src/data/object_events/object_event_pic_tables.h"))
    pic_tables = {m.group(1): m.group(2) for m in re.finditer(r"static const struct SpriteFrameImage (\w+)\[\] = \{(.*?)\};", pic_text, re.S)}
    for const, ptr in ptrs.items():
        info_sym = ptr.strip().lstrip("&")
        f = struct_fields(infos.get(info_sym, "{}"))
        pics = list(dict.fromkeys(re.findall(r"\b(gObjectEventPic_\w+)", pic_tables.get(f.get("images", ""), ""))))
        paths = [gfx[p] for p in pics if p in gfx]
        e = gfx_id(const)
        entities.append(entity(e, "object_graphics", "overworld-sprites", title_case(slug(const, "OBJ_EVENT_GFX_").replace("-", " ")),
                               source_constant=const, source_file="src/data/object_events/object_event_graphics_info.h",
                               graphics_info_symbol=info_sym, sprite_width=f.get("width", ""), sprite_height=f.get("height", ""),
                               inanimate=f.get("inanimate", "") == "TRUE", palette_tag=f.get("paletteTag", ""),
                               sprite_paths=paths, image_path=_copy(paths[0], "overworld", const) if paths else "",
                               image_status="available" if paths else "placeholder",
                               description="Overworld sprite used by map objects (NPCs, items, props)."))
        for p in paths:
            links.append({"entity_id": e, "asset_id": p, "role": "overworld_sprite"})
        if paths:
            images.append({"entity_id": e, "position": 1, "path": _image_rel("overworld", const), "status": "available"})

    for i in "0123456789ABCDEF":
        entities.append(entity(gfx_id(f"OBJ_EVENT_GFX_VAR_{i}"), "object_graphics", "overworld-sprites", f"Variable sprite {i}",
                               collection="dynamic", source_constant=f"OBJ_EVENT_GFX_VAR_{i}", source_file="include/constants/event_objects.h",
                               description=f"Sprite chosen at runtime from VAR_OBJ_GFX_ID_{i} (rival, contest/frontier opponents, secret base owners, etc.)."))

    # ---- species art ------------------------------------------------------------------
    for rel_path, macro, role in (("src/data/pokemon_graphics/front_pic_table.h", "SPECIES_SPRITE", "front_pic"),
                                  ("src/data/pokemon_graphics/back_pic_table.h", "SPECIES_SPRITE", "back_pic"),
                                  ("src/data/pokemon_graphics/palette_table.h", "SPECIES_PAL", "palette"),
                                  ("src/data/pokemon_graphics/shiny_palette_table.h", "SPECIES_SHINY_PAL", "shiny_palette")):
        for name, sym in re.findall(macro + r"\((\w+),\s*(\w+)\)", read(rel_path)):
            if name == "NONE" or sym not in gfx:
                continue
            links.append({"entity_id": sid("SPECIES_" + name), "asset_id": gfx[sym], "role": role})
            if role == "front_pic":
                images.append({"entity_id": sid("SPECIES_" + name), "position": 1, "path": _image_rel("species", name), "status": "available"})
                _copy(gfx[sym], "species", name)
                entities.append({"id": sid("SPECIES_" + name), "image_path": _image_rel("species", name), "image_status": "available"})
    for rel_path, table, role in (("src/data/pokemon_graphics/footprint_table.h", "gMonFootprintTable", "footprint"),
                                  ("src/pokemon_icon.c", "gMonIconTable", "menu_icon")):
        for const, sym in designated_entries(array_body(strip_c_comments(read(rel_path)), table)).items():
            if const == "SPECIES_NONE" or sym.strip() not in gfx:
                continue
            links.append({"entity_id": sid(const), "asset_id": gfx[sym.strip()], "role": role})

    # ---- trainer back pics ------------------------------------------------------------
    for sym in sorted(s for s in gfx if s.startswith("gTrainerBackPic_")):
        links.append({"entity_id": "trainer-pic:back-" + slug(re.sub(r"(?<=[a-z])(?=[A-Z])", "_", sym.removeprefix("gTrainerBackPic_"))),
                      "asset_id": gfx[sym], "role": "trainer_back_pic"})

    # ---- full inventory ------------------------------------------------------------------
    assets = []
    for p in sorted(list(SRC.glob("graphics/**/*.png")) + list(SRC.glob("data/tilesets/**/*.png"))):
        relp = str(p.relative_to(SRC))
        w, h = png_size(p)
        parts = relp.split("/")
        kind = parts[1] if parts[0] == "graphics" else "tileset"
        assets.append({"asset_id": relp, "kind": kind, "subkind": parts[2] if len(parts) > 3 else "",
                       "path": relp, "width": w, "height": h, "symbols": "|".join(sorted(sym_by_path.get(relp, []))),
                       "referenced_in_code": "true" if relp in sym_by_path else "false", "art_status": "ORIGINAL"})

    # wiki images for trainer pics & items
    trainer_pics = re.findall(r"TRAINER_SPRITE\((\w+),\s*(\w+)", read("src/data/trainer_graphics/front_pic_tables.h"))
    for key, sym in trainer_pics:
        if sym in gfx:
            _copy(gfx[sym], "trainer", key)
            images.append({"entity_id": "trainer-pic:" + slug(key), "position": 1, "path": _image_rel("trainer", key), "status": "available"})
            entities.append({"id": "trainer-pic:" + slug(key), "image_path": _image_rel("trainer", key), "image_status": "available"})
    icons = designated_entries(array_body(strip_c_comments(read("src/data/item_icon_table.h")), "gItemIconTable"))
    for const, val in icons.items():
        sym = val.strip("{} ").split(",")[0].strip()
        if const == "ITEM_NONE" or sym not in gfx:
            continue
        key = slug(const, "ITEM_")
        _copy(gfx[sym], "item", key)
        images.append({"entity_id": "item:" + key, "position": 1, "path": _image_rel("item", key), "status": "available"})
        entities.append({"id": "item:" + key, "image_path": _image_rel("item", key), "image_status": "available"})
    return {"entities": entities, "art_assets": assets, "entity_art": links, "entity_images": images}


def _image_rel(kind: str, key: str) -> str:
    return f"images/{kind}__{slug(key)}.png"


def _copy(src_rel: str, kind: str, key: str) -> str:
    dest = DATABASE_DIR / _image_rel(kind, key)
    if COPY_IMAGES:
        dest.parent.mkdir(parents=True, exist_ok=True)
        s = SRC / src_rel
        if s.exists() and (not dest.exists() or dest.stat().st_size != s.stat().st_size):
            shutil.copyfile(s, dest)
    return _image_rel(kind, key)


if __name__ == "__main__":
    d = extract()
    for k, v in d.items():
        print(k, len(v))
