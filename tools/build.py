"""Regenerate every table in database/ from the pokeemerald source + curated/ overlays.

    python3 tools/build.py

Extractors are deterministic: rerunning produces identical CSVs for the same
pokeemerald commit. Hand-written lore lives in curated/*.csv and is merged on
top (curated rows win on matching ids; extra columns are added).
"""
from __future__ import annotations

import importlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CORE_ENTITY_COLUMNS, CURATED_DIR, DATABASE_DIR, SRC, read_csv, write_csv  # noqa: E402

# Order matters only for readability of the output; ids are unique across modules.
EXTRACTORS = [
    "extract_pokemon",
    "extract_moves_items",
    "extract_trainers",
    "extract_maps",
    "extract_scripts",
    "extract_world_systems",
    "extract_graphics",
    "extract_story",
]

# Preferred column order for relational tables (anything else is appended).
TABLE_KEYS = {
    "entities": CORE_ENTITY_COLUMNS,
    "relationships": ["source_id", "relationship", "target_id"],
    "metadata": ["entity_id", "field", "value", "related_entity_id"],
    "timeline_events": ["id", "title", "year", "sequence", "type", "era", "release_year", "canon", "tagline",
                        "description", "lore", "previous_event_id", "lane", "color"],
    "timeline_entities": ["event_id", "entity_id", "relationship"],
}
# Tables that use an id column for de-duplication / curated overlays.
ID_COLUMN = {"entities": "id", "timeline_events": "id", "dialogue": "line_id", "scripts": "script_id",
             "texts": "text_id", "art_assets": "asset_id", "story_flags": "flag_id", "entity_images": "entity_id"}


def run() -> None:
    if not SRC.exists():
        sys.exit(f"pokeemerald not found at {SRC}; set POKEEMERALD_DIR")
    tables: dict[str, list[dict]] = defaultdict(list)
    for name in EXTRACTORS:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as err:
            if err.name == name:
                print(f"  (skip {name}: not written yet)")
                continue
            raise
        t0 = time.time()
        out = mod.extract()
        print(f"  {name}: " + ", ".join(f"{k}={len(v)}" for k, v in out.items()) + f"  ({time.time() - t0:.1f}s)")
        for k, rows in out.items():
            tables[k].extend(rows)

    for path in sorted(CURATED_DIR.glob("*.csv")):
        table = path.stem
        rows = read_csv(path)
        _overlay(tables[table], rows, ID_COLUMN.get(table))
        print(f"  curated/{path.name}: {len(rows)} rows")

    for table, rows in tables.items():
        key = ID_COLUMN.get(table)
        if key:
            rows[:] = _dedupe(rows, key)
        write_csv(DATABASE_DIR / f"{table}.csv", rows, TABLE_KEYS.get(table))
    _write_build_info(tables)
    _validate(tables)


def _dedupe(rows: list[dict], key: str) -> list[dict]:
    seen: dict[str, dict] = {}
    order = []
    for r in rows:
        k = r.get(key, "")
        if k in seen:
            seen[k].update({c: v for c, v in r.items() if v not in ("", None)})
        else:
            seen[k] = r
            order.append(k)
    return [seen[k] for k in order]


def _overlay(rows: list[dict], curated: list[dict], key: str | None) -> None:
    if not key:
        rows.extend(curated)
        return
    index = {r.get(key): r for r in rows}
    for c in curated:
        target = index.get(c.get(key))
        if target is None:
            rows.append(c)
            index[c.get(key)] = c
        else:
            target.update({k: v for k, v in c.items() if v not in ("", None)})


def _write_build_info(tables) -> None:
    import subprocess
    try:
        commit = subprocess.check_output(["git", "-C", str(SRC), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        commit = "unknown"
    rows = [{"key": "pokeemerald_commit", "value": commit}]
    rows += [{"key": f"rows.{t}", "value": str(len(r))} for t, r in sorted(tables.items())]
    write_csv(DATABASE_DIR / "build_info.csv", rows)


def _validate(tables) -> None:
    ids = {r["id"] for r in tables.get("entities", [])}
    missing = defaultdict(int)
    for r in tables.get("relationships", []):
        for col in ("source_id", "target_id"):
            if r.get(col) and r[col] not in ids:
                missing[r[col].split(":")[0]] += 1
    if missing:
        print("  WARNING dangling relationship ids by prefix:", json.dumps(dict(missing)))
    print(f"  entities={len(ids)} relationships={len(tables.get('relationships', []))}")


if __name__ == "__main__":
    run()
