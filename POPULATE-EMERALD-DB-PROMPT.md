# POPULATE-EMERALD-DB-PROMPT

You are continuing the build of **emerald-db**: a relational, chronological
database (CSV files + a small read-only wiki) that snapshots everything in the
Pokémon Emerald decompilation (`pokeemerald`). Hand this file to an agent and it
can pick up exactly where the last session stopped.

## Why this exists

This is Step 2 of a five-step project to rebuild Pokémon Emerald with Star Wars
content:

1. `starwars-db` — Star Wars database (done; structural reference for this repo).
2. **`emerald-db` — this repo: every character, place, creature, item, move,
   trainer, line of dialogue, story beat and art file in Emerald, with stable
   ids and the exact source constants.**
3. `emerald-starwars-db` — a clone of this DB with every row rewritten to Star
   Wars lore (roughly 1:1 mapping, so keep ids and structure stable).
4. Refactor the game source using old→new rows (find/replace by constant/text).
   Art stays Pokémon art but is renamed; new things are marked `PENDING_ART`.
5. Redraw all art, driven by `art_assets.csv` / `entity_art.csv`.

So: precision over prose. Every row should carry the constant (`source_constant`)
and file (`source_file`) it came from, and the exact game text (`text_raw`)
wherever text is involved. Balance data (levels, stats, encounter rates,
gating) matters as much as lore.

## Setup

Clone side by side (only emerald-db is written to):

```sh
git clone https://github.com/spencerlepine/emerald-db.git
git clone https://github.com/spencerlepine/pokeemerald.git      # read-only source
git clone https://github.com/spencerlepine/starwars-db.git      # read-only reference
cd emerald-db
python3 tools/build.py        # regenerates database/ from ../pokeemerald + curated/
python3 tools/coverage.py     # writes progress/COVERAGE.md
python3 wiki/server.py        # optional: http://127.0.0.1:8000
```

Python 3.10+ standard library only. Set `POKEEMERALD_DIR` if pokeemerald is not
at `../pokeemerald`.

## Rules

- **Never push to `pokeemerald` or `starwars-db`.** Read them only.
- **Never hand-edit `database/*.csv`.** It is generated. Change an extractor in
  `tools/` (game facts) or a file in `curated/` (lore written by you), then
  rebuild. build.py overlays curated rows on extracted rows by id.
- Commit and push after every chunk (small, frequent commits). Use the branch
  your session tells you to; otherwise a feature branch + PR into `main`.
- Before committing: run `python3 tools/build.py` (must finish with no new
  dangling-id warnings) and `python3 tools/coverage.py`.
- Lore must be grounded in the game: cite the text ids, flags, maps or trainers
  you used (put them in `source_constant` / `source_file` / relationship rows).
  Don't import knowledge from other Pokémon games unless the Emerald source
  shows it.
- Keep ids stable once published; downstream DBs key off them.

## How to resume

1. Read `progress/CHECKLIST.md`. The first chunk that is not `[x]` is your job.
   `[~]` means a previous session started it — check `git log` and the log at
   the bottom of the checklist for where it stopped.
2. Read `progress/COVERAGE.md` for the numbers (game vs DB).
3. Read `README.md` for the schema and id conventions.
4. Do the chunk. Rebuild, run coverage, tick the box, append a log line,
   commit, push. Repeat with the next chunk.
5. If the session is ending mid-chunk, mark it `[~]`, write what's left in
   the log line, commit and push. Nothing should live only in your context.

Working notes and decisions that don't fit the checklist go in
`progress/NOTES.md`.

## Layout

```
POPULATE-EMERALD-DB-PROMPT.md   this file (single entry point)
README.md                       schema, ids, table reference
progress/CHECKLIST.md           chunked work list + session log
progress/COVERAGE.md            generated coverage report
progress/NOTES.md               decisions, gotchas, open questions
tools/common.py                 C/asm parsing helpers, id helpers, CSV writer
tools/extract_*.py              one extractor per domain (deterministic)
tools/build.py                  runs extractors + curated overlay → database/
tools/coverage.py               coverage report
curated/*.csv                   hand-written lore merged into database/ tables
database/*.csv                  generated tables (+ images/ for the wiki)
wiki/                           read-only browser for database/ (from starwars-db)
```

## Conventions (short version; README has the rest)

- Entity ids are `<type>:<slug>` from the game constant: `species:treecko`,
  `move:pound`, `item:poke-ball`, `trainer:roxanne-1`, `map:littleroot-town`,
  `location:littleroot-town` (region-map section), `npc:<map-slug>:<n>`
  (n = 1-based object event index in map.json), `object-gfx:twin`,
  `trainer-class:leader`, `trainer-pic:leader-roxanne`, `tileset:general`,
  `ability:overgrow`, `type:fire`. Curated: `character:<slug>`,
  `organization:<slug>`, `storyline:<slug>`.
- Flags/vars are rows in `story_flags.csv` (`flag:badge01-get`,
  `var:littleroot-town-state`) with the scripts that set/check them.
- Script/text ids are the assembler labels (`LittlerootTown_Text_...`).
- Lists inside a cell are JSON arrays (entities.csv) or `|`-separated (other tables).
- `art_status` is `ORIGINAL` for all art here. Step 3/4 DBs use `PENDING_ART`.
- Timeline: `year` = chapter number, `sequence` = global order,
  `release_year` = badges the player holds at that point (kept as the column
  name for wiki compatibility with starwars-db).
