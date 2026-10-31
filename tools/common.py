"""Shared helpers for extracting data from the pokeemerald decompilation.

Every extractor reads the pokeemerald checkout (POKEEMERALD_DIR, default
../pokeemerald next to this repo) and returns rows for the tables in
database/. Nothing here writes files; build.py does that.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = REPO_DIR / "database"
CURATED_DIR = REPO_DIR / "curated"
SRC = Path(os.environ.get("POKEEMERALD_DIR", REPO_DIR.parent / "pokeemerald")).resolve()

csv.field_size_limit(sys.maxsize)


def src_path(rel: str) -> Path:
    return SRC / rel


def read(rel: str) -> str:
    return src_path(rel).read_text(encoding="utf-8", errors="replace")


def load_json(rel: str):
    return json.loads(read(rel))


def strip_c_comments(text: str) -> str:
    """Remove // and /* */ comments without touching string literals."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


STRING_LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')


def c_string(expr: str) -> str:
    """Concatenate every string literal in expr (handles _("a" "b"))."""
    return "".join(STRING_LIT.findall(expr))


def clean_text(raw: str) -> str:
    """Game text -> readable text. Keeps {PLAYER}-style placeholders.

    \\n and \\l are line breaks inside a text box; \\p starts a new box;
    a trailing $ terminates the string in .inc files.
    """
    t = raw.replace("\\p", "\n\n").replace("\\n", " ").replace("\\l", " ")
    t = t.replace('\\"', '"').rstrip("$")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    return t.strip()


def match_brace(text: str, start: int) -> int:
    """Given index of an opening brace, return index of its matching close."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces")


def array_body(text: str, name: str) -> str:
    """Return the text between the outer braces of `... name[...] = { ... };`."""
    m = re.search(r"\b" + re.escape(name) + r"\s*(\[[^\]]*\])*\s*=\s*\{", text)
    if not m:
        raise KeyError(name)
    start = m.end() - 1
    return text[start + 1:match_brace(text, start)]


def designated_entries(body: str) -> dict[str, str]:
    """Parse `[KEY] = value,` entries (value may be {...} or an expression)."""
    entries: dict[str, str] = {}
    i, n = 0, len(body)
    pat = re.compile(r"\[\s*([A-Za-z0-9_ +\-()]+?)\s*\]\s*=\s*")
    while True:
        m = pat.search(body, i)
        if not m:
            break
        key, j = m.group(1).strip(), m.end()
        if j < n and body[j] == "{":
            end = match_brace(body, j)
            entries[key] = body[j:end + 1]
            i = end + 1
        else:
            depth, k = 0, j
            while k < n:
                c = body[k]
                if c == '"':
                    k += 1
                    while k < n and body[k] != '"':
                        k += 2 if body[k] == "\\" else 1
                elif c in "({":
                    depth += 1
                elif c in ")}":
                    depth -= 1
                elif c == "," and depth == 0:
                    break
                elif c == "[" and depth == 0 and pat.match(body, k):
                    break
                k += 1
            entries[key] = body[j:k].strip()
            i = k + 1
    return entries


def split_top(text: str, sep: str = ",") -> list[str]:
    """Split on sep at brace/paren depth 0."""
    parts, depth, cur, i, n = [], 0, [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            cur.append(text[i:j + 1])
            i = j + 1
            continue
        if c in "({[":
            depth += 1
        elif c in ")}]":
            depth -= 1
        if c == sep and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def struct_fields(block: str) -> dict[str, str]:
    """Parse `{ .a = 1, .b = {X, Y}, }` into {'a': '1', 'b': '{X, Y}'}."""
    inner = block.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    fields = {}
    for part in split_top(inner):
        m = re.match(r"\.(\w+)\s*=\s*(.*)$", part, re.S)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def brace_list(value: str) -> list[str]:
    v = value.strip()
    if v.startswith("{") and v.endswith("}"):
        v = v[1:-1]
    return [p for p in split_top(v) if p]


def string_arrays(text: str) -> dict[str, str]:
    """Map `const u8 sName[] = _("...");` symbol -> raw concatenated string."""
    out = {}
    for m in re.finditer(r"(?:static\s+)?const\s+u8\s+(\w+)\s*\[[^\]]*\]\s*=\s*_\((.*?)\)\s*;", text, re.S):
        out[m.group(1)] = c_string(m.group(2))
    return out


def defines(rel: str, prefix: str = "") -> dict[str, str]:
    """Return #define NAME VALUE pairs from a header (in file order)."""
    out = {}
    for m in re.finditer(r"^\s*#define\s+(" + prefix + r"\w*)\s+(.+?)\s*$", strip_c_comments(read(rel)), re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


def eval_defines(defs: dict[str, str], extra: dict[str, int] | None = None) -> dict[str, int]:
    """Best-effort evaluation of integer #defines that reference each other."""
    vals: dict[str, int] = dict(extra or {})
    for _ in range(6):
        for k, v in defs.items():
            if k in vals:
                continue
            expr = re.sub(r"\b([A-Za-z_]\w*)\b", lambda m: str(vals[m.group(1)]) if m.group(1) in vals else m.group(1), v)
            expr = re.sub(r"(?<=\d)[uU]\b", "", expr)
            if re.fullmatch(r"[0-9xXa-fA-F+\-*/()<>| ~&]+", expr):
                try:
                    vals[k] = int(eval(expr, {"__builtins__": {}}))
                except Exception:
                    pass
    return vals


def slug(value: str, strip_prefix: str = "") -> str:
    v = value
    if strip_prefix and v.startswith(strip_prefix):
        v = v[len(strip_prefix):]
    v = v.lower().replace("_", "-")
    v = re.sub(r"[^a-z0-9\-]+", "-", v)
    return re.sub(r"-+", "-", v).strip("-")


def camel_to_const(name: str) -> str:
    """LittlerootTown_House1 -> LITTLEROOT_TOWN_HOUSE1 (pokeemerald map naming)."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return s.upper()


def title_case(name: str) -> str:
    """Game names are ALL CAPS; give a readable display title."""
    small = {"of", "the", "and", "a", "in", "on"}
    words = re.split(r"(\s+)", name.strip())
    out = []
    for idx, w in enumerate(words):
        if not w.strip():
            out.append(w)
            continue
        lw = w.lower()
        out.append(lw if idx and lw in small else lw[:1].upper() + lw[1:])
    s = "".join(out)
    return s.replace("Pokémon", "Pokémon").replace("Pokéball", "Poké Ball")


def game_name(raw: str) -> str:
    """Decode common charmap escapes in names."""
    return raw.replace("{POKEBLOCK}", "POKéBLOCK").replace("{PKMN}", "PKMN")


def entity(eid: str, entity_type: str, category: str, title: str, **fields) -> dict:
    row = {
        "id": eid,
        "entity_type": entity_type,
        "category": category,
        "collection": fields.pop("collection", ""),
        "title": title,
        "description": fields.pop("description", ""),
        "history": fields.pop("history", ""),
        "image_path": fields.pop("image_path", ""),
        "image_status": fields.pop("image_status", ""),
        "source_constant": fields.pop("source_constant", ""),
        "source_file": fields.pop("source_file", ""),
    }
    for k, v in fields.items():
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, bool):
            v = "true" if v else "false"
        row[k] = "" if v is None else str(v)
    return row


def rel(source: str, relationship: str, target: str, **extra) -> dict:
    row = {"source_id": source, "relationship": relationship, "target_id": target}
    row.update({k: str(v) for k, v in extra.items()})
    return row


def meta(entity_id: str, field: str, value, related: str = "") -> dict:
    return {"entity_id": entity_id, "field": field, "value": "" if value is None else str(value), "related_entity_id": related}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


CORE_ENTITY_COLUMNS = ["id", "entity_type", "category", "collection", "title", "description", "history",
                       "image_path", "image_status", "source_constant", "source_file"]


def write_csv(path: Path, rows: list[dict], first: list[str] | None = None) -> None:
    columns: list[str] = list(first or [])
    seen = set(columns)
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                columns.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in columns})


def enum_values(rel_or_text: str, first_name: str) -> dict[str, int]:
    """Return {NAME: index} for the enum block that contains first_name."""
    text = strip_c_comments(read(rel_or_text) if "\n" not in rel_or_text else rel_or_text)
    for m in re.finditer(r"enum\s*\w*\s*\{", text):
        start = m.end() - 1
        body = text[start + 1:match_brace(text, start)]
        if re.search(r"\b" + first_name + r"\b", body):
            out, idx = {}, 0
            for part in split_top(body):
                part = part.strip()
                if not part:
                    continue
                if "=" in part:
                    name, val = [p.strip() for p in part.split("=", 1)]
                    try:
                        idx = int(val, 0)
                    except ValueError:
                        idx = out.get(val, idx)
                else:
                    name = part
                out[name] = idx
                idx += 1
            return out
    raise KeyError(first_name)


_INCBIN = None


def incbin_index() -> dict[str, str]:
    """Map graphics symbol -> source image path (.png/.pal source of the INCBIN'd asset)."""
    global _INCBIN
    if _INCBIN is None:
        _INCBIN = {}
        pat = re.compile(r"\b(\w+)\s*\[[^\]]*\]\s*=\s*INC(?:BIN|GFX)_\w+\(\s*\"([^\"]+)\"")
        for path in list(SRC.glob("src/**/*.h")) + list(SRC.glob("src/**/*.c")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "INCBIN" not in text and "INCGFX" not in text:
                continue
            for m in pat.finditer(text):
                _INCBIN[m.group(1)] = asset_source(m.group(2))
    return _INCBIN


def asset_source(built: str) -> str:
    """graphics/x/y.4bpp.lz -> graphics/x/y.png (the editable source)."""
    p = re.sub(r"\.lz$", "", built)
    p = re.sub(r"\.(4bpp|8bpp|1bpp|gbapal|bin)$", lambda m: ".pal" if m.group(1) == "gbapal" else (".bin" if m.group(1) == "bin" else ".png"), p)
    if p.endswith(".pal") and not (SRC / p).exists() and (SRC / p.replace(".pal", ".png")).exists():
        p = p.replace(".pal", ".png")
    return p
