# Curated lore

Hand-written rows merged into `database/` by `tools/build.py`. File name =
target table. Rows overlay extracted rows with the same id (non-empty curated
values win; new columns are added), or are appended when the id is new.

| File | Target | Notes |
|---|---|---|
| `entities.csv` | entities | `character:*` and `organization:*` rows. Extra columns used by `extract_story.py`: `speaker_labels` (pipe list matching `texts.speaker_label`), `trainer_ids`, `sprite_ids`, `organization_ids`, `home_map`, `specialty_type`. Also the place to add `history` text to `location:*` / `map:*` ids (B4). |
| `timeline_events.csv` | timeline_events | Story chronology. `year` = chapter, `release_year` = badges held, `trigger_flag` / `completion_flag` = game constants, `map_ids` / `trainer_ids` / `character_ids` / `related_entity_ids` = pipe lists that become `timeline_entities`. |
| `area_progression.csv` | area_progression | (B5) per-map `requires` (HMs / key items / flags) and `gating_notes`; overlays the auto-computed level ranges by `map_id`. |

Rules: ground every row in the game (cite flags, maps, trainers, texts);
keep ids stable; run `python3 tools/build.py` and fix any dangling-id
warnings before committing.
