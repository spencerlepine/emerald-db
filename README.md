# Emerald DB

A relational, chronological snapshot of **Pokémon Emerald**, extracted directly
from the [pokeemerald](https://github.com/spencerlepine/pokeemerald)
decompilation, plus a curated lore layer (story timeline, characters,
organizations, location history, area progression).

It follows the layout of [starwars-db](https://github.com/spencerlepine/starwars-db)
so both databases can be browsed with the same wiki and mapped onto each other
in the next step (`emerald-starwars-db`).

**Resuming work?** Start at [`POPULATE-EMERALD-DB-PROMPT.md`](POPULATE-EMERALD-DB-PROMPT.md).
Progress: [`progress/CHECKLIST.md`](progress/CHECKLIST.md) ·
coverage: [`progress/COVERAGE.md`](progress/COVERAGE.md).

## Build

```sh
# pokeemerald checked out next to this repo (or set POKEEMERALD_DIR)
python3 tools/build.py      # regenerate database/
python3 tools/coverage.py   # refresh progress/COVERAGE.md
python3 tools/balance_audit.py  # level curve vs gym aces -> progress/BALANCE.md
python3 wiki/server.py      # browse at http://127.0.0.1:8000
```

`database/` is generated; never edit it by hand. Game facts come from
`tools/extract_*.py`; hand-written lore lives in `curated/*.csv` and is
overlaid by id (curated values win, extra columns are added).
`database/build_info.csv` records the pokeemerald commit and row counts.

## IDs

Ids are opaque, stable strings `<type>:<slug>` derived from the game constant
(`SPECIES_TREECKO` → `species:treecko`). Every entity also stores
`source_constant` and `source_file`, which is what Step 4 find/replace keys on.

| Prefix | Entity type | From |
|---|---|---|
| `species:` | species | `src/data/pokemon/species_info.h` |
| `move:` | move | `src/data/battle_moves.h` |
| `item:` | item (incl. TMs/HMs, berries, key items) | `src/data/items.h` |
| `ability:` / `type:` / `growth-rate:` | ability / game_type / growth_rate | text + constants |
| `trainer:` / `trainer-class:` / `trainer-pic:` | trainer data | `src/data/trainers.h` etc. |
| `map:` | map (every `data/maps/*/map.json`) | map.json |
| `location:` | region-map section (town/route/dungeon as named on the map) | `region_map_sections.json` |
| `npc:<map>:<n>` | object event n (1-based) on a map | map.json `object_events` |
| `object-gfx:` | overworld sprite | `object_event_graphics_info*.h` |
| `tileset:` | tileset | `src/data/tilesets/headers.h` |
| `nature:` / `decoration:` / `ribbon:` | natures, secret-base decorations, ribbons | `src/pokemon.c`, `src/data/decoration/`, ribbon text |
| `facility:` / `facility-trainer:<facility>:<name>` | Battle Frontier facilities; frontier / tent / Trainer Hill opponents | `src/data/battle_frontier/` |
| `contest-opponent:` | contest rivals | `src/data/contest_opponents.h` |
| `badge:` | the eight gym badges (field move + obedience gates) | `src/party_menu.c`, `src/battle_util.c` |
| `character:` / `organization:` / `storyline:` | curated lore | `curated/` |

Non-entity rows: script and text ids are assembler labels
(`LittlerootTown_Text_...`); flags/vars are `flag:<slug>` / `var:<slug>` in
`story_flags.csv`; art assets are keyed by their path in pokeemerald.

## Tables

Core (same shape as starwars-db; the wiki reads these):

- `entities.csv` — one row per entity. Common columns `id, entity_type,
  category, collection, title, description, history, image_path, image_status,
  source_constant, source_file`, then the sparse union of type-specific
  attributes (base stats, power/accuracy, price, map weather, …). List values
  are JSON arrays.
- `relationships.csv` — `(source_id, relationship, target_id)`: `has_type`,
  `has_ability`, `evolves_to`, `teaches_move`, `trainer_class`, `uses_species`,
  `rematch_N`, `located_in`, `connects_<dir>`, `warps_to`, `appears_on`,
  `uses_sprite`, `is_trainer`, `battled_on`, `found_wild_in`, `hidden_item`,
  `gives_item`, `gives_pokemon`, `static_encounter_on`, plus curated links.
- `metadata.csv` — repeatable `(entity_id, field, value, related_entity_id)`.
- `timeline_events.csv` / `timeline_entities.csv` — curated story chronology
  and the entities involved in each event. `year` is the chapter number,
  `release_year` the badges held.
- `entity_images.csv` — wiki images (copied into `database/images/`).

Game data:

- `species_learnsets.csv` — `species_id, method (level_up|tm_hm|egg|tutor), level, order, move_id, source_symbol`.
- `species_evolutions.csv` — `species_id, method, parameter, parameter_entity_id, evolves_to_id`.
- `type_effectiveness.csv` — attacking/defending type multipliers (incl. Foresight-ignored rows).
- `trainer_parties.csv` — `trainer_id, slot, species_id, level, iv, held_item_id, moves (|), party_symbol`.
- `wild_encounters.csv` — `map_id, method (land|water|rock_smash|old_rod|good_rod|super_rod), slot, slot_rate_percent, area_rate, species_id, min_level, max_level`.
- `map_connections.csv` — edge connections and warps between maps.
- `map_events.csv` — every object, trigger (coord) and sign/hidden-item (bg) event with coordinates, sprite, script, visibility flag.
- `mart_inventory.csv` — what each Poké Mart / shop script sells.
- `area_progression.csv` — one row per playable map: wild level range (land / any method), first-tier trainer level range, first timeline event that visits it, `badges_expected`, `requires` (HM items, badge flags, key items) and `gating_notes`. The balancing reference for adding or moving content.
- `item_locations.csv` — every item ball, hidden item and scripted item gift with map, coordinates, flag and `badges_expected`.
- `pokemon_gifts.csv` — scripted gift Pokémon, eggs and static encounters with level and map (starters and fossils are given from C specials, not listed here).
- `facility_mons.csv` / `facility_trainer_pools.csv` — Battle Frontier and Battle Tent Pokémon sets and which sets each facility trainer draws from.
- `easy_chat_words.csv` — every Easy Chat word (used to decode frontier/Trainer Hill speech and by TV/Mauville man features).

Scripts and text:

- `texts.csv` — every `.string` block in the scripts plus every `const u8 x[] = _("…")` string in `src/`: `text_id, map_id, source_file, source_line, speaker_label, text (clean), text_raw (exact), used_by_scripts, text_origin (script|c), text_context`.
- `scripts.csv` — every script label with what it touches: texts, jumps, movement, flags set/cleared/checked, vars, items given/taken, Pokémon given/battled, trainers, warps, marts, specials, music.
- `dialogue.csv` — text lines attributed to the NPC / sign / trigger that shows them, in script order, with `role` (dialogue, trainer_intro, trainer_defeat, postbattle, rematch, sign …).
- `trainer_dialogue.csv` — trainer intro/defeat/not-enough-Pokémon text per trainer.
- `story_flags.csv` — every flag and var with category and the scripts/maps that set and check it (the backbone of story progression and gating).

Art:

- `art_assets.csv` — every PNG in `graphics/` and `data/tilesets/` plus move animation scripts; `art_status` = `ORIGINAL`.
- `entity_art.csv` — `(entity_id, asset_id, role)`: front/back pics, palettes, icons, footprints, overworld sprites, trainer pics, item icons, battle animations.

Curated (see `curated/README.md`): story timeline, characters, organizations,
location lore, area progression, storylines.

## Wiki

`wiki/` is the starwars-db wiki with Emerald labels: it discovers CSVs at
runtime, so new tables appear automatically. See `wiki/README.md`.
