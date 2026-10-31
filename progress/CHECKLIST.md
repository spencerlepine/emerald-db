# Emerald DB build checklist

Status legend: `[x]` done · `[~]` in progress / partial · `[ ]` not started.
Work top to bottom. One chunk = one commit (or a few) + push. After each chunk:
`python3 tools/build.py && python3 tools/coverage.py`, then tick the box here and
add a line to the log at the bottom.

## Phase A — automated extraction (tools/extract_*.py → database/)

- [x] **A1 Pokémon core** — `extract_pokemon.py`: species (stats, dex text, abilities, egg groups, held items), evolutions, learnsets (level/TM-HM/egg/tutor), types + type chart, abilities, growth rates.
- [x] **A2 Moves & items** — `extract_moves_items.py`: moves (battle + contest data, animation script), items (all pockets), TM/HM ↔ move, berries (flavor/growth).
- [x] **A3 Trainers** — `extract_trainers.py`: trainers, parties (species/level/IV/item/moves), trainer classes (+prize money), trainer pics, rematch chains.
- [x] **A4 World** — `extract_maps.py`: maps, region-map locations, layouts/tilesets, connections & warps, object/coord/bg events, NPC entities, hidden items, wild encounters, heal locations.
- [x] **A5 Scripts & text** — `extract_scripts.py`: every `.string` text, every script label (flags/vars/items/mons/trainers/warps/specials it touches), dialogue attributed to NPC/sign/trigger, trainer intro/defeat text, flags & vars with setters/checkers, mart inventories.
- [x] **A6 Art inventory** — `extract_graphics.py`: every PNG (art_assets), overworld sprite entities, species/trainer/item art links (entity_art), wiki images.
- [x] **A7 World systems** — `extract_world_systems.py`: natures, decorations, ribbons, easy chat words, Battle Frontier facilities + Frontier Brain parties (silver/gold), 300 frontier trainers + mon pools (EC speech decoded), Battle Tent trainers/mons, Trainer Hill trainers, contest opponents. Move tutors, HM field-move checks, TV/news, Game Corner, Safari Zone, Day Care and event tickets are covered by scripts/texts/flags (A5); their *lore* is B5/B6 work.
- [x] **A8 C-side strings** — `extract_c_strings.py`: 3.2k `const u8 x[] = _("…")` strings from `src/` (UI, battle messages, match call profiles, union room, credits, landmarks…) added to texts.csv with `text_origin=c` and `text_context`. Follow-up idea: link match-call profile texts to trainer ids via `sMatchCallTrainers` in `src/match_call.c`.

## Phase B — curated lore (curated/*.csv, merged by build.py)

Use the extracted dialogue (texts.csv / dialogue.csv / trainer_dialogue.csv), script flags and map data as evidence. Cite constants (flags, maps, trainers) in each row so Step 3/4 can find/replace.

- [x] **B1 Story timeline** (45 events: 38 main story + 7 post-game; extend with more side quests in B6) — `curated/timeline_events.csv` + `curated/timeline_entities.csv`: main story in order from the moving truck to the Hall of Fame, then post-game (Lati@s / S.S. Tidal, Battle Frontier, Rayquaza/Kyogre/Groudon weather, Regis, Sky Pillar, Southern Island, events). Columns: id, title, year (= chapter), sequence, type (story/gym/villain/legendary/postgame/side-quest), era (act), release_year (= badges held), canon (main/optional), tagline, description, lore, previous_event_id, lane, color, plus `trigger_flag`, `completion_flag`, `map_ids`.
- [~] **B2 Characters** (47 done in curated/entities.csv: family, professor, rivals, all gym leaders/E4/champion, both teams' leaders+admins, frontier brains, key NPCs. TODO: role characters MC/JUDGE/REFEREE/GUIDE/CLERK/INTERVIEWER/REPORTER, talking Pokémon, minor named NPCs Dock/Dez & Luke/Jed & Lea/Blend Master/Big Bro/Big Sis, Trick Master, Winstrate family, Cozmo's wife, Mr. Stone's secretary — see COVERAGE 'unmapped') — `curated/entities.csv` rows with entity_type `character`: player (Brendan/May), family, Prof. Birch, rival, Wally, gym leaders, Elite Four, Champion(s), Steven, Mr. Stone, Teams Aqua/Magma leaders & admins, Scott, Mr. Briney, Capt. Stern, Cozmo, Lanette, Gabby & Ty, Rydel, frontier brains, etc. Columns: speaker_labels (pipe list matching texts.speaker_label), trainer_ids, sprite ids, home map, role. Plus `curated/relationships.csv` links (family_of, rival_of, leads, member_of, battles_as, appears_in_event).
- [x] **B3 Organizations** (25 rows) — Team Aqua, Team Magma, Devon Corp., Pokémon League, the 8 gyms, Weather Institute, Mossdeep Space Center, Battle Frontier, Contest committee, Trick House, Pokémon Fan Club, Game Corner, Safari Zone, Day Care, Pokémon Center/Mart chains, Cycling Road, etc.
- [ ] **B4 Location lore** — `history` + `description` for every region-map location (`location:*`) using town signs, NPC dialogue and story events. Do it in route order:
  - [ ] B4a Littleroot, Route 101, Oldale, Route 102/103, Petalburg, Route 104, Petalburg Woods, Rustboro, Route 116, Rusturf Tunnel
  - [ ] B4b Dewford, Granite Cave, Routes 105–109, Slateport, Oceanic Museum
  - [ ] B4c Route 110, Mauville, New Mauville, Routes 111–114, Fallarbor, Meteor Falls, Desert, Fiery Path, Mt. Chimney, Jagged Pass, Lavaridge
  - [ ] B4d Routes 115–121, Verdanturf, Fortree, Lilycove, Mt. Pyre, Safari Zone, Weather Institute, Scorched Slab
  - [ ] B4e Routes 122–134, Mossdeep, Shoal Cave, Seafloor Cavern, Sootopolis, Cave of Origin, Pacifidlog, Sealed Chamber, Sky Pillar, Ever Grande, Victory Road
  - [ ] B4f Post-game & special: Battle Frontier, Artisan Cave, islands (Southern, Faraway, Navel Rock, Birth), Abandoned Ship, Trainer Hill, secret bases, Mirage spots, unused/test maps
- [ ] **B5 Area progression & balance** — `curated/area_progression.csv` (one row per outdoor/dungeon map): chapter, badges expected, required HMs/key items/flags to enter, wild level range and trainer level range (auto-filled by build from wild_encounters / trainer_parties), notes on gating (e.g. Go-Goggles for desert, Devon Scope for Kecleon). This is the balancing reference for Steps 3–4.
- [ ] **B6 Legendaries, side quests & mysteries** — Regi braille puzzle, weather trio, Lati@s roaming, Deoxys/Mew/Lugia/Ho-Oh event islands, Trick House, Mirage Island, Kecleon, Fossils, Lilycove lady, Mauville storyteller/bard, Pokémon News, apprentice. Entity type `storyline` with linked flags/maps/texts.

## Phase C — quality

- [ ] **C1 Referential integrity** — `build.py` prints zero dangling relationship ids.
- [ ] **C2 Wiki smoke test** — `python3 wiki/server.py`, open home, an entity, a timeline event, and a table.
- [ ] **C3 Docs** — README schema section matches the CSVs that exist.

## Log

Append one line per working session: date · chunk(s) · commit · notes.

- 2026-10-31 · A1–A8 · see git log · toolchain, wiki copy, first full extraction (6.1k entities, 16k relationships, 8k texts).
- 2026-10-31 · B1, B2 (partial), B3 · story timeline, 47 characters, 25 organizations; extract_story.py derives timeline_entities, character links, area_progression levels.
